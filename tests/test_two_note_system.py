"""Two-note system: a Reflections field that never leaves in an export.

Reflections are the practitioner's own process notes. They live on the
session entry, so retention, disposal, backup and encryption cover them
automatically — the alternative, a new entry class, would have needed each of
those paths told about it, which is the failure that produced three separate
defects on 2026-09-04.

The toggle hides the field; it never deletes. Reflections already written stay
in the database and reappear when it is switched back on. That is deliberate:
a control in Settings that destroys clinical notes would be dangerous.
"""
import io
import time

import pytest

pypdf = pytest.importorskip("pypdf")

from core.db.private_columns import strip_private

MARKER = "ZZQX-reflection-marker-ZZQX"


def _text(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or '') for p in reader.pages)


def _client(db, file_number="TWO-001"):
    return db.add_client({
        "file_number": file_number, "first_name": "Two", "middle_name": "",
        "last_name": "Note", "type_id": 1,
    })


def _session_with_reflections(db, client_id, reflections=MARKER):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "session",
        "description": "Session 1",
        "content": "Clinical note: presented with low mood.",
        "reflections": reflections,
        "session_date": "2026-03-01",
        "created_at": now,
        "modified_at": now,
    })


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

def test_reflections_are_stored_and_read_back(app_db):
    cid = _client(app_db)
    eid = _session_with_reflections(app_db, cid)
    assert app_db.get_entry(eid)['reflections'] == MARKER


def test_reflections_can_be_edited(app_db):
    cid = _client(app_db)
    eid = _session_with_reflections(app_db, cid)
    app_db.update_entry(eid, {'reflections': 'revised'})
    assert app_db.get_entry(eid)['reflections'] == 'revised'


def test_a_session_without_reflections_is_unaffected(app_db):
    cid = _client(app_db)
    now = int(time.time())
    eid = app_db.add_entry({
        "client_id": cid, "class": "session", "description": "s",
        "content": "note", "created_at": now, "modified_at": now})
    assert app_db.get_entry(eid)['reflections'] is None


# ----------------------------------------------------------------------
# The exclusion guarantee
# ----------------------------------------------------------------------

def test_strip_private_removes_reflections(app_db):
    row = {'id': 1, 'content': 'kept', 'reflections': MARKER}
    assert strip_private(row) == {'id': 1, 'content': 'kept'}
    assert strip_private([row])[0] == {'id': 1, 'content': 'kept'}
    assert strip_private(None) is None


def test_client_file_export_never_contains_reflections(client, app_db):
    cid = _client(app_db)
    _session_with_reflections(app_db, cid)

    resp = client.get(f'/client/{cid}/export/pdf',
                      query_string={'types': 'session', 'all_time': '1'})
    assert resp.status_code == 200
    text = _text(resp.data)
    assert "Clinical note" in text          # the export still works
    assert MARKER not in text
    resp.close()


def test_client_report_never_contains_reflections(client, app_db):
    cid = _client(app_db)
    _session_with_reflections(app_db, cid)

    resp = client.get(f'/client/{cid}/session-report',
                      query_string={'start_year': '2026', 'start_month': '1',
                                    'start_day': '1', 'end_year': '2026',
                                    'end_month': '12', 'end_day': '31'})
    assert resp.status_code == 200
    assert MARKER not in _text(resp.data)
    resp.close()


# ----------------------------------------------------------------------
# The toggle hides; it does not delete
# ----------------------------------------------------------------------

def test_field_is_absent_from_the_session_form_by_default(client, app_db):
    cid = _client(app_db)
    html = client.get(f'/client/{cid}/session').get_data(as_text=True)
    assert 'name="reflections"' not in html


def test_field_appears_when_enabled(client, app_db):
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db)
    html = client.get(f'/client/{cid}/session').get_data(as_text=True)
    assert 'name="reflections"' in html


def test_turning_the_toggle_off_does_not_erase_anything(client, app_db):
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db)
    eid = _session_with_reflections(app_db, cid)

    client.post('/api/note_settings', json={'two_note_system': False})

    assert app_db.get_entry(eid)['reflections'] == MARKER


def test_saving_a_session_with_the_field_hidden_preserves_reflections(
        client, app_db):
    """The dangerous case: the toggle is off, so the form has no reflections
    field, and saving the session must not blank what is stored."""
    cid = _client(app_db)
    eid = _session_with_reflections(app_db, cid)
    app_db.set_setting('two_note_system', 'false')

    client.post(f'/client/entry/{eid}/edit', data={
        'session_date': '2026-03-01',
        'content': 'Clinical note, amended.',
    })

    assert app_db.get_entry(eid)['reflections'] == MARKER


def test_the_toggle_round_trips_through_the_api(client, app_db):
    assert client.get('/api/note_settings').get_json()['two_note_system'] is False
    client.post('/api/note_settings', json={'two_note_system': True})
    assert client.get('/api/note_settings').get_json()['two_note_system'] is True
