"""A request's unfinished writes must not be committed by a later request.

Database.connect() is one connection per worker thread, so a handler that
fails between its first write and its commit used to leave those writes
pending — and the next request on that thread committed them. The net is
web.app.rollback_unfinished_transaction (teardown_request).
"""
import threading
import time

import pytest
import sqlcipher3

from web.app import app as flask_app


def _seed_ready_statement(app_db, client):
    type_id = app_db.get_all_client_types()[0]['id']
    cid = app_db.add_client({'file_number': 'RB-1', 'first_name': 'A',
                             'last_name': 'B', 'type_id': type_id})
    app_db.add_entry({'client_id': cid, 'class': 'session',
                      'description': 'Session 1',
                      'session_date': int(time.time()) - 86400,
                      'base_fee': 100.0, 'fee': 100.0, 'locked': 1})
    start = time.strftime('%Y-%m-%d', time.localtime(time.time() - 40 * 86400))
    resp = client.post('/statements/generate', json={
        'client_ids': [cid], 'start_date': start,
        'end_date': time.strftime('%Y-%m-%d')})
    assert resp.get_json()['count'] == 1
    return app_db.connect().execute(
        "SELECT id FROM statement_portions").fetchone()[0]


def _committed_count(app_db, sql):
    """Count from a SEPARATE connection: only committed rows are visible."""
    out = {}

    def read():
        conn = sqlcipher3.connect(str(app_db.db_path))
        out['n'] = conn.execute(sql).fetchone()[0]
        conn.close()

    t = threading.Thread(target=read)
    t.start()
    t.join()
    return out['n']


def test_failed_request_leaves_nothing_for_the_next_one_to_commit(
        client, app_db, monkeypatch):
    import web.blueprints.statements.delivery as delivery

    portion_id = _seed_ready_statement(app_db, client)

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    # mark-sent inserts its Communication entry, then copies the PDF.
    monkeypatch.setattr(delivery.shutil, 'copy2', disk_full)
    monkeypatch.setitem(flask_app.config, 'PROPAGATE_EXCEPTIONS', False)
    resp = client.post(f'/statements/mark-sent/{portion_id}?skip_email=1',
                       json={})
    assert resp.status_code == 500

    assert not app_db.connect().in_transaction

    # An unrelated save on the same thread must not carry the orphan along.
    app_db.set_setting('unrelated', '1')
    assert _committed_count(
        app_db, "SELECT COUNT(*) FROM entries "
                "WHERE description LIKE 'Statement Generated%'") == 0


def test_completed_request_is_untouched(client, app_db):
    """The net only catches unfinished work: a normal save still persists."""
    resp = client.post('/api/time_format', json={'time_format': '24h'})
    assert resp.status_code == 200
    assert _committed_count(
        app_db, "SELECT COUNT(*) FROM settings "
                "WHERE key = 'time_format' AND value = '24h'") == 1
