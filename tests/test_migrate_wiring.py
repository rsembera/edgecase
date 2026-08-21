"""Stage 4b: login-flow wiring for the v1->v2 migration.

Covers the credential handoff (single-use, expiring) and that the migration
stream route is reachable without an open database (gated by the token), plus a
sanity check that login still renders. The migration *logic* is covered by
test_migrate_crypto.py; this file covers the glue.
"""
import time

import pytest

from web.blueprints import auth


def test_migration_handoff_single_use():
    token = auth._store_migration_handoff("secret-pw")
    assert auth._pop_migration_handoff(token) == "secret-pw"
    # Single-use: the second pop returns nothing.
    assert auth._pop_migration_handoff(token) is None


def test_migration_handoff_rejects_bad_or_missing_token():
    auth._store_migration_handoff("secret-pw")
    assert auth._pop_migration_handoff("not-the-token") is None
    assert auth._pop_migration_handoff(None) is None


def test_migration_handoff_expires():
    token = auth._store_migration_handoff("secret-pw")
    # Backdate beyond the TTL.
    auth._migration_handoff[token]["created"] = time.time() - (auth._HANDOFF_TTL_SECONDS + 10)
    assert auth._pop_migration_handoff(token) is None


@pytest.fixture
def client():
    from web.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_migrate_stream_reachable_without_db_and_errors_without_token(client):
    # require_login must let this route through even with config['db'] unset;
    # with no handoff token it should emit an SSE error event, not redirect.
    resp = client.get("/migrate/stream", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "error" in body and "log in again" in body


def test_login_page_still_renders(client):
    # Login runs recover_if_interrupted() first; with no migration pending it is
    # a harmless no-op and the page renders normally.
    resp = client.get("/login", headers={"Host": "localhost"})
    assert resp.status_code == 200


def test_first_run_login_routes_through_encryption_setup(
        bare_client, monkeypatch, tmp_path):
    """A brand-new install gets the v3 envelope (and its recovery key) on the
    FIRST login: the POST that creates the database renders the setup screen
    with first-run wording instead of redirecting into the app, and driving
    the migration stream leaves the install on v3 with a key pending."""
    import re
    import core.config as config
    from core import encryption_v2 as v2
    from core import migrate_crypto as mc

    data_dir = tmp_path / "data"
    for name in ("data", "attachments", "assets", "backups"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(v2, "KEYINFO_FILE", data_dir / ".keyinfo")
    monkeypatch.setattr("flask_wtf.csrf.validate_csrf", lambda *a, **k: None)

    resp = bare_client.post("/login", data={
        "password": "fresh-install-pw!",
        "confirm_password": "fresh-install-pw!",
    }, headers={"Host": "localhost"})

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Securing your practice" in body          # first-run wording
    assert "One-time security upgrade" not in body   # not the legacy wording
    assert (data_dir / "edgecase.db").exists()       # DB was created
    assert mc.install_crypto_version() == 1          # ...as v1, pre-stream

    token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)
    stream = bare_client.get(f"/migrate/stream?token={token}",
                             headers={"Host": "localhost"})
    stream_body = stream.get_data(as_text=True)

    assert "complete" in stream_body
    assert mc.install_crypto_version() == 3
    assert (data_dir / ".rk_pending").exists()
