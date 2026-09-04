"""The provider line reaches the documents an insurer will read — and only
those, and only for clients who have an insurer.

A statement for a client with no insurer must look exactly as it did before;
the business Financial Report is a tax document with no insurer audience and
must never carry a provider number at all.
"""
import io
import time

import pytest

pypdf = pytest.importorskip("pypdf", reason="PDF text extraction")


def _text(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or '') for page in reader.pages)


def _client(db, file_number="PRV-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Prov",
        "middle_name": "",
        "last_name": "Ider",
        "type_id": 1,
    })


def _statement_with_portion(db, client_id, total=150.0):
    now = int(time.time())
    stmt = db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": "Statement",
        "statement_total": total,
        "statement_tax_total": 0.0,
        "created_at": now,
        "modified_at": now,
    })
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, created_at
        ) VALUES (?, ?, NULL, ?, 0.0, 'sent', ?)
    """, (stmt, client_id, total, now))
    conn.commit()
    return cur.lastrowid


# ----------------------------------------------------------------------
# Statements
# ----------------------------------------------------------------------

def test_statement_carries_the_provider_line_for_an_insured_client(
        client, app_db):
    cid = _client(app_db)
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(cid, pid)
    portion = _statement_with_portion(app_db, cid)

    resp = client.get(f'/statements/pdf/{portion}')
    assert resp.status_code == 200
    text = _text(resp.data)
    assert "Blue Cross" in text
    assert "123456" in text


def test_statement_for_an_uninsured_client_carries_no_provider_line(
        client, app_db):
    """The number must not appear on documents for clients who have no
    relationship with that insurer."""
    insured = _client(app_db, "PRV-INS")
    uninsured = _client(app_db, "PRV-NONE")
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(insured, pid)

    portion = _statement_with_portion(app_db, uninsured)
    resp = client.get(f'/statements/pdf/{portion}')
    text = _text(resp.data)
    assert "Blue Cross" not in text
    assert "123456" not in text


def test_statement_uses_the_practitioners_own_format(client, app_db):
    cid = _client(app_db)
    pid = app_db.add_insurance_provider(
        "Blue Cross", "123456",
        number_format="BC Provider #{number}")
    app_db.set_client_provider(cid, pid)
    portion = _statement_with_portion(app_db, cid)

    text = _text(client.get(f'/statements/pdf/{portion}').data)
    assert "BC Provider #123456" in text


def test_dropping_an_insurer_removes_the_line_from_new_statements(
        client, app_db):
    cid = _client(app_db)
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(cid, pid)
    portion = _statement_with_portion(app_db, cid)
    assert "Blue Cross" in _text(client.get(f'/statements/pdf/{portion}').data)

    app_db.set_client_provider(cid, None)
    assert "Blue Cross" not in _text(
        client.get(f'/statements/pdf/{portion}').data)


# ----------------------------------------------------------------------
# Payment Record vs the business Financial Report
# ----------------------------------------------------------------------

def test_payment_record_carries_the_provider_line(client, app_db):
    cid = _client(app_db)
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(cid, pid)

    resp = client.get('/ledger/report/pdf',
                      query_string={'start': '2026-01-01',
                                    'end': '2026-12-31', 'client': cid})
    assert resp.status_code == 200
    assert "123456" in _text(resp.data)
    resp.close()


def test_business_financial_report_never_carries_a_provider_number(
        client, app_db):
    """The business report is a tax document. No insurer reads it, and it
    covers every client at once — there is no 'the' provider."""
    cid = _client(app_db)
    pid = app_db.add_insurance_provider("Blue Cross", "123456")
    app_db.set_client_provider(cid, pid)

    resp = client.get('/ledger/report/pdf',
                      query_string={'start': '2026-01-01',
                                    'end': '2026-12-31'})
    assert resp.status_code == 200
    text = _text(resp.data)
    assert "Blue Cross" not in text
    assert "123456" not in text
    resp.close()
