"""Client report payment status: Paid / Owing / Written off / Unbilled per line.

The use case (docs/Receipt_Plan.md, retired 2026-08-27): an insurer asked a
client for proof of payment for services already rendered. The Report is the
identity-bearing document — letterhead, registration info, signature — so it
carries the payment facts: a per-entry status computed from statement
portions, and a paid-in-full line that prints only when every fee-bearing
entry's statement is fully settled. Written-off is its own state: nothing is
owing, but nothing was paid, and it must never support the paid-in-full line.
"""
import time

from pypdf import PdfReader

from pdf.generator import generate_client_report_pdf, payment_status_label

PAID_IN_FULL = 'have been paid in full'


def _make_client(db, file_number="RPT-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Report",
        "middle_name": "",
        "last_name": "Client",
        "type_id": 1,
    })


def _make_statement(db, client_id, total=180.0, description="Statement July 2026"):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": description,
        "statement_total": total,
        "statement_tax_total": 0.0,
        "created_at": now,
        "modified_at": now,
    })


def _make_portion(db, statement_entry_id, client_id, amount_due=180.0,
                  status="sent", amount_paid=0.0, guardian_number=None):
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


def _make_session(db, client_id, fee=180.0, statement_id=None, date=None):
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "session",
        "description": "Session",
        "session_date": date or int(time.time()),
        "duration": 50,
        "base_fee": fee,
        "fee": fee,
    })
    if statement_id is not None:
        conn = db.connect()
        conn.execute("UPDATE entries SET statement_id = ? WHERE id = ?",
                     (statement_id, entry_id))
        conn.commit()
    return entry_id


def _make_absence(db, client_id, fee=0.0):
    return db.add_entry({
        "client_id": client_id,
        "class": "absence",
        "description": "Cancelled",
        "absence_date": int(time.time()),
        "base_fee": fee,
        "fee": fee,
    })


def _report_text(db, client_id, include_payment_status=True, **kw):
    buf = generate_client_report_pdf(
        db, client_id, include_sessions=True,
        include_payment_status=include_payment_status, **kw)
    return "\n".join(page.extract_text() for page in PdfReader(buf).pages)


# ---------------------------------------------------------------------------
# payment_status_label — pure portion-status arithmetic
# ---------------------------------------------------------------------------

def test_label_collapses_portion_statuses():
    assert payment_status_label([]) == 'Unbilled'
    assert payment_status_label(['paid']) == 'Paid'
    assert payment_status_label(['paid', 'paid']) == 'Paid'
    # Money still owed anywhere wins over everything; some of it having
    # arrived is its own word
    assert payment_status_label(['paid', 'sent']) == 'Owing'
    assert payment_status_label(['written_off', 'partial']) == 'Partial'
    assert payment_status_label(['ready']) == 'Owing'
    assert payment_status_label(['partial']) == 'Partial'
    assert payment_status_label(['paid', 'partial']) == 'Partial'
    # A write-off is nothing-owing but NOT paid
    assert payment_status_label(['written_off']) == 'Written off'
    assert payment_status_label(['paid', 'written_off']) == 'Written off'


# ---------------------------------------------------------------------------
# The report itself
# ---------------------------------------------------------------------------

def test_unbilled_session_shows_unbilled_and_no_paid_in_full(app_db):
    cid = _make_client(app_db)
    _make_session(app_db, cid)

    text = _report_text(app_db, cid)

    assert 'Unbilled' in text
    assert PAID_IN_FULL not in text


def test_paid_statement_shows_paid_and_the_paid_in_full_line(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='paid', amount_paid=180.0)
    _make_session(app_db, cid, statement_id=stmt)

    text = _report_text(app_db, cid)

    assert 'Paid' in text
    assert PAID_IN_FULL in text


def test_partial_statement_shows_partial_and_the_balance_line(app_db):
    """$50 against a $180 single-session statement: the one session is
    partly covered, so it says Partial; the balance line gives the
    statement-level figures. No paid-in-full."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='partial', amount_paid=50.0)
    _make_session(app_db, cid, statement_id=stmt)

    text = _report_text(app_db, cid)

    assert 'Partial' in text
    assert 'Owing' not in text
    assert 'billed $180.00, paid $50.00, balance owing $130.00' in text
    assert PAID_IN_FULL not in text


def test_sent_statement_shows_owing_and_the_balance_line(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='sent')
    _make_session(app_db, cid, statement_id=stmt)

    text = _report_text(app_db, cid)

    assert 'Owing' in text
    assert 'billed $180.00, paid $0.00, balance owing $180.00' in text
    assert PAID_IN_FULL not in text


def test_half_paid_two_session_statement_pays_the_older_session_first(app_db):
    """Today's case: August paid; September statement carries Sep 5 and
    Sep 12, $150 paid against it. Oldest-first: Sep 5 Paid, Sep 12 Owing —
    not two Partials. Balance line sums both statements."""
    from datetime import datetime
    cid = _make_client(app_db)
    aug = _make_statement(app_db, cid, total=150.0, description="Statement August 2026")
    _make_portion(app_db, aug, cid, amount_due=150.0, status='paid', amount_paid=150.0)
    _make_session(app_db, cid, statement_id=aug, fee=150.0,
                  date=int(datetime(2026, 8, 15).timestamp()))
    sep = _make_statement(app_db, cid, total=300.0, description="Statement September 2026")
    _make_portion(app_db, sep, cid, amount_due=300.0, status='partial', amount_paid=150.0)
    _make_session(app_db, cid, statement_id=sep, fee=150.0,
                  date=int(datetime(2026, 9, 5).timestamp()))
    _make_session(app_db, cid, statement_id=sep, fee=150.0,
                  date=int(datetime(2026, 9, 12).timestamp()))

    text = _report_text(app_db, cid)
    lines = [ln for ln in text.split('\n') if ln in ('Paid', 'Partial', 'Owing')]

    assert lines == ['Paid', 'Paid', 'Owing']
    assert 'billed $450.00, paid $300.00, balance owing $150.00' in text
    assert PAID_IN_FULL not in text


def test_oldest_first_convention_is_pure_and_deterministic():
    from pdf.generator import entry_payment_labels
    ents = [(3, 300, 150.0), (1, 100, 150.0), (2, 200, 150.0), (4, 400, 0.0)]
    # $150: oldest paid, rest owing; $0 entry gets a dash
    assert entry_payment_labels(ents, 150.0) == {1: 'Paid', 2: 'Owing', 3: 'Owing', 4: '\u2014'}
    # $200: one paid, next partial, last owing
    assert entry_payment_labels(ents, 200.0) == {1: 'Paid', 2: 'Partial', 3: 'Owing', 4: '\u2014'}
    # $450: all paid
    assert entry_payment_labels(ents, 450.0) == {1: 'Paid', 2: 'Paid', 3: 'Paid', 4: '\u2014'}
    # nothing: all owing
    assert entry_payment_labels(ents, 0) == {1: 'Owing', 2: 'Owing', 3: 'Owing', 4: '\u2014'}


def test_older_entry_outside_report_range_absorbs_money_first(app_db):
    """The convention runs over the whole statement, not the report's
    window: $150 on a statement whose older session is outside the range
    covers THAT one, so the in-range session still reads Owing."""
    from datetime import datetime
    cid = _make_client(app_db)
    sep = _make_statement(app_db, cid, total=300.0, description="Statement September 2026")
    _make_portion(app_db, sep, cid, amount_due=300.0, status='partial', amount_paid=150.0)
    _make_session(app_db, cid, statement_id=sep, fee=150.0,
                  date=int(datetime(2026, 9, 5).timestamp()))
    _make_session(app_db, cid, statement_id=sep, fee=150.0,
                  date=int(datetime(2026, 9, 12).timestamp()))

    text = _report_text(app_db, cid,
                        start_date=int(datetime(2026, 9, 10).timestamp()),
                        end_date=int(datetime(2026, 9, 30).timestamp()))
    lines = [ln for ln in text.split('\n') if ln in ('Paid', 'Partial', 'Owing')]
    assert lines == ['Owing']


def test_written_off_is_its_own_state_and_blocks_paid_in_full(app_db):
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='written_off')
    _make_session(app_db, cid, statement_id=stmt)

    text = _report_text(app_db, cid)

    assert 'Written off' in text
    assert PAID_IN_FULL not in text


def test_guardian_split_needs_every_portion_paid(app_db):
    """One statement, two payers: guardian 1 paid, guardian 2 owing."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid, total=180.0)
    _make_portion(app_db, stmt, cid, amount_due=90.0, status='paid',
                  amount_paid=90.0, guardian_number=1)
    _make_portion(app_db, stmt, cid, amount_due=90.0, status='sent',
                  guardian_number=2)
    _make_session(app_db, cid, statement_id=stmt)

    text = _report_text(app_db, cid)

    assert 'Owing' in text
    assert PAID_IN_FULL not in text


def test_zero_fee_entries_do_not_block_the_paid_in_full_line(app_db):
    """A $0 absence is not billable; it must not read as 'Unbilled'."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='paid', amount_paid=180.0)
    _make_session(app_db, cid, statement_id=stmt)
    _make_absence(app_db, cid, fee=0.0)

    text = _report_text(app_db, cid, include_absences=True)

    assert PAID_IN_FULL in text
    assert 'Unbilled' not in text


def test_status_is_absent_unless_requested(app_db):
    """The default report is unchanged: no status column, no attestation."""
    cid = _make_client(app_db)
    stmt = _make_statement(app_db, cid)
    _make_portion(app_db, stmt, cid, status='paid', amount_paid=180.0)
    _make_session(app_db, cid, statement_id=stmt)
    _make_session(app_db, cid)  # unbilled

    text = _report_text(app_db, cid, include_payment_status=False)

    assert 'Unbilled' not in text
    assert PAID_IN_FULL not in text
