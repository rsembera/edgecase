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
        "session_date": int(time.mktime((2026, 3, 1, 0, 0, 0, 0, 0, -1))),
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

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Clinical note, amended.',
    })

    assert app_db.get_entry(eid)['reflections'] == MARKER


def test_the_toggle_round_trips_through_the_api(client, app_db):
    assert client.get('/api/note_settings').get_json()['two_note_system'] is False
    client.post('/api/note_settings', json={'two_note_system': True})
    assert client.get('/api/note_settings').get_json()['two_note_system'] is True


# ----------------------------------------------------------------------
# Locked entries
# ----------------------------------------------------------------------

def _locked_session(db, client_id):
    eid = _session_with_reflections(db, client_id)
    db.update_entry(eid, {'locked': 1, 'locked_at': int(time.time())})
    return eid


def test_reflections_can_be_edited_on_a_locked_entry(client, app_db):
    """The bug: the locked-entry path builds a list of amendment-trail
    changes and returns early when it is empty. Reflections are deliberately
    not in that list, so a reflections-only edit was silently discarded."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-LOCK")
    eid = _locked_session(app_db, cid)

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Clinical note: presented with low mood.',   # unchanged
        'reflections': 'revised reflection',
    })

    assert app_db.get_entry(eid)['reflections'] == 'revised reflection'


def test_a_reflections_only_edit_leaves_no_amendment_trail(client, app_db):
    """Logging it would put process notes — and the fact that the field is in
    use — into an edit history that appears in exports."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-TRAIL")
    eid = _locked_session(app_db, cid)
    before = len(app_db.get_edit_history(eid))

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Clinical note: presented with low mood.',
        'reflections': 'revised reflection',
    })

    assert len(app_db.get_edit_history(eid)) == before


def test_a_reflections_only_edit_does_not_move_modified_at(client, app_db):
    """No trail entry means modified_at must not move either — bumping it
    would assert an edit the amendment trail doesn't show."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-MTIME")
    eid = _locked_session(app_db, cid)
    before = app_db.get_entry(eid)['modified_at']

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Clinical note: presented with low mood.',
        'reflections': 'revised reflection',
    })

    assert app_db.get_entry(eid)['modified_at'] == before


def test_a_clinical_edit_on_a_locked_entry_still_logs(client, app_db):
    """The guard above must not have disabled normal amendment logging."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-CLIN")
    eid = _locked_session(app_db, cid)
    before = len(app_db.get_edit_history(eid))

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Clinical note, amended.',
        'reflections': MARKER,
    })

    assert len(app_db.get_edit_history(eid)) > before


# ----------------------------------------------------------------------
# AI Scribe knows which field it was invoked for
# ----------------------------------------------------------------------

def test_scribe_opens_the_reflections_text_when_asked(client, app_db):
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-AI")
    eid = _session_with_reflections(app_db, cid)

    html = client.get(f'/ai/scribe/{eid}',
                      query_string={'field': 'reflections'}).get_data(as_text=True)
    assert MARKER in html


def test_scribe_defaults_to_the_clinical_note(client, app_db):
    cid = _client(app_db, "TWO-AI2")
    eid = _session_with_reflections(app_db, cid)

    html = client.get(f'/ai/scribe/{eid}').get_data(as_text=True)
    assert "Clinical note" in html
    assert MARKER not in html


def test_scribe_refuses_reflections_when_the_toggle_is_off(client, app_db):
    """A stale link must not open a field the practitioner has hidden."""
    app_db.set_setting('two_note_system', 'false')
    cid = _client(app_db, "TWO-AI3")
    eid = _session_with_reflections(app_db, cid)

    html = client.get(f'/ai/scribe/{eid}',
                      query_string={'field': 'reflections'}).get_data(as_text=True)
    assert MARKER not in html
    assert "Clinical note" in html


def test_scribe_saves_back_to_the_field_it_edited(client, app_db):
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-AI4")
    eid = _session_with_reflections(app_db, cid)

    resp = client.post(f'/ai/scribe/{eid}/save',
                       json={'content': 'scribed reflection',
                             'field': 'reflections'})
    assert resp.status_code == 200

    entry = app_db.get_entry(eid)
    assert entry['reflections'] == 'scribed reflection'
    assert entry['content'] == "Clinical note: presented with low mood."


def test_scribe_rejects_an_unknown_field(client, app_db):
    cid = _client(app_db, "TWO-AI5")
    eid = _session_with_reflections(app_db, cid)

    resp = client.post(f'/ai/scribe/{eid}/save',
                       json={'content': 'x', 'field': 'file_number'})
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# The AI Scribe button is a form submit: nothing typed may be lost
# ----------------------------------------------------------------------

def test_scribe_button_saves_both_fields_before_redirecting(client, app_db):
    """Clicking Scribe on Reflections submits the whole form. Text typed into
    Session Notes in the same sitting must survive the trip."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-TRIP")
    eid = _session_with_reflections(app_db, cid)

    resp = client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Typed into notes just now, not yet saved elsewhere.',
        'reflections': 'Typed into reflections just now.',
        'ai_scribe': 'reflections',
    })
    assert resp.status_code in (200, 302)

    entry = app_db.get_entry(eid)
    assert entry['content'] == 'Typed into notes just now, not yet saved elsewhere.'
    assert entry['reflections'] == 'Typed into reflections just now.'


def test_scribe_button_on_notes_also_saves_reflections(client, app_db):
    """The mirror case."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-TRIP2")
    eid = _session_with_reflections(app_db, cid)

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Notes text.',
        'reflections': 'Reflections text that must not be dropped.',
        'ai_scribe': '1',
    })

    entry = app_db.get_entry(eid)
    assert entry['reflections'] == 'Reflections text that must not be dropped.'
    assert entry['content'] == 'Notes text.'


def test_scribe_save_writes_only_its_own_field(client, app_db):
    """Accepting the Scribe's rewrite of one field must not disturb the other."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-TRIP3")
    eid = _session_with_reflections(app_db, cid)
    original_note = app_db.get_entry(eid)['content']

    client.post(f'/ai/scribe/{eid}/save',
                json={'content': 'Scribe rewrote the reflection.',
                      'field': 'reflections'})

    entry = app_db.get_entry(eid)
    assert entry['reflections'] == 'Scribe rewrote the reflection.'
    assert entry['content'] == original_note


def test_scribe_button_does_not_lock_the_entry(client, app_db):
    """A Scribe trip is a draft save; locking would strand the user at a
    Scribe that refuses locked entries."""
    app_db.set_setting('two_note_system', 'true')
    cid = _client(app_db, "TWO-TRIP4")
    eid = _session_with_reflections(app_db, cid)

    client.post(f'/client/{cid}/session/{eid}', data={
        'year': '2026', 'month': '03', 'day': '01',
        'content': 'Notes.', 'reflections': 'Reflections.',
        'ai_scribe': 'reflections',
    })

    assert not app_db.is_entry_locked(eid)
