"""The smaller fixes from the 2026-11-11 review."""
import io
import json
import time

import pytest

from web.app import app as flask_app


@pytest.fixture(autouse=True)
def no_backup(monkeypatch):
    monkeypatch.setattr('web.cli._run_shutdown_backup', lambda *a, **k: None)


def _client(app_db, file_number='SF-1'):
    type_id = next(t['id'] for t in app_db.get_all_client_types()
                   if not t.get('is_system_locked'))
    return app_db.add_client({'file_number': file_number, 'first_name': 'A',
                              'last_name': 'B', 'type_id': type_id})


def test_profile_save_with_no_date_of_birth_logs_nothing(client, app_db):
    cid = _client(app_db)
    form = {'first_name': 'A', 'last_name': 'B', 'file_number': 'SF-1',
            'phone': '613-555-0100'}
    client.post(f'/client/{cid}/profile', data=form)
    client.post(f'/client/{cid}/profile', data=dict(form, phone='613-555-0199'))

    history = json.loads(app_db.get_profile_entry(cid)['edit_history'])
    assert 'Date of Birth' not in history[-1]['description']
    assert 'Cell Phone' in history[-1]['description']


def test_schedule_page_opens_with_a_blank_consultation_duration(client, app_db):
    cid = _client(app_db)
    app_db.set_setting('consultation_duration', '')
    assert client.get(f'/client/{cid}/schedule').status_code == 200


def test_renaming_a_type_to_an_existing_name_is_an_error_message(client, app_db):
    existing = app_db.get_all_client_types()[0]['name']
    type_id = app_db.add_client_type({'name': 'Low Fee', 'color': '#fff',
                                      'retention_period': 3650})
    resp = client.post(f'/edit_type/{type_id}', data={
        'name': existing, 'color': '#fff', 'color_name': 'x',
        'bubble_color': '#fff', 'retention_value': '', 'retention_unit': 'years'})
    assert resp.status_code == 200
    assert 'already exists' in resp.get_data(as_text=True)
    assert app_db.get_client_type(type_id)['name'] == 'Low Fee'


def test_item_edit_rounds_money_to_cents(client, app_db):
    cid = _client(app_db)
    eid = app_db.add_entry({'client_id': cid, 'class': 'item', 'description': 'Report',
                            'item_date': int(time.time()), 'base_price': 10.0,
                            'fee': 10.0, 'locked': 1})
    client.post(f'/client/{cid}/item/{eid}', data={
        'description': 'Report', 'item_date': time.strftime('%Y-%m-%d'),
        'base_price': '10.005', 'fee': '10.005', 'guardian1_amount': '3.335'})
    entry = app_db.get_entry(eid)
    assert (entry['fee'], entry['base_price'], entry['guardian1_amount']) == \
        (10.01, 10.01, 3.34)


def test_uploads_lock_on_save_and_later_edits_are_logged(client, app_db):
    cid = _client(app_db)
    day = time.strftime('%Y-%m-%d')
    client.post(f'/client/{cid}/upload', data={
        'description': 'Referral letter', 'date': day,
        'files[]': (io.BytesIO(b''), '')}, content_type='multipart/form-data')
    entry = app_db.get_client_entries(cid, 'upload')[0]
    assert entry['locked'] == 1

    client.post(f"/client/{cid}/upload/{entry['id']}", data={
        'description': 'Referral letter (Dr. Lee)', 'date': day,
        'files[]': (io.BytesIO(b''), '')}, content_type='multipart/form-data')
    history = json.loads(app_db.get_entry(entry['id'])['edit_history'])
    assert 'Description' in history[0]['description']


def test_backfill_is_quiet_about_payments_whose_statement_is_gone(app_db, capsys):
    app_db.add_entry({'client_id': None, 'class': 'income', 'ledger_type': 'income',
                      'ledger_date': int(time.time()), 'total_amount': 100.0,
                      'tax_amount': 0, 'statement_id': 999999})
    capsys.readouterr()
    result = app_db.backfill_payment_allocations(verbose=True)
    assert result['skipped_ambiguous'] == 0
    assert result['skipped_no_statement'] == 1
    assert capsys.readouterr().out == ''


def test_logout_forgets_cached_keys(client, app_db):
    from core import encryption, encryption_v2
    encryption._fernet_cache['pw'] = object()
    encryption_v2._key_cache['pw'] = ('00', b'k')
    client.get('/logout')
    assert flask_app.config['db'] is None
    assert not encryption._fernet_cache and not encryption_v2._key_cache


def test_a_disposed_clients_file_number_is_not_reissued(app_db):
    conn = app_db.connect()
    conn.execute("INSERT INTO archived_clients (file_number, full_name, deleted_at) "
                 "VALUES ('OLD-7', 'Gone Client', 0)")
    conn.commit()
    assert app_db.file_number_exists('OLD-7')
    assert not app_db.file_number_exists('NEW-1')


def test_ics_text_has_no_bare_carriage_returns():
    from web.blueprints.scheduler import escape_ics_text
    assert escape_ics_text('line one\r\nline two') == 'line one\\nline two'


def test_export_with_an_impossible_date_is_refused_not_widened(client, app_db):
    cid = _client(app_db)
    query = ('types=session&start_year=2026&start_month=1&start_day=1'
             '&end_year=2026&end_month=11&end_day=31')
    assert client.get(f'/client/{cid}/export/pdf?{query}').status_code == 400
    assert client.get(f'/client/{cid}/export/calculate?{query}').status_code == 400
