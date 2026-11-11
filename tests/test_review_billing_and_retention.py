"""Billing, retention and home-page fixes from the 2026-11-11 review."""
import time
from datetime import datetime
from decimal import Decimal

TODAY = time.strftime('%Y-%m-%d')
START = time.strftime('%Y-%m-%d', time.localtime(time.time() - 60 * 86400))


def _types(app_db):
    types = app_db.get_all_client_types()
    active = next(t['id'] for t in types if not t.get('is_system_locked'))
    inactive = next(t['id'] for t in types if t.get('is_system_locked'))
    return active, inactive


def _client(app_db, file_number='BR-1'):
    return app_db.add_client({'file_number': file_number, 'first_name': 'A',
                              'last_name': 'B', 'type_id': _types(app_db)[0]})


def _session(app_db, cid, days_ago=1, fee=100.0):
    return app_db.add_entry({
        'client_id': cid, 'class': 'session', 'description': 'Session',
        'session_date': int(time.time()) - days_ago * 86400,
        'base_fee': fee, 'fee': fee, 'locked': 1})


def _sent_portions(app_db, client, cid):
    resp = client.post('/statements/generate', json={
        'client_ids': [cid], 'start_date': START, 'end_date': TODAY})
    assert resp.get_json()['count'] == 1
    conn = app_db.connect()
    conn.execute("UPDATE statement_portions SET status = 'sent'")
    conn.commit()
    return [r[0] for r in conn.execute(
        "SELECT id FROM statement_portions ORDER BY id").fetchall()]


def _write_off(client, portion_id, reason):
    return client.post('/statements/write-off',
                       json={'portion_id': portion_id, 'reason': reason})


# ---- write-off ----------------------------------------------------------------

def test_a_portion_can_only_be_written_off_once(client, app_db):
    cid = _client(app_db)
    _session(app_db, cid)
    (pid,) = _sent_portions(app_db, client, cid)

    assert _write_off(client, pid, 'uncollectible').status_code == 200
    assert _write_off(client, pid, 'uncollectible').status_code == 409

    count, total = app_db.connect().execute(
        "SELECT COUNT(*), SUM(total_amount) FROM entries WHERE class = 'expense'"
    ).fetchone()
    assert (count, total) == (1, 100.0)


def test_a_paid_portion_cannot_be_written_off(client, app_db):
    cid = _client(app_db)
    _session(app_db, cid)
    (pid,) = _sent_portions(app_db, client, cid)
    client.post('/statements/record-payment',
                json={'portion_id': pid, 'payment_amount': 100})
    assert _write_off(client, pid, 'waived').status_code == 409


def test_billing_error_leaves_the_payment_entry_linked(client, app_db):
    cid = _client(app_db)
    sid = _session(app_db, cid)
    (pid,) = _sent_portions(app_db, client, cid)
    client.post('/statements/record-payment',
                json={'portion_id': pid, 'payment_amount': 40})

    assert _write_off(client, pid, 'billing_error').status_code == 200

    assert app_db.get_entry(sid)['statement_id'] is None          # re-billable
    payment = app_db.connect().execute(
        "SELECT statement_id FROM entries WHERE class = 'income'").fetchone()
    assert payment[0] is not None                                 # untouched


def test_billing_error_on_a_split_waits_for_both_guardians(client, app_db):
    cid = _client(app_db)
    app_db.add_entry({'client_id': cid, 'class': 'profile', 'description': 'p',
                      'is_minor': 1, 'guardian1_name': 'G One',
                      'has_guardian2': 1, 'guardian2_name': 'G Two',
                      'guardian1_pays_percent': 50, 'guardian2_pays_percent': 50})
    sid = _session(app_db, cid)
    g1, g2 = _sent_portions(app_db, client, cid)

    assert _write_off(client, g1, 'billing_error').status_code == 200
    assert app_db.get_entry(sid)['statement_id'] is not None      # g2 still open

    assert _write_off(client, g2, 'billing_error').status_code == 200
    assert app_db.get_entry(sid)['statement_id'] is None


# ---- retention ------------------------------------------------------------------

def test_ten_years_means_ten_calendar_years(app_db):
    last_contact = int(datetime(2016, 11, 11).timestamp())
    due = app_db._calculate_retain_until(last_contact, 10 * 365, 0, None)
    assert datetime.fromtimestamp(due).date() == datetime(2026, 11, 11).date()


def test_leap_day_rolls_forward_and_plain_day_counts_are_unchanged(app_db):
    feb29 = int(datetime(2016, 2, 29).timestamp())
    due = app_db._calculate_retain_until(feb29, 7 * 365, 0, None)
    assert datetime.fromtimestamp(due).date() == datetime(2023, 3, 1).date()

    start = int(datetime(2026, 1, 1).timestamp())
    assert app_db._calculate_retain_until(start, 90, 0, None) == start + 90 * 86400


def test_minor_runs_ten_calendar_years_past_the_eighteenth_birthday(app_db):
    last_contact = int(datetime(2020, 6, 1).timestamp())
    due = app_db._calculate_retain_until(last_contact, 10 * 365, 1, '2010-03-15')
    assert datetime.fromtimestamp(due).date() == datetime(2038, 3, 15).date()


# ---- home page -------------------------------------------------------------------

def test_home_page_survives_a_session_with_no_date(client, app_db):
    cid = _client(app_db)
    _session(app_db, cid)
    app_db.add_entry({'client_id': cid, 'class': 'session',
                      'description': 'undated draft'})
    assert client.get('/').status_code == 200


def test_home_page_totals_match_the_per_client_figures(client, app_db):
    a, b = _client(app_db, 'BR-1'), _client(app_db, 'BR-2')
    _session(app_db, a, days_ago=0, fee=100.0)
    _session(app_db, b, days_ago=0, fee=62.5)
    app_db.add_entry({'client_id': b, 'class': 'session', 'description': 'C',
                      'session_date': int(time.time()), 'is_consultation': 1,
                      'locked': 1})

    assert app_db.get_unbilled_total_all() == \
        app_db.get_unbilled_total(a) + app_db.get_unbilled_total(b) == Decimal('162.50')
    midnight = int(datetime.now().replace(hour=0, minute=0, second=0,
                                          microsecond=0).timestamp())
    assert app_db.count_sessions_between(midnight, int(time.time())) == 2


# ---- Inactive clients are billable ---------------------------------------------

def test_find_unbilled_includes_inactive_clients_and_marks_them(client, app_db):
    cid = _client(app_db)
    _session(app_db, cid)
    client.post(f'/client/{cid}/change_type',
                data={'type_id': str(_types(app_db)[1])})

    listed = client.get(
        f'/statements/find-unbilled?start={START}&end={TODAY}').get_json()['clients']

    assert [(c['id'], c['inactive'], c['unbilled_total']) for c in listed] == \
        [(cid, True, 100.0)]
