"""Retention deletion must leave nothing of the client behind.

`archive_and_delete_client` is the disposal path: when a client's retention
period expires, it writes an archive row and removes their records. Anything
it misses is a fragment of a clinical record that outlives a disposal the
practitioner believes is complete -- which is the thing disposal exists to
prevent.

The gap (found 2026-09-04): `payment_allocations` is never deleted. The table
arrived with the payment-allocation work on 2026-08-09; this function predates
it and was not updated, so a disposal leaves allocation rows referencing a
deleted client, a deleted entry and a deleted statement portion. Attachments,
entry links, client links, statement portions and entries were all handled
correctly -- allocations were simply never added to the list.

These tests assert the whole sweep, not just the known gap, so the next table
added to the schema fails here rather than silently joining the leftovers.
"""
import time

import pytest


def _client(db, file_number="RET-001"):
    return db.add_client({
        "file_number": file_number,
        "first_name": "Ret",
        "middle_name": "",
        "last_name": "Ention",
        "type_id": 1,
    })


def _statement(db, client_id, total=150.0):
    now = int(time.time())
    return db.add_entry({
        "client_id": client_id,
        "class": "statement",
        "description": "Statement for disposal test",
        "statement_total": total,
        "statement_tax_total": 0.0,
        "created_at": now,
        "modified_at": now,
    })


def _portion(db, statement_entry_id, client_id, amount_due=150.0):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO statement_portions (
            statement_entry_id, client_id, guardian_number,
            amount_due, amount_paid, status, created_at
        ) VALUES (?, ?, NULL, ?, 0.0, 'sent', ?)
    """, (statement_entry_id, client_id, amount_due, int(time.time())))
    conn.commit()
    return cur.lastrowid


def _seed_full_client(client, app_db, file_number="RET-001"):
    """A client with a statement, a portion, a recorded payment (which creates
    a payment_allocations row) and an attachment row."""
    cid = _client(app_db, file_number)
    stmt = _statement(app_db, cid)
    portion = _portion(app_db, stmt, cid)

    resp = client.post('/statements/record-payment', json={
        'portion_id': portion, 'payment_amount': 150.0})
    assert resp.status_code == 200

    conn = app_db.connect()
    cur = conn.cursor()
    now = int(time.time())
    cur.execute("""
        INSERT INTO entries (client_id, class, created_at, modified_at,
                             description)
        VALUES (?, 'communication', ?, ?, 'Statement sent')
    """, (cid, now, now))
    comm_id = cur.lastrowid
    cur.execute("""
        INSERT INTO attachments (entry_id, filename, description, filepath,
                                 filesize, uploaded_at)
        VALUES (?, 'Statement.pdf', '', ?, 100, ?)
    """, (comm_id, f"attachments/{cid}/{comm_id}/whatever.enc", now))
    conn.commit()
    return cid


def _counts_for(app_db, client_id):
    conn = app_db.connect()
    cur = conn.cursor()
    out = {}
    cur.execute("SELECT COUNT(*) FROM clients WHERE id = ?", (client_id,))
    out['clients'] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM entries WHERE client_id = ?", (client_id,))
    out['entries'] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM statement_portions WHERE client_id = ?",
                (client_id,))
    out['statement_portions'] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM payment_allocations WHERE client_id = ?",
                (client_id,))
    out['payment_allocations'] = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM attachments a
        WHERE NOT EXISTS (SELECT 1 FROM entries e WHERE e.id = a.entry_id)
    """)
    out['orphaned_attachments'] = cur.fetchone()[0]
    return out


def test_disposal_removes_payment_allocations(client, app_db):
    """The known gap: allocation rows survived a disposal."""
    cid = _seed_full_client(client, app_db)

    before = _counts_for(app_db, cid)
    assert before['payment_allocations'] > 0, "fixture did not create one"

    assert app_db.archive_and_delete_client(cid) is True

    after = _counts_for(app_db, cid)
    assert after['payment_allocations'] == 0


def test_disposal_leaves_nothing_of_the_client(client, app_db):
    """The whole sweep, so a newly added table fails here rather than silently
    joining the leftovers."""
    cid = _seed_full_client(client, app_db, file_number="RET-002")

    assert app_db.archive_and_delete_client(cid) is True

    after = _counts_for(app_db, cid)
    assert after == {
        'clients': 0,
        'entries': 0,
        'statement_portions': 0,
        'payment_allocations': 0,
        'orphaned_attachments': 0,
    }


def test_disposal_does_not_touch_another_client(client, app_db):
    """Deleting one client must not reach into anyone else's records."""
    keep = _seed_full_client(client, app_db, file_number="RET-KEEP")
    drop = _seed_full_client(client, app_db, file_number="RET-DROP")

    kept_before = _counts_for(app_db, keep)
    assert app_db.archive_and_delete_client(drop) is True

    assert _counts_for(app_db, keep) == kept_before


def test_disposal_writes_the_archive_row(client, app_db):
    """Disposal is recorded, not silent -- the archive is what survives."""
    cid = _seed_full_client(client, app_db, file_number="RET-ARCH")

    assert app_db.archive_and_delete_client(cid) is True

    conn = app_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM archived_clients "
                "WHERE file_number = ?", ("RET-ARCH",))
    assert cur.fetchone()[0] == 1
