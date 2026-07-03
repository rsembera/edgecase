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


# --- dirty-state Save button markup (form-guard.js contract) ---
#
# Edit forms opt in to the shared dirty guard: the form carries
# data-dirty-guard and the save button starts disabled as "No Changes" with
# its active label in data-dirty-label. Create forms must NOT carry the
# guard (a fresh form is work-in-progress; Save stays enabled). The profile
# form is always effectively edit mode, so it always carries the guard.
# The SESSION edit form is deliberately absent here: it keeps its own
# dirty-tracking in session.js (which also owns the beforeunload guard and
# the leave-confirmation modal) and does not use the data-attribute
# contract. form-guard.js itself is exercised in the browser; these tests
# pin the server-rendered contract it binds to.

_GUARDED_EDIT_KINDS = ["communication", "absence", "item"]


@pytest.mark.parametrize("kind", _GUARDED_EDIT_KINDS)
def test_edit_form_has_dirty_guard(client, app_db, kind):
    cid = _client(app_db)
    assert client.post(f"/client/{cid}/{kind}",
                       data=_CREATE_POST[kind]).status_code == 302
    entry_id = app_db.get_client_entries(cid, kind)[0]["id"]
    html = client.get(f"/client/{cid}/{kind}/{entry_id}").get_data(as_text=True)
    assert "data-dirty-guard" in html, f"{kind} edit form lacks data-dirty-guard"
    assert "data-dirty-save" in html, f"{kind} edit form lacks data-dirty-save button"
    assert "data-dirty-label=" in html
    assert ">No Changes</button>" in html
    assert "js/form-guard.js" in html


def test_upload_edit_form_has_dirty_guard(client, app_db, tmp_path, monkeypatch):
    """Upload creation needs a real multipart file (hermetic temp root)."""
    from io import BytesIO
    import web.utils as wu
    import web.blueprints.entries.common as ent_common
    monkeypatch.setattr(wu, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(wu, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(ent_common, "DATA_ROOT", tmp_path)

    cid = _client(app_db)
    resp = client.post(
        f"/client/{cid}/upload",
        data={"description": "Intake form", "date": "2026-06-19",
              "files[]": (BytesIO(b"x"), "note.txt"),
              "file_descriptions[]": "Scan"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    entry_id = app_db.get_client_entries(cid, "upload")[0]["id"]
    html = client.get(f"/client/{cid}/upload/{entry_id}").get_data(as_text=True)
    assert "data-dirty-guard" in html
    assert "data-dirty-save" in html
    assert "js/form-guard.js" in html


@pytest.mark.parametrize("kind", ["session", "communication", "absence",
                                  "item", "upload"])
def test_create_form_has_no_dirty_guard(client, app_db, kind):
    cid = _client(app_db)
    html = client.get(f"/client/{cid}/{kind}").get_data(as_text=True)
    assert "data-dirty-guard" not in html, \
        f"{kind} create form must not carry the dirty guard"


def test_profile_form_has_dirty_guard(client, app_db):
    cid = _client(app_db)
    html = client.get(f"/client/{cid}/profile").get_data(as_text=True)
    assert "data-dirty-guard" in html
    assert "data-dirty-save" in html
    assert "js/form-guard.js" in html
