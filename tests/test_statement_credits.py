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


# ---------------------------------------------------------------------------
# Guardian splits: the per-payer version of the same rule
# ---------------------------------------------------------------------------

def _add_guardian_profile(db, client_id, g1_percent=100):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "profile",
        "description": "Client Profile",
        "is_minor": 1,
        "guardian1_name": "G1",
        "guardian1_pays_percent": g1_percent,
        "has_guardian2": 1,
        "guardian2_name": "G2",
        "created_at": now,
        "modified_at": now,
    })


def _add_locked_credit_split(db, client_id, g1=0.0, g2=-50.0, date=(2026, 6, 12)):
    """A credit item explicitly assigned between the guardians."""
    now = int(time.time())
    amount = g1 + g2
    entry_id = db.add_entry({
        "client_id": client_id,
        "class": "item",
        "description": "Overcharge refunded",
        "item_date": int(datetime(*date).timestamp()),
        "base_price": amount,
        "fee": amount,
        "guardian1_amount": g1,
        "guardian2_amount": g2,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(entry_id)
    return entry_id


def test_negative_guardian_portion_skips_the_statement(client, app_db):
    """Statement total positive, ONE guardian's share negative: no statement.

    Sessions split 100% to guardian 1; a credit item explicitly assigned
    to guardian 2. Without the per-payer check the -$50 portion would be
    created 'ready', and mark-sent's "amount_paid >= amount_due" test
    (0 >= -50) would settle it on the spot — money guardian 2 is owed,
    evaporated. The whole statement waits instead, exactly as it does
    when the client-level total goes negative.
    """
    cid = _make_client(app_db, file_number="CR-G01", first="Minor", last="Split")
    _add_guardian_profile(app_db, cid, g1_percent=100)
    sess = _add_locked_session(app_db, cid, fee=200.0)
    cred = _add_locked_credit_split(app_db, cid, g1=0.0, g2=-50.0)

    resp = _generate(client, [cid])
    data = resp.get_json()

    assert data["success"]
    assert _statement_totals(app_db, cid) == []       # no statement created
    assert not _is_billed(app_db, sess)               # entries stay unbilled
    assert not _is_billed(app_db, cred)
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["total"] == -50.0       # the negative share


def test_guardian_credit_absorbed_by_own_charges_generates(client, app_db):
    """The same credit is fine once that guardian's charges can absorb it."""
    cid = _make_client(app_db, file_number="CR-G02", first="Minor", last="Absorb")
    _add_guardian_profile(app_db, cid, g1_percent=50)   # sessions split 50/50
    _add_locked_session(app_db, cid, fee=200.0)          # guardian 2 carries $100
    _add_locked_credit_split(app_db, cid, g1=0.0, g2=-50.0)

    resp = _generate(client, [cid])
    data = resp.get_json()

    assert data["success"]
    assert data["skipped"] == []
    assert _statement_totals(app_db, cid) == [150.0]
