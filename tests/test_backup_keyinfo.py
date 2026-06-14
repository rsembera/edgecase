"""The v2 key-info file must be in the backup set, or a restored v2 install
cannot derive its raw key (same role .salt plays for v1)."""
from utils import backup


def test_keyinfo_included_when_present(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "edgecase.db").write_bytes(b"db")
    (data / ".salt").write_bytes(b"salt")
    (data / ".keyinfo").write_bytes(b"ECC2keyinfo")

    monkeypatch.setattr(backup, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "ASSETS_DIR", tmp_path / "assets")

    files = backup.get_all_backup_files()
    assert "data/.keyinfo" in files
    assert files["data/.keyinfo"] == data / ".keyinfo"


def test_keyinfo_absent_on_v1(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "edgecase.db").write_bytes(b"db")
    (data / ".salt").write_bytes(b"salt")  # v1: no .keyinfo

    monkeypatch.setattr(backup, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "ASSETS_DIR", tmp_path / "assets")

    files = backup.get_all_backup_files()
    assert "data/.keyinfo" not in files
    assert "data/.salt" in files
