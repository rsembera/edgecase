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
