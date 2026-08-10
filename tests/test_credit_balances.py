"""Credit balances: held on overpayment, spent on the next statement.

Phase 4 of docs/Payment_Allocation_Plan.md. The decision taken was to
auto-apply, by symmetry with carry-forward: prior debits are already
pulled onto the next statement without asking, and making credits wait
for the practitioner to remember them is asymmetric in the practitioner's
favour — the wrong direction on a clinical bill.
"""
import time
from datetime import datetime
from decimal import Decimal

RANGE = {"start_date": "2026-06-01", "end_date": "2026-06-30"}
JULY = {"start_date": "2026-07-01", "end_date": "2026-07-31"}


def _make_client(db, file_number="CB-001", first="Cree", last="Ditt"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _add_locked_session(db, client_id, fee=100.0, base=100.0, tax=0.0,
                        date=(2026, 6, 10)):
    now = int(time.time())
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "session",
        "description": "Session",
        "session_date": int(datetime(*date).timestamp()),
        "base_fee": base,
        "tax_rate": tax,
        "fee": fee,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(entry_id)
    return entry_id


def _portions(db, client_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id, statement_entry_id, guardian_number, amount_due, "
                "amount_paid, status FROM statement_portions "
                "WHERE client_id = ? ORDER BY id", (client_id,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _mark_sent(db, portion_id):
    conn = db.connect()
    conn.execute("UPDATE statement_portions SET status = 'sent' WHERE id = ?",
                 (portion_id,))
    conn.commit()


def _generate(client, cid, dates=RANGE):
    return client.post("/statements/generate",
                       json={"client_ids": [cid], **dates})


def _overpay(client, db, cid, session_fee, payment):
    """Bill a session, send it, and pay more than it asks for."""
    _add_locked_session(db, cid, fee=session_fee, base=session_fee)
    _generate(client, cid)
    portion = _portions(db, cid)[0]
    _mark_sent(db, portion["id"])
    client.post("/statements/record-payment",
                json={"portion_id": portion["id"], "payment_amount": payment})
    return portion


# ---------------------------------------------------------------------------
# Credit is created, and survives until something spends it
# ---------------------------------------------------------------------------

def test_overpayment_leaves_credit_on_the_account(client, app_db):
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    assert app_db.get_client_credit(cid, None) == Decimal('50.00')


def test_credit_is_spent_by_the_next_statement(client, app_db):
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)

    july = _portions(app_db, cid)[-1]
    assert july["amount_due"] == 100.0
    assert july["amount_paid"] == 50.0        # credit applied
    assert app_db.get_credit_applied(july["id"]) == Decimal('50.00')
    assert app_db.get_client_credit(cid, None) == Decimal('0.00')


def test_credit_larger_than_the_statement_leaves_a_remainder(client, app_db):
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=250.0)  # $150 credit

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)

    july = _portions(app_db, cid)[-1]
    assert july["amount_paid"] == 100.0
    # amount_paid never exceeds amount_due; the rest stays on account
    assert july["amount_paid"] <= july["amount_due"]
    assert app_db.get_client_credit(cid, None) == Decimal('50.00')


def test_credit_cannot_be_spent_twice_in_one_batch(client, app_db):
    """Two clients, one credit — and the same client billed twice over.

    Generation consumes inside its own transaction, so a second statement
    in the same run reads a balance that already reflects the first.
    """
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=180.0)  # $80 credit

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)
    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 8, 8))
    _generate(client, cid, {"start_date": "2026-08-01", "end_date": "2026-08-31"})

    portions = _portions(app_db, cid)
    july, august = portions[-2], portions[-1]
    assert july["amount_paid"] == 80.0
    assert august["amount_paid"] == 0.0
    assert app_db.get_client_credit(cid, None) == Decimal('0.00')


def test_no_credit_means_nothing_changes(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid, fee=100.0, base=100.0)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    assert portion["amount_paid"] == 0.0
    assert app_db.get_credit_applied(portion["id"]) == Decimal('0.00')


# ---------------------------------------------------------------------------
# Scoping — a credit belongs to one payer
# ---------------------------------------------------------------------------

def test_credit_does_not_cross_clients(client, app_db):
    payer = _make_client(app_db, "CB-001", "Over", "Payer")
    other = _make_client(app_db, "CB-002", "Some", "Oneelse")
    _overpay(client, app_db, payer, session_fee=100.0, payment=150.0)

    _add_locked_session(app_db, other, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, other, JULY)

    assert _portions(app_db, other)[0]["amount_paid"] == 0.0
    assert app_db.get_client_credit(payer, None) == Decimal('50.00')


# ---------------------------------------------------------------------------
# Lifecycle after the credit lands
# ---------------------------------------------------------------------------

def test_partly_credited_statement_still_owes_the_rest(client, app_db):
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)
    july = _portions(app_db, cid)[-1]
    _mark_sent(app_db, july["id"])

    data = client.get('/statements/payment-proposal',
                      query_string={'portion_id': july["id"]}).get_json()

    assert data['total_owing'] == 50.0
    assert data['portions'][0]['amount_owing'] == 50.0


def test_credited_statement_is_still_ready_to_send(client, app_db):
    """Credit settles the money, not the obligation to issue the document."""
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=250.0)  # $150 credit

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)

    july = _portions(app_db, cid)[-1]
    assert july["status"] == 'ready'
    assert july["amount_paid"] == 100.0


def test_paying_a_credited_statement_settles_only_the_remainder(client, app_db):
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)
    july = _portions(app_db, cid)[-1]
    _mark_sent(app_db, july["id"])

    resp = client.post("/statements/record-payment",
                       json={"portion_id": july["id"], "payment_amount": 50.0})

    assert resp.get_json()["success"] is True
    assert _portions(app_db, cid)[-1]["status"] == 'paid'


def test_overpaying_a_credited_statement_is_rejected(client, app_db):
    """The credit already reduced what's owed; $100 no longer fits."""
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)
    july = _portions(app_db, cid)[-1]
    _mark_sent(app_db, july["id"])

    resp = client.post("/statements/record-payment",
                       json={"portion_id": july["id"],
                             "payment_amount": 100.0,
                             "allocations": [{"portion_id": july["id"],
                                              "amount": 100.0}]})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# The originating ledger entry is never rewritten
# ---------------------------------------------------------------------------

def test_consuming_credit_does_not_alter_the_original_payment(client, app_db):
    """The deposit was recorded when it arrived; that figure stands.

    Rewriting it to reflect where the money later landed would change a
    number that may already have been reported.
    """
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id, total_amount, tax_amount, ledger_date "
                "FROM entries WHERE class = 'income'")
    before = cur.fetchall()

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)

    cur.execute("SELECT id, total_amount, tax_amount, ledger_date "
                "FROM entries WHERE class = 'income'")
    assert cur.fetchall() == before


def test_allocation_rows_still_sum_to_the_entry_after_consumption(client, app_db):
    """The invariant survives credit being spent: nothing is created or lost."""
    cid = _make_client(app_db)
    _overpay(client, app_db, cid, session_fee=100.0, payment=150.0)

    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM entries WHERE class = 'income'")
    entry_id = cur.fetchone()[0]

    _add_locked_session(app_db, cid, fee=100.0, base=100.0, date=(2026, 7, 8))
    _generate(client, cid, JULY)

    assert app_db.get_allocated_total(entry_id) == Decimal('150.00')
