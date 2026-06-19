"""Harness smoke tests for the route-level test client (database.py refactor
Step 2). Proves the ``client`` fixture authenticates and reaches read-only
routes end-to-end against a real temp database, and that the auth gate is real
(so the authenticated route tests that follow are meaningful)."""


def test_settings_index_renders(client):
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_statements_index_renders(client):
    resp = client.get("/statements/")
    assert resp.status_code == 200


def test_protected_route_redirects_without_auth():
    """Without the session marker, a protected route must not serve — it
    redirects to login (or 401 for API requests). Confirms the gate is live."""
    from web.app import app

    app.config["TESTING"] = True
    app.config["db"] = None
    with app.test_client() as c:
        resp = c.get("/settings")
        assert resp.status_code in (302, 401)
