"""Master-key rotation: Settings arming, the login-time screen, the SSE
progress stream (worker thread + queue), and the recovery-key handoff.

The rotation LOGIC is covered by test_master_rotation.py; this file covers
the glue — and one end-to-end run through the real login flow against a
synthetic install, because the login-time slot is the whole design.
"""
import json
import re

import pytest

from core import encryption_v2 as v2
from core import encryption_v3 as v3
from core import master_rotation as rot
from core import migrate_crypto as mc
from tests.test_migrate_v3 import PAYLOADS, PW, build_v2
from web.blueprints import auth as auth_bp

HOST = {"Host": "localhost"}


# --- Settings: arming ---------------------------------------------------------

@pytest.fixture
def v3_ui(monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 3)
    monkeypatch.setattr("core.migrate_crypto.has_recovery_key", lambda *a, **k: True)
    monkeypatch.setattr("core.migrate_crypto.recovery_key_pending", lambda *a, **k: False)


def test_settings_offers_rotation_on_v3(client, v3_ui, monkeypatch):
    monkeypatch.setattr("core.master_rotation.rotation_armed", lambda *a, **k: False)
    monkeypatch.setattr("core.master_rotation.rotation_in_progress", lambda *a, **k: False)
    resp = client.get("/settings", headers=HOST)
    assert resp.status_code == 200
    assert b"Rotate Master Key" in resp.data
    assert b"Cancel Rotation" not in resp.data


def test_settings_shows_armed_state_with_cancel(client, v3_ui, monkeypatch):
    monkeypatch.setattr("core.master_rotation.rotation_armed", lambda *a, **k: True)
    monkeypatch.setattr("core.master_rotation.rotation_in_progress", lambda *a, **k: False)
    resp = client.get("/settings", headers=HOST)
    assert b"will run the next time you log in" in resp.data
    assert b"Cancel Rotation" in resp.data


def test_settings_shows_in_progress_without_cancel(client, v3_ui, monkeypatch):
    monkeypatch.setattr("core.master_rotation.rotation_armed", lambda *a, **k: False)
    monkeypatch.setattr("core.master_rotation.rotation_in_progress", lambda *a, **k: True)
    resp = client.get("/settings", headers=HOST)
    assert b"under way" in resp.data
    assert b"Cancel Rotation" not in resp.data


def test_settings_hides_rotation_before_v3(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.has_recovery_key", lambda *a, **k: False)
    resp = client.get("/settings", headers=HOST)
    assert b"Rotate Master Key" not in resp.data


def test_arm_form_renders_and_states_the_backup_limit(client, v3_ui):
    resp = client.get("/rotate-master-key", headers=HOST)
    assert resp.status_code == 200
    assert b"Rotate the master key" in resp.data
    assert b"does not protect old backups" in resp.data


def test_arm_requires_the_password(client, app_db, v3_ui, monkeypatch):
    monkeypatch.setattr(app_db, "verify_password", lambda pw: False)
    armed = {"n": 0}
    monkeypatch.setattr("core.master_rotation.arm_rotation",
                        lambda *a, **k: armed.__setitem__("n", 1))
    resp = client.post("/rotate-master-key", headers=HOST,
                       data={"password": "definitely-wrong"})
    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower()
    assert armed["n"] == 0


def test_arm_with_the_password_arms_and_returns_to_settings(client, app_db, v3_ui, monkeypatch):
    monkeypatch.setattr(app_db, "verify_password", lambda pw: pw == "right-pw")
    armed = {"n": 0}
    monkeypatch.setattr("core.master_rotation.arm_rotation",
                        lambda *a, **k: armed.__setitem__("n", 1))
    resp = client.post("/rotate-master-key", headers=HOST, data={"password": "right-pw"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/settings")
    assert armed["n"] == 1


def test_arm_refused_before_v3(client, monkeypatch):
    monkeypatch.setattr("core.migrate_crypto.install_crypto_version", lambda *a, **k: 2)
    resp = client.get("/rotate-master-key", headers=HOST)
    assert resp.status_code == 302


def test_cancel_disarms(client, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("core.master_rotation.disarm_rotation",
                        lambda *a, **k: called.__setitem__("n", 1) or True)
    resp = client.post("/rotate-master-key/cancel", headers=HOST)
    assert resp.status_code == 302
    assert called["n"] == 1


# --- The stream, without a database -----------------------------------------

def test_rotate_stream_reachable_without_db_and_errors_without_token():
    from web.app import app
    app.config["TESTING"] = True
    prev = app.config.get("db")
    app.config["db"] = None
    try:
        resp = app.test_client().get("/rotate/stream", headers=HOST)
    finally:
        app.config["db"] = prev
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "error" in body and "log in again" in body


# --- End to end through the real login ----------------------------------------

@pytest.fixture
def live_install(tmp_path, monkeypatch):
    """A synthetic v3 install that the LIVE code paths (root=None) point at:
    core.config, utils.backup's module-level copies, and the key-info path."""
    import core.config as config
    from utils import backup as backup_mod

    build_v2(tmp_path)
    mc.migrate_to_v3(PW, root=tmp_path)
    mc.clear_recovery_key_pending(root=tmp_path)

    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config, "BACKUPS_DIR", tmp_path / "backups")
    for name in ("DATA_ROOT", "DATA_DIR", "ATTACHMENTS_DIR", "ASSETS_DIR", "BACKUPS_DIR"):
        monkeypatch.setattr(backup_mod, name, getattr(config, name))
    monkeypatch.setattr(backup_mod, "MANIFEST_FILE", tmp_path / "backups" / "manifest.json")
    monkeypatch.setattr(backup_mod, "RESTORE_STAGING_DIR", tmp_path / ".restore_staging")
    monkeypatch.setattr(v2, "KEYINFO_FILE", data_dir / ".keyinfo")
    monkeypatch.setattr("flask_wtf.csrf.validate_csrf", lambda *a, **k: None)
    v2._key_cache.clear()
    return tmp_path


def _events(body: str):
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def _decrypts_everything(root, password):
    master = v3.unwrap_with_password(v3.read_keyinfo(path=root / "data" / ".keyinfo"), password)
    _db, fk = v2.derive_subkeys(master)
    for name, payload in PAYLOADS.items():
        assert v2.decrypt_bytes(fk, (root / "attachments" / name).read_bytes()) == payload


def test_login_runs_an_armed_rotation_and_hands_over_the_key(bare_client, live_install):
    from web.app import app as flask_app

    root = live_install
    old_keyinfo = (root / "data" / ".keyinfo").read_bytes()
    rot.arm_rotation()

    # Wrong password: refused at the key file, nothing runs.
    resp = bare_client.post("/login", data={"password": "nope-nope-nope"}, headers=HOST)
    assert b"Incorrect password" in resp.data
    assert rot.rotation_armed()

    # Right password: the rotation screen, not the app.
    resp = bare_client.post("/login", data={"password": PW}, headers=HOST)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Rotating the master key" in body
    assert "Begin rotation" in body
    assert (root / "data" / ".keyinfo").read_bytes() == old_keyinfo  # nothing yet
    token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)

    stream = bare_client.get(f"/rotate/stream?token={token}", headers=HOST)
    events = _events(stream.get_data(as_text=True))
    statuses = [e["status"] for e in events]

    assert "backing_up" in statuses              # no manifest -> fresh backup
    assert "encrypting" in statuses
    encrypting = [e for e in events if e["status"] == "encrypting"]
    assert encrypting[-1]["current"] == encrypting[-1]["total"] == len(PAYLOADS)
    assert statuses[-1] == "complete"
    assert statuses.count("complete") == 1       # the worker's own is swallowed
    assert "recovery_key" not in json.dumps(events)

    # Committed, opened, and the flag is gone.
    assert (root / "data" / ".keyinfo").read_bytes() != old_keyinfo
    _decrypts_everything(root, PW)
    assert flask_app.config["db"] is not None
    assert not rot.rotation_pending()
    assert (root / "backups" / "manifest.json").exists()

    # The recovery-key screen peeks rather than consumes: a refresh still
    # shows it; acknowledgement drops it.
    redirect = events[-1]["redirect"]
    first = bare_client.get(redirect, headers=HOST)
    assert first.status_code == 200
    rk_token = re.search(r"token=([A-Za-z0-9_\-]+)", redirect).group(1)
    key = auth_bp._peek_recovery_handoff(rk_token)
    assert key and key.encode() in first.data
    again = bare_client.get(redirect, headers=HOST)
    assert key.encode() in again.data
    assert mc.verify_recovery_key(key) is True

    flask_app.config["db"].close()
    flask_app.config["db"] = None
    auth_bp._recovery_key_handoff.clear()


def test_login_resumes_an_interrupted_rotation(bare_client, live_install, monkeypatch):
    """Crash in the narrowest window (database swapped, key file not yet
    written), then log in with the OLD password: it must reach the rotation
    screen with resume wording, not 'Incorrect password', and the stream
    must finish the job."""
    from web.app import app as flask_app

    root = live_install
    rot.arm_rotation()
    with pytest.MonkeyPatch.context() as crash:
        crash.setattr(v3, "write_keyinfo", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("crash before keyinfo")))
        with pytest.raises(RuntimeError):
            rot.rotate_master(PW)
    assert rot.rotation_in_progress()

    resp = bare_client.post("/login", data={"password": PW}, headers=HOST)
    body = resp.get_data(as_text=True)
    assert "Finishing the master-key rotation" in body
    token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)

    stream = bare_client.get(f"/rotate/stream?token={token}", headers=HOST)
    events = _events(stream.get_data(as_text=True))
    assert events[-1]["status"] == "complete"
    _decrypts_everything(root, PW)
    assert not rot.rotation_pending()

    flask_app.config["db"].close()
    flask_app.config["db"] = None
    auth_bp._recovery_key_handoff.clear()


def test_stream_reports_a_refusal_honestly(bare_client, live_install, monkeypatch):
    """A rotation refused before it starts (a file under neither key) must
    say the data is unchanged and leave the flag so Settings can cancel."""
    import os
    from web.app import app as flask_app

    root = live_install
    rot.arm_rotation()
    (root / "attachments" / "mystery.enc").write_bytes(
        v2.encrypt_bytes(os.urandom(32), b"someone else's"))

    body = bare_client.post("/login", data={"password": PW}, headers=HOST).get_data(as_text=True)
    token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)
    events = _events(bare_client.get(f"/rotate/stream?token={token}", headers=HOST)
                     .get_data(as_text=True))

    assert events[-1]["status"] == "error"
    assert "mystery.enc" in events[-1]["message"]
    assert "unchanged" in events[-1]["message"]
    assert events[-1]["in_progress"] is False
    assert rot.rotation_armed() and not rot.rotation_in_progress()
    assert flask_app.config.get("db") is None
    _decrypts_everything(root, PW)
