"""Attachment lifecycle route tests (database.py refactor Step 2).

Exercises the filesystem seam end-to-end through real routes: upload (multipart)
-> download (bytes back) -> view (inline) -> delete (DB row + file gone).

save_uploaded_files writes under ATTACHMENTS_DIR and stores the path relative to
DATA_ROOT; resolve_attachment_path re-resolves against DATA_ROOT. To keep the
test hermetic (and never touch the real attachments tree) all three are pointed
at one temp root.
"""
import os
from io import BytesIO

import pytest


@pytest.fixture
def temp_attachments(tmp_path, monkeypatch):
    """Redirect the attachment storage + data root to a temp tree."""
    import web.utils as wu
    import web.blueprints.entries as ent

    root = tmp_path
    monkeypatch.setattr(wu, "DATA_ROOT", root)
    monkeypatch.setattr(wu, "ATTACHMENTS_DIR", root / "attachments")
    monkeypatch.setattr(ent, "DATA_ROOT", root)
    return root


def _make_client(db):
    return db.add_client({
        "file_number": "AT-001",
        "first_name": "Att",
        "middle_name": "",
        "last_name": "Achment",
        "type_id": 1,
    })


def _attachments(db):
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id, filename, filepath FROM attachments")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def test_attachment_upload_download_delete_roundtrip(
        client, app_db, temp_attachments):
    cid = _make_client(app_db)
    payload = b"clinician note body"

    # 1. Upload (multipart) -> creates an 'upload' entry + attachment record.
    resp = client.post(
        f"/client/{cid}/upload",
        data={
            "description": "Intake form",
            "date": "2026-06-19",
            "files[]": (BytesIO(payload), "note.txt"),
            "file_descriptions[]": "Scanned intake",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302

    rows = _attachments(app_db)
    assert len(rows) == 1
    att = rows[0]
    assert att["filename"] == "note.txt"
    # Stored relative to DATA_ROOT, physically under the temp tree.
    resolved = temp_attachments / att["filepath"]
    assert resolved.exists()

    # 2. Download -> original bytes come back (db unencrypted in tests).
    resp = client.get(f"/attachment/{att['id']}/download")
    assert resp.status_code == 200
    assert resp.data == payload

    # 3. View -> .txt is on the inline-safe allowlist, served 200.
    resp = client.get(f"/attachment/{att['id']}/view")
    assert resp.status_code == 200

    # 4. Delete -> DB record removed and file gone from disk.
    resp = client.post(f"/attachment/{att['id']}/delete")
    assert resp.status_code == 200
    assert _attachments(app_db) == []
    assert not resolved.exists()
    # The now-dangling id 404s.
    assert client.get(f"/attachment/{att['id']}/download").status_code == 404
