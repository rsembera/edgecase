"""Restoring a backup whose credentials you no longer hold (the brick).

A backup carries its key material as it stood, so a restored practice
opens with the master password (and recovery key) of the moment the
backup was TAKEN. Before this fix, EdgeCase said nothing about that at
the point of restore, and nothing on the login screen after — so a
correct restore was indistinguishable from a rejected password, and a
user who restored a backup with lost credentials was locked out with the
disaster-recovery routes dead behind them (a database now existed).

Two halves, pinned here:

  PREVENTION (Daybook's fix, mechanics shared with MailRepo): fingerprint
  the backup's key-info against the live one WITHOUT trying a password —
  the ECC3 envelope's two halves each get a fresh salt on every rewrap,
  so hashing them separately says which credential changed — and put the
  answer beside every restore point and on the post-restore login screen.

  THE WAY BACK (EdgeCase first, neither sibling has it yet): a completed
  restore is marked UNVERIFIED until the first successful login. While
  the marker stands, the disaster-recovery routes stay open, so a restore
  that turns out to be unopenable can be followed by a different one —
  including the pre-restore safety backup. Login clears the marker, which
  is what closes the door; a practice in normal use is never exposed.
"""
import base64
import json
import zipfile

import pytest

from core import encryption_v3 as v3
from utils import backup

from tests.test_disaster_recovery import (  # shared harness
    _edgecase_full,
    _make_zip,
    _wire_paths,
    HOST,
    _set_first_run,
    _csrf,
)


def _recovery_key():
    """A syntactically valid recovery key (32 base32 chars, hyphenated)."""
    raw = base64.b32encode(b"\x01" * v3.RECOVERY_KEY_BYTES).decode()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def _fresh_blob(password="pw-original-123"):
    master = v3.new_master()
    return master, v3.build_keyinfo(master, password, _recovery_key())


# ----------------------------------------------------------------------------
# Fingerprinting: which half moved, without trying a password
# ----------------------------------------------------------------------------

class TestKeyinfoFingerprint:
    def test_v3_halves_identified(self):
        _, blob = _fresh_blob()
        fp = backup.keyinfo_fingerprint(blob)
        assert fp["version"] == 3
        assert fp["password_id"] and fp["recovery_id"]

    def test_password_rewrap_moves_only_password_half(self):
        master, blob = _fresh_blob()
        rewrapped = v3.rewrap_password(blob, master, "pw-changed-456")
        a, b = backup.keyinfo_fingerprint(blob), backup.keyinfo_fingerprint(rewrapped)
        assert a["password_id"] != b["password_id"]
        assert a["recovery_id"] == b["recovery_id"]

    def test_recovery_rewrap_moves_only_recovery_half(self):
        master, blob = _fresh_blob()
        raw = base64.b32encode(b"\x02" * v3.RECOVERY_KEY_BYTES).decode()
        new_key = "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))
        rewrapped = v3.rewrap_recovery_key(blob, master, new_key)
        a, b = backup.keyinfo_fingerprint(blob), backup.keyinfo_fingerprint(rewrapped)
        assert a["password_id"] == b["password_id"]
        assert a["recovery_id"] != b["recovery_id"]

    def test_v2_recognised_without_halves(self):
        fp = backup.keyinfo_fingerprint(b"ECC2" + b"x" * 60)
        assert fp == {"version": 2, "password_id": None, "recovery_id": None}

    def test_garbage_is_not_a_keyinfo(self):
        assert backup.keyinfo_fingerprint(None) is None
        assert backup.keyinfo_fingerprint(b"") is None
        assert backup.keyinfo_fingerprint(b"not a key file") is None
        # Right magic, wrong length: truncated, not trusted
        assert backup.keyinfo_fingerprint(b"ECC3" + b"x" * 10) is None


# ----------------------------------------------------------------------------
# The chain: the key-info a restore would actually land on disk
# ----------------------------------------------------------------------------

class TestChainKeyMaterial:
    def test_last_keyinfo_in_chain_wins(self, tmp_path):
        _, blob_a = _fresh_blob("pw-a")
        _, blob_b = _fresh_blob("pw-b")
        folder = tmp_path / "b"
        full = _make_zip(folder, "full_2026-08-01_100000.zip",
                         {"data/edgecase.db": b"db", "data/.keyinfo": blob_a})
        incr = _make_zip(folder, "incr_2026-08-02_100000.zip",
                         {"data/.keyinfo": blob_b})
        got, _ = backup.read_restore_point_key_material([str(full), str(incr)])
        assert got == blob_b

    def test_salt_without_keyinfo_flags_v1(self, tmp_path):
        folder = tmp_path / "b"
        full = _make_zip(folder, "full_2026-08-01_100000.zip",
                         {"data/edgecase.db": b"db", "data/.salt": b"s"})
        blob, saw_salt = backup.read_restore_point_key_material([str(full)])
        assert blob is None and saw_salt is True


# ----------------------------------------------------------------------------
# The notes, written for someone about to click Restore
# ----------------------------------------------------------------------------

class TestDescribeCredentials:
    def _chain_with(self, tmp_path, members):
        folder = tmp_path / "chain"
        path = _make_zip(folder, "full_2026-08-01_100000.zip",
                         {"data/edgecase.db": b"db", **members})
        return [str(path)]

    def test_unchanged_credentials_are_current(self, tmp_path):
        _, blob = _fresh_blob()
        files = self._chain_with(tmp_path, {"data/.keyinfo": blob})
        result = backup.describe_restore_point_credentials(files, blob)
        assert result["status"] == "current" and result["note"] == ""

    def test_password_change_is_named(self, tmp_path):
        master, blob = _fresh_blob()
        files = self._chain_with(tmp_path, {"data/.keyinfo": blob})
        live = v3.rewrap_password(blob, master, "pw-changed-456")
        result = backup.describe_restore_point_credentials(files, live)
        assert result["status"] == "password_changed"
        assert "password you used then" in result["note"]
        assert "recovery key still works" in result["note"]

    def test_both_changed_warns_of_lockout(self, tmp_path):
        _, backup_blob = _fresh_blob("pw-old")
        _, live_blob = _fresh_blob("pw-new")  # both halves differ
        files = self._chain_with(tmp_path, {"data/.keyinfo": backup_blob})
        result = backup.describe_restore_point_credentials(files, live_blob)
        assert result["status"] == "both_changed"
        assert "locked out" in result["note"]

    def test_no_live_key_is_the_disaster_note(self, tmp_path):
        _, blob = _fresh_blob()
        files = self._chain_with(tmp_path, {"data/.keyinfo": blob})
        result = backup.describe_restore_point_credentials(files, None)
        assert result["status"] == "no_current_key"
        assert "when this backup was made" in result["note"]

    def test_v2_backup_predates_recovery_keys(self, tmp_path):
        files = self._chain_with(
            tmp_path, {"data/.keyinfo": b"ECC2" + b"x" * 60})
        _, live = _fresh_blob()
        result = backup.describe_restore_point_credentials(files, live)
        assert result["status"] == "predates_recovery_keys"
        assert "no recovery key will open it" in result["note"]

    def test_v1_backup_predates_recovery_keys(self, tmp_path):
        files = self._chain_with(tmp_path, {"data/.salt": b"s"})
        _, live = _fresh_blob()
        result = backup.describe_restore_point_credentials(files, live)
        assert result["status"] == "predates_recovery_keys"

    def test_no_key_material_at_all_is_quiet(self, tmp_path):
        files = self._chain_with(tmp_path, {})
        result = backup.describe_restore_point_credentials(files, None)
        assert result == {"status": "unknown", "note": ""}

    def test_never_raises_on_unreadable_chain(self):
        result = backup.describe_restore_point_credentials(
            ["/nowhere/full_2026-08-01_100000.zip"], None)
        assert result["status"] in ("unknown", "no_current_key")


# ----------------------------------------------------------------------------
# Every restore point carries its note
# ----------------------------------------------------------------------------

class TestPointsAnnotated:
    def test_build_restore_points_annotates(self, tmp_path, monkeypatch):
        _, backups_dir = _wire_paths(tmp_path, monkeypatch)
        _edgecase_full(backups_dir, "full_2026-08-01_100000.zip")
        entries = backup.reconstruct_manifest_entries(backups_dir)
        points = backup.build_restore_points(entries, override_dir=backups_dir)
        assert points
        for point in points:
            assert "credential_status" in point
            assert "credential_note" in point


# ----------------------------------------------------------------------------
# The way back: unverified restores keep the recovery door open
# ----------------------------------------------------------------------------

class TestUnverifiedMarker:
    def test_roundtrip(self):
        assert not backup.restore_unverified()
        backup.set_restore_unverified()
        assert backup.restore_unverified()
        backup.clear_restore_unverified()
        assert not backup.restore_unverified()

    def test_clear_is_safe_when_absent(self):
        backup.clear_restore_unverified()  # must not raise
        assert not backup.restore_unverified()

    def test_complete_restore_sets_marker_and_carries_note(
            self, tmp_path, monkeypatch):
        data, backups_dir = _wire_paths(tmp_path, monkeypatch)
        staging = tmp_path / ".restore_staging"
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "edgecase.db").write_bytes(b"restored-db")
        marker = {
            "restore_point_id": "c_full",
            "prepared_at": "2026-08-16T00:00:00",
            "point_info": {
                "created_at": "2026-08-01T10:00:00",
                "credential_note": "Opens with the password of the day.",
            },
        }
        (staging / ".restore_marker").write_text(json.dumps(marker))

        result = backup.complete_restore()

        assert result is not None
        assert backup.restore_unverified()
        assert result["credential_note"] == "Opens with the password of the day."


class TestRecoveryDoorReopens:
    def test_routes_open_while_restore_unverified(
            self, bare_client, monkeypatch, tmp_path):
        """The anti-brick: a database exists, but it arrived by restore
        and nobody has opened it — the recovery routes must still work
        so a different backup can be tried."""
        _set_first_run(monkeypatch, False)  # a database exists
        backup.set_restore_unverified()

        resp = bare_client.get("/restore", headers=HOST)
        assert resp.status_code == 200

        folder = tmp_path / "b"
        _edgecase_full(folder)
        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/scan",
                                json={"folder": str(folder)}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["success"]

    def test_routes_close_once_marker_cleared(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, False)
        backup.set_restore_unverified()
        backup.clear_restore_unverified()

        resp = bare_client.get("/restore", headers=HOST)
        assert resp.status_code == 302

        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/search", json={}, headers=headers)
        assert resp.status_code == 403

    def test_successful_login_clears_marker(
            self, bare_client, monkeypatch, tmp_path):
        """The vouch: opening the database is what closes the door."""
        from web.blueprints import auth as auth_mod
        from core.config import DATA_DIR  # noqa: F401

        # Point the login route's DATA_DIR at a temp dir so first-run
        # creation builds a throwaway database.
        import core.config as config_mod
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(config_mod, "DATA_DIR", data_dir)
        monkeypatch.setattr("flask_wtf.csrf.validate_csrf", lambda *a, **k: None)
        from web.app import app as flask_app
        flask_app.config["WTF_CSRF_ENABLED"] = False

        backup.set_restore_unverified()
        assert backup.restore_unverified()

        resp = bare_client.post("/login", data={
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        }, headers=HOST)

        assert resp.status_code == 302, resp.data
        assert not backup.restore_unverified()

        # Leave no db handle behind for other tests
        db = flask_app.config.get("db")
        if db:
            try:
                db.close()
            except Exception:
                pass
        flask_app.config["db"] = None


class TestLoginBanner:
    def test_login_page_names_the_password_after_restore(
            self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, False)
        backup.set_restore_unverified()
        from web.app import app as flask_app
        flask_app.config["RESTORE_COMPLETED"] = {
            "restored_at": "2026-08-16T00:00:00",
            "restore_point": "c_full",
            "original_date": "2026-08-01T10:00:00",
            "credential_note": "Opens with the password of the day.",
        }
        try:
            resp = bare_client.get("/login", headers=HOST)
            assert resp.status_code == 200
            assert b"restored from a backup" in resp.data
            assert b"Opens with the password of the day." in resp.data
            # The way back is offered while the restore is unverified
            assert b"Restore a different backup" in resp.data
            # Peeked, not popped: the post-login code owns consuming it
            assert flask_app.config.get("RESTORE_COMPLETED") is not None
        finally:
            flask_app.config.pop("RESTORE_COMPLETED", None)

    def test_banner_generic_note_without_restore_info(
            self, bare_client, monkeypatch):
        """Marker present but RESTORE_COMPLETED already consumed (e.g. the
        app restarted twice): the banner still says which password."""
        _set_first_run(monkeypatch, False)
        backup.set_restore_unverified()
        resp = bare_client.get("/login", headers=HOST)
        assert resp.status_code == 200
        assert b"in use when the backup was made" in resp.data

    def test_no_banner_in_normal_use(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, False)
        resp = bare_client.get("/login", headers=HOST)
        assert resp.status_code == 200
        assert b"restored from a backup" not in resp.data
