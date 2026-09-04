"""One-time rename pass for readable attachment filenames (Attachment_Filename_Fix_Plan).

Everything runs against a temp tree and a plain sqlite database with just the
attachments table — the pass never reads file contents, so encryption state is
irrelevant to it, and the real install is never touched.
"""
import os
import sqlite3
from pathlib import Path

import pytest

from core import attachment_names as an


@pytest.fixture
def tree(tmp_path):
    """A DATA_ROOT with an attachments/ tree and a bare attachments table."""
    root = tmp_path
    (root / "attachments").mkdir()
    con = sqlite3.connect(":memory:")
    con.execute("""
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY, entry_id INTEGER, filename TEXT,
            description TEXT, filepath TEXT NOT NULL, filesize INTEGER,
            uploaded_at INTEGER)
    """)
    return root, con


def _plant(root, rel, payload=b"\x02ciphertext"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(payload)
    return p


def _add_row(con, filename, filepath):
    cur = con.execute(
        "INSERT INTO attachments (entry_id, filename, description, filepath, "
        "filesize, uploaded_at) VALUES (1, ?, '', ?, 0, 0)", (filename, filepath))
    con.commit()
    return cur.lastrowid


def _run(root, con, **kw):
    return an.rename_readable_attachments(
        con, attachments_dir=root / "attachments", data_root=root,
        log=lambda *_: None, **kw)


def _filepath(con, row_id):
    return con.execute("SELECT filepath FROM attachments WHERE id = ?",
                       (row_id,)).fetchone()[0]


# --- The fix itself ---

def test_readable_statement_is_renamed_and_row_updated_together(tree):
    root, con = tree
    old = _plant(root, "attachments/2/6/Statement_20251102-KL_20260302.pdf",
                 b"\x02statement-bytes")
    row = _add_row(con, "Statement_20251102-KL_20260302.pdf", str(old))

    summary = _run(root, con)

    assert summary["renamed"] == 1
    new_value = _filepath(con, row)
    assert an.is_anonymized_name(Path(new_value).name)
    assert Path(new_value).parent == old.parent          # same directory
    assert Path(new_value).read_bytes() == b"\x02statement-bytes"
    assert not old.exists()
    # Display name is untouched.
    assert con.execute("SELECT filename FROM attachments").fetchone()[0] == \
        "Statement_20251102-KL_20260302.pdf"


def test_relative_paths_stay_relative(tree):
    """web/utils.py stores paths relative to DATA_ROOT; a renamed row keeps
    whichever style it had so resolve_attachment_path behaves the same."""
    root, con = tree
    _plant(root, "attachments/ledger/7/2025-12-KL.pdf")
    row = _add_row(con, "2025-12-KL.pdf", "attachments/ledger/7/2025-12-KL.pdf")

    _run(root, con)

    new_value = _filepath(con, row)
    assert not os.path.isabs(new_value)
    assert new_value.startswith("attachments/ledger/7/")
    assert (root / new_value).exists()


def test_already_anonymized_rows_are_skipped(tree):
    root, con = tree
    name = "5e08ddf6-4ba0-488b-aedd-44d768b5e111.enc"
    p = _plant(root, f"attachments/9/118/{name}")
    row = _add_row(con, "note.pdf", str(p))

    summary = _run(root, con)

    assert summary["renamed"] == 0
    assert summary["already_anonymized"] == 1
    assert _filepath(con, row) == str(p)
    assert p.exists()


def test_pass_is_idempotent(tree):
    root, con = tree
    old = _plant(root, "attachments/2/6/Statement_X_1.pdf")
    row = _add_row(con, "Statement_X_1.pdf", str(old))

    first = _run(root, con)
    after_first = _filepath(con, row)
    second = _run(root, con)

    assert first["renamed"] == 1
    assert second["renamed"] == 0
    assert second["already_anonymized"] == 1
    assert _filepath(con, row) == after_first
    assert Path(after_first).exists()


def test_file_with_no_row_is_reported_not_renamed(tree):
    root, con = tree
    orphan = _plant(root, "attachments/3/40/Statement_ORPHAN_1.pdf")

    summary = _run(root, con)

    assert summary["renamed"] == 0
    assert summary["orphans"] == [str(orphan)]
    assert orphan.exists()
    assert list((root / "attachments").rglob("*.enc")) == []


def test_row_with_missing_file_is_reported_not_updated(tree):
    root, con = tree
    row = _add_row(con, "gone.pdf", str(root / "attachments/1/1/gone.pdf"))

    summary = _run(root, con)

    assert summary["missing"] == [str(root / "attachments/1/1/gone.pdf")]
    assert _filepath(con, row) == str(root / "attachments/1/1/gone.pdf")


def test_dotfiles_are_ignored(tree):
    root, con = tree
    ds = _plant(root, "attachments/2/.DS_Store", b"junk")

    summary = _run(root, con)

    assert summary["orphans"] == []
    assert ds.exists()


def test_failed_rename_leaves_the_row_unchanged(tree, monkeypatch):
    """A refused rename must not leave the database pointing at a name that
    does not exist on disk."""
    root, con = tree
    old = _plant(root, "attachments/2/6/Statement_X_1.pdf")
    row = _add_row(con, "Statement_X_1.pdf", str(old))

    def refuse(src, dst):
        raise PermissionError("read-only volume")
    monkeypatch.setattr(an.os, "rename", refuse)

    summary = _run(root, con)

    assert summary["renamed"] == 0
    assert len(summary["failed"]) == 1
    assert _filepath(con, row) == str(old)
    assert old.exists()


def test_failed_commit_moves_the_file_back(tree, monkeypatch):
    """The commit is the one step that can fail after the disk has moved."""
    root, con = tree
    old = _plant(root, "attachments/2/6/Statement_X_1.pdf")
    row = _add_row(con, "Statement_X_1.pdf", str(old))

    class Flaky:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, *a, **k):
            return self._inner.execute(*a, **k)

        def commit(self):
            raise sqlite3.OperationalError("disk I/O error")

        def rollback(self):
            return self._inner.rollback()

    summary = an.rename_readable_attachments(
        Flaky(con), attachments_dir=root / "attachments", data_root=root,
        log=lambda *_: None)

    assert summary["renamed"] == 0
    assert len(summary["failed"]) == 1
    assert old.exists(), "file was not moved back after the failed commit"
    assert _filepath(con, row) == str(old)
    assert list(old.parent.glob("*.enc")) == []


def test_mixed_tree_matches_the_live_install_shape(tree):
    """The shape the plan describes: UUID uploads, readable statements, two
    pre-UUID uploads on ledger/client paths, and .DS_Store droppings."""
    root, con = tree
    rows = {}
    for rel in ("attachments/2/6/2025-12-KL.pdf",
                "attachments/ledger/7/2025-12-KL.pdf",
                "attachments/2/50/Statement_20251209-BB_20251210.pdf",
                "attachments/5/59/Statement_20251209-EE_20251210.pdf"):
        p = _plant(root, rel)
        rows[rel] = _add_row(con, Path(rel).name, str(p))
    for rel in ("attachments/9/118/5e08ddf6-4ba0-488b-aedd-44d768b5e111.enc",
                "attachments/5/105/2c1a7ff7-1866-491a-b6b9-9e5e58ef47f4.enc"):
        p = _plant(root, rel)
        rows[rel] = _add_row(con, "upload.pdf", str(p))
    _plant(root, "attachments/.DS_Store", b"x")
    _plant(root, "attachments/2/.DS_Store", b"x")

    summary = _run(root, con)

    assert summary["renamed"] == 4
    assert summary["already_anonymized"] == 2
    assert summary["orphans"] == [] and summary["missing"] == []
    for name in (p.name for p in (root / "attachments").rglob("*") if p.is_file()):
        assert name.startswith(".") or an.is_anonymized_name(name), name
    # Every row still resolves to a real file.
    for stored, in con.execute("SELECT filepath FROM attachments"):
        assert Path(stored).exists(), stored


# --- Wiring: the pass runs when a login opens the database ---

def test_login_runs_the_rename_pass(bare_client, monkeypatch, tmp_path):
    """End to end on a synthetic install: create it (first-run login + upgrade
    stream), plant a readable-named statement row the old writer would have
    left, log in again, and the file is anonymized before the app opens."""
    import re
    import core.config as config
    from core import encryption_v2 as v2
    from web.app import app as flask_app

    data_dir = tmp_path / "data"
    for name in ("data", "attachments", "assets", "backups"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(config, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(v2, "KEYINFO_FILE", data_dir / ".keyinfo")
    monkeypatch.setattr("flask_wtf.csrf.validate_csrf", lambda *a, **k: None)

    pw = "fresh-install-pw!"
    body = bare_client.post("/login", data={"password": pw, "confirm_password": pw},
                            headers={"Host": "localhost"}).get_data(as_text=True)
    token = re.search(r"token=([A-Za-z0-9_\-]+)", body).group(1)
    stream = bare_client.get(f"/migrate/stream?token={token}",
                             headers={"Host": "localhost"})
    assert "complete" in stream.get_data(as_text=True)  # drives the generator
    db = flask_app.config["db"]
    assert db is not None

    import time
    cid = db.add_client({"file_number": "20251102-KL", "first_name": "K",
                         "middle_name": "", "last_name": "L", "type_id": 1})
    now = int(time.time())
    eid = db.add_entry({"client_id": cid, "class": "communication",
                        "description": "Statement Sent", "created_at": now,
                        "modified_at": now})
    old = _plant(tmp_path, f"attachments/{cid}/{eid}/Statement_20251102-KL_20260302.pdf")
    con = db.connect()
    con.execute(
        "INSERT INTO attachments (entry_id, filename, description, filepath, "
        "filesize, uploaded_at) VALUES (?, ?, '', ?, 0, 0)",
        (eid, "Statement_20251102-KL_20260302.pdf", str(old)))
    con.commit()
    db.close()

    resp = bare_client.post("/login", data={"password": pw},
                            headers={"Host": "localhost"})
    assert resp.status_code == 302

    stored = flask_app.config["db"].connect().execute(
        "SELECT filepath FROM attachments").fetchone()[0]
    assert an.is_anonymized_name(Path(stored).name), stored
    assert Path(stored).exists()
    assert not old.exists()
    flask_app.config["db"].close()


# --- Relocation: absolute paths from a previous install location ------------

def test_absolute_path_from_an_old_install_location_is_adopted_and_renamed(tree):
    """Found in the fictional test install: rows written as
    /Users/x/apps/edgecase-testing/attachments/8/97/Statement_….pdf after the
    folder had moved. The file is right there under the current tree; the
    row must be re-pointed (relative from now on) AND anonymized."""
    root, con = tree
    here = _plant(root, "attachments/8/97/Statement_20251209-HG_20260103.pdf",
                  b"\x02moved")
    row = _add_row(con, "Statement_20251209-HG_20260103.pdf",
                   "/Users/x/apps/old-install/attachments/8/97/Statement_20251209-HG_20260103.pdf")

    summary = _run(root, con)

    assert summary["relocated"] == 1 and summary["renamed"] == 1
    assert summary["missing"] == [] and summary["orphans"] == []
    new_value = _filepath(con, row)
    assert not os.path.isabs(new_value)
    assert new_value.startswith("attachments/8/97/")
    assert an.is_anonymized_name(Path(new_value).name)
    assert (root / new_value).read_bytes() == b"\x02moved"
    assert not here.exists()


def test_relocated_uuid_row_is_repointed_without_renaming(tree):
    root, con = tree
    name = "5e08ddf6-4ba0-488b-aedd-44d768b5e111.enc"
    here = _plant(root, f"attachments/9/118/{name}")
    row = _add_row(con, "note.pdf", f"/old/place/attachments/9/118/{name}")

    summary = _run(root, con)

    assert summary["relocated"] == 1 and summary["renamed"] == 0
    assert _filepath(con, row) == f"attachments/9/118/{name}"
    assert here.exists()


def test_relocation_requires_an_exact_tail_match(tree):
    """A file for a different client/entry with the same name must not be
    adopted; the row stays 'missing'."""
    root, con = tree
    _plant(root, "attachments/3/40/Statement_X.pdf")
    row = _add_row(con, "Statement_X.pdf", "/old/place/attachments/2/40/Statement_X.pdf")

    summary = _run(root, con)

    assert summary["relocated"] == 0
    assert summary["missing"] == ["/old/place/attachments/2/40/Statement_X.pdf"]
    assert summary["orphans"] == [str(root / "attachments/3/40/Statement_X.pdf")]
    assert _filepath(con, row) == "/old/place/attachments/2/40/Statement_X.pdf"


def test_never_renames_a_file_outside_this_installs_tree(tree, tmp_path_factory):
    """A database restored from ANOTHER install on the same machine carries
    that install's absolute paths. Following them would rename the other
    install's files while updating only this database. Found the hard way
    against a copy of the fictional test install."""
    root, con = tree
    other = tmp_path_factory.mktemp("other-install")
    theirs = other / "attachments" / "2" / "117" / "Statement_20251209-BB_20260309.pdf"
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(b"\x02theirs")
    row = _add_row(con, "Statement_20251209-BB_20260309.pdf", str(theirs))

    summary = _run(root, con)

    assert theirs.exists(), "renamed a file outside the install"
    assert theirs.read_bytes() == b"\x02theirs"
    assert summary["renamed"] == 0
    assert summary["outside_tree"] == [str(theirs)]
    assert _filepath(con, row) == str(theirs)


def test_outside_tree_row_is_relocated_when_the_file_is_also_here(tree, tmp_path_factory):
    """Same shape as above, but the file also exists under the current tree
    at the same tail — the install was moved and the old location still
    exists. Adopt ours, leave theirs alone."""
    root, con = tree
    other = tmp_path_factory.mktemp("other-install")
    theirs = other / "attachments" / "2" / "117" / "Statement_X.pdf"
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(b"\x02theirs")
    ours = _plant(root, "attachments/2/117/Statement_X.pdf", b"\x02ours")
    row = _add_row(con, "Statement_X.pdf", str(theirs))

    summary = _run(root, con)

    assert theirs.exists() and theirs.read_bytes() == b"\x02theirs"
    assert summary["relocated"] == 1 and summary["renamed"] == 1
    new_value = _filepath(con, row)
    assert new_value.startswith("attachments/2/117/")
    assert (root / new_value).read_bytes() == b"\x02ours"
    assert not ours.exists()
