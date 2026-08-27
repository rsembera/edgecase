"""Client file export: promised PDF attachments that can't be merged.

The narrative says "PDF attached at end of document"; if the file is missing
or unreadable at export time, the appendix must say so explicitly rather
than silently omitting it — a clinical record states its own gaps.
"""
import time

from pypdf import PdfReader

from pdf.client_export import generate_client_export_pdf


def _client_with_pdf_attachment(db, filepath):
    client_id = db.add_client({'first_name': 'Test', 'last_name': 'Export',
                               'file_number': 'EXP-001', 'type_id': 1})
    entry_id = db.add_entry({'client_id': client_id, 'class': 'communication',
                             'description': 'Referral letter received',
                             'comm_date': '2026-08-01', 'comm_type': 'email',
                             'recipient': 'from_client'})
    conn = db.connect()
    conn.execute(
        "INSERT INTO attachments (entry_id, filename, description, filepath, filesize, uploaded_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (entry_id, 'referral.pdf', 'Referral letter', str(filepath), 123, int(time.time())))
    conn.commit()
    return client_id


def _export_text(db, client_id):
    buf = generate_client_export_pdf(db, client_id, ['communication'])
    return "\n".join(page.extract_text() for page in PdfReader(buf).pages)


def test_missing_attachment_is_declared_not_silently_dropped(app_db, tmp_path):
    missing = tmp_path / "gone.pdf"  # never created
    client_id = _client_with_pdf_attachment(app_db, missing)
    text = _export_text(app_db, client_id)
    assert "attached at end of document" in text          # the promise
    assert "could not be included" in text                # the honest gap
    assert "missing at export time" in text


def test_unreadable_attachment_is_declared(app_db, tmp_path):
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"this is not a pdf")
    client_id = _client_with_pdf_attachment(app_db, corrupt)
    text = _export_text(app_db, client_id)
    assert "could not be included" in text
    assert "could not be read" in text


def test_readable_attachment_still_merges_without_notice(app_db, tmp_path):
    from reportlab.pdfgen import canvas
    good = tmp_path / "good.pdf"
    c = canvas.Canvas(str(good))
    c.drawString(100, 700, "REFERRAL BODY TEXT")
    c.save()
    client_id = _client_with_pdf_attachment(app_db, good)
    text = _export_text(app_db, client_id)
    assert "REFERRAL BODY TEXT" in text
    assert "could not be included" not in text


def test_payment_record_carries_quotable_received_summary(app_db, tmp_path):
    """Insurer-facing sentence: total received and payment count for the period.

    Factual ('received $X across N payments'), never 'paid in full' — that
    would be an account-state attestation a date-range report can't make.
    """
    from pdf.ledger_report import generate_ledger_report_pdf
    client_id = app_db.add_client({'first_name': 'Carla', 'last_name': 'Claimant',
                                   'file_number': 'CL-777', 'type_id': 1})
    for ts, amt in ((1755000000, 120.0), (1756000000, 80.0)):
        app_db.add_entry({'client_id': None, 'class': 'income',
                          'ledger_type': 'income', 'ledger_date': ts,
                          'total_amount': amt, 'tax_amount': 0.0,
                          'source': 'CL-777', 'description': 'e-transfer'})
    out = tmp_path / "record.pdf"
    generate_ledger_report_pdf(app_db, 1754000000, 1757000000, str(out),
                               start_date_str='2026-08-01', end_date_str='2026-08-31',
                               client={'id': client_id, 'file_number': 'CL-777',
                                       'name': 'Carla Claimant'})
    raw = "\n".join(p.extract_text() for p in PdfReader(str(out)).pages)
    text = " ".join(raw.split())  # PDF extraction breaks lines mid-phrase
    assert "Payments received from Carla Claimant" in text
    assert "file CL-777" in text
    assert "200.00" in text
    assert "2 payments" in text
    assert "paid in full" not in text.lower()
