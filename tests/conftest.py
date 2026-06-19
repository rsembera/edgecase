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
def client(app_db):
    """Authenticated Flask test client wired to ``app_db``.

    Blueprints capture their db reference via ``init_blueprint`` at login (a
    module-level ``db`` global), so setting ``app.config['db']`` alone is not
    enough — we also call ``init_all_blueprints(app_db)`` so route handlers use
    the test database. CSRF is disabled: the app calls ``csrf.protect()``
    manually in a before_request, and ``WTF_CSRF_ENABLED=False`` makes that a
    no-op so form POSTs don't need a token.
    """
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

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
