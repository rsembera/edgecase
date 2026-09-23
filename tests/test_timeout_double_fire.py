"""Two requests arriving after the session timeout must run one backup, not two.

The timeout check in before_request read config['db'], ran the (slow)
shutdown backup, and only then cleared config['db'] — the same shape
/logout had before 2026-09-16. Two requests landing together after the
timeout (two open tabs on wake, or a page firing several fetches) each
found the db and ran a concurrent backup check, racing on the manifest.
Now the timeout path claims the db under the same lock /logout uses, so
the second request finds nothing to back up and is sent to login.

As in test_logout_double_fire, the second request is fired from inside
the first one's backup, which is exactly the overlap window.
"""
import time

from web.app import app as flask_app


def _expired_client():
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["authenticated"] = True
        sess["login_time"] = time.time() - 7200
        sess["last_activity"] = time.time() - 7200  # far past the 30-min default
    return c


def test_second_request_after_timeout_does_not_rerun_backup(client, app_db, monkeypatch):
    from web import cli

    calls = []
    closed = []
    other = _expired_client()
    first = _expired_client()
    second_status = []

    def fake_backup(db, label="Shutdown"):
        calls.append(label)
        if len(calls) == 1:
            second_status.append(other.get("/").status_code)

    monkeypatch.setattr(cli, "_run_shutdown_backup", fake_backup)
    monkeypatch.setattr(app_db, "close", lambda: closed.append(True))

    resp = first.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    assert calls == ["Timeout"], f"backup check ran {len(calls)} times: {calls}"
    assert second_status == [302]
    assert flask_app.config.get("db") is None
    # The timed-out session's database is closed, as /logout does.
    assert closed == [True]
