"""A second /logout arriving mid-backup must not run a second backup check.

Seen in production 2026-09-16: two "[Logout] Checking backup status..."
lines interleaved with one rsync run. The route read config['db'], ran the
(slow) backup + post-backup command, and only then cleared config['db'] —
so a duplicate request (double-click, or the timeout-warning countdown
firing while an explicit logout was still running) found the db still
present and ran the whole check again, concurrently.

The nested request below stands in for that overlap deterministically:
the backup stub fires a second /logout from *inside* the first one's
backup, exactly when the real duplicate arrives.
"""
from web.app import app as flask_app


def test_second_logout_during_backup_does_not_rerun_backup(client, app_db, monkeypatch):
    from web import cli

    calls = []
    other = flask_app.test_client()

    def fake_backup(db, label="Shutdown"):
        calls.append(label)
        if len(calls) == 1:
            # Duplicate /logout lands while the first is still backing up.
            other.get("/logout")

    monkeypatch.setattr(cli, "_run_shutdown_backup", fake_backup)
    # db.close() is per-thread and harmless here; keep the fixture's own
    # teardown from double-closing.
    monkeypatch.setattr(app_db, "close", lambda: None)

    resp = client.get("/logout")
    assert resp.status_code == 302

    assert calls == ["Logout"], f"backup check ran {len(calls)} times: {calls}"
    assert flask_app.config.get("db") is None
