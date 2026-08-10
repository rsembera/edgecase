"""Statements lifecycle route tests (database.py refactor Step 2, Target B).

Drives the billing seam through real routes: find-unbilled -> generate ->
record-payment (full and partial). All DB-only — billable entries are set up
directly via the db fixture, and mark-sent is deliberately excluded here
because it writes a PDF into the attachments tree (filesystem side effects);
it needs its own harness with the attachment dir redirected.
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
        "SELECT id, statement_entry_id, status, amount_due, amount_paid, "
        "write_off_reason "
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


def _mark_sent(db, portion_id):
    """Put a portion in 'sent' without the PDF/email machinery.

    Payment is only offered on statements the client has actually
    received, so a freshly generated 'ready' portion is not payable.
    """
    conn = db.connect()
    conn.execute("UPDATE statement_portions SET status = 'sent' WHERE id = ?",
                 (portion_id,))
    conn.commit()


def test_payment_full_settles_portion_and_records_income(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    _mark_sent(app_db, portion["id"])
    resp = client.post(
        "/statements/record-payment",
        json={"portion_id": portion["id"],
              "payment_amount": portion["amount_due"]},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["allocations"][0]["status"] == "paid"
    assert payload["allocations"][0]["amount_owing"] == 0

    assert _portions(app_db, cid)[0]["status"] == "paid"
    # Payment recorded an income ledger entry (statements -> ledger seam).
    assert _count_class(app_db, "income") == 1


def test_payment_partial_leaves_balance(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)

    portion = _portions(app_db, cid)[0]
    _mark_sent(app_db, portion["id"])
    half = round(portion["amount_due"] / 2, 2)
    resp = client.post(
        "/statements/record-payment",
        json={"portion_id": portion["id"], "payment_amount": half},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["allocations"][0]["status"] != "paid"
    assert payload["allocations"][0]["amount_owing"] > 0


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


def test_mark_sent_skip_email_records_attachment_and_sets_status(
        client, app_db, tmp_path, monkeypatch):
    """mark-sent in generate-only mode (skip_email=1) generates the PDF, records
    a communication entry + attachment, and moves the portion ready -> sent.

    ATTACHMENTS_DIR is redirected to a temp tree and PDF generation is stubbed,
    so the test touches neither the real attachments folder nor ReportLab/assets
    (the route's own email step is frontend AppleScript and does not run here).
    """
    import web.blueprints.statements.delivery as st
    from pathlib import Path

    monkeypatch.setattr(st, "ATTACHMENTS_DIR", tmp_path / "attachments")

    def _fake_pdf(database, portion_id, out_path, assets_dir):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4 test\n")

    monkeypatch.setattr(st, "generate_statement_pdf", _fake_pdf)

    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)
    portion_id = _portions(app_db, cid)[0]["id"]

    resp = client.post(f"/statements/mark-sent/{portion_id}?skip_email=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body.get("skip_email") is True

    assert _portions(app_db, cid)[0]["status"] == "sent"
    assert _count_class(app_db, "communication") == 1

    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(filepath) FROM attachments")
    count, filepath = cur.fetchone()
    assert count == 1
    # Proof the redirect held: the attachment landed under the temp tree.
    assert str(tmp_path) in filepath


def test_email_preview_composes_without_side_effects(client, app_db):
    """/email-preview returns the composed recipient/subject/body and changes
    NOTHING: no PDF, no communication entry, portion stays 'ready'. This is
    the contract the pre-send review modal depends on — Cancel must truly
    abort."""
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)
    portion_id = _portions(app_db, cid)[0]["id"]

    resp = client.get(f"/statements/email-preview/{portion_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["subject"].startswith("Statement for ")
    assert "Please find attached your statement" in body["body"]
    assert "recipient_email" in body

    # Read-only: nothing was created or transitioned.
    assert _portions(app_db, cid)[0]["status"] == "ready"
    assert _count_class(app_db, "communication") == 0

    # Unknown portion -> 404.
    assert client.get("/statements/email-preview/99999").status_code == 404


def test_mark_sent_records_edited_email_in_communication(
        client, app_db, tmp_path, monkeypatch):
    """mark-sent with an edited subject/body (the pre-send modal payload) uses
    the edits verbatim for both the returned email fields and the
    Communication entry content — the client file matches what was actually
    sent, not the template."""
    import shutil
    import web.blueprints.statements.delivery as st
    from pathlib import Path

    monkeypatch.setattr(st, "ATTACHMENTS_DIR", tmp_path / "attachments")

    def _fake_pdf(database, portion_id, out_path, assets_dir):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4 test\n")

    monkeypatch.setattr(st, "generate_statement_pdf", _fake_pdf)

    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)
    portion_id = _portions(app_db, cid)[0]["id"]

    edited_subject = "Statement for June 2026 — underpayment note"
    edited_body = ("Dear State,\n\nPlease find attached your statement. "
                   "Note the balance reflects your early payment of $100; "
                   "$13 remains owing.")

    resp = client.post(f"/statements/mark-sent/{portion_id}",
                       json={"subject": edited_subject, "body": edited_body})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    # The email handed to the frontend is the edited one.
    assert payload["subject"] == edited_subject
    assert payload["body"] == edited_body

    # The Communication entry records the edited body verbatim.
    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT description, content FROM entries "
                "WHERE class = 'communication'")
    rows = cur.fetchall()
    assert len(rows) == 1
    description, content = rows[0]
    assert description.startswith("Statement Sent - ")
    assert content == edited_body

    assert _portions(app_db, cid)[0]["status"] == "sent"

    # The email path leaves the temp PDF for the frontend attach step;
    # clean it up here so the test leaves nothing behind.
    shutil.rmtree(Path(payload["pdf_path"]).parent, ignore_errors=True)


def test_statement_pdf_renders_previous_balance_block(client, app_db, tmp_path):
    """Real ReportLab render: a client with an earlier SENT statement still
    owing gets the balance-forward block on their next statement's PDF
    (current charges + previous balance), and a client with no prior
    balance renders a byte-identical-shape PDF without it (no crash either
    way). Exercises get_prior_outstanding wiring inside
    generate_statement_pdf, not a stub."""
    from pdf.generator import generate_statement_pdf

    cid = _make_client(app_db)

    # Statement 1 (June), marked sent and unpaid -> a prior balance of 113.
    _add_locked_session(app_db, cid, date=(2026, 6, 10))
    _generate(client, cid)
    first = _portions(app_db, cid)[0]
    conn = app_db.connect()
    conn.cursor().execute(
        "UPDATE statement_portions SET status = 'sent' WHERE id = ?",
        (first["id"],))
    conn.commit()

    # Statement 2 (July) for the same client.
    _add_locked_session(app_db, cid, date=(2026, 7, 10))
    client.post("/statements/generate",
                json={"client_ids": [cid], "start_date": "2026-07-01",
                      "end_date": "2026-07-31"})
    second = [p for p in _portions(app_db, cid) if p["id"] != first["id"]][0]

    out = tmp_path / "with_prior.pdf"
    assert generate_statement_pdf(app_db, second["id"], str(out), str(tmp_path))
    assert out.stat().st_size > 0
    assert out.read_bytes()[:5] == b"%PDF-"

    # Sanity: the prior figure the block renders from.
    prior = app_db.get_prior_outstanding(cid, second["statement_entry_id"], None)
    assert prior > 0

    # And the first statement's own PDF has NO prior balance (nothing
    # earlier was sent) — the no-block path still renders.
    out2 = tmp_path / "no_prior.pdf"
    assert app_db.get_prior_outstanding(cid, first["statement_entry_id"], None) == 0
    assert generate_statement_pdf(app_db, first["id"], str(out2), str(tmp_path))
    assert out2.read_bytes()[:5] == b"%PDF-"


def test_pdf_routes_generate_and_serve(client, app_db, monkeypatch):
    """download (/pdf) and view (/view-pdf) generate a PDF and serve it (200,
    application/pdf). PDF generation is stubbed; _private_pdf_dir is a mkdtemp
    dir that the routes clean up via after_this_request, so nothing persists."""
    import web.blueprints.statements.delivery as st
    from pathlib import Path

    def _fake_pdf(database, portion_id, out_path, assets_dir):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4 test\n")

    monkeypatch.setattr(st, "generate_statement_pdf", _fake_pdf)

    cid = _make_client(app_db)
    _add_locked_session(app_db, cid)
    _generate(client, cid)
    pid = _portions(app_db, cid)[0]["id"]

    download = client.get(f"/statements/pdf/{pid}")
    assert download.status_code == 200
    assert download.mimetype == "application/pdf"

    view = client.get(f"/statements/view-pdf/{pid}")
    assert view.status_code == 200
    assert view.mimetype == "application/pdf"


def test_send_applescript_email_success(client, monkeypatch):
    """The email route shells out to osascript via subprocess.run; with run
    stubbed to succeed, it reports success and never launches Mail. Asserts the
    recipient is escaped into the -e AppleScript that would have been run."""
    import subprocess

    captured = {}

    class _Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    resp = client.post("/statements/send-applescript-email", json={
        "recipient_email": "client@example.com",
        "subject": "Your statement",
        "body": "Attached.",
    })
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert captured["cmd"][0] == "osascript"
    assert "-e" in captured["cmd"]
    assert "client@example.com" in captured["cmd"][-1]


def test_send_applescript_email_reports_osascript_failure(client, monkeypatch):
    """A non-zero osascript return surfaces as success=False carrying stderr."""
    import subprocess

    class _Result:
        returncode = 1
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())

    resp = client.post("/statements/send-applescript-email", json={
        "recipient_email": "client@example.com",
        "subject": "S",
        "body": "B",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "boom"


def test_send_applescript_email_cleans_up_temp_pdf(client, monkeypatch):
    """When pdf_path points into a private 'edgecase-' temp dir, the route
    removes that whole dir after the AppleScript step."""
    import subprocess
    import tempfile
    import shutil
    from pathlib import Path

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})(),
    )

    tmpdir = Path(tempfile.mkdtemp(prefix="edgecase-"))
    pdf = tmpdir / "Statement.pdf"
    pdf.write_bytes(b"%PDF-1.4 test\n")
    assert tmpdir.exists()

    try:
        resp = client.post("/statements/send-applescript-email", json={
            "recipient_email": "client@example.com",
            "subject": "S",
            "body": "B",
            "pdf_path": str(pdf),
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert not tmpdir.exists()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
