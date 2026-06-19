"""Entries lifecycle route tests (database.py refactor Step 2, Target A).

Drives the session create -> lock -> amendment lifecycle through real routes, so
the entries/edit-history data-layer methods are exercised end-to-end. Session is
the centrepiece (numbering, locking, amendment trail); the other entry types
follow the same create/edit pattern and can be added on top of this net.
"""


def _make_client(db):
    return db.add_client({
        "file_number": "LC-001",
        "first_name": "Life",
        "middle_name": "",
        "last_name": "Cycle",
        "type_id": 1,
    })


def _session_form(content, date="2026-06-19"):
    """Minimal valid session POST body. is_consultation/is_pro_bono omitted
    (falsy), so the entry is a normal numbered session."""
    return {
        "modality": "Individual",
        "format": "In-person",
        "date": date,
        "duration": "50",
        "content": content,
    }


def test_session_create_locks_and_starts_clean(client, app_db):
    """Creating a (non-draft) session locks it on save with an empty amendment
    trail."""
    cid = _make_client(app_db)
    resp = client.post(f"/client/{cid}/session", data=_session_form("Original notes"))
    assert resp.status_code == 302

    sessions = app_db.get_client_entries(cid, "session")
    assert len(sessions) == 1
    entry = sessions[0]
    assert entry["content"] == "Original notes"
    assert app_db.is_entry_locked(entry["id"])
    assert len(app_db.get_edit_history(entry["id"])) == 0


def test_session_locked_noop_save_is_true_noop(client, app_db):
    """Re-saving a locked session with identical data must not append an
    amendment row or bump modified_at (guards stale tabs / double-submits)."""
    cid = _make_client(app_db)
    client.post(f"/client/{cid}/session", data=_session_form("Original notes"))
    entry_id = app_db.get_client_entries(cid, "session")[0]["id"]
    modified_before = app_db.get_entry(entry_id)["modified_at"]

    resp = client.post(
        f"/client/{cid}/session/{entry_id}", data=_session_form("Original notes")
    )
    assert resp.status_code == 302

    after = app_db.get_entry(entry_id)
    assert len(app_db.get_edit_history(entry_id)) == 0
    assert after["modified_at"] == modified_before


def test_session_locked_edit_appends_exactly_one_amendment(client, app_db):
    """A genuine edit to a locked session updates content and appends exactly
    one edit-history row."""
    cid = _make_client(app_db)
    client.post(f"/client/{cid}/session", data=_session_form("Original notes"))
    entry_id = app_db.get_client_entries(cid, "session")[0]["id"]
    assert len(app_db.get_edit_history(entry_id)) == 0

    resp = client.post(
        f"/client/{cid}/session/{entry_id}", data=_session_form("Amended notes")
    )
    assert resp.status_code == 302

    assert app_db.get_entry(entry_id)["content"] == "Amended notes"
    assert len(app_db.get_edit_history(entry_id)) == 1
