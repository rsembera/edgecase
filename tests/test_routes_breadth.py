"""Breadth smoke tests (database.py refactor Step 2).

Every primary read-only page must render 200 against a realistic DB. This is the
cheap guard that catches blueprint import/registration breakage when the Step 3
split rearranges core/database.py — a route that 500s or fails to register shows
up here immediately.
"""
import pytest


def _seed_client(db):
    return db.add_client({
        "file_number": "BR-001", "first_name": "Bread", "middle_name": "",
        "last_name": "Th", "type_id": 1,
    })


PARAMLESS_ROUTES = [
    "/",                 # dashboard / client list
    "/deleted-clients",
    "/ledger",
    "/ledger/report",
    "/settings",
    "/statements/",
]


@pytest.mark.parametrize("path", PARAMLESS_ROUTES)
def test_readonly_route_renders(client, app_db, path):
    _seed_client(app_db)
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"


def test_client_file_renders(client, app_db):
    cid = _seed_client(app_db)
    resp = client.get(f"/client/{cid}")
    assert resp.status_code == 200
