"""Record-integrity fixes from the 2026-11-11 review.

- A locked session cannot be rewritten through the draft / AI Scribe save.
- Edit-history values are escaped when rendered.
- Redaction removes the edit history and attachments along with the content.
"""
import json
import os
import time


def _client(app_db, file_number='RI-1'):
    type_id = app_db.get_all_client_types()[0]['id']
    return app_db.add_client({'file_number': file_number, 'first_name': 'A',
                              'last_name': 'B', 'type_id': type_id})


def _locked_session(app_db, cid):
    sid = app_db.add_entry({
        'client_id': cid, 'class': 'session', 'description': 'Session 1',
        'session_number': 1, 'session_date': int(time.time()) - 86400,
        'content': 'original note', 'base_fee': 100.0, 'fee': 100.0,
        'modality': 'in-person', 'format': 'individual'})
    app_db.lock_entry(sid)
    return sid


def _session_form(content, **extra):
    day = time.strftime('%Y-%m-%d', time.localtime(time.time() - 86400))
    form = {'date': day, 'content': content, 'modality': 'in-person',
            'format': 'individual', 'base_fee': '100', 'fee': '100'}
    form.update(extra)
    return form


# ---- locked session vs. draft save -----------------------------------------

def test_draft_save_on_a_locked_session_is_logged_as_an_amendment(client, app_db):
    cid = _client(app_db)
    sid = _locked_session(app_db, cid)

    client.post(f'/client/{cid}/session/{sid}',
                data=_session_form('rewritten note', save_draft='1'))

    entry = app_db.get_entry(sid)
    assert entry['content'] == 'rewritten note'
    history = json.loads(entry['edit_history'] or '[]')
    assert len(history) == 1 and 'Notes:' in history[0]['description']


def test_scribe_save_on_a_locked_session_is_logged_and_stays_on_the_file(client, app_db):
    cid = _client(app_db)
    sid = _locked_session(app_db, cid)

    resp = client.post(f'/client/{cid}/session/{sid}',
                       data=_session_form('rewritten note', ai_scribe='1'))

    assert '/ai/scribe/' not in resp.headers['Location']
    assert json.loads(app_db.get_entry(sid)['edit_history'] or '[]')


def test_draft_save_on_an_unlocked_draft_is_unchanged(client, app_db):
    cid = _client(app_db)
    sid = app_db.add_entry({
        'client_id': cid, 'class': 'session', 'description': 'Session 1',
        'session_number': 1, 'session_date': int(time.time()) - 86400,
        'content': 'draft', 'modality': 'in-person', 'format': 'individual'})

    client.post(f'/client/{cid}/session/{sid}',
                data=_session_form('still a draft', save_draft='1'))

    entry = app_db.get_entry(sid)
    assert entry['content'] == 'still a draft'
    assert not entry['locked'] and not entry['edit_history']


# ---- edit-history escaping ---------------------------------------------------

def test_sanitizer_escapes_values_and_keeps_diff_tags():
    from core.db.edit_history import sanitize_history_html

    raw = 'Emergency Contact: <img src=x onerror=alert(1)> → Mom'
    assert sanitize_history_html(raw) == \
        'Emergency Contact: &lt;img src=x onerror=alert(1)&gt; → Mom'
    diff = 'Notes: one <del>two</del> <strong>three</strong> a &lt; b'
    assert sanitize_history_html(diff) == diff
    assert sanitize_history_html('') == '' and sanitize_history_html(None) is None


def test_profile_history_renders_stored_values_as_text(client, app_db):
    cid = _client(app_db)
    payload = '<img src=x onerror=alert(1)>'
    base = {'first_name': 'A', 'last_name': 'B', 'file_number': 'RI-1',
            'emergency_contact_name': payload}
    client.post(f'/client/{cid}/profile', data=base)
    client.post(f'/client/{cid}/profile',
                data=dict(base, emergency_contact_name='Mom'))

    html = client.get(f'/client/{cid}/profile').get_data(as_text=True)
    line = html[html.index('Emergency Contact:'):][:200]
    assert payload not in line
    assert '&lt;img src=x onerror=alert(1)&gt;' in line


def test_content_diff_markup_still_renders(client, app_db):
    cid = _client(app_db)
    sid = _locked_session(app_db, cid)
    client.post(f'/client/{cid}/session/{sid}',
                data=_session_form('original memo'))
    html = client.get(f'/client/{cid}/session/{sid}').get_data(as_text=True)
    assert '<del>note</del>' in html and '<strong>memo</strong>' in html


# ---- redaction ---------------------------------------------------------------

def test_redaction_removes_history_and_attachments(app_db, tmp_path):
    cid = _client(app_db)
    eid = app_db.add_entry({'client_id': cid, 'class': 'communication',
                            'description': 'x',
                            'content': 'about another client'})
    app_db.lock_entry(eid)
    app_db.add_to_edit_history(
        eid, 'Content: <del>about another client</del> <strong>fixed</strong>')
    stored = tmp_path / 'misfiled.enc'
    stored.write_bytes(b'ciphertext')
    conn = app_db.connect()
    conn.execute(
        "INSERT INTO attachments (entry_id, filename, description, filepath, "
        "filesize, uploaded_at) VALUES (?, 'a.pdf', 'a', ?, 10, 0)",
        (eid, str(stored)))
    conn.commit()

    assert app_db.redact_entry(eid, 'wrong file') is True

    entry = app_db.get_entry(eid)
    assert entry['content'] is None and entry['edit_history'] is None
    assert app_db.get_attachments(eid) == []
    assert not os.path.exists(stored)
