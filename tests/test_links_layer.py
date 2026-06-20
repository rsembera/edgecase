"""Data-layer tests for the client-linking mutations not covered elsewhere.

test_edgecase.py covers create_link_group / get_link_group / is_client_linked /
get_linked_clients; this fills the gap before the database.py split:
update_link_group, delete_link_group, get_all_link_groups — the mutating link
operations the split must preserve. Uses the temp-DB app_db fixture directly.
"""


def _client(db, fn):
    return db.add_client({"file_number": fn, "first_name": "Link",
                          "middle_name": "", "last_name": "Member", "type_id": 1})


def _fees(*ids):
    return {str(i): {"base_fee": 75, "tax_rate": 13, "total_fee": 84.75}
            for i in ids}


def test_get_all_link_groups_returns_created_group(app_db):
    c1, c2 = _client(app_db, "G-1A"), _client(app_db, "G-1B")
    gid = app_db.create_link_group([c1, c2], "couples", 60, _fees(c1, c2))

    groups = app_db.get_all_link_groups()
    assert any(g["id"] == gid for g in groups)


def test_update_link_group_changes_format_membership_and_duration(app_db):
    c1, c2, c3 = (_client(app_db, "U-1A"), _client(app_db, "U-1B"),
                  _client(app_db, "U-1C"))
    gid = app_db.create_link_group([c1, c2], "couples", 60, _fees(c1, c2))

    assert app_db.update_link_group(
        gid, [c1, c2, c3], "family", 90, _fees(c1, c2, c3)) is True

    group = app_db.get_link_group(gid)
    assert group["format"] == "family"
    assert group["session_duration"] == 90
    assert {m["id"] for m in group["members"]} == {c1, c2, c3}
    assert app_db.is_client_linked(c3)


def test_delete_link_group_unlinks_members(app_db):
    c1, c2 = _client(app_db, "D-1A"), _client(app_db, "D-1B")
    gid = app_db.create_link_group([c1, c2], "couples", 60, _fees(c1, c2))
    assert app_db.is_client_linked(c1)

    assert app_db.delete_link_group(gid) is True
    assert app_db.get_link_group(gid) is None
    assert not app_db.is_client_linked(c1)
    assert not app_db.is_client_linked(c2)
