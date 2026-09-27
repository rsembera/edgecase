"""File-number generation, pinned at the Add Client route.

Nothing tested this before AirLock. AirLock's import has to number clients
exactly as Add Client does, so the logic moves into core/file_numbers.py and
both callers share it. These tests describe the route's behaviour as it was
before the move and must pass unchanged after it.
"""
from datetime import datetime

import pytest


def _post(client, **form):
    data = {"first_name": "Ada", "middle_name": "", "last_name": "Lovelace",
            "type_id": "1", "session_offset": "0"}
    data.update(form)
    return client.post("/add_client", data=data)


def _numbers(db):
    cur = db.connect().cursor()
    cur.execute("SELECT file_number FROM clients ORDER BY id")
    return [r[0] for r in cur.fetchall()]


# --- manual -----------------------------------------------------------------

def test_manual_uses_the_typed_number(client, app_db):
    app_db.set_setting("file_number_format", "manual")
    r = _post(client, file_number="  M-001  ")
    assert r.status_code == 302
    assert _numbers(app_db) == ["M-001"]


def test_manual_collision_is_refused(client, app_db):
    app_db.set_setting("file_number_format", "manual")
    _post(client, file_number="M-001")
    r = _post(client, file_number="M-001")
    assert r.status_code == 200
    assert b"already exists" in r.data
    assert _numbers(app_db) == ["M-001"]


# --- date-initials ----------------------------------------------------------

def test_date_initials(client, app_db):
    app_db.set_setting("file_number_format", "date-initials")
    today = datetime.now().strftime("%Y%m%d")
    _post(client)
    _post(client, middle_name="byron")
    _post(client)
    assert _numbers(app_db) == [f"{today}-AL", f"{today}-ABL", f"{today}-AL-2"]


def test_date_initials_needs_both_names(client, app_db):
    app_db.set_setting("file_number_format", "date-initials")
    r = _post(client, last_name="  ")
    assert r.status_code == 200
    assert b"First and last name are required" in r.data
    assert _numbers(app_db) == []


# --- prefix-counter ---------------------------------------------------------

def test_prefix_counter(client, app_db):
    app_db.set_setting("file_number_format", "prefix-counter")
    app_db.set_setting("file_number_prefix", "EC")
    app_db.set_setting("file_number_suffix", "X")
    app_db.set_setting("file_number_counter", "7")
    _post(client)
    _post(client)
    assert _numbers(app_db) == ["EC-0007-X", "EC-0008-X"]
    assert app_db.get_setting("file_number_counter") == "9"


def test_prefix_counter_skips_a_taken_number(client, app_db):
    app_db.set_setting("file_number_format", "prefix-counter")
    app_db.set_setting("file_number_counter", "1")
    app_db.add_client({"file_number": "0001", "first_name": "T",
                       "last_name": "Aken", "type_id": 1})
    _post(client)
    assert _numbers(app_db) == ["0001", "0002"]
    assert app_db.get_setting("file_number_counter") == "3"


@pytest.mark.parametrize("fmt", ["date-initials", "prefix-counter"])
def test_generated_formats_ignore_a_posted_number(client, app_db, fmt):
    app_db.set_setting("file_number_format", fmt)
    _post(client, file_number="SMUGGLED")
    assert "SMUGGLED" not in _numbers(app_db)
