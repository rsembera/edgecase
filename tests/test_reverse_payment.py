"""Reverse payment: unwind a recorded payment and reopen its portions."""
import time
from decimal import Decimal

from core.money import dec, quantize_cents


def _make_client(db, file_number="RP-001", first="Rev", last="Pay"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _make_statement(db, client_id, total, tax=0.0, description="Statement"):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": description,
        "statement_total": total,
        "statement_tax_total": tax,
    })


def _make_portion(db, statement_entry_id, client_id, amount_due,
                  guardian_number=None, status="sent"):
    conn = db.connect()
    cur = conn.cursor()
    now = int(time.time())
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, date_sent, created_at
        ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
    """, (statement_entry_id, client_id, guardian_number, amount_due,
          status, now if status != 'ready' else None, now))
    conn.commit()
    return cur.lastrowid


def _portion(db, portion_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT amount_due, amount_paid, status "
                "FROM statement_portions WHERE id = ?", (portion_id,))
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, cur.fetchone()))


def _alloc_count(db, entry_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM payment_allocations WHERE entry_id = ?",
                (entry_id,))
    return cur.fetchone()[0]


def _income_count(db):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entries WHERE class = 'income'")
    return cur.fetchone()[0]


def _pay(client, portion_id, amount, payment_date=None):
    """Record a payment via the route; return the JSON response."""
    payload = {
        'portion_id': portion_id,
        'payment_amount': amount,
    }
    if payment_date:
        payload['payment_date'] = payment_date
    resp = client.post('/statements/record-payment',
                       json=payload,
                       content_type='application/json')
    return resp.get_json()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_reverse_single_payment(client, app_db):
    """Reverse a payment that settled one statement exactly."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 150.0)
    pid = _make_portion(app_db, stmt, cid, 150.0)

    pay_data = _pay(client, pid, 150.0)
    assert pay_data['success'] is True
    entry_id = pay_data['entry_id']

    # Portion should be paid
    assert _portion(app_db, pid)['status'] == 'paid'

    # Reverse it
    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    data = resp.get_json()
    assert data['success'] is True

    # Portion should be back to 'sent'
    p = _portion(app_db, pid)
    assert p['status'] == 'sent'
    assert p['amount_paid'] == 0.0

    # Income entry should be gone
    assert _income_count(app_db) == 0

    # Allocations should be gone
    assert _alloc_count(app_db, entry_id) == 0


def test_reverse_payment_with_credit_remainder(client, app_db):
    """Reverse a payment that created credit (overpayment)."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    pid = _make_portion(app_db, stmt, cid, 100.0)

    pay_data = _pay(client, pid, 150.0)
    assert pay_data['success'] is True
    assert pay_data['credit'] == 50.0
    entry_id = pay_data['entry_id']

    # Reverse it — should delete both the portion allocation and the credit row
    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    assert resp.get_json()['success'] is True

    assert _portion(app_db, pid)['status'] == 'sent'
    assert _income_count(app_db) == 0
    assert _alloc_count(app_db, entry_id) == 0

    # Credit should be zero
    credit = app_db.get_client_credit(cid, None)
    assert credit == Decimal('0.00')


def test_reverse_multi_statement_payment(client, app_db):
    """Reverse a lump-sum payment that settled two statements."""
    cid = _make_client(app_db)
    s1 = _make_statement(app_db, cid, 100.0, description="July")
    s2 = _make_statement(app_db, cid, 200.0, description="August")
    p1 = _make_portion(app_db, s1, cid, 100.0)
    p2 = _make_portion(app_db, s2, cid, 200.0)

    pay_data = _pay(client, p1, 300.0)
    assert pay_data['success'] is True
    entry_id = pay_data['entry_id']

    assert _portion(app_db, p1)['status'] == 'paid'
    assert _portion(app_db, p2)['status'] == 'paid'

    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    assert resp.get_json()['success'] is True

    assert _portion(app_db, p1)['status'] == 'sent'
    assert _portion(app_db, p2)['status'] == 'sent'
    assert _income_count(app_db) == 0


# ---------------------------------------------------------------------------
# Refusal cases
# ---------------------------------------------------------------------------

def test_refuses_when_credit_consumed(client, app_db):
    """Cannot reverse a payment whose credit was consumed by a later stmt."""
    cid = _make_client(app_db)
    s1 = _make_statement(app_db, cid, 100.0)
    p1 = _make_portion(app_db, s1, cid, 100.0)

    # Pay $150 against $100 → $50 credit
    pay_data = _pay(client, p1, 150.0)
    entry_id = pay_data['entry_id']

    # Simulate credit consumption: insert an is_credit allocation row
    # as consume_credit would during statement generation
    conn = app_db.connect()
    cur = conn.cursor()
    now = int(time.time())
    # Create a second statement and portion
    s2 = _make_statement(app_db, cid, 50.0, description="September")
    p2 = _make_portion(app_db, s2, cid, 50.0)

    # Spend the credit (as consume_credit would)
    app_db.consume_credit(cur, cid, None, p2, Decimal('50.00'), now,
                          statement_tax=Decimal('0'), statement_total=Decimal('50'))
    conn.commit()

    # Now try to reverse the original payment
    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    data = resp.get_json()
    assert data['success'] is False
    assert resp.status_code == 409
    assert 'credit' in data['error'].lower()

    # Original payment and portions should be untouched
    assert _income_count(app_db) == 1
    assert _portion(app_db, p1)['status'] == 'paid'


def test_refuses_non_income_entry(client, app_db):
    """Cannot reverse a statement or expense entry."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)

    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': stmt},
                       content_type='application/json')
    data = resp.get_json()
    assert data['success'] is False
    assert resp.status_code == 400


def test_refuses_manual_income_without_allocations(client, app_db):
    """A manual income entry (no allocations) should use Delete, not Reverse."""
    entry_id = app_db.add_entry({
        'client_id': None,
        'class': 'income',
        'ledger_type': 'income',
        'total_amount': 50.0,
        'description': 'Manual income',
    })

    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    data = resp.get_json()
    assert data['success'] is False
    assert 'no payment allocations' in data['error'].lower()


def test_refuses_nonexistent_entry(client, app_db):
    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': 99999},
                       content_type='application/json')
    assert resp.get_json()['success'] is False
    assert resp.status_code == 404


def test_portion_always_returns_to_sent(client, app_db):
    """record_payment only touches sent/partial portions, so reversal
    always returns to 'sent' — there is no 'ready' branch."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    pid = _make_portion(app_db, stmt, cid, 100.0)

    # Even if date_sent is NULL (inconsistent record), we return to 'sent'
    conn = app_db.connect()
    conn.execute("UPDATE statement_portions SET date_sent = NULL WHERE id = ?", (pid,))
    conn.commit()

    pay_data = _pay(client, pid, 100.0)
    assert pay_data['success'] is True
    entry_id = pay_data['entry_id']

    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': entry_id},
                       content_type='application/json')
    assert resp.get_json()['success'] is True

    # Always 'sent', never 'ready'
    assert _portion(app_db, pid)['status'] == 'sent'


def test_reverse_one_of_two_payments_leaves_partial(client, app_db):
    """Two payments on one portion; reverse only the later one."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 200.0)
    pid = _make_portion(app_db, stmt, cid, 200.0)

    # First payment: $80
    pay1 = _pay(client, pid, 80.0)
    assert pay1['success'] is True

    # Second payment: $120 (settles it)
    pay2 = _pay(client, pid, 120.0)
    assert pay2['success'] is True
    assert _portion(app_db, pid)['status'] == 'paid'

    # Reverse only the second payment
    resp = client.post('/statements/reverse-payment',
                       json={'entry_id': pay2['entry_id']},
                       content_type='application/json')
    assert resp.get_json()['success'] is True

    p = _portion(app_db, pid)
    assert p['status'] == 'partial'
    assert p['amount_paid'] == 80.0

    # First payment's allocations should be untouched
    assert _alloc_count(app_db, pay1['entry_id']) == 1


def test_delete_income_refuses_allocated_entry(client, app_db):
    """The delete route should refuse entries that have allocations."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    pid = _make_portion(app_db, stmt, cid, 100.0)

    pay_data = _pay(client, pid, 100.0)
    entry_id = pay_data['entry_id']

    resp = client.post(f'/ledger/income/{entry_id}/delete',
                       content_type='application/json')
    assert resp.status_code == 409

    # Entry and allocations should still exist
    assert _income_count(app_db) == 1
    assert _alloc_count(app_db, entry_id) > 0
    assert _portion(app_db, pid)['status'] == 'paid'
