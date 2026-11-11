"""The practice's currency symbol is used everywhere, not a hard-coded "$"."""
import json
import time


def test_edit_history_and_page_script_use_the_practice_currency(client, app_db):
    app_db.set_setting('currency', 'EUR')
    type_id = app_db.get_all_client_types()[0]['id']
    cid = app_db.add_client({'file_number': 'CS-1', 'first_name': 'A',
                             'last_name': 'B', 'type_id': type_id})
    eid = app_db.add_entry({'client_id': cid, 'class': 'absence',
                            'description': 'Late cancellation',
                            'absence_date': int(time.time()), 'base_fee': 50.0,
                            'fee': 50.0, 'locked': 1})

    client.post(f'/client/{cid}/absence/{eid}', data={
        'description': 'Late cancellation', 'date': time.strftime('%Y-%m-%d'),
        'base_fee': '60', 'fee': '60'})

    description = json.loads(app_db.get_entry(eid)['edit_history'])[0]['description']
    assert 'Total Fee: €50.00 → €60.00' in description
    assert '$' not in description

    page = client.get(f'/client/{cid}').get_data(as_text=True)
    assert 'window.CURRENCY_SYMBOL = "\\u20ac";' in page or \
        'window.CURRENCY_SYMBOL = "€";' in page


def test_dollar_practices_read_exactly_as_before(client, app_db):
    type_id = app_db.get_all_client_types()[0]['id']
    cid = app_db.add_client({'file_number': 'CS-2', 'first_name': 'A',
                             'last_name': 'B', 'type_id': type_id})
    eid = app_db.add_entry({'client_id': cid, 'class': 'absence',
                            'description': 'x', 'absence_date': int(time.time()),
                            'base_fee': 50.0, 'fee': 50.0, 'locked': 1})
    client.post(f'/client/{cid}/absence/{eid}', data={
        'description': 'x', 'date': time.strftime('%Y-%m-%d'),
        'base_fee': '1250', 'fee': '1250'})
    description = json.loads(app_db.get_entry(eid)['edit_history'])[0]['description']
    assert 'Total Fee: $50.00 → $1250.00' in description
