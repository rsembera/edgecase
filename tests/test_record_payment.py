"""record_payment: one deposit settling one or more statements (Phase 2).

The defect being fixed: a $300 transfer covering a $100 July statement and
a $200 August one used to need two hand-split payments, neither of which
matched the amount that actually arrived. See
docs/Payment_Allocation_Plan.md.
"""
import time
from decimal import Decimal

from core.billing import propose_allocation


def _make_client(db, file_number="PA-001", first="Pay", last="Er"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _make_statement(db, client_id, total, tax=0.0, description="Statement",
                    created_at=None):
    now = int(time.time())
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": description,
        "statement_total": total,
        "statement_tax_total": tax,
        "created_at": now,
        "modified_at": now,
    })
    if created_at is not None:
        conn = db.connect()
        conn.execute("UPDATE entries SET created_at = ? WHERE id = ?",
                     (created_at, entry_id))
        conn.commit()
    return entry_id


def _make_portion(db, statement_entry_id, client_id, amount_due,
                  guardian_number=None, status="sent", amount_paid=0.0):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (statement_entry_id, client_id, guardian_number, amount_due,
          amount_paid, status, int(time.time())))
    conn.commit()
    return cur.lastrowid


def _two_statements(db, cid, july_total=100.0, august_total=200.0,
                    july_tax=0.0, august_tax=0.0):
    """July ($100) then August ($200), both sent. The plan's worked example."""
    july = _make_statement(db, cid, july_total, tax=july_tax,
                           description="Statement July 2026",
                           created_at=1_780_000_000)
    august = _make_statement(db, cid, august_total, tax=august_tax,
                             description="Statement August 2026",
                             created_at=1_785_000_000)
    return (_make_portion(db, july, cid, july_total),
            _make_portion(db, august, cid, august_total))


def _portion(db, portion_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT amount_due, amount_paid, status "
                "FROM statement_portions WHERE id = ?", (portion_id,))
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, cur.fetchone()))


def _entry(db, entry_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT total_amount, tax_amount, ledger_date, statement_id, "
                "source, description, content FROM entries WHERE id = ?",
                (entry_id,))
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, cur.fetchone()))


def _income_count(db):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entries WHERE class = 'income'")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# propose_allocation — pure oldest-first arithmetic
# ---------------------------------------------------------------------------

def test_propose_fills_oldest_first():
    portions = [
        {'id': 1, 'amount_due': 100.0, 'amount_paid': 0.0},
        {'id': 2, 'amount_due': 200.0, 'amount_paid': 0.0},
    ]
    proposed, remainder = propose_allocation(portions, 150)
    assert proposed == [(1, Decimal('100.00')), (2, Decimal('50.00'))]
    assert remainder == Decimal('0.00')


def test_propose_returns_a_row_for_every_portion_including_zero():
    portions = [
        {'id': 1, 'amount_due': 100.0, 'amount_paid': 0.0},
        {'id': 2, 'amount_due': 200.0, 'amount_paid': 0.0},
    ]
    proposed, _ = propose_allocation(portions, 60)
    assert proposed == [(1, Decimal('60.00')), (2, Decimal('0.00'))]


def test_propose_never_overfills_a_portion():
    """The overpayment goes to the remainder, not onto the last statement."""
    portions = [{'id': 1, 'amount_due': 100.0, 'amount_paid': 0.0}]
    proposed, remainder = propose_allocation(portions, 150)
    assert proposed == [(1, Decimal('100.00'))]
    assert remainder == Decimal('50.00')


def test_propose_accounts_for_amounts_already_paid():
    portions = [{'id': 1, 'amount_due': 100.0, 'amount_paid': 40.0}]
    proposed, remainder = propose_allocation(portions, 100)
    assert proposed == [(1, Decimal('60.00'))]
    assert remainder == Decimal('40.00')


def test_propose_with_nothing_outstanding_is_all_remainder():
    proposed, remainder = propose_allocation([], 75)
    assert proposed == []
    assert remainder == Decimal('75.00')


# ---------------------------------------------------------------------------
# payment-proposal route
# ---------------------------------------------------------------------------

def test_proposal_defaults_to_everything_outstanding(client, app_db):
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.get('/statements/payment-proposal',
                      query_string={'portion_id': july})
    data = resp.get_json()

    assert data['success'] is True
    assert data['total_owing'] == 300.0
    assert data['amount'] == 300.0
    assert [p['proposed'] for p in data['portions']] == [100.0, 200.0]
    assert data['unallocated'] == 0.0


def test_proposal_lists_oldest_statement_first(client, app_db):
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.get('/statements/payment-proposal',
                      query_string={'portion_id': august})
    portions = resp.get_json()['portions']

    assert [p['portion_id'] for p in portions] == [july, august]
    assert portions[0]['description'] == "Statement July 2026"


def test_proposal_splits_a_partial_amount(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.get('/statements/payment-proposal',
                      query_string={'portion_id': july, 'amount': 150})
    data = resp.get_json()

    assert [p['proposed'] for p in data['portions']] == [100.0, 50.0]
    assert data['unallocated'] == 0.0


def test_proposal_reports_the_overpayment_as_unallocated(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.get('/statements/payment-proposal',
                      query_string={'portion_id': july, 'amount': 350})
    data = resp.get_json()

    assert [p['proposed'] for p in data['portions']] == [100.0, 200.0]
    assert data['unallocated'] == 50.0


def test_proposal_is_scoped_to_one_guardian(client, app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)

    data = client.get('/statements/payment-proposal',
                      query_string={'portion_id': g1}).get_json()

    assert [p['portion_id'] for p in data['portions']] == [g1]
    assert data['total_owing'] == 200.0
    assert data['payer_label'] == 'Guardian 1'


def test_proposal_excludes_unsent_statements(client, app_db):
    """A statement the client has never received is not payable."""
    cid = _make_client(app_db)
    sent = _make_portion(app_db, _make_statement(app_db, cid, 100.0), cid, 100.0)
    _make_portion(app_db, _make_statement(app_db, cid, 50.0), cid, 50.0,
                  status="ready")

    data = client.get('/statements/payment-proposal',
                      query_string={'portion_id': sent}).get_json()

    assert [p['portion_id'] for p in data['portions']] == [sent]
    assert data['total_owing'] == 100.0


def test_proposal_404s_for_an_unknown_portion(client, app_db):
    resp = client.get('/statements/payment-proposal',
                      query_string={'portion_id': 9999})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# record-payment — the lump sum
# ---------------------------------------------------------------------------

def test_lump_sum_settles_two_statements_with_one_entry(client, app_db):
    """The plan's worked example: $300 arrives, July and August close."""
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 300.0,
        'allocations': [{'portion_id': july, 'amount': 100.0},
                        {'portion_id': august, 'amount': 200.0}],
    })
    data = resp.get_json()

    assert data['success'] is True
    assert _income_count(app_db) == 1
    assert _entry(app_db, data['entry_id'])['total_amount'] == 300.0
    assert _portion(app_db, july)['status'] == 'paid'
    assert _portion(app_db, august)['status'] == 'paid'

    allocations = app_db.get_payment_allocations(data['entry_id'])
    assert len(allocations) == 2
    assert app_db.get_allocated_total(data['entry_id']) == Decimal('300.00')


def test_tax_is_prorated_per_statement_not_on_the_total(client, app_db):
    """Different tax rates on the two statements settled by one payment.

    July is 13% HST on $100 base ($113 / $13). August is tax-free ($200).
    One prorata call against the $313 total would spread July's tax across
    August's untaxed fees — the entry's tax would come out wrong.
    """
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid, july_total=113.0,
                                   august_total=200.0, july_tax=13.0,
                                   august_tax=0.0)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 313.0,
        'allocations': [{'portion_id': july, 'amount': 113.0},
                        {'portion_id': august, 'amount': 200.0}],
    })
    entry_id = resp.get_json()['entry_id']

    assert _entry(app_db, entry_id)['tax_amount'] == 13.0

    rows = {r['portion_id']: r for r in app_db.get_payment_allocations(entry_id)}
    assert rows[july]['tax_amount'] == 13.0
    assert rows[august]['tax_amount'] == 0.0


def test_partial_lump_sum_pays_oldest_and_leaves_next_partial(client, app_db):
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 150.0,
        'allocations': [{'portion_id': july, 'amount': 100.0},
                        {'portion_id': august, 'amount': 50.0}],
    })

    assert _portion(app_db, july)['status'] == 'paid'
    august_row = _portion(app_db, august)
    assert august_row['status'] == 'partial'
    assert august_row['amount_paid'] == 50.0


def test_omitted_allocations_fall_back_to_oldest_first(client, app_db):
    """A single-statement payment is the degenerate case, not a second path."""
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 150.0,
    })
    entry_id = resp.get_json()['entry_id']

    rows = {r['portion_id']: r['amount']
            for r in app_db.get_payment_allocations(entry_id)}
    assert rows == {july: 100.0, august: 50.0}


def test_manual_override_can_ignore_oldest_first(client, app_db):
    """'This cheque is for August only' must be expressible."""
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 200.0,
        'allocations': [{'portion_id': august, 'amount': 200.0}],
    })
    entry_id = resp.get_json()['entry_id']

    assert _portion(app_db, july)['status'] == 'sent'
    assert _portion(app_db, july)['amount_paid'] == 0.0
    assert _portion(app_db, august)['status'] == 'paid'

    rows = app_db.get_payment_allocations(entry_id)
    assert [r['portion_id'] for r in rows] == [august]


# ---------------------------------------------------------------------------
# Overpayment and credit
# ---------------------------------------------------------------------------

def test_overpayment_becomes_credit_and_never_overfills_a_portion(client, app_db):
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 350.0,
    })
    data = resp.get_json()

    assert data['credit'] == 50.0
    assert app_db.get_client_credit(cid, None) == Decimal('50.00')
    # amount_paid must never exceed amount_due
    assert _portion(app_db, july)['amount_paid'] == 100.0
    assert _portion(app_db, august)['amount_paid'] == 200.0
    # and the deposit is still recorded whole
    assert _entry(app_db, data['entry_id'])['total_amount'] == 350.0
    assert app_db.get_allocated_total(data['entry_id']) == Decimal('350.00')


def test_prepayment_with_nothing_outstanding_is_all_credit(client, app_db):
    cid = _make_client(app_db)
    portion = _make_portion(app_db, _make_statement(app_db, cid, 100.0), cid,
                            100.0, status="paid", amount_paid=100.0)

    resp = client.post('/statements/record-payment', json={
        'portion_id': portion,
        'payment_amount': 80.0,
        'allocations': [],
    })
    data = resp.get_json()

    assert data['success'] is True
    assert data['credit'] == 80.0
    assert app_db.get_client_credit(cid, None) == Decimal('80.00')
    assert _entry(app_db, data['entry_id'])['statement_id'] is None


def test_credit_is_scoped_to_the_paying_guardian(client, app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)

    client.post('/statements/record-payment', json={
        'portion_id': g1,
        'payment_amount': 250.0,
    })

    assert app_db.get_client_credit(cid, 1) == Decimal('50.00')
    assert app_db.get_client_credit(cid, 2) == Decimal('0.00')


# ---------------------------------------------------------------------------
# Validation — nothing is written when the request is wrong
# ---------------------------------------------------------------------------

def test_allocation_cannot_exceed_a_statements_outstanding(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 300.0,
        'allocations': [{'portion_id': july, 'amount': 300.0}],
    })

    assert resp.status_code == 400
    assert _portion(app_db, july)['amount_paid'] == 0.0
    assert _income_count(app_db) == 0


def test_allocations_cannot_exceed_the_payment(client, app_db):
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 100.0,
        'allocations': [{'portion_id': july, 'amount': 100.0},
                        {'portion_id': august, 'amount': 50.0}],
    })

    assert resp.status_code == 400
    assert _income_count(app_db) == 0


def test_payment_cannot_cross_payers(client, app_db):
    """Guardian 1's money must never settle guardian 2's portion."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    g2 = _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)

    resp = client.post('/statements/record-payment', json={
        'portion_id': g1,
        'payment_amount': 100.0,
        'allocations': [{'portion_id': g2, 'amount': 100.0}],
    })

    assert resp.status_code == 400
    assert _portion(app_db, g2)['amount_paid'] == 0.0
    assert _income_count(app_db) == 0


def test_payment_cannot_cross_clients(client, app_db):
    cid_a = _make_client(app_db, "PA-001")
    cid_b = _make_client(app_db, "PA-002", "Other", "Client")
    a_portion = _make_portion(app_db, _make_statement(app_db, cid_a, 100.0),
                              cid_a, 100.0)
    b_portion = _make_portion(app_db, _make_statement(app_db, cid_b, 100.0),
                              cid_b, 100.0)

    resp = client.post('/statements/record-payment', json={
        'portion_id': a_portion,
        'payment_amount': 100.0,
        'allocations': [{'portion_id': b_portion, 'amount': 100.0}],
    })

    assert resp.status_code == 400
    assert _portion(app_db, b_portion)['amount_paid'] == 0.0


def test_unsent_statement_cannot_be_allocated_against(client, app_db):
    cid = _make_client(app_db)
    sent = _make_portion(app_db, _make_statement(app_db, cid, 100.0), cid, 100.0)
    ready = _make_portion(app_db, _make_statement(app_db, cid, 50.0), cid, 50.0,
                          status="ready")

    resp = client.post('/statements/record-payment', json={
        'portion_id': sent,
        'payment_amount': 50.0,
        'allocations': [{'portion_id': ready, 'amount': 50.0}],
    })

    assert resp.status_code == 400
    assert _portion(app_db, ready)['status'] == 'ready'


def test_negative_and_zero_payments_are_rejected(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    for amount in (0, -50.0):
        resp = client.post('/statements/record-payment', json={
            'portion_id': july, 'payment_amount': amount})
        assert resp.status_code == 400
    assert _income_count(app_db) == 0


def test_duplicate_allocation_for_one_statement_is_rejected(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 100.0,
        'allocations': [{'portion_id': july, 'amount': 50.0},
                        {'portion_id': july, 'amount': 50.0}],
    })

    assert resp.status_code == 400
    assert _income_count(app_db) == 0


# ---------------------------------------------------------------------------
# The ledger entry itself
# ---------------------------------------------------------------------------

def test_payment_date_is_recorded_as_the_ledger_date(client, app_db):
    from datetime import datetime

    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july,
        'payment_amount': 100.0,
        'payment_date': '2026-07-15',
        'allocations': [{'portion_id': july, 'amount': 100.0}],
    })
    entry = _entry(app_db, resp.get_json()['entry_id'])

    assert entry['ledger_date'] == int(datetime(2026, 7, 15).timestamp())


def test_payment_date_defaults_to_today(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)
    before = int(time.time())

    resp = client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 100.0})
    entry = _entry(app_db, resp.get_json()['entry_id'])

    assert before <= entry['ledger_date'] <= int(time.time())


def test_invalid_payment_date_is_rejected(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 100.0,
        'payment_date': 'not-a-date'})

    assert resp.status_code == 400
    assert _income_count(app_db) == 0


def test_entry_carries_the_first_statement_and_the_file_number(client, app_db):
    """statement_id stays populated so existing readers keep working."""
    cid = _make_client(app_db)
    july, august = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 300.0})
    entry = _entry(app_db, resp.get_json()['entry_id'])

    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT statement_entry_id FROM statement_portions WHERE id = ?",
                (july,))
    july_statement = cur.fetchone()[0]

    assert entry['statement_id'] == july_statement
    assert entry['source'] == 'PA-001'
    assert entry['description'] == 'Client Payment'


def test_guardian_payment_is_labelled_in_the_entry(client, app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 200.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)

    resp = client.post('/statements/record-payment', json={
        'portion_id': g1, 'payment_amount': 200.0})
    entry = _entry(app_db, resp.get_json()['entry_id'])

    assert entry['description'] == 'Client Payment (Guardian 1)'


def test_notes_are_stored_on_the_entry(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 100.0,
        'allocations': [{'portion_id': july, 'amount': 100.0}],
        'notes': 'e-transfer, ref 4471'})
    entry = _entry(app_db, resp.get_json()['entry_id'])

    assert entry['content'] == 'e-transfer, ref 4471'


def test_second_payment_closes_a_partial_statement(client, app_db):
    cid = _make_client(app_db)
    july, _ = _two_statements(app_db, cid)

    client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 40.0,
        'allocations': [{'portion_id': july, 'amount': 40.0}]})
    client.post('/statements/record-payment', json={
        'portion_id': july, 'payment_amount': 60.0,
        'allocations': [{'portion_id': july, 'amount': 60.0}]})

    assert _portion(app_db, july)['status'] == 'paid'
    assert _income_count(app_db) == 2
    assert len(app_db.get_portion_allocations(july)) == 2
