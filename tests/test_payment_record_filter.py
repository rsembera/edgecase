"""Payment Record filter: exactly this client's payments and refunds.

Phase 5 of docs/Payment_Allocation_Plan.md. SQL-level tests rather than
PDF inspection — what matters is which rows the per-client filter selects,
and a PDF assertion could only tell us the file was written.
"""
import time
from datetime import datetime


def _make_client(db, file_number="PR-001", first="Pay", last="Record"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _make_statement(db, client_id, total=100.0):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": "Statement",
        "statement_total": total,
        "statement_tax_total": 0.0,
        "created_at": now,
        "modified_at": now,
    })


def _make_portion(db, statement_entry_id, client_id, amount_due,
                  status="sent"):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, created_at
        ) VALUES (?, ?, NULL, ?, 0, ?, ?)
    """, (statement_entry_id, client_id, amount_due, status, int(time.time())))
    conn.commit()
    return cur.lastrowid


def _income_rows_for_client(db, client_id, file_number,
                            start_ts=0, end_ts=4_000_000_000):
    """The production income filter from pdf/ledger_report.py, verbatim."""
    stmt_subq = ("(SELECT id FROM entries WHERE class = 'statement' "
                 "AND client_id = ?)")
    alloc_subq = ("(SELECT entry_id FROM payment_allocations "
                  "WHERE client_id = ?)")
    conn = db.connect()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, total_amount FROM entries
        WHERE class = 'income' AND ledger_type = 'income'
        AND ledger_date >= ? AND ledger_date <= ?
        AND (source = ? OR statement_id IN {stmt_subq} OR id IN {alloc_subq})
        ORDER BY ledger_date
    """, (start_ts, end_ts, file_number, client_id, client_id))
    return cur.fetchall()


def _expense_rows_for_client(db, client_id, file_number,
                             start_ts=0, end_ts=4_000_000_000):
    """The production expense (refund) filter, verbatim."""
    stmt_subq = ("(SELECT id FROM entries WHERE class = 'statement' "
                 "AND client_id = ?)")
    conn = db.connect()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT e.id, e.total_amount
        FROM entries e
        LEFT JOIN payees p ON e.payee_id = p.id
        WHERE e.class = 'expense' AND e.ledger_type = 'expense'
        AND e.ledger_date >= ? AND e.ledger_date <= ?
        AND (e.statement_id IN {stmt_subq} OR p.name = ?)
        ORDER BY e.ledger_date
    """, (start_ts, end_ts, client_id, file_number))
    return cur.fetchall()


def test_lump_sum_appears_on_every_client_it_settled(client, app_db):
    """The case statement_id alone cannot express.

    One payment settling two statements carries statement_id for only the
    first. Before allocations, the second statement's record would have
    been missing the payment entirely.
    """
    cid = _make_client(app_db)
    first = _make_statement(app_db, cid)
    second = _make_statement(app_db, cid)
    p1 = _make_portion(app_db, first, cid, 100.0)
    p2 = _make_portion(app_db, second, cid, 200.0)

    resp = client.post("/statements/record-payment", json={
        "portion_id": p1, "payment_amount": 300.0,
        "allocations": [{"portion_id": p1, "amount": 100.0},
                        {"portion_id": p2, "amount": 200.0}],
    })
    entry_id = resp.get_json()["entry_id"]

    rows = _income_rows_for_client(app_db, cid, "PR-001")
    assert [r[0] for r in rows] == [entry_id]
    assert rows[0][1] == 300.0


def test_filter_excludes_another_clients_payment(client, app_db):
    mine = _make_client(app_db, "PR-001", "My", "Client")
    theirs = _make_client(app_db, "PR-002", "Their", "Client")
    my_portion = _make_portion(app_db, _make_statement(app_db, mine), mine, 100.0)
    their_portion = _make_portion(
        app_db, _make_statement(app_db, theirs), theirs, 100.0)

    mine_resp = client.post("/statements/record-payment", json={
        "portion_id": my_portion, "payment_amount": 100.0})
    client.post("/statements/record-payment", json={
        "portion_id": their_portion, "payment_amount": 100.0})

    rows = _income_rows_for_client(app_db, mine, "PR-001")
    assert [r[0] for r in rows] == [mine_resp.get_json()["entry_id"]]


def test_prepayment_with_no_statement_still_appears(client, app_db):
    """A pure credit has no statement_id — allocations are what find it."""
    cid = _make_client(app_db)
    portion = _make_portion(app_db, _make_statement(app_db, cid), cid, 100.0,
                            status="paid")

    resp = client.post("/statements/record-payment", json={
        "portion_id": portion, "payment_amount": 80.0, "allocations": []})
    entry_id = resp.get_json()["entry_id"]

    rows = _income_rows_for_client(app_db, cid, "PR-001")
    assert [r[0] for r in rows] == [entry_id]


def test_legacy_payment_still_matches_by_source(client, app_db):
    """Payments predating allocations are found the way they always were."""
    cid = _make_client(app_db)
    now = int(time.time())
    entry_id = app_db.add_entry({
        "client_id": None, "class": "income", "ledger_type": "income",
        "description": "Client Payment", "ledger_date": now,
        "source": "PR-001", "total_amount": 60.0, "tax_amount": 0.0,
        "created_at": now, "modified_at": now,
    })

    rows = _income_rows_for_client(app_db, cid, "PR-001")
    assert [r[0] for r in rows] == [entry_id]


def test_date_range_still_bounds_the_record(client, app_db):
    cid = _make_client(app_db)
    portion = _make_portion(app_db, _make_statement(app_db, cid), cid, 100.0)
    client.post("/statements/record-payment", json={
        "portion_id": portion, "payment_amount": 100.0,
        "payment_date": "2026-03-15"})

    in_range = _income_rows_for_client(
        app_db, cid, "PR-001",
        start_ts=int(datetime(2026, 3, 1).timestamp()),
        end_ts=int(datetime(2026, 3, 31, 23, 59, 59).timestamp()))
    out_of_range = _income_rows_for_client(
        app_db, cid, "PR-001",
        start_ts=int(datetime(2026, 4, 1).timestamp()),
        end_ts=int(datetime(2026, 4, 30, 23, 59, 59).timestamp()))

    assert len(in_range) == 1
    assert out_of_range == []


def test_hand_entered_refund_appears_on_the_record(client, app_db):
    """A cash refund is a manual Ledger expense payable to the file number.

    No statement_id, so the statement chain alone would miss it — the
    payee match is what puts it on the client's record.
    """
    cid = _make_client(app_db)
    now = int(time.time())
    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO payees (name, created_at) VALUES (?, ?)",
                ("PR-001", now))
    payee_id = cur.lastrowid
    cur.execute("INSERT INTO expense_categories (name, created_at) "
                "VALUES (?, ?)", ("Client Refund", now))
    category_id = cur.lastrowid
    conn.commit()

    entry_id = app_db.add_entry({
        "client_id": None, "class": "expense", "ledger_type": "expense",
        "description": "Client Refund", "ledger_date": now,
        "payee_id": payee_id, "category_id": category_id,
        "total_amount": 50.0, "tax_amount": 0.0,
        "created_at": now, "modified_at": now,
    })

    rows = _expense_rows_for_client(app_db, cid, "PR-001")
    assert [r[0] for r in rows] == [entry_id]


def test_business_expenses_stay_off_the_client_record(client, app_db):
    """Rent is not a refund, and must never appear on a client's record."""
    cid = _make_client(app_db)
    now = int(time.time())
    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO payees (name, created_at) VALUES (?, ?)",
                ("Landlord", now))
    payee_id = cur.lastrowid
    conn.commit()

    app_db.add_entry({
        "client_id": None, "class": "expense", "ledger_type": "expense",
        "description": "Office rent", "ledger_date": now,
        "payee_id": payee_id, "total_amount": 1200.0, "tax_amount": 0.0,
        "created_at": now, "modified_at": now,
    })

    assert _expense_rows_for_client(app_db, cid, "PR-001") == []
