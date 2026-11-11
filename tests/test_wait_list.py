"""The wait list: an Inactive client flagged as waiting for an opening.

Stored as clients.waitlisted_at (flag and queue position in one) plus
clients.waitlist_note. Rules under test:

  * only Inactive clients can be on the list;
  * leaving Inactive takes the client off it, whichever path changed the type;
  * the date is stamped once — editing the note keeps the place in line;
  * the Profile form only touches the list when it carried the section;
  * Manage -> Wait List shows longest-waiting first and can remove.
"""
import time


def _types(db):
    by_name = {t['name']: t['id'] for t in db.get_all_client_types()}
    return by_name['Active'], by_name['Inactive']


def _client(db, type_id, file_number="WL-001", first="Wanda"):
    cid = db.add_client({
        "file_number": file_number, "first_name": first, "middle_name": "",
        "last_name": "Waits", "type_id": type_id,
    })
    db.add_entry({"client_id": cid, "class": "profile",
                  "description": f"{first} Waits - Profile",
                  "phone": "613-555-0100", "email": "w@example.com"})
    return cid


def _profile_form(db, cid, **extra):
    c = db.get_client(cid)
    form = {"first_name": c["first_name"], "middle_name": "",
            "last_name": c["last_name"], "file_number": c["file_number"]}
    form.update(extra)
    return form


# ----------------------------------------------------------------------
# Data layer
# ----------------------------------------------------------------------

def test_only_inactive_clients_can_join(app_db):
    active, inactive = _types(app_db)
    a = _client(app_db, active, "WL-A")
    i = _client(app_db, inactive, "WL-I")

    assert app_db.set_client_waitlist(a, True, "evenings") is False
    assert app_db.get_client(a)["waitlisted_at"] is None

    assert app_db.set_client_waitlist(i, True, "evenings") is True
    row = app_db.get_client(i)
    assert row["waitlisted_at"] and row["waitlist_note"] == "evenings"
    assert [w["id"] for w in app_db.get_waitlist()] == [i]


def test_editing_the_note_keeps_the_place_in_line(app_db):
    _, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    app_db.set_client_waitlist(cid, True, "first")
    conn = app_db.connect()
    conn.execute("UPDATE clients SET waitlisted_at = 1000 WHERE id = ?", (cid,))
    conn.commit()

    app_db.set_client_waitlist(cid, True, "second")
    row = app_db.get_client(cid)
    assert row["waitlisted_at"] == 1000
    assert row["waitlist_note"] == "second"


def test_leaving_inactive_clears_the_list(app_db):
    active, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    app_db.set_client_waitlist(cid, True, "note")

    app_db.update_client(cid, {"type_id": active})
    row = app_db.get_client(cid)
    assert row["waitlisted_at"] is None and row["waitlist_note"] is None
    assert app_db.get_waitlist() == []


def test_unrelated_client_update_leaves_the_list_alone(app_db):
    _, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    app_db.set_client_waitlist(cid, True, "note")

    app_db.update_client(cid, {"first_name": "Wendy"})
    app_db.update_client(cid, {"type_id": inactive})
    assert app_db.get_client(cid)["waitlist_note"] == "note"


def test_list_is_longest_waiting_first(app_db):
    _, inactive = _types(app_db)
    ids = [_client(app_db, inactive, f"WL-{n}", first=n) for n in ("One", "Two", "Three")]
    conn = app_db.connect()
    for cid, stamp in zip(ids, (3000, 1000, 2000)):
        app_db.set_client_waitlist(cid, True)
        conn.execute("UPDATE clients SET waitlisted_at = ? WHERE id = ?", (stamp, cid))
    conn.commit()

    assert [w["id"] for w in app_db.get_waitlist()] == [ids[1], ids[2], ids[0]]


# ----------------------------------------------------------------------
# Profile form
# ----------------------------------------------------------------------

def test_profile_shows_the_checkbox_only_for_inactive(client, app_db):
    active, inactive = _types(app_db)
    a = _client(app_db, active, "WL-A")
    i = _client(app_db, inactive, "WL-I")

    assert b'name="on_waitlist"' not in client.get(f"/client/{a}/profile").data
    assert b'name="on_waitlist"' in client.get(f"/client/{i}/profile").data


def test_profile_form_adds_edits_and_removes(client, app_db):
    _, inactive = _types(app_db)
    cid = _client(app_db, inactive)

    client.post(f"/client/{cid}/profile", data=_profile_form(
        app_db, cid, waitlist_present="1", on_waitlist="1",
        waitlist_note="Evenings only"))
    row = app_db.get_client(cid)
    assert row["waitlisted_at"] and row["waitlist_note"] == "Evenings only"

    client.post(f"/client/{cid}/profile", data=_profile_form(
        app_db, cid, waitlist_present="1"))
    row = app_db.get_client(cid)
    assert row["waitlisted_at"] is None and row["waitlist_note"] is None


def test_profile_post_without_the_section_changes_nothing(client, app_db):
    _, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    app_db.set_client_waitlist(cid, True, "keep me")

    client.post(f"/client/{cid}/profile", data=_profile_form(app_db, cid))
    assert app_db.get_client(cid)["waitlist_note"] == "keep me"


def test_profile_form_cannot_waitlist_an_active_client(client, app_db):
    active, _ = _types(app_db)
    cid = _client(app_db, active)

    client.post(f"/client/{cid}/profile", data=_profile_form(
        app_db, cid, waitlist_present="1", on_waitlist="1", waitlist_note="x"))
    assert app_db.get_client(cid)["waitlisted_at"] is None


def test_changing_type_through_the_route_clears_the_list(client, app_db):
    active, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    app_db.set_client_waitlist(cid, True, "note")

    client.post(f"/client/{cid}/change_type", data={"type_id": str(active)})
    assert app_db.get_client(cid)["waitlisted_at"] is None


# ----------------------------------------------------------------------
# Wait List page
# ----------------------------------------------------------------------

def test_page_lists_waiting_clients_and_removes(client, app_db):
    _, inactive = _types(app_db)
    cid = _client(app_db, inactive)
    other = _client(app_db, inactive, "WL-002", first="Nora")
    app_db.set_client_waitlist(cid, True, "Couples; evenings")

    page = client.get("/wait-list").data.decode()
    assert "Wanda Waits" in page and "Couples; evenings" in page
    assert "613-555-0100" in page
    assert "Nora Waits" not in page          # Inactive, but not waiting
    assert "confirm(" not in page and "alert(" not in page

    resp = client.post(f"/wait-list/{cid}/remove")
    assert resp.status_code == 302
    assert app_db.get_client(cid)["waitlisted_at"] is None
    assert app_db.get_client(other)["waitlisted_at"] is None
    assert "No One Waiting" in client.get("/wait-list").data.decode()


def test_manage_menu_links_to_the_wait_list_before_deleted(client, app_db):
    page = client.get("/").data.decode()
    assert page.index("/wait-list") < page.index("/deleted-clients")


def test_waiting_for_labels():
    from web.blueprints.clients import _waiting_for
    now = int(time.time())
    day = 86400
    assert _waiting_for(now - 3600, now) == "Added today"
    assert _waiting_for(now - day, now) == "1 day"
    assert _waiting_for(now - 10 * day, now) == "10 days"
    assert _waiting_for(now - 21 * day, now) == "3 weeks"
    assert _waiting_for(now - 90 * day, now) == "3 months"
