"""Disaster recovery: restoring when the database (or all of DATA_ROOT) is gone.

Before this existed, a missing edgecase.db dropped the user into the
first-run "create a password" flow with no mention of backups — typing a
password built a fresh empty practice. All restore endpoints sat behind
login, unreachable by exactly the person they exist for, and restore-point
discovery depended on the local manifest, which dies with the data root.

These tests pin the fix:
  - manifests are stamped with the app id and mirrored as sidecars into
    every custom backup destination
  - backup destinations are recorded outside DATA_ROOT
  - restore points can be discovered in an arbitrary folder, from the
    sidecar or by filename reconstruction
  - foreign (MailRepo-shaped) backup folders are refused
  - the public /restore routes work on first run and are dead once a
    database exists
  - staging applies incremental deletions per zip (delete-then-recreate)
"""
import json
import zipfile
from pathlib import Path

import pytest

from utils import backup


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _wire_paths(tmp_path, monkeypatch):
    """Point the backup module at an isolated tree."""
    data = tmp_path / "data"
    data.mkdir()
    backups = tmp_path / "backups"
    monkeypatch.setattr(backup, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(backup, "BACKUPS_DIR", backups)
    monkeypatch.setattr(backup, "MANIFEST_FILE", backups / "manifest.json")
    monkeypatch.setattr(backup, "RESTORE_STAGING_DIR",
                        tmp_path / ".restore_staging")
    return data, backups


def _make_zip(folder, name, members):
    """Write a zip at folder/name with {arcname: bytes} members."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    with zipfile.ZipFile(path, "w") as zf:
        for arcname, content in members.items():
            zf.writestr(arcname, content)
    return path


def _edgecase_full(folder, name="full_2026-08-01_100000.zip", extra=None):
    members = {
        "data/edgecase.db": b"db-bytes",
        "data/.salt": b"salt",
        "data/.secret_key": b"secret",
    }
    if extra:
        members.update(extra)
    return _make_zip(folder, name, members)


def _mailrepo_full(folder, name="full_2026-08-01_100000.zip"):
    return _make_zip(folder, name, {
        "data/mailrepo.db": b"db-bytes",
        "data/.salt": b"salt",
        "data/.secret_key": b"secret",
    })


# ----------------------------------------------------------------------------
# Manifest stamping, sidecars, and the locations record
# ----------------------------------------------------------------------------

class TestManifestStamping:
    def test_save_manifest_stamps_app_id(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        backup.save_manifest({"backups": []})
        written = json.loads((tmp_path / "backups" / "manifest.json").read_text())
        assert written["app"] == "edgecase"

    def test_sidecar_written_to_custom_destination(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        cloud = tmp_path / "cloud" / "EdgeCase Backups"
        cloud.mkdir(parents=True)
        manifest = {"backups": [{
            "filename": "full_2026-08-01_100000.zip",
            "type": "full", "chain_id": "c1",
            "created_at": "2026-08-01T10:00:00",
            "backup_dir": str(cloud),
        }]}
        backup.save_manifest(manifest)
        sidecar = json.loads((cloud / "manifest.json").read_text())
        assert sidecar["app"] == "edgecase"
        assert sidecar["backups"][0]["filename"] == "full_2026-08-01_100000.zip"

    def test_sidecar_does_not_resurrect_missing_destination(self, tmp_path, monkeypatch):
        """An old install path lingering in the manifest history must not
        be re-created on every backup. If the folder is gone, its zips are
        gone, and a manifest there describes nothing."""
        _wire_paths(tmp_path, monkeypatch)
        ghost = tmp_path / "old-install" / "backups"
        manifest = {"backups": [{
            "filename": "full_2025-12-30_105307.zip",
            "type": "full", "chain_id": "c0",
            "created_at": "2025-12-30T10:53:07",
            "backup_dir": str(ghost),
        }]}
        backup.save_manifest(manifest)
        assert not ghost.exists()
        recorded = {loc["path"] for loc in backup.get_known_locations()}
        assert str(ghost) not in recorded

    def test_locations_recorded_and_read_back(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        cloud = tmp_path / "cloud"
        cloud.mkdir()
        backup.record_backup_location(cloud)
        locations = backup.get_known_locations()
        assert [e["path"] for e in locations] == [str(cloud)]

    def test_missing_folder_dropped_but_not_forgotten(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        unplugged = tmp_path / "external"
        unplugged.mkdir()
        backup.record_backup_location(unplugged)
        unplugged.rmdir()  # drive unplugged
        assert backup.get_known_locations() == []
        # Still in the file: reappears when the drive comes back
        unplugged.mkdir()
        assert [e["path"] for e in backup.get_known_locations()] == [str(unplugged)]


# ----------------------------------------------------------------------------
# Folder recognition (the EdgeCase/MailRepo guard)
# ----------------------------------------------------------------------------

class TestFolderRecognition:
    def test_stamped_folder_recognised(self, tmp_path):
        folder = tmp_path / "b"
        folder.mkdir()
        (folder / "manifest.json").write_text(
            json.dumps({"app": "edgecase", "backups": []}))
        assert backup.folder_holds_edgecase_backups(folder)

    def test_foreign_stamp_refused(self, tmp_path):
        folder = tmp_path / "b"
        folder.mkdir()
        (folder / "manifest.json").write_text(
            json.dumps({"app": "mailrepo", "backups": []}))
        assert not backup.folder_holds_edgecase_backups(folder)

    def test_unstamped_folder_recognised_by_zip_contents(self, tmp_path):
        folder = tmp_path / "b"
        _edgecase_full(folder)
        assert backup.folder_holds_edgecase_backups(folder)

    def test_unstamped_mailrepo_folder_refused(self, tmp_path):
        folder = tmp_path / "b"
        _mailrepo_full(folder)
        assert not backup.folder_holds_edgecase_backups(folder)

    def test_discover_refuses_foreign_folder_with_error(self, tmp_path):
        folder = tmp_path / "b"
        _mailrepo_full(folder)
        with pytest.raises(ValueError, match="different application"):
            backup.discover_restore_points_in(folder)

    def test_discover_empty_folder(self, tmp_path):
        folder = tmp_path / "b"
        folder.mkdir()
        points, source = backup.discover_restore_points_in(folder)
        assert points == [] and source == "empty"


# ----------------------------------------------------------------------------
# Discovery: sidecar first, reconstruction fallback
# ----------------------------------------------------------------------------

class TestDiscovery:
    def test_sidecar_manifest_preferred(self, tmp_path):
        folder = tmp_path / "b"
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        (folder / "manifest.json").write_text(json.dumps({
            "app": "edgecase",
            "backups": [{
                "filename": "full_2026-08-01_100000.zip",
                "type": "full", "chain_id": "20260801_100000",
                "created_at": "2026-08-01T10:00:00",
                "backup_dir": "/somewhere/that/no/longer/exists",
            }],
        }))
        points, source = backup.discover_restore_points_in(folder)
        assert source == "manifest"
        assert len(points) == 1
        # override_dir: files resolve against THIS folder, not the stale
        # backup_dir recorded on another machine
        assert points[0]["files_needed"] == [str(folder / "full_2026-08-01_100000.zip")]

    def test_stale_sidecar_falls_back_to_reconstruction(self, tmp_path):
        folder = tmp_path / "b"
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        (folder / "manifest.json").write_text(json.dumps({
            "app": "edgecase",
            "backups": [{
                "filename": "full_2020-01-01_000000.zip",  # not on disk
                "type": "full", "chain_id": "x",
                "created_at": "2020-01-01T00:00:00",
            }],
        }))
        points, source = backup.discover_restore_points_in(folder)
        assert source == "reconstructed"
        assert len(points) == 1

    def test_reconstruction_chains_by_time_not_name(self, tmp_path):
        """Two chains in one folder must not get stitched into one."""
        folder = tmp_path / "b"
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        _make_zip(folder, "incr_2026-08-02_100000.zip", {"data/edgecase.db": b"x"})
        _edgecase_full(folder, "full_2026-08-08_100000.zip")
        _make_zip(folder, "incr_2026-08-09_100000.zip", {"data/edgecase.db": b"y"})

        entries = backup.reconstruct_manifest_entries(folder)
        chains = {e["filename"]: e["chain_id"] for e in entries}
        assert chains["incr_2026-08-02_100000.zip"] == chains["full_2026-08-01_100000.zip"]
        assert chains["incr_2026-08-09_100000.zip"] == chains["full_2026-08-08_100000.zip"]
        assert chains["full_2026-08-01_100000.zip"] != chains["full_2026-08-08_100000.zip"]

    def test_orphan_incremental_excluded(self, tmp_path):
        folder = tmp_path / "b"
        # An incremental before any full: unrecoverable orphan. The zip
        # content doesn't matter for reconstruction, but the folder must
        # be recognised as EdgeCase's, so give it a real full AFTER it.
        _make_zip(folder, "incr_2026-07-01_100000.zip", {"data/edgecase.db": b"x"})
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        entries = backup.reconstruct_manifest_entries(folder)
        names = [e["filename"] for e in entries]
        assert "incr_2026-07-01_100000.zip" not in names
        assert "full_2026-08-01_100000.zip" in names

    def test_pre_restore_stands_alone(self, tmp_path):
        folder = tmp_path / "b"
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        _make_zip(folder, "pre_restore_2026-08-03_100000.zip",
                  {"data/edgecase.db": b"z"})
        points, source = backup.discover_restore_points_in(folder)
        assert source == "reconstructed"
        types = sorted(p["type"] for p in points)
        assert types == ["full", "pre_restore"]

    def test_reconstructed_points_flagged(self, tmp_path):
        folder = tmp_path / "b"
        _edgecase_full(folder)
        points, _ = backup.discover_restore_points_in(folder)
        assert all(p.get("reconstructed") for p in points)


# ----------------------------------------------------------------------------
# find_backup_locations
# ----------------------------------------------------------------------------

class TestFindBackupLocations:
    def test_recorded_location_found(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        cloud = tmp_path / "cloud"
        _edgecase_full(cloud)
        (cloud / "manifest.json").write_text(json.dumps({
            "app": "edgecase",
            "backups": [{
                "filename": "full_2026-08-01_100000.zip",
                "type": "full", "chain_id": "c",
                "created_at": "2026-08-01T10:00:00",
                "backup_dir": str(cloud),
            }],
        }))
        backup.record_backup_location(cloud)

        locations = backup.find_backup_locations()
        assert len(locations) == 1
        assert locations[0]["path"] == str(cloud)
        assert locations[0]["known"] is True
        assert locations[0]["restore_point_count"] == 1

    def test_foreign_recorded_location_skipped(self, tmp_path, monkeypatch):
        _wire_paths(tmp_path, monkeypatch)
        foreign = tmp_path / "mailrepo_backups"
        _mailrepo_full(foreign)
        backup.record_backup_location(foreign)
        assert backup.find_backup_locations() == []

    def test_default_folder_checked_without_record(self, tmp_path, monkeypatch):
        _, backups_dir = _wire_paths(tmp_path, monkeypatch)
        _edgecase_full(backups_dir)
        locations = backup.find_backup_locations()
        assert len(locations) == 1
        assert locations[0]["known"] is False


# ----------------------------------------------------------------------------
# Staging via prepare_restore_from_point
# ----------------------------------------------------------------------------

class TestStaging:
    def test_delete_then_recreate_survives(self, tmp_path, monkeypatch):
        """Deletions must apply per zip. A file deleted in incr1 and
        recreated in incr2 exists at the restore point; accumulated
        tombstones wrongly removed it (the logo.png case)."""
        _, backups_dir = _wire_paths(tmp_path, monkeypatch)
        full = _edgecase_full(backups_dir, "full_2026-08-01_100000.zip",
                              extra={"assets/logo.png": b"logo-v1"})
        incr1 = _make_zip(backups_dir, "incr_2026-08-02_100000.zip", {
            "_backup_metadata.json": json.dumps(
                {"deleted_files": ["assets/logo.png"]}),
        })
        incr2 = _make_zip(backups_dir, "incr_2026-08-03_100000.zip", {
            "assets/logo.png": b"logo-v2",
        })

        point = {
            "id": "c_incr_1",
            "files_needed": [str(full), str(incr1), str(incr2)],
        }
        staging = Path(backup.prepare_restore_from_point(point))
        assert (staging / "assets" / "logo.png").read_bytes() == b"logo-v2"

    def test_deletion_still_applies_when_final(self, tmp_path, monkeypatch):
        _, backups_dir = _wire_paths(tmp_path, monkeypatch)
        full = _edgecase_full(backups_dir, "full_2026-08-01_100000.zip",
                              extra={"assets/logo.png": b"logo-v1"})
        incr1 = _make_zip(backups_dir, "incr_2026-08-02_100000.zip", {
            "_backup_metadata.json": json.dumps(
                {"deleted_files": ["assets/logo.png"]}),
        })
        point = {"id": "c_incr_0", "files_needed": [str(full), str(incr1)]}
        staging = Path(backup.prepare_restore_from_point(point))
        assert not (staging / "assets" / "logo.png").exists()

    def test_marker_written_with_point_id(self, tmp_path, monkeypatch):
        _, backups_dir = _wire_paths(tmp_path, monkeypatch)
        full = _edgecase_full(backups_dir)
        point = {"id": "c_full", "files_needed": [str(full)]}
        staging = Path(backup.prepare_restore_from_point(point))
        marker = json.loads((staging / ".restore_marker").read_text())
        assert marker["restore_point_id"] == "c_full"


# ----------------------------------------------------------------------------
# verify_restore_point_files
# ----------------------------------------------------------------------------

class TestVerifyFiles:
    def test_good_chain_verifies_clean(self, tmp_path):
        full = _edgecase_full(tmp_path / "b")
        assert backup.verify_restore_point_files(
            {"files_needed": [str(full)]}) == []

    def test_missing_and_corrupt_reported(self, tmp_path):
        folder = tmp_path / "b"
        folder.mkdir()
        corrupt = folder / "full_2026-08-01_100000.zip"
        corrupt.write_bytes(b"this is not a zip")
        problems = backup.verify_restore_point_files({
            "files_needed": [str(corrupt), str(folder / "gone.zip")]})
        assert len(problems) == 2
        assert any("not a readable zip" in p for p in problems)
        assert any("missing" in p for p in problems)


# ----------------------------------------------------------------------------
# Routes: public on first run, dead once a database exists
# ----------------------------------------------------------------------------

# bare_client (the unauthenticated no-db Flask client these routes exist
# for) lives in conftest.py, shared with test_restore_credentials.py.

HOST = {"Host": "localhost:8080"}


def _set_first_run(monkeypatch, value):
    from web.blueprints import auth as auth_mod
    monkeypatch.setattr(auth_mod, "is_first_run", lambda: value)


def _csrf(client):
    """Mint the recovery CSRF token into the test session."""
    with client.session_transaction() as sess:
        sess["recovery_csrf"] = "test-token"
    return {"X-CSRF-Token": "test-token", **HOST}


class TestRecoveryRoutes:
    def test_page_renders_on_first_run(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, True)
        resp = bare_client.get("/restore", headers=HOST)
        assert resp.status_code == 200
        assert b"Restore from a backup" in resp.data

    def test_page_redirects_once_database_exists(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, False)
        resp = bare_client.get("/restore", headers=HOST)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_json_routes_dead_once_database_exists(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, False)
        headers = _csrf(bare_client)
        for url in ("/restore/search", "/restore/scan",
                    "/restore/browse", "/restore/prepare"):
            resp = bare_client.post(url, json={}, headers=headers)
            assert resp.status_code == 403, url

    def test_json_routes_require_csrf(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, True)
        resp = bare_client.post("/restore/search", json={}, headers=HOST)
        assert resp.status_code == 403

    def test_scan_finds_points_in_folder(self, bare_client, monkeypatch, tmp_path):
        _set_first_run(monkeypatch, True)
        folder = tmp_path / "b"
        _edgecase_full(folder)
        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/scan",
                                json={"folder": str(folder)}, headers=headers)
        data = resp.get_json()
        assert resp.status_code == 200 and data["success"]
        assert data["source"] == "reconstructed"
        assert len(data["restore_points"]) == 1

    def test_scan_refuses_foreign_folder(self, bare_client, monkeypatch, tmp_path):
        _set_first_run(monkeypatch, True)
        folder = tmp_path / "b"
        _mailrepo_full(folder)
        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/scan",
                                json={"folder": str(folder)}, headers=headers)
        assert resp.status_code == 400
        assert "different application" in resp.get_json()["error"]

    def test_prepare_stages_restore(self, bare_client, monkeypatch, tmp_path):
        _set_first_run(monkeypatch, True)
        _wire_paths(tmp_path, monkeypatch)
        folder = tmp_path / "cloud"
        _edgecase_full(folder, "full_2026-08-01_100000.zip")
        headers = _csrf(bare_client)

        scan = bare_client.post("/restore/scan",
                                json={"folder": str(folder)},
                                headers=headers).get_json()
        point_id = scan["restore_points"][0]["id"]

        resp = bare_client.post("/restore/prepare",
                                json={"folder": str(folder),
                                      "restore_point_id": point_id},
                                headers=headers)
        data = resp.get_json()
        assert resp.status_code == 200 and data["success"], data
        staging = tmp_path / ".restore_staging"
        assert (staging / ".restore_marker").exists()
        assert (staging / "data" / "edgecase.db").read_bytes() == b"db-bytes"

    def test_prepare_unknown_point_404(self, bare_client, monkeypatch, tmp_path):
        _set_first_run(monkeypatch, True)
        _wire_paths(tmp_path, monkeypatch)
        folder = tmp_path / "cloud"
        _edgecase_full(folder)
        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/prepare",
                                json={"folder": str(folder),
                                      "restore_point_id": "nope"},
                                headers=headers)
        assert resp.status_code == 404

    def test_login_page_offers_restore_on_first_run(self, bare_client, monkeypatch):
        _set_first_run(monkeypatch, True)
        resp = bare_client.get("/login", headers=HOST)
        assert resp.status_code == 200
        # Case-insensitive: the offer is what matters, not the copy's casing
        # (the notice moved below the Create button and got recapitalized).
        assert b"restore from a backup" in resp.data.lower()
        assert b"/restore" in resp.data


class TestPickerShortcuts:
    """The folder picker must be able to REACH an external drive — the
    empty-state text promises it, and '..' navigation to /Volumes is not
    something a stressed non-technical user will discover."""

    def test_home_and_standard_folders(self, tmp_path):
        home = tmp_path / "home"
        (home / "Desktop").mkdir(parents=True)
        (home / "Documents").mkdir()
        result = backup.picker_shortcuts(home=home, volumes_root=tmp_path / "novol",
                                         media_roots=[])
        names = [s["name"] for s in result]
        assert names == ["Home", "Desktop", "Documents"]
        assert all((tmp_path / "home") in Path(s["path"]).parents
                   or Path(s["path"]) == home for s in result)

    def test_missing_folders_are_omitted_not_invented(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        result = backup.picker_shortcuts(home=home, volumes_root=tmp_path / "novol",
                                         media_roots=[])
        assert [s["name"] for s in result] == ["Home"]

    def test_icloud_drive_when_present(self, tmp_path):
        home = tmp_path / "home"
        icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        icloud.mkdir(parents=True)
        result = backup.picker_shortcuts(home=home, volumes_root=tmp_path / "novol",
                                         media_roots=[])
        assert {"name": "iCloud Drive", "path": str(icloud)} in result

    def test_external_volumes_listed_by_name(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        volumes = tmp_path / "Volumes"
        (volumes / "Backup HD").mkdir(parents=True)
        (volumes / "USB Stick").mkdir()
        (volumes / "somefile.txt").write_text("not a volume")
        result = backup.picker_shortcuts(home=home, volumes_root=volumes,
                                         media_roots=[])
        names = [s["name"] for s in result]
        assert "Backup HD" in names and "USB Stick" in names
        assert "somefile.txt" not in names

    def test_boot_volume_link_is_skipped(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        volumes = tmp_path / "Volumes"
        volumes.mkdir()
        (volumes / "Real Drive").mkdir()
        (volumes / "Macintosh HD").symlink_to("/")
        result = backup.picker_shortcuts(home=home, volumes_root=volumes,
                                         media_roots=[])
        names = [s["name"] for s in result]
        assert "Real Drive" in names
        assert "Macintosh HD" not in names

    def test_browse_response_carries_shortcuts(self, bare_client, monkeypatch,
                                               tmp_path):
        _wire_paths(tmp_path, monkeypatch)
        headers = _csrf(bare_client)
        resp = bare_client.post("/restore/browse", json={"path": str(tmp_path)},
                                headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert isinstance(data["shortcuts"], list)
        assert any(s["name"] == "Home" for s in data["shortcuts"])
