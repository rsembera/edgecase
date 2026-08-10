"""Statement generation with credit lines (negative items).

The item form invites credits: "Use negative amounts for credits." They
normally just reduce the period's total. These tests cover what happens
when there aren't enough charges to absorb one.
"""
import time
from datetime import datetime

RANGE = {"start_date": "2026-06-01", "end_date": "2026-06-30"}


def _make_client(db, file_number="CR-001", first="Cred", last="It"):
    return db.add_client({
        "file_number": file_number,
        "first_name": first,
        "middle_name": "",
        "last_name": last,
        "type_id": 1,
    })


def _add_locked_session(db, client_id, fee=200.0, date=(2026, 6, 10)):
    now = int(time.time())
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "session",
        "description": "Session",
        "session_date": int(datetime(*date).timestamp()),
        "base_fee": fee,
        "tax_rate": 0.0,
        "fee": fee,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(entry_id)
    return entry_id


def _add_locked_credit(db, client_id, amount=-40.0, date=(2026, 6, 12)):
    """A returned book: an Item with a negative amount."""
    now = int(time.time())
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "item",
        "description": "Book returned",
        "item_date": int(datetime(*date).timestamp()),
        "base_price": amount,
        "fee": amount,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(entry_id)
    return entry_id


def _generate(client, client_ids):
    return client.post("/statements/generate",
                       json={"client_ids": client_ids, **RANGE})


def _statement_totals(db, client_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT statement_total FROM entries "
                "WHERE class = 'statement' AND client_id = ?", (client_id,))
    return [row[0] for row in cur.fetchall()]


def _is_billed(db, entry_id):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT statement_id FROM entries WHERE id = ?", (entry_id,))
    return cur.fetchone()[0] is not None


def test_credit_reduces_the_statement_total(client, app_db):
    """The ordinary case: a session and a returned book in one period."""
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid, fee=200.0)
    _add_locked_credit(app_db, cid, amount=-40.0)

    resp = _generate(client, [cid])

    assert resp.get_json()["count"] == 1
    assert _statement_totals(app_db, cid) == [160.0]


def test_no_statement_when_credits_exceed_charges(client, app_db):
    """A $40 credit with no sessions produces no statement at all."""
    cid = _make_client(app_db)
    credit = _add_locked_credit(app_db, cid, amount=-40.0)

    data = _generate(client, [cid]).get_json()

    assert data["count"] == 0
    assert _statement_totals(app_db, cid) == []
    assert data["skipped"][0]["client_id"] == cid
    assert data["skipped"][0]["total"] == -40.0
    assert data["skipped"][0]["name"] == "Cred It"
    # The credit must stay unbilled so it carries to the next period
    assert _is_billed(app_db, credit) is False


def test_skipped_credit_lands_on_a_later_statement(client, app_db):
    """Carrying forward is the whole point of not billing it."""
    cid = _make_client(app_db)
    _add_locked_credit(app_db, cid, amount=-40.0)
    _generate(client, [cid])

    # Next month the client has a session; the credit is still waiting
    _add_locked_session(app_db, cid, fee=200.0, date=(2026, 7, 8))
    resp = client.post("/statements/generate",
                       json={"client_ids": [cid],
                             "start_date": "2026-06-01",
                             "end_date": "2026-07-31"})

    assert resp.get_json()["count"] == 1
    assert _statement_totals(app_db, cid) == [160.0]


def test_exactly_offsetting_credit_still_generates(client, app_db):
    """Zero is not negative: the statement documents the offset."""
    cid = _make_client(app_db)
    session = _add_locked_session(app_db, cid, fee=40.0)
    credit = _add_locked_credit(app_db, cid, amount=-40.0)

    data = _generate(client, [cid]).get_json()

    assert data["count"] == 1
    assert _statement_totals(app_db, cid) == [0.0]
    # Both entries are settled rather than reappearing every month
    assert _is_billed(app_db, session) is True
    assert _is_billed(app_db, credit) is True


def test_one_skip_does_not_stop_the_batch(client, app_db):
    """Selecting five clients shouldn't fail because one has a credit."""
    payer = _make_client(app_db, "CR-001", "Reg", "Ular")
    credited = _make_client(app_db, "CR-002", "Neg", "Ative")
    _add_locked_session(app_db, payer, fee=200.0)
    _add_locked_credit(app_db, credited, amount=-40.0)

    data = _generate(client, [payer, credited]).get_json()

    assert data["count"] == 1
    assert _statement_totals(app_db, payer) == [200.0]
    assert [s["client_id"] for s in data["skipped"]] == [credited]


def test_no_skips_reported_when_everything_generates(client, app_db):
    cid = _make_client(app_db)
    _add_locked_session(app_db, cid, fee=200.0)

    assert _generate(client, [cid]).get_json()["skipped"] == []
