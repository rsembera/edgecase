"""Bill Now — on-demand statement from an entry, and the statement PDF as
receipt once paid.

Bill Now must go through the same generator as the month-end run, bill
everything the client owes up to the entry's date (nothing stranded), and
record nothing about payment. A paid portion's PDF must carry the client
report's paid-in-full sentence and drop the payment instructions; an unpaid
one must not. Paid portions must remain reachable on the Statements page.
"""

import time
from datetime import datetime

from pypdf import PdfReader

from pdf.generator import generate_statement_pdf

PAID_LINE = "All fees for the services listed above have been paid in full."


def _make_client(db, file_number="BN-001"):
    return db.add_client({
        "file_number": file_number, "first_name": "Bill", "middle_name": "",
        "last_name": "Now", "type_id": 1,
    })


def _add_entry(db, client_id, cls, date, fee=113.0, base=100.0, tax=13.0,
               lock=True):
    now = int(time.time())
    date_field = {"session": "session_date", "absence": "absence_date",
                  "item": "item_date"}[cls]
    data = {
        "client_id": client_id, "class": cls, "description": f"{cls} entry",
        date_field: int(datetime(*date).timestamp()),
        "tax_rate": tax, "fee": fee, "created_at": now, "modified_at": now,
    }
    if cls == "session":
        data.update({"base_fee": base, "session_number": 1,
                     "is_consultation": 0})
    elif cls == "absence":
        data["base_fee"] = base
    else:
        data["base_price"] = base
    eid = db.add_entry(data)
    if lock:
        db.lock_entry(eid)
    return eid


def _portions(db, client_id):
    cur = db.connect().cursor()
    cur.execute("SELECT id, statement_entry_id, status, amount_due, amount_paid "
                "FROM statement_portions WHERE client_id = ?", (client_id,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _pdf_text(path):
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


# --- preview + generate -------------------------------------------------

def test_bill_now_bills_single_locked_session(client, app_db):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))

    prev = client.get(f"/statements/bill-now/preview/{sid}").get_json()
    assert prev["success"] and len(prev["entries"]) == 1
    assert prev["total"] == 113.0

    resp = client.post(f"/statements/bill-now/{sid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] and data["entry_count"] == 1 and data["total"] == 113.0

    assert app_db.get_entry(sid)["statement_id"] == data["statement_id"]
    portions = _portions(app_db, cid)
    assert len(portions) == 1
    assert portions[0]["status"] == "ready"      # NOT paid — Record Payment's job
    assert portions[0]["amount_due"] == 113.0
    assert portions[0]["amount_paid"] == 0


def test_bill_now_sweeps_earlier_unbilled_entries_not_later_ones(client, app_db):
    """Everything the client owes as of this entry: an older unbilled
    absence and item come along (nothing stranded); a later session does
    not (not owed yet)."""
    cid = _make_client(app_db)
    older_abs = _add_entry(app_db, cid, "absence", (2026, 9, 1), fee=50, base=50, tax=0)
    older_item = _add_entry(app_db, cid, "item", (2026, 9, 5), fee=20, base=20, tax=0)
    target = _add_entry(app_db, cid, "session", (2026, 9, 12))
    later = _add_entry(app_db, cid, "session", (2026, 9, 19))

    prev = client.get(f"/statements/bill-now/preview/{target}").get_json()
    assert {e["id"] for e in prev["entries"]} == {older_abs, older_item, target}
    assert prev["total"] == 183.0

    data = client.post(f"/statements/bill-now/{target}").get_json()
    assert data["success"] and data["entry_count"] == 3
    sid = data["statement_id"]
    for eid in (older_abs, older_item, target):
        assert app_db.get_entry(eid)["statement_id"] == sid
    assert app_db.get_entry(later)["statement_id"] is None


def test_bill_now_refuses_billed_unlocked_and_zero_fee(client, app_db):
    cid = _make_client(app_db)
    unlocked = _add_entry(app_db, cid, "session", (2026, 9, 12), lock=False)
    free = _add_entry(app_db, cid, "session", (2026, 9, 12), fee=0, base=0)
    billed = _add_entry(app_db, cid, "session", (2026, 9, 12))
    assert client.post(f"/statements/bill-now/{billed}").get_json()["success"]

    for eid in (unlocked, free, billed):
        assert client.get(f"/statements/bill-now/preview/{eid}").status_code == 400
        assert client.post(f"/statements/bill-now/{eid}").status_code == 400
    assert client.post("/statements/bill-now/999999").status_code == 404
    assert app_db.get_entry(unlocked)["statement_id"] is None
    assert app_db.get_entry(free)["statement_id"] is None


def test_bill_now_leaves_nothing_for_month_end_run(client, app_db):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))
    assert client.post(f"/statements/bill-now/{sid}").get_json()["success"]

    resp = client.get("/statements/find-unbilled?start=2026-09-01&end=2026-09-30")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert all(c["client_id"] != cid for c in payload.get("clients", []))


def test_bill_now_rolls_back_a_net_negative_period(client, app_db):
    """A credit item larger than the charges: same rule as month end — no
    statement, entries stay unbilled, and the transaction is rolled back
    rather than half-written."""
    cid = _make_client(app_db)
    _add_entry(app_db, cid, "item", (2026, 9, 1), fee=-500, base=-500, tax=0)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))

    resp = client.post(f"/statements/bill-now/{sid}")
    assert resp.status_code == 400
    assert "carries forward" in resp.get_json()["error"]
    assert _portions(app_db, cid) == []
    assert app_db.get_entry(sid)["statement_id"] is None


# --- the PDF as receipt ---------------------------------------------------

def test_statement_pdf_paid_in_full_line_only_when_paid(client, app_db, tmp_path):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))
    assert client.post(f"/statements/bill-now/{sid}").get_json()["success"]
    portion = _portions(app_db, cid)[0]

    # Unpaid: a statement. No paid-in-full line.
    out = tmp_path / "unpaid.pdf"
    assert generate_statement_pdf(app_db, portion["id"], str(out), str(tmp_path))
    unpaid_text = _pdf_text(out)
    assert PAID_LINE not in unpaid_text

    # Sent, then paid in full through the real route.
    conn = app_db.connect()
    conn.execute("UPDATE statement_portions SET status = 'sent' WHERE id = ?",
                 (portion["id"],))
    conn.commit()
    resp = client.post("/statements/record-payment",
                       json={"portion_id": portion["id"],
                             "payment_amount": portion["amount_due"]})
    assert resp.get_json()["allocations"][0]["status"] == "paid"

    # Same portion, re-rendered: the receipt.
    out2 = tmp_path / "paid.pdf"
    assert generate_statement_pdf(app_db, portion["id"], str(out2), str(tmp_path))
    paid_text = _pdf_text(out2)
    assert PAID_LINE in paid_text


def test_statement_pdf_partial_and_written_off_are_not_receipts(client, app_db, tmp_path):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))
    assert client.post(f"/statements/bill-now/{sid}").get_json()["success"]
    portion = _portions(app_db, cid)[0]
    conn = app_db.connect()

    for status in ("partial", "written_off"):
        conn.execute("UPDATE statement_portions SET status = ? WHERE id = ?",
                     (status, portion["id"]))
        conn.commit()
        out = tmp_path / f"{status}.pdf"
        assert generate_statement_pdf(app_db, portion["id"], str(out), str(tmp_path))
        assert PAID_LINE not in _pdf_text(out), status


# --- Statements page keeps paid portions reachable ------------------------

def test_outstanding_page_lists_paid_portion_with_receipt_action(client, app_db):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))
    data = client.post(f"/statements/bill-now/{sid}").get_json()
    portion = _portions(app_db, cid)[0]
    conn = app_db.connect()
    conn.execute("UPDATE statement_portions SET status = 'paid', amount_paid = amount_due "
                 "WHERE id = ?", (portion["id"],))
    conn.commit()

    html = client.get("/statements/").data.decode()
    assert f'data-statement="{data["statement_id"]}"' in html
    assert 'data-status="paid"' in html
    assert f"viewReceipt({portion['id']})" in html
    # Paid rows never get the send / pay / write-off actions.
    assert f"showPaymentForm({portion['id']})" not in html
    assert f"markSent({portion['id']})" not in html


# --- the button itself ----------------------------------------------------

def test_bill_now_button_shown_only_on_billable_locked_entries(client, app_db):
    cid = _make_client(app_db)
    billable = _add_entry(app_db, cid, "session", (2026, 9, 12))
    html = client.get(f"/client/{cid}/session/{billable}").data.decode()
    assert 'id="bill-now-btn"' in html and f'data-entry-id="{billable}"' in html

    absence = _add_entry(app_db, cid, "absence", (2026, 9, 12))
    assert 'id="bill-now-btn"' in client.get(
        f"/client/{cid}/absence/{absence}").data.decode()
    item = _add_entry(app_db, cid, "item", (2026, 9, 12))
    assert 'id="bill-now-btn"' in client.get(
        f"/client/{cid}/item/{item}").data.decode()

    # Billed: gone.
    assert client.post(f"/statements/bill-now/{billable}").get_json()["success"]
    assert 'id="bill-now-btn"' not in client.get(
        f"/client/{cid}/session/{billable}").data.decode()
    # Zero fee (consultation / pro bono shape): never shown.
    free = _add_entry(app_db, cid, "session", (2026, 9, 13), fee=0, base=0)
    assert 'id="bill-now-btn"' not in client.get(
        f"/client/{cid}/session/{free}").data.decode()
    # New entry form: nothing to bill yet.
    assert 'id="bill-now-btn"' not in client.get(f"/client/{cid}/session").data.decode()


# --- "Paid now": the pay-at-desk shortcut ---------------------------------

def _count_class(db, cls):
    cur = db.connect().cursor()
    cur.execute("SELECT COUNT(*) FROM entries WHERE class = ?", (cls,))
    return cur.fetchone()[0]


def test_bill_now_paid_now_settles_and_records_income(client, app_db, tmp_path):
    """One transaction: statement generated, marked sent (handed over),
    full payment recorded through the same write path as Record Payment —
    income entry with the note, allocation row, portion paid — and the
    PDF is immediately the receipt."""
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))

    resp = client.post(f"/statements/bill-now/{sid}",
                       json={"paid_now": True, "note": "e-transfer"})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] and data["payment"]["status"] == "paid"

    portion = _portions(app_db, cid)[0]
    assert portion["status"] == "paid"
    assert portion["amount_paid"] == portion["amount_due"] == 113.0

    assert _count_class(app_db, "income") == 1
    income = app_db.get_entry(data["payment"]["income_entry_id"])
    assert income["class"] == "income"
    assert income["total_amount"] == 113.0
    assert income["tax_amount"] == 13.0
    assert income["content"] == "e-transfer"
    assert income["statement_id"] == data["statement_id"]

    cur = app_db.connect().cursor()
    cur.execute("SELECT amount FROM payment_allocations WHERE portion_id = ?",
                (portion["id"],))
    assert [r[0] for r in cur.fetchall()] == [113.0]
    cur.execute("SELECT date_sent FROM statement_portions WHERE id = ?",
                (portion["id"],))
    assert cur.fetchone()[0] is not None

    out = tmp_path / "receipt.pdf"
    assert generate_statement_pdf(app_db, portion["id"], str(out), str(tmp_path))
    assert PAID_LINE in _pdf_text(out)


def test_bill_now_without_paid_now_records_no_money(client, app_db):
    cid = _make_client(app_db)
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))
    data = client.post(f"/statements/bill-now/{sid}",
                       json={"paid_now": False, "note": "ignored"}).get_json()
    assert data["success"] and data["payment"] is None
    assert _portions(app_db, cid)[0]["status"] == "ready"
    assert _count_class(app_db, "income") == 0


def test_bill_now_paid_now_refused_for_guardian_split_and_rolls_back(client, app_db):
    """Two payers means two payments; the shortcut cannot know who paid.
    Refused, and nothing is generated — the entries stay unbilled."""
    cid = _make_client(app_db)
    now = int(time.time())
    pid = app_db.add_entry({"client_id": cid, "class": "profile",
                            "description": "Profile", "content": "",
                            "created_at": now, "modified_at": now})
    app_db.update_entry(pid, {
        "is_minor": 1, "guardian1_name": "G One", "has_guardian2": 1,
        "guardian2_name": "G Two", "guardian1_pays_percent": 50,
        "guardian2_pays_percent": 50})
    sid = _add_entry(app_db, cid, "session", (2026, 9, 12))

    resp = client.post(f"/statements/bill-now/{sid}", json={"paid_now": True})
    assert resp.status_code == 400
    assert "two guardians" in resp.get_json()["error"]
    assert _portions(app_db, cid) == []
    assert app_db.get_entry(sid)["statement_id"] is None
    assert _count_class(app_db, "income") == 0

    # Without the shortcut the split statement generates normally.
    data = client.post(f"/statements/bill-now/{sid}").get_json()
    assert data["success"]
    assert len(_portions(app_db, cid)) == 2
