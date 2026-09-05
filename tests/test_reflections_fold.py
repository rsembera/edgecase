"""2.0.3: the two-note system is withdrawn; its text is folded into the note.

2.0.2 added `entries.reflections`. 2.0.3 removes the field from the UI. Any
text already written there must not be stranded in a column nothing shows,
so on open the migration appends it to `content` under a divider and blanks
the column. The column itself stays (inert); dropping it is not worth the
risk on an encrypted database.
"""

import os
import tempfile
import time

import pytest

from core.database import Database, REFLECTIONS_DIVIDER

MARKER = "ZZQX-reflection-marker-ZZQX"


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)


def _seed_2_0_2_database(path, rows):
    """Build a database the way 2.0.2 left it: a reflections column, with
    the given (content, reflections) pairs on one client's sessions."""
    db = Database(path)
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(entries)")
    if 'reflections' not in {r[1] for r in cur.fetchall()}:
        cur.execute("ALTER TABLE entries ADD COLUMN reflections TEXT")
    now = int(time.time())
    cur.execute("INSERT INTO clients (file_number, first_name, last_name, "
                "type_id, created_at, modified_at) "
                "VALUES ('FOLD-1', 'Fold', 'Test', 1, ?, ?)", (now, now))
    cid = cur.lastrowid
    ids = []
    for content, reflections in rows:
        cur.execute(
            "INSERT INTO entries (client_id, class, description, "
            "content, reflections, created_at, modified_at) "
            "VALUES (?, 'session', 'Session 1', ?, ?, ?, ?)",
            (cid, content, reflections, now, now))
        ids.append(cur.lastrowid)
    conn.commit()
    db.close()
    return ids


def _read(path, eid):
    db = Database(path)
    row = db.get_entry(eid)
    cur = db.connect().cursor()
    cur.execute("SELECT reflections, modified_at FROM entries WHERE id = ?",
                (eid,))
    reflections, modified_at = cur.fetchone()
    db.close()
    return row['content'], reflections, modified_at


def test_reflections_are_folded_into_content_on_open(db_path):
    (eid,) = _seed_2_0_2_database(db_path, [("Clinical note.", MARKER)])
    content, reflections, _ = _read(db_path, eid)
    assert content == "Clinical note." + REFLECTIONS_DIVIDER + MARKER
    assert reflections is None


def test_fold_is_idempotent(db_path):
    (eid,) = _seed_2_0_2_database(db_path, [("Clinical note.", MARKER)])
    _read(db_path, eid)
    content, reflections, _ = _read(db_path, eid)  # second open
    assert content.count(MARKER) == 1
    assert reflections is None


def test_an_entry_without_reflections_is_untouched(db_path):
    eid_a, eid_b = _seed_2_0_2_database(
        db_path, [("Plain note.", None), ("Blank note.", "")])
    assert _read(db_path, eid_a)[0] == "Plain note."
    assert _read(db_path, eid_b)[0] == "Blank note."


def test_reflections_with_no_content_become_the_content(db_path):
    (eid,) = _seed_2_0_2_database(db_path, [(None, MARKER)])
    content, reflections, _ = _read(db_path, eid)
    assert content == REFLECTIONS_DIVIDER.lstrip() + MARKER
    assert reflections is None


def test_fold_does_not_move_modified_at(db_path):
    """A migration is not an amendment; it must not pose as one."""
    (eid,) = _seed_2_0_2_database(db_path, [("Clinical note.", MARKER)])
    _, _, after = _read(db_path, eid)
    # The seed writes modified_at == created_at; a fold that bumped it
    # would break the equality even within the same second.
    db = Database(db_path)
    cur = db.connect().cursor()
    cur.execute("SELECT created_at FROM entries WHERE id = ?", (eid,))
    created = cur.fetchone()[0]
    db.close()
    assert after == created


def test_a_fresh_database_never_gains_the_column(db_path):
    db = Database(db_path)
    cur = db.connect().cursor()
    cur.execute("PRAGMA table_info(entries)")
    cols = {r[1] for r in cur.fetchall()}
    db.close()
    assert 'reflections' not in cols
