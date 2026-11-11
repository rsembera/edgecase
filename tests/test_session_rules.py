"""Who counts as logged in, and what an expired or foreign session can do.

web/session_state.py. Before these rules: /api/keepalive revived an
already-expired session with no password; GET /logout with no cookie
closed the database on whoever was working; and a stale cookie on a second
device did the same through the timeout branch.
"""
import time

import pytest

from web.app import app as flask_app

TWO_HOURS_AGO = lambda: time.time() - 7200  # noqa: E731


@pytest.fixture(autouse=True)
def no_backup(monkeypatch):
    monkeypatch.setattr('web.cli._run_shutdown_backup', lambda *a, **k: None)


def _session(client, **values):
    with client.session_transaction() as sess:
        sess.update(values)


def _other_client(**values):
    other = flask_app.test_client()
    _session(other, authenticated=True, **values)
    return other


def test_keepalive_does_not_revive_an_expired_session(client, app_db):
    _session(client, last_activity=TWO_HOURS_AGO())

    resp = client.post('/api/keepalive', json={})
    assert resp.status_code == 401

    # Still expired: the next page load is sent to login.
    assert client.get('/').status_code == 302


def test_keepalive_extends_a_live_session(client, app_db):
    almost = time.time() - 29 * 60
    _session(client, last_activity=almost)
    assert client.post('/api/keepalive', json={}).status_code == 200
    with client.session_transaction() as sess:
        assert sess['last_activity'] > almost + 60


def test_logout_without_a_session_leaves_the_practice_open(client, app_db):
    anonymous = flask_app.test_client()
    resp = anonymous.get('/logout')
    assert resp.status_code == 302
    assert flask_app.config['db'] is app_db
    assert client.get('/').status_code == 200


def test_logout_from_the_live_session_still_locks(client, app_db):
    assert client.get('/logout').status_code == 302
    assert flask_app.config['db'] is None


def test_idle_second_session_does_not_close_the_active_one(client, app_db):
    _session(client, sid='mac')
    assert client.get('/').status_code == 200          # the Mac, in use

    ipad = _other_client(sid='ipad', last_activity=TWO_HOURS_AGO())
    assert ipad.get('/').status_code == 302             # sent to login
    assert flask_app.config['db'] is app_db             # practice still open
    assert client.get('/').status_code == 200           # the Mac carries on

    # ...and the same through the idle page's own /logout call.
    ipad = _other_client(sid='ipad', last_activity=TWO_HOURS_AGO())
    assert ipad.get('/logout').status_code == 302
    assert flask_app.config['db'] is app_db


def test_sole_expired_session_still_locks_the_practice(client, app_db):
    _session(client, sid='mac', last_activity=TWO_HOURS_AGO())
    assert client.get('/').status_code == 302
    assert flask_app.config['db'] is None


def test_cookie_from_an_earlier_unlock_is_not_logged_in(client, app_db):
    flask_app.config['SESSION_EPOCH'] = 'current-unlock'
    _session(client, epoch='current-unlock', sid='mac')
    assert client.get('/').status_code == 200

    stale = _other_client(epoch='yesterdays-unlock', sid='old',
                          last_activity=time.time())
    assert stale.get('/').status_code == 302
    assert stale.post('/api/keepalive', json={}).status_code == 401
    assert stale.get('/api/session-status').get_json() == {'logged_in': False}
    assert stale.get('/logout').status_code == 302

    assert flask_app.config['db'] is app_db
    assert client.get('/').status_code == 200


def test_login_from_locked_mints_a_new_epoch_and_a_second_login_joins_it(
        client, app_db):
    from web import session_state

    with flask_app.test_request_context('/login'):
        flask_app.config['db'] = None
        first = session_state.ensure_epoch()
        flask_app.config['db'] = app_db
        assert session_state.ensure_epoch() == first      # already unlocked
        flask_app.config['db'] = None
        assert session_state.ensure_epoch() != first      # locked again
