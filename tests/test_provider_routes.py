"""The provider feature through the routes: Settings API and the profile form.

The data layer is covered by tests/test_insurance_providers.py and the printed
output by tests/test_provider_on_documents.py. This is the wiring between —
the part that is easy to get right in isolation and leave unconnected.
"""
import pytest


def _client(db, file_number="RTE-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Route",
        "middle_name": "",
        "last_name": "Test",
        "type_id": 1,
    })


# ----------------------------------------------------------------------
# Settings API
# ----------------------------------------------------------------------

def test_add_list_and_edit_through_the_api(client, app_db):
    resp = client.post('/api/insurance_providers',
                       json={'name': 'Blue Cross', 'provider_number': '123456'})
    assert resp.status_code == 200
    pid = resp.get_json()['id']

    listed = client.get('/api/insurance_providers').get_json()['providers']
    assert [p['name'] for p in listed] == ['Blue Cross']

    resp = client.post(f'/api/insurance_providers/{pid}',
                       json={'name': 'Blue Cross', 'provider_number': '654321'})
    assert resp.get_json()['success'] is True
    assert app_db.get_insurance_provider(pid)['provider_number'] == '654321'


def test_blank_name_or_number_is_rejected(client, app_db):
    resp = client.post('/api/insurance_providers',
                       json={'name': '', 'provider_number': '123456'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_blank_format_falls_back_to_the_default(client, app_db):
    """The format field is collapsed in the UI; most adds will omit it."""
    resp = client.post('/api/insurance_providers',
                       json={'name': 'Blue Cross', 'provider_number': '123456',
                             'number_format': ''})
    pid = resp.get_json()['id']
    assert '{name}' in app_db.get_insurance_provider(pid)['number_format']


def test_deleting_an_unused_provider(client, app_db):
    pid = app_db.add_insurance_provider('Blue Cross', '123456')
    resp = client.delete(f'/api/insurance_providers/{pid}')
    assert resp.status_code == 200
    assert app_db.get_insurance_provider(pid) is None


def test_deleting_a_provider_in_use_returns_409_and_says_how_many(
        client, app_db):
    pid = app_db.add_insurance_provider('Blue Cross', '123456')
    app_db.set_client_provider(_client(app_db, 'RTE-A'), pid)
    app_db.set_client_provider(_client(app_db, 'RTE-B'), pid)

    resp = client.delete(f'/api/insurance_providers/{pid}')
    assert resp.status_code == 409
    assert '2 clients' in resp.get_json()['error']
    assert app_db.get_insurance_provider(pid) is not None


def test_editing_a_missing_provider_is_404(client, app_db):
    resp = client.post('/api/insurance_providers/9999',
                       json={'name': 'X', 'provider_number': 'Y'})
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Client profile form
# ----------------------------------------------------------------------

def test_profile_form_offers_every_provider_plus_none(client, app_db):
    app_db.add_insurance_provider('Blue Cross', '123456')
    app_db.add_insurance_provider('Green Shield', 'GS-99')
    cid = _client(app_db)

    html = client.get(f'/client/{cid}/profile').get_data(as_text=True)
    assert 'Blue Cross' in html
    assert 'Green Shield' in html
    assert '<option value="">None</option>' in html


def test_profile_form_points_at_settings_when_there_are_no_providers(
        client, app_db):
    cid = _client(app_db)
    html = client.get(f'/client/{cid}/profile').get_data(as_text=True)
    assert 'Settings' in html


def test_saving_the_profile_assigns_the_provider(client, app_db):
    pid = app_db.add_insurance_provider('Blue Cross', '123456')
    cid = _client(app_db)

    resp = client.post(f'/client/{cid}/profile', data={
        'first_name': 'Route', 'middle_name': '', 'last_name': 'Test',
        'file_number': 'RTE-001', 'provider_id': str(pid),
    })
    assert resp.status_code in (200, 302)
    assert app_db.get_client_provider(cid)['name'] == 'Blue Cross'


def test_saving_with_none_clears_the_provider(client, app_db):
    """Changing insurer -- or dropping cover -- is just reselecting."""
    pid = app_db.add_insurance_provider('Blue Cross', '123456')
    cid = _client(app_db)
    app_db.set_client_provider(cid, pid)

    client.post(f'/client/{cid}/profile', data={
        'first_name': 'Route', 'middle_name': '', 'last_name': 'Test',
        'file_number': 'RTE-001', 'provider_id': '',
    })
    assert app_db.get_client_provider(cid) is None


def test_a_form_without_the_field_leaves_the_assignment_alone(client, app_db):
    """Other forms post to this route; absent must mean 'no change', not
    'clear it'."""
    pid = app_db.add_insurance_provider('Blue Cross', '123456')
    cid = _client(app_db)
    app_db.set_client_provider(cid, pid)

    client.post(f'/client/{cid}/profile', data={
        'first_name': 'Route', 'middle_name': '', 'last_name': 'Test',
        'file_number': 'RTE-001',
    })
    assert app_db.get_client_provider(cid)['name'] == 'Blue Cross'
