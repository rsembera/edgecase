"""Create -> edit round trips for the remaining entry types (Step 2, Target A).

Session and redaction live in test_entries_lifecycle.py; this rounds out the
type matrix (communication, absence, item, profile) so every blueprint route
that builds an entry is exercised against the data layer before the split.
"""


def _make_client(db):
    return db.add_client({
        "file_number": "RT-001", "first_name": "Round", "middle_name": "",
        "last_name": "Trip", "type_id": 1,
    })


def _comm_form(content):
    return {"description": "Phone call", "recipient": "Client",
            "comm_type": "phone", "date": "2026-06-19", "content": content}


def test_communication_create_then_edit(client, app_db):
    cid = _make_client(app_db)
    assert client.post(f"/client/{cid}/communication",
                       data=_comm_form("Initial")).status_code == 302
    entry = app_db.get_client_entries(cid, "communication")[0]
    assert entry["content"] == "Initial"

    eid = entry["id"]
    assert client.post(f"/client/{cid}/communication/{eid}",
                       data=_comm_form("Updated")).status_code == 302
    assert app_db.get_entry(eid)["content"] == "Updated"


def test_absence_create_then_edit(client, app_db):
    cid = _make_client(app_db)
    form = {"description": "No-show", "date": "2026-06-19",
            "base_fee": "100", "tax_rate": "13", "fee": "113"}
    assert client.post(f"/client/{cid}/absence", data=form).status_code == 302
    entry = app_db.get_client_entries(cid, "absence")[0]
    assert entry["description"] == "No-show"

    eid = entry["id"]
    assert client.post(f"/client/{cid}/absence/{eid}",
                       data=dict(form, description="Late cancellation")
                       ).status_code == 302
    assert app_db.get_entry(eid)["description"] == "Late cancellation"


def test_item_create_then_edit(client, app_db):
    cid = _make_client(app_db)
    form = {"description": "Report fee", "item_date": "2026-06-19",
            "base_price": "50", "tax_rate": "13", "fee": "56.50"}
    assert client.post(f"/client/{cid}/item", data=form).status_code == 302
    entry = app_db.get_client_entries(cid, "item")[0]
    assert entry["description"] == "Report fee"

    eid = entry["id"]
    assert client.post(f"/client/{cid}/item/{eid}",
                       data=dict(form, description="Letter fee")
                       ).status_code == 302
    assert app_db.get_entry(eid)["description"] == "Letter fee"


def test_profile_create_then_edit(client, app_db):
    cid = _make_client(app_db)
    form = {"file_number": "RT-001", "first_name": "Round", "middle_name": "",
            "last_name": "Trip", "email": "a@example.com"}
    assert client.post(f"/client/{cid}/profile", data=form).status_code == 302
    profile = app_db.get_profile_entry(cid)
    assert profile is not None
    assert profile["email"] == "a@example.com"

    assert client.post(f"/client/{cid}/profile",
                       data=dict(form, email="b@example.com")).status_code == 302
    assert app_db.get_profile_entry(cid)["email"] == "b@example.com"
