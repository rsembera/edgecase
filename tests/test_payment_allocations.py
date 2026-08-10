"""Payment allocation data layer (docs/Payment_Allocation_Plan.md, Phase 1).

Covers the table's scoping rules, the credit representation, and the
backfill. Payment RECORDING (record_payment) is exercised separately once
the route lands — these tests are pure data layer.
"""
import time
from decimal import Decimal


def _make_client(db, file_number="AL-001", first="Alice", last="Locate"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _make_statement(db, client_id, total, tax=0.0, description="Statement",
                    created_at=None):
    """A statement entry with its own total/tax, as generate_statements writes.

    add_entry always stamps created_at with the current time, so an explicit
    created_at is applied afterwards — the allocation order is oldest
    STATEMENT first, and same-second ties would otherwise hide a regression.
    """
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


def _make_income(db, total, tax=0.0, statement_id=None,
                 description="Client Payment", source="AL-001"):
    now = int(time.time())
    return db.add_entry({
        "client_id": None,
        "class": "income",
        "ledger_type": "income",
        "description": description,
        "ledger_date": now,
        "source": source,
        "total_amount": total,
        "tax_amount": tax,
        "statement_id": statement_id,
        "created_at": now,
        "modified_at": now,
    })


def _alloc(db, entry_id, portion_id, client_id, guardian_number, amount,
           tax_amount=None):
    """Write one allocation row through the production helper."""
    conn = db.connect()
    cur = conn.cursor()
    row_id = db.insert_allocation(cur, entry_id, portion_id, client_id,
                                  guardian_number, amount, tax_amount,
                                  int(time.time()))
    conn.commit()
    return row_id


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_payment_allocations_table_exists(app_db):
    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='payment_allocations'")
    assert cur.fetchone() is not None


def test_allocation_indexes_exist(app_db):
    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    names = {row[0] for row in cur.fetchall()}
    assert {'idx_alloc_entry', 'idx_alloc_portion', 'idx_alloc_credit'} <= names


# ---------------------------------------------------------------------------
# get_client_outstanding_portions — the allocation set
# ---------------------------------------------------------------------------

def test_outstanding_portions_oldest_statement_first(app_db):
    cid = _make_client(app_db)
    older = _make_statement(app_db, cid, 100.0, created_at=1_700_000_000)
    newer = _make_statement(app_db, cid, 200.0, created_at=1_800_000_000)
    # Insert the NEWER portion first so ordering cannot pass by accident
    _make_portion(app_db, newer, cid, 200.0)
    _make_portion(app_db, older, cid, 100.0)

    portions = app_db.get_client_outstanding_portions(cid, None)
    assert [p['amount_due'] for p in portions] == [100.0, 200.0]


def test_outstanding_portions_excludes_ready_paid_and_written_off(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    _make_portion(app_db, stmt, cid, 100.0, status="ready")
    _make_portion(app_db, stmt, cid, 100.0, status="paid")
    _make_portion(app_db, stmt, cid, 100.0, status="written_off")
    kept = _make_portion(app_db, stmt, cid, 100.0, status="sent")

    portions = app_db.get_client_outstanding_portions(cid, None)
    assert [p['id'] for p in portions] == [kept]


def test_outstanding_portions_includes_partial_with_owing(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    _make_portion(app_db, stmt, cid, 100.0, status="partial", amount_paid=40.0)

    portions = app_db.get_client_outstanding_portions(cid, None)
    assert len(portions) == 1
    assert portions[0]['amount_owing'] == Decimal('60.00')


def test_outstanding_portions_scoped_to_guardian(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    g2 = _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)

    assert [p['id'] for p in app_db.get_client_outstanding_portions(cid, 1)] == [g1]
    assert [p['id'] for p in app_db.get_client_outstanding_portions(cid, 2)] == [g2]
    assert app_db.get_client_outstanding_portions(cid, None) == []


def test_outstanding_portions_scoped_to_client(app_db):
    cid_a = _make_client(app_db, "AL-001")
    cid_b = _make_client(app_db, "AL-002", "Bob", "Other")
    stmt_a = _make_statement(app_db, cid_a, 100.0)
    stmt_b = _make_statement(app_db, cid_b, 100.0)
    p_a = _make_portion(app_db, stmt_a, cid_a, 100.0)
    _make_portion(app_db, stmt_b, cid_b, 100.0)

    assert [p['id'] for p in app_db.get_client_outstanding_portions(cid_a, None)] == [p_a]


def test_outstanding_portions_carry_statement_totals_for_prorata_tax(app_db):
    """Per-allocation tax needs each statement's OWN total and tax."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 113.0, tax=13.0)
    _make_portion(app_db, stmt, cid, 113.0)

    portion = app_db.get_client_outstanding_portions(cid, None)[0]
    assert portion['statement_total'] == 113.0
    assert portion['statement_tax_total'] == 13.0


# ---------------------------------------------------------------------------
# Allocation rows and the sum invariant
# ---------------------------------------------------------------------------

def test_allocations_sum_to_entry_total(app_db):
    """One $300 payment across two statements: SUM(rows) == total_amount."""
    cid = _make_client(app_db)
    july = _make_statement(app_db, cid, 100.0, created_at=1_700_000_000)
    august = _make_statement(app_db, cid, 200.0, created_at=1_800_000_000)
    p_july = _make_portion(app_db, july, cid, 100.0)
    p_august = _make_portion(app_db, august, cid, 200.0)

    entry = _make_income(app_db, 300.0)
    _alloc(app_db, entry, p_july, cid, None, 100.0)
    _alloc(app_db, entry, p_august, cid, None, 200.0)

    assert app_db.get_allocated_total(entry) == Decimal('300.00')
    assert len(app_db.get_payment_allocations(entry)) == 2


def test_credit_row_completes_the_sum_on_overpayment(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    portion = _make_portion(app_db, stmt, cid, 300.0)

    entry = _make_income(app_db, 350.0)
    _alloc(app_db, entry, portion, cid, None, 300.0)
    _alloc(app_db, entry, None, cid, None, 50.0)

    assert app_db.get_allocated_total(entry) == Decimal('350.00')
    assert app_db.get_client_credit(cid, None) == Decimal('50.00')


def test_portion_allocations_lists_every_payment_against_it(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    portion = _make_portion(app_db, stmt, cid, 100.0)

    first = _make_income(app_db, 40.0)
    second = _make_income(app_db, 60.0)
    _alloc(app_db, first, portion, cid, None, 40.0)
    _alloc(app_db, second, portion, cid, None, 60.0)

    rows = app_db.get_portion_allocations(portion)
    assert [r['amount'] for r in rows] == [40.0, 60.0]


# ---------------------------------------------------------------------------
# Credit scoping
# ---------------------------------------------------------------------------

def test_credit_scoped_to_guardian(app_db):
    """Guardian 1's overpayment must not be spendable by guardian 2."""
    cid = _make_client(app_db)
    entry = _make_income(app_db, 50.0)
    _alloc(app_db, entry, None, cid, 1, 50.0)

    assert app_db.get_client_credit(cid, 1) == Decimal('50.00')
    assert app_db.get_client_credit(cid, 2) == Decimal('0.00')
    assert app_db.get_client_credit(cid, None) == Decimal('0.00')


def test_credit_scoped_to_client(app_db):
    cid_a = _make_client(app_db, "AL-001")
    cid_b = _make_client(app_db, "AL-002", "Bob", "Other")
    entry = _make_income(app_db, 50.0)
    _alloc(app_db, entry, None, cid_a, None, 50.0)

    assert app_db.get_client_credit(cid_a, None) == Decimal('50.00')
    assert app_db.get_client_credit(cid_b, None) == Decimal('0.00')


def test_credit_all_payers_sums_guardian_scopes(app_db):
    cid = _make_client(app_db)
    entry = _make_income(app_db, 80.0)
    _alloc(app_db, entry, None, cid, 1, 50.0)
    _alloc(app_db, entry, None, cid, 2, 30.0)

    assert app_db.get_client_credit_all_payers(cid) == Decimal('80.00')


def test_allocated_payment_creates_no_credit(app_db):
    """A fully allocated payment leaves nothing on account."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    portion = _make_portion(app_db, stmt, cid, 100.0)
    entry = _make_income(app_db, 100.0)
    _alloc(app_db, entry, portion, cid, None, 100.0)

    assert app_db.get_client_credit(cid, None) == Decimal('0.00')


def test_legacy_entry_without_rows_is_not_credit(app_db):
    """Credit is read from explicit NULL-portion rows, never inferred.

    An entry with no allocation rows at all (legacy, or skipped by the
    backfill) must read as zero credit — inferring credit from
    total_amount minus allocations would invent money here.
    """
    cid = _make_client(app_db)
    _make_income(app_db, 500.0)

    assert app_db.get_client_credit(cid, None) == Decimal('0.00')
    assert app_db.get_client_credit_all_payers(cid) == Decimal('0.00')


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def test_backfill_allocates_legacy_single_portion_payment(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 113.0, tax=13.0)
    portion = _make_portion(app_db, stmt, cid, 113.0, status="paid",
                            amount_paid=113.0)
    entry = _make_income(app_db, 113.0, tax=13.0, statement_id=stmt)

    result = app_db.backfill_payment_allocations()

    assert result['created'] == 1
    rows = app_db.get_payment_allocations(entry)
    assert len(rows) == 1
    assert rows[0]['portion_id'] == portion
    assert rows[0]['amount'] == 113.0
    assert rows[0]['tax_amount'] == 13.0
    assert rows[0]['client_id'] == cid


def test_backfill_is_idempotent(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 100.0)
    _make_portion(app_db, stmt, cid, 100.0, status="paid", amount_paid=100.0)
    entry = _make_income(app_db, 100.0, statement_id=stmt)

    first = app_db.backfill_payment_allocations()
    second = app_db.backfill_payment_allocations()

    assert first['created'] == 1
    assert second['created'] == 0
    assert len(app_db.get_payment_allocations(entry)) == 1


def test_backfill_resolves_guardian_from_description(app_db):
    """A split statement has two portions; the old description names one."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    g1 = _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    g2 = _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)
    entry = _make_income(app_db, 100.0, statement_id=stmt,
                         description="Client Payment (Guardian 2)")

    app_db.backfill_payment_allocations()

    rows = app_db.get_payment_allocations(entry)
    assert len(rows) == 1
    assert rows[0]['portion_id'] == g2
    assert rows[0]['guardian_number'] == 2


def test_backfill_skips_ambiguous_split_rather_than_guessing(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    _make_portion(app_db, stmt, cid, 200.0, guardian_number=1)
    _make_portion(app_db, stmt, cid, 100.0, guardian_number=2)
    entry = _make_income(app_db, 100.0, statement_id=stmt,
                         description="Client Payment")

    result = app_db.backfill_payment_allocations()

    assert result['created'] == 0
    assert result['skipped_ambiguous'] == 1
    assert app_db.get_payment_allocations(entry) == []
    # And the skip must not read as money on account
    assert app_db.get_client_credit(cid, None) == Decimal('0.00')


def test_backfill_ignores_income_without_a_statement(app_db):
    """Non-statement income (workshop fees, etc.) is not a client payment."""
    _make_client(app_db)
    entry = _make_income(app_db, 500.0, description="Workshop fee")

    result = app_db.backfill_payment_allocations()

    assert result['created'] == 0
    assert app_db.get_payment_allocations(entry) == []


def test_backfill_leaves_hand_written_allocations_alone(app_db):
    """An entry already carrying rows is never touched."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, 300.0)
    portion = _make_portion(app_db, stmt, cid, 300.0)
    entry = _make_income(app_db, 350.0, statement_id=stmt)
    _alloc(app_db, entry, portion, cid, None, 300.0)
    _alloc(app_db, entry, None, cid, None, 50.0)

    result = app_db.backfill_payment_allocations()

    assert result['created'] == 0
    assert len(app_db.get_payment_allocations(entry)) == 2
    assert app_db.get_allocated_total(entry) == Decimal('350.00')
