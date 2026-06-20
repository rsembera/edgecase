"""Statements lifecycle route tests (database.py refactor Step 2, Target B).

Drives the billing seam through real routes: find-unbilled -> generate ->
mark-paid (full and partial). All DB-only — billable entries are set up directly
via the db fixture, and mark-sent is deliberately excluded here because it writes
a PDF into the attachments tree (filesystem side effects); it needs its own
harness with the attachment dir redirected.
"""
import time
from datetime import datetime

RANGE = {"start": "2026-06-01", "end": "2026-06-30"}


def _make_client(db):
    return db.add_client({
        "file_number": "ST-001",
        "first_name": "State",
        "middle_name": "",
        "last_name": "Ment",
        "type_id": 1,  # default "Active" type
    })


def _add_locked_session(db, client_id, fee=113.0, base=100.0, tax=13.0,
                        date=(2026, 6, 10)):
    """A locked, billable session (fee > 0) on the given date — the shape
    find-unbilled / generate look for."""
    now = int(time.time())
    session_id = db.add_entry({
        "client_id": client_id,
        "class": "session",
        "description": "Session 1",
        "session_number": 1,
        "session_date": int(datetime(*date).timestamp()),
        "base_fee": base,
        "tax_rate": tax,
        "fee": fee,
        "is_consultation": 0,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(session_id)
    return session_id


def _portions(db, client_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, status, amount_due, amount_paid, write_off_reason "
        "FROM statement_portions WHERE client_id = ?",
        (client_id,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _count_class(db, cls):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entries WHERE class = ?", (cls,))
    return cur.fetchone()[0]


def _generate(client, cid):
    return client.post(
        "/statements/generate",
        json={"client_ids": [cid], "start_date": RANGE["start"],
              "end_date": RANGE["end"]},
    )


def test_find_unbilled_lists_locked_billable_session(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)

    resp = client.get("/statements/find-unbilled", query_string=RANGE)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    listed = {c["id"]: c for c in payload["clients"]}
    assert cid in listed
    assert listed[cid]["unbilled_total"] > 0
    assert len(listed[cid]["entries"]) == 1


def test_generate_creates_portion_and_bills_the_session(client, app_db):
    cid = _make_client(app_db)
    sid = _add_locked_session(app_db, cid)

    resp = _generate(client, cid)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["count"] == 1
    assert payload["portion_count"] == 1

    portions = _portions(app_db, cid)
    assert len(portions) == 1
    assert portions[0]["status"] == "ready"
    assert portions[0]["amount_due"] > 0

    # The session is now linked to the statement (no longer unbilled).
    assert app_db.get_entry(sid)["statement_id"] is not None


def test_mark_paid_full_settles_portion_and_records_income(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    resp = client.post(
        "/statements/mark-paid",
        json={"portion_id": portion["id"],
              "payment_amount": portion["amount_due"],
              "payment_type": "full"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["new_status"] == "paid"
    assert payload["amount_owing"] == 0

    assert _portions(app_db, cid)[0]["status"] == "paid"
    # Payment recorded an income ledger entry (statements -> ledger seam).
    assert _count_class(app_db, "income") == 1


def test_mark_paid_partial_leaves_balance(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    half = round(portion["amount_due"] / 2, 2)
    resp = client.post(
        "/statements/mark-paid",
        json={"portion_id": portion["id"], "payment_amount": half,
              "payment_type": "partial"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["new_status"] != "paid"
    assert payload["amount_owing"] > 0


def test_write_off_waived_marks_portion_written_off(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    resp = client.post(
        "/statements/write-off",
        json={"portion_id": portion["id"], "reason": "waived",
              "note": "Goodwill"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    after = _portions(app_db, cid)[0]
    assert after["status"] == "written_off"
    assert after["write_off_reason"] == "waived"


def test_write_off_uncollectible_records_bad_debt_expense(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    resp = client.post(
        "/statements/write-off",
        json={"portion_id": portion["id"], "reason": "uncollectible"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    assert _portions(app_db, cid)[0]["status"] == "written_off"
    # Uncollectible write-off books a Bad Debt expense (statements -> ledger).
    assert _count_class(app_db, "expense") == 1


def test_write_off_billing_error_unlinks_entry_for_rebilling(client, app_db):
    cid = _make_client(app_db)
    sid = _add_locked_session(app_db, cid)
    _generate(client, cid)
    # After generating, the session is billed.
    assert app_db.get_entry(sid)["statement_id"] is not None

    portion = _portions(app_db, cid)[0]
    resp = client.post(
        "/statements/write-off",
        json={"portion_id": portion["id"], "reason": "billing_error"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    assert _portions(app_db, cid)[0]["status"] == "written_off"
    # Billing-error write-off unlinks the entry so it can be edited and re-billed.
    assert app_db.get_entry(sid)["statement_id"] is None
