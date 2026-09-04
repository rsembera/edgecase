"""`entries.ledger_date` is a DATE — always local midnight, every writer.

The defect: three code paths wrote ledger entries and each used a different
convention for the same column. The manual ledger forms stored local
midnight *except* when the date was today, in which case they stored the
moment of data entry ("so new entries appear at top"). The payment path
stored midnight always. The uncollectible write-off path stored the moment
of entry always.

Consequence, observed 2026-09-03: an expense entered manually at 19:00 got
ledger_date 19:00, a client payment recorded at 20:00 got ledger_date
00:00, and the ledger — which sorts ledger_date DESC — put the expense
above the payment, as though the payment had happened first.

The fix is to give the column one meaning. Newest-first-within-a-day comes
from created_at, which is what created_at is for and is already the second
sort key; `id` is the final tiebreaker so entries written in the same
second still have a defined order.
"""
import time
from datetime import datetime

import pytest


def _today_midnight():
    now = datetime.now()
    return int(datetime(now.year, now.month, now.day).timestamp())


def _today_str():
    return datetime.now().strftime('%Y-%m-%d')


def _ledger_date(db, entry_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT ledger_date FROM entries WHERE id = ?", (entry_id,))
    return cur.fetchone()[0]


def _newest_entry_id(db, ledger_type):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM entries WHERE ledger_type = ? "
                "ORDER BY id DESC LIMIT 1", (ledger_type,))
    row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Helpers for the payment paths (mirrors tests/test_record_payment.py)
# ---------------------------------------------------------------------------

def _make_client(db, file_number="LD-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Led",
        "middle_name": "",
        "last_name": "Ger",
        "type_id": 1,
    })


def _make_statement(db, client_id, total):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": "Statement August 2026",
        "statement_total": total,
        "statement_tax_total": 0.0,
        "created_at": now,
        "modified_at": now,
    })


def _make_portion(db, statement_entry_id, client_id, amount_due):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, created_at
        ) VALUES (?, ?, NULL, ?, 0.0, 'sent', ?)
    """, (statement_entry_id, client_id, amount_due, int(time.time())))
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Every writer stores midnight
# ---------------------------------------------------------------------------

def test_manual_expense_dated_today_is_stored_at_midnight(client, app_db):
    resp = client.post('/ledger/expense', data={
        'date': _today_str(),
        'payee_name': 'Google',
        'category_name': 'Advertising',
        'total_amount': '323.15',
        'description': 'Google Ads Aug. 2026',
    })
    assert resp.status_code in (200, 302)

    entry_id = _newest_entry_id(app_db, 'expense')
    assert _ledger_date(app_db, entry_id) == _today_midnight()


def test_manual_income_dated_today_is_stored_at_midnight(client, app_db):
    resp = client.post('/ledger/income', data={
        'date': _today_str(),
        'source': 'Workshop',
        'total_amount': '150.00',
        'description': 'Workshop fee',
    })
    assert resp.status_code in (200, 302)

    entry_id = _newest_entry_id(app_db, 'income')
    assert _ledger_date(app_db, entry_id) == _today_midnight()


def test_manual_expense_back_dated_is_unaffected(client, app_db):
    client.post('/ledger/expense', data={
        'date': '2026-07-15',
        'payee_name': 'Landlord',
        'category_name': 'Rent',
        'total_amount': '900.00',
        'description': 'July rent',
    })

    entry_id = _newest_entry_id(app_db, 'expense')
    assert _ledger_date(app_db, entry_id) == int(datetime(2026, 7, 15).timestamp())


def test_payment_with_no_date_is_stored_at_midnight(client, app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 150.0)
    portion = _make_portion(app_db, stmt, cid, 150.0)

    resp = client.post('/statements/record-payment', json={
        'portion_id': portion, 'payment_amount': 150.0})
    entry_id = resp.get_json()['entry_id']

    assert _ledger_date(app_db, entry_id) == _today_midnight()


def test_write_off_expense_is_stored_at_midnight(client, app_db):
    cid = _make_client(app_db, file_number="LD-002")
    stmt = _make_statement(app_db, cid, 150.0)
    portion = _make_portion(app_db, stmt, cid, 150.0)

    resp = client.post('/statements/write-off', json={
        'portion_id': portion, 'reason': 'uncollectible'})
    assert resp.status_code == 200

    entry_id = _newest_entry_id(app_db, 'expense')
    assert entry_id is not None
    assert _ledger_date(app_db, entry_id) == _today_midnight()


# ---------------------------------------------------------------------------
# The observed symptom
# ---------------------------------------------------------------------------

def test_payment_recorded_later_sorts_above_earlier_same_day_expense(
        client, app_db):
    """Rick's 2026-09-03 case: expense at 19:00, payment at 20:00."""
    client.post('/ledger/expense', data={
        'date': _today_str(),
        'payee_name': 'Google',
        'category_name': 'Advertising',
        'total_amount': '323.15',
        'description': 'Google Ads Aug. 2026',
    })
    expense_id = _newest_entry_id(app_db, 'expense')

    # The expense was entered an hour before the payment arrived. Without
    # this the two entries share a created_at second and the assertion
    # would be testing the tiebreaker instead of the date column.
    conn = app_db.connect()
    conn.execute("UPDATE entries SET created_at = created_at - 3600 "
                 "WHERE id = ?", (expense_id,))
    conn.commit()

    cid = _make_client(app_db, file_number="LD-003")
    stmt = _make_statement(app_db, cid, 150.0)
    portion = _make_portion(app_db, stmt, cid, 150.0)
    resp = client.post('/statements/record-payment', json={
        'portion_id': portion, 'payment_amount': 150.0,
        'payment_date': _today_str()})
    income_id = resp.get_json()['entry_id']

    order = [e['id'] for e in app_db.get_all_ledger_entries()]
    assert order.index(income_id) < order.index(expense_id)


def test_same_second_entries_have_a_defined_order(client, app_db):
    """created_at collides at one-second resolution; id breaks the tie."""
    for n in range(3):
        client.post('/ledger/expense', data={
            'date': _today_str(),
            'payee_name': 'Supplier',
            'category_name': 'Supplies',
            'total_amount': f'{10 + n}.00',
            'description': f'Order {n}',
        })

    conn = app_db.connect()
    conn.execute("UPDATE entries SET created_at = 1788400000 "
                 "WHERE ledger_type = 'expense'")
    conn.commit()

    ids = [e['id'] for e in app_db.get_all_ledger_entries()]
    assert ids == sorted(ids, reverse=True)
