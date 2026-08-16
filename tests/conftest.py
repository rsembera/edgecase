"""Route/integration test harness for EdgeCase.

Added for the core/database.py refactor (Step 2): gives route-level tests a Flask
test client wired to a fresh temp-file database with an authenticated session, so
handlers run end-to-end against the real data layer without master-password / key
derivation. Tests-only — nothing here touches the production checkout.
"""
import os
import tempfile
import time

import pytest

from core.database import Database
from web.app import app as flask_app, init_all_blueprints


@pytest.fixture(autouse=True)
def isolate_keyinfo(tmp_path_factory, monkeypatch):
    """No test may read the real install's key-info file.

    Several tests create a temp Database with an arbitrary password and never
    redirected v2.KEYINFO_FILE, so key derivation silently consulted whatever
    .keyinfo happened to exist in the developer's DATA_DIR. Under v2 that was
    invisible: get_keys() with a mismatched password returned garbage keys
    deterministically, and encrypt-then-decrypt with consistently garbage keys
    round-trips fine. Under v3 the wrapper's GCM tag fails and get_keys()
    raises — so the moment a live install became ECC3, four tests broke that
    had nothing to do with the change.

    Beyond the breakage, the dependency itself was wrong: the suite behaved
    differently on a machine with a migrated install than on a fresh clone.

    Points the path at an empty temp dir (so, no key-info -> v1 keying, which
    is what those tests were written against). Tests needing a specific
    version write their own key-info and override this.
    """
    from core import encryption_v2
    keyinfo_dir = tmp_path_factory.mktemp("keyinfo")
    monkeypatch.setattr(encryption_v2, "KEYINFO_FILE", keyinfo_dir / ".keyinfo")
    encryption_v2._key_cache.clear()
    yield
    encryption_v2._key_cache.clear()


@pytest.fixture(autouse=True)
def isolate_backup_locations(tmp_path_factory, monkeypatch):
    """No test may read or write the real install's backup-locations record.

    The record deliberately lives OUTSIDE DATA_ROOT (see
    core.config.get_state_dir), which means the suite's usual trick of
    monkeypatching backup.DATA_ROOT / BACKUPS_DIR does not cover it —
    save_manifest would happily write test folders into the developer's
    real ~/Library/Preferences record, and disaster-recovery tests would
    see the developer's real backup folders. Global isolation, same
    reasoning as isolate_keyinfo above.
    """
    from utils import backup
    state_dir = tmp_path_factory.mktemp("backup_state")
    monkeypatch.setattr(backup, "_backup_locations_file",
                        lambda: state_dir / "backup_locations.json")
    yield


@pytest.fixture(autouse=True)
def isolate_restore_unverified_marker(tmp_path_factory, monkeypatch):
    """No test may read or clear the real install's unverified-restore marker.

    The marker gates the disaster-recovery door and is DELETED on every
    successful login — so an auth test logging in against a temp database
    would silently unlink the real install's marker (and marker-presence
    tests would see the developer's state). Same reasoning as the two
    isolation fixtures above.
    """
    from utils import backup
    marker_dir = tmp_path_factory.mktemp("restore_marker")
    monkeypatch.setattr(backup, "_restore_unverified_marker",
                        lambda: marker_dir / ".restore_unverified")
    yield


@pytest.fixture
def bare_client(monkeypatch):
    """Unauthenticated Flask client with no database in app config —
    the state the disaster-recovery routes exist for. Shared by
    test_disaster_recovery.py and test_restore_credentials.py."""
    from web.app import app as flask_app
    flask_app.config["TESTING"] = True
    prev_db = flask_app.config.get("db")
    flask_app.config["db"] = None
    with flask_app.test_client() as c:
        yield c
    flask_app.config["db"] = prev_db


@pytest.fixture
def app_db():
    """A fresh temp-file Database per test (route-level analogue of the ``db``
    fixture in test_edgecase.py). Schema and the default client type are created
    by the Database constructor."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    database = Database(db_path)
    yield database
    try:
        database.close()
    except Exception:
        pass
    os.unlink(db_path)


@pytest.fixture
def client(app_db, monkeypatch):
    """Authenticated Flask test client wired to ``app_db``.

    Blueprints capture their db reference via ``init_blueprint`` at login (a
    module-level ``db`` global), so setting ``app.config['db']`` alone is not
    enough — we also call ``init_all_blueprints(app_db)`` so route handlers use
    the test database.

    CSRF: the app disables Flask-WTF's automatic check
    (``WTF_CSRF_CHECK_DEFAULT=False``) and instead calls ``csrf.protect()``
    manually in a before_request. In flask_wtf 1.2.x ``protect()`` does *not*
    honour ``WTF_CSRF_ENABLED``, so that flag alone leaves form POSTs returning
    400 ("CSRF token is missing"). We no-op ``validate_csrf`` for the duration of
    the test (function-scoped monkeypatch, auto-reverted) — the documented intent
    of disabling CSRF in a test client — without touching production code.
    """
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    monkeypatch.setattr("flask_wtf.csrf.validate_csrf", lambda *a, **k: None)

    prev_db = flask_app.config.get("db")
    flask_app.config["db"] = app_db
    init_all_blueprints(app_db)

    with flask_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["authenticated"] = True
            sess["login_time"] = time.time()
            sess["last_activity"] = time.time()
        yield c

    flask_app.config["db"] = prev_db
