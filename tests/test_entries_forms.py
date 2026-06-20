"""GET-form smoke tests (entries.py refactor Step 0).

Every create/edit form route must render 200. This guards the
url_for('entries.<fn>') endpoint contract before the blueprint split: a renamed
route function or a broken endpoint reference fails here on template render,
before it can reach a real page. Create forms need only a seeded client; edit
forms create an entry first (via the real create route) and GET its edit form.
"""
import pytest


def _client(db):
    return db.add_client({"file_number": "FM-001", "first_name": "Form",
                          "middle_name": "", "last_name": "Test", "type_id": 1})


# --- create / profile form renders (need only a client) ---

CREATE_FORMS = ["session", "communication", "absence", "item", "upload", "profile"]


@pytest.mark.parametrize("kind", CREATE_FORMS)
def test_create_form_renders(client, app_db, kind):
    cid = _client(app_db)
    resp = client.get(f"/client/{cid}/{kind}")
    assert resp.status_code == 200, f"{kind} form -> {resp.status_code}"


# --- edit form renders (create the entry via its real route, then GET edit) ---

_CREATE_POST = {
    "session": {"modality": "Individual", "format": "In-person",
                "date": "2026-06-19", "duration": "50", "content": "x"},
    "communication": {"description": "Call", "recipient": "Client",
                      "comm_type": "phone", "date": "2026-06-19", "content": "x"},
    "absence": {"description": "No-show", "date": "2026-06-19"},
    "item": {"description": "Report fee", "item_date": "2026-06-19"},
}


@pytest.mark.parametrize("kind", list(_CREATE_POST))
def test_edit_form_renders(client, app_db, kind):
    cid = _client(app_db)
    assert client.post(f"/client/{cid}/{kind}",
                       data=_CREATE_POST[kind]).status_code == 302
    entry_id = app_db.get_client_entries(cid, kind)[0]["id"]
    resp = client.get(f"/client/{cid}/{kind}/{entry_id}")
    assert resp.status_code == 200, f"{kind} edit form -> {resp.status_code}"
