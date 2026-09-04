"""Pin the on-disk attachment-naming invariant across EVERY writer.

The rule — "no client information in the filesystem" — existed only as a
comment in web/utils.py, which is why a second writer (statement delivery)
could violate it silently for months: generated statement PDFs were stored
as Statement_<file_number>_<date>.pdf, disclosing initials, intake date and
billing month to anyone who could list the directory or a backup zip.

This test exercises BOTH code paths that write into ATTACHMENTS_DIR — the
upload path and the statement-delivery path — and then asserts that no file
under the tree has a name derived from client data. A third writer would
have to pass here too. Written red-first against the defective delivery.py.
"""
import re
from io import BytesIO
from pathlib import Path

import pytest

UUID_ENC = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.enc$")

FILE_NUMBER = "20251102-KL"


@pytest.fixture
def attachments_root(tmp_path, monkeypatch):
    """One temp tree for every module that reads or writes attachments."""
    import web.utils as wu
    import web.blueprints.entries.common as ent_common
    import web.blueprints.statements.delivery as delivery

    root = tmp_path
    monkeypatch.setattr(wu, "DATA_ROOT", root)
    monkeypatch.setattr(wu, "ATTACHMENTS_DIR", root / "attachments")
    monkeypatch.setattr(ent_common, "DATA_ROOT", root)
    monkeypatch.setattr(delivery, "ATTACHMENTS_DIR", root / "attachments")

    def _fake_pdf(database, portion_id, out_path, assets_dir):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4 test\n")

    monkeypatch.setattr(delivery, "generate_statement_pdf", _fake_pdf)
    return root


def _make_client(db):
    return db.add_client({
        "file_number": FILE_NUMBER,
        "first_name": "Kara",
        "middle_name": "",
        "last_name": "Lindqvist",
        "type_id": 1,
    })


def _upload(client, cid):
    resp = client.post(
        f"/client/{cid}/upload",
        data={
            "description": "Intake form",
            "date": "2026-06-19",
            "files[]": (BytesIO(b"intake body"), "Intake_Lindqvist.pdf"),
            "file_descriptions[]": "Scanned intake",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302


def _deliver_statement(client, db, cid):
    """Generate a statement for a locked session and mark it sent
    (generate-only mode, so no email step)."""
    import time
    from datetime import datetime

    now = int(time.time())
    sid = db.add_entry({
        "client_id": cid,
        "class": "session",
        "description": "Session 1",
        "session_number": 1,
        "session_date": int(datetime(2026, 6, 10).timestamp()),
        "base_fee": 100.0,
        "tax_rate": 13.0,
        "fee": 113.0,
        "is_consultation": 0,
        "created_at": now,
        "modified_at": now,
    })
    db.lock_entry(sid)
    resp = client.post(
        "/statements/generate",
        json={"client_ids": [cid], "start_date": "2026-06-01",
              "end_date": "2026-06-30"},
    )
    assert resp.status_code == 200 and resp.get_json()["success"]

    conn = db.connect()
    portion_id = conn.execute(
        "SELECT id FROM statement_portions WHERE client_id = ?", (cid,)
    ).fetchone()[0]
    resp = client.post(f"/statements/mark-sent/{portion_id}?skip_email=1")
    assert resp.status_code == 200 and resp.get_json()["success"]


def _attachment_rows(db):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT filename, filepath FROM attachments ORDER BY id")
    return cur.fetchall()


def _files_on_disk(root):
    return [p for p in (root / "attachments").rglob("*")
            if p.is_file() and not p.name.startswith(".")]


def test_no_writer_puts_client_data_in_a_filename(client, app_db, attachments_root):
    """Both writers, then one assertion over the whole tree."""
    cid = _make_client(app_db)
    _upload(client, cid)
    _deliver_statement(client, app_db, cid)

    files = _files_on_disk(attachments_root)
    assert len(files) == 2, [p.name for p in files]

    for path in files:
        assert UUID_ENC.match(path.name), f"non-anonymized filename: {path.name}"
        for needle in (FILE_NUMBER, "KL", "Lindqvist", "Statement", "Intake"):
            assert needle not in path.name, f"{needle!r} leaked into {path.name}"


def test_statement_display_name_is_kept_in_the_database(client, app_db, attachments_root):
    """Only the on-disk name changes: the user still sees and downloads
    Statement_<file#>_<date>.pdf, exactly as before."""
    cid = _make_client(app_db)
    _deliver_statement(client, app_db, cid)

    rows = _attachment_rows(app_db)
    assert len(rows) == 1
    filename, filepath = rows[0]
    assert filename.startswith(f"Statement_{FILE_NUMBER}_")
    assert filename.endswith(".pdf")
    assert UUID_ENC.match(Path(filepath).name), filepath
    assert Path(filepath).exists()


def test_statement_attachment_still_downloads_under_its_display_name(
        client, app_db, attachments_root):
    cid = _make_client(app_db)
    _deliver_statement(client, app_db, cid)

    conn = app_db.connect()
    att_id, filename = conn.execute(
        "SELECT id, filename FROM attachments").fetchone()
    resp = client.get(f"/attachment/{att_id}/download")
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")
    assert filename in resp.headers.get("Content-Disposition", "")
