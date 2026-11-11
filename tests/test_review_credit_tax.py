"""Tax on an overpayment is counted when the credit is applied.

A payment's tax is stored on its ledger entry, pro-rated against what it
settles. Credit settles nothing until a later statement consumes it; the tax
then lands on the allocation row, and the recorded ledger entry is never
rewritten. Reports that summed only ledger entries under-reported tax
collected by that share (2026-11-11 review).
"""
import time
from decimal import Decimal

TODAY = time.strftime('%Y-%m-%d')
START = time.strftime('%Y-%m-%d', time.localtime(time.time() - 400 * 86400))


def _taxed_session(app_db, cid, days_ago):
    app_db.add_entry({'client_id': cid, 'class': 'session', 'description': 'S',
                      'session_date': int(time.time()) - days_ago * 86400,
                      'base_fee': 100.0, 'tax_rate': 13.0, 'fee': 113.0,
                      'locked': 1})


def _generate(client, cid):
    resp = client.post('/statements/generate', json={
        'client_ids': [cid], 'start_date': START, 'end_date': TODAY})
    assert resp.get_json()['count'] == 1


def test_tax_on_credit_is_reported_and_the_ledger_entry_is_untouched(client, app_db):
    type_id = app_db.get_all_client_types()[0]['id']
    cid = app_db.add_client({'file_number': 'CT-1', 'first_name': 'A',
                             'last_name': 'B', 'type_id': type_id})
    _taxed_session(app_db, cid, 30)
    _generate(client, cid)
    conn = app_db.connect()
    portion_id = conn.execute("SELECT id FROM statement_portions").fetchone()[0]
    conn.execute("UPDATE statement_portions SET status = 'sent'")
    conn.commit()

    # 226 against a 113 statement: 113 settles it, 113 is held as credit.
    client.post('/statements/record-payment',
                json={'portion_id': portion_id, 'payment_amount': 226})
    assert app_db.get_ledger_totals()['total_tax_collected'] == 13.0
    assert app_db.get_credit_tax_applied() == Decimal('0.00')

    # The next statement consumes the credit.
    _taxed_session(app_db, cid, 2)
    _generate(client, cid)

    assert app_db.get_credit_tax_applied() == Decimal('13.00')
    assert app_db.get_credit_tax_applied(client_id=cid + 1) == Decimal('0.00')
    assert app_db.get_ledger_totals()['total_tax_collected'] == 26.0
    entry_tax = conn.execute(
        "SELECT tax_amount FROM entries WHERE class = 'income'").fetchone()[0]
    assert entry_tax == 13.0                      # as recorded, not rewritten

    report = client.get(
        f'/ledger/report/calculate?start={START}&end={TODAY}').get_json()
    assert report['tax_collected'] == 26.0
    per_client = client.get(
        f'/ledger/report/calculate?start={START}&end={TODAY}&client={cid}').get_json()
    assert per_client['tax_collected'] == 26.0
