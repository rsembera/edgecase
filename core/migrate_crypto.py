"""
EdgeCase crypto v1 -> v2 migration runner.

Migrates a v1 install (Fernet files + passphrase-keyed SQLCipher) to v2
(Argon2id -> AES-256-GCM files + raw-keyed SQLCipher), in place, on the user's
machine. Designed to run unattended right after the user enters their password
at login, before anything opens the database.

Safety model (see Architecture_Decisions.md, Attachment Encryption v2):
  1. Full verified backup first (reuses utils.backup). Abort if it fails.
  2. Write a `.v2_migrating` marker recording the backup to restore from.
  3. Re-encrypt every v1 file in place (atomic per file; resumable: a file
     already in v2 form is skipped).
  4. Build the raw-keyed DB as a SEPARATE file and verify it (integrity_check +
     row-count parity). The original DB is untouched until this passes.
  5. Commit: swap the verified DB in, clear stale WAL, then write `.keyinfo`
     (the commit point — its presence means "migrated").
  6. Remove the marker.

recover_if_interrupted() runs at startup. It needs no password: `.keyinfo` is
written only after the DB swap, so its presence proves the migration reached
commit -> finalize (clear stale state, drop marker). Its absence with a marker
present means an interrupted run -> roll back to the backup. No crash point can
leave the user locked out: the result is always fully-v2 or fully-v1.

Precondition: no other SQLCipher connection to the database is open while
migrate() or recover_if_interrupted() runs.

The `root` parameter (default: live config paths) exists for testing against a
temporary install directory.
"""
import base64
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import sqlcipher3 as sqlite3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import core.config as config
from core import encryption_v2 as v2


@dataclass
class _Paths:
    data_dir: Path
    attachments_dir: Path
    assets_dir: Path
    backups_dir: Path
    data_root: Path
    keyinfo: Path

    @property
    def db(self):
        return self.data_dir / "edgecase.db"

    @property
    def new_db(self):
        return self.data_dir / "edgecase.db.v2new"

    @property
    def marker(self):
        return self.data_dir / ".v2_migrating"

    @property
    def salt_file(self):
        return self.data_dir / ".salt"


def _resolve_paths(root):
    if root is None:
        return _Paths(config.DATA_DIR, config.ATTACHMENTS_DIR, config.ASSETS_DIR,
                      config.BACKUPS_DIR, config.DATA_ROOT, v2.KEYINFO_FILE)
    root = Path(root)
    return _Paths(root / "data", root / "attachments", root / "assets",
                  root / "backups", root, root / "data" / ".keyinfo")


def _old_fernet(password: str, salt: bytes) -> Fernet:
    # Mirrors core.encryption._get_fernet exactly (PBKDF2-SHA256, 480k iters).
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=480000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode())))


def _candidate_files(paths: _Paths):
    """The exact set of encrypted files the backup also covers, so rollback can
    always restore anything the migration touches: all attachments plus the
    logo/signature in assets."""
    files = []
    if paths.attachments_dir.exists():
        files += [p for p in paths.attachments_dir.rglob("*")
                  if p.is_file() and not p.name.startswith(".")]
    if paths.assets_dir.exists():
        files += [p for p in paths.assets_dir.iterdir()
                  if p.is_file() and p.stem in ("logo", "signature")]
    return files


def _reencrypt_file(path: Path, old_fernet: Fernet, file_key: bytes) -> str:
    """Re-encrypt one file v1 -> v2 in place, atomically. Returns the outcome."""
    blob = path.read_bytes()
    if v2.is_v2(blob):
        return "skip_v2"
    if not v2.is_v1(blob):
        return "skip_plain"
    plain = old_fernet.decrypt(blob)
    new_blob = v2.encrypt_bytes(file_key, plain)
    tmp = str(path) + ".v2tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(new_blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    return "migrated"


def _build_raw_keyed_db(paths: _Paths, password: str, db_key_hex: str):
    """Export the v1 (passphrase) DB into a fresh raw-keyed DB and verify it.
    Raises on integrity failure or row-count mismatch. Leaves the original DB
    untouched; the result is written to paths.new_db."""
    src, dst = str(paths.db), str(paths.new_db)
    for p in (dst, dst + "-wal", dst + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    esc = password.replace("'", "''")

    con = sqlite3.connect(src)
    con.execute(f"PRAGMA key = '{esc}'")
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]
    src_counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in tables}
    con.execute(f"ATTACH DATABASE '{dst}' AS v2db KEY \"x'{db_key_hex}'\"")
    con.execute("SELECT sqlcipher_export('v2db')")
    con.execute("DETACH DATABASE v2db")
    con.close()

    ver = sqlite3.connect(dst)
    ver.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    integrity = ver.execute("PRAGMA integrity_check").fetchone()[0]
    dst_counts = {t: ver.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in tables}
    ver.close()
    for p in (dst + "-wal", dst + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    if integrity != "ok":
        raise RuntimeError(f"new DB failed integrity_check: {integrity!r}")
    if src_counts != dst_counts:
        raise RuntimeError("new DB row counts differ from source")


def _backup_file_set(paths: _Paths):
    """{arcname-relative-to-data_root: absolute_path} — mirrors backup scope."""
    files = {}
    if paths.db.exists():
        files["data/edgecase.db"] = paths.db
    for name in ("edgecase.db-wal", ".salt", ".secret_key"):
        p = paths.data_dir / name
        if p.exists():
            files[f"data/{name}"] = p
    for p in _candidate_files(paths):
        files[str(p.relative_to(paths.data_root))] = p
    return files


def _zip_backup(paths: _Paths) -> dict:
    """Self-contained backup used for non-live (test) roots."""
    paths.backups_dir.mkdir(parents=True, exist_ok=True)
    name = "pre_v2_migration.zip"
    out = paths.backups_dir / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, abs_path in _backup_file_set(paths).items():
            zf.write(abs_path, arc)
    return {"filename": name, "backup_dir": str(paths.backups_dir)}


def _live_backup() -> dict:
    from utils import backup as backup_mod
    return backup_mod.create_full_backup()


def _extract_backup(backup_path: Path, data_root: Path):
    with zipfile.ZipFile(backup_path) as zf:
        for entry in zf.namelist():
            dest = data_root / entry
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(entry) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


def _write_marker(paths: _Paths, backup_info: dict):
    paths.marker.write_text(json.dumps({
        "backup_filename": backup_info["filename"],
        "backup_dir": backup_info.get("backup_dir", str(paths.backups_dir)),
    }))


def _commit(paths: _Paths, salt: bytes, file_key: bytes):
    # Drop the freshly-built DB's own sidecars so they don't follow the swap.
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.new_db) + sfx)
        if s.exists():
            s.unlink()
    # Atomic swap: edgecase.db is now the raw-keyed database.
    os.replace(str(paths.new_db), str(paths.db))
    # Remove the OLD passphrase DB's stale sidecars (they would corrupt reads).
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.db) + sfx)
        if s.exists():
            s.unlink()
    # COMMIT POINT: once .keyinfo exists, the install is detected as v2.
    v2.write_keyinfo(salt, v2.make_verification_token(file_key), path=paths.keyinfo)
    os.chmod(str(paths.db), 0o600)


def _rollback(paths: _Paths, backup_filename: str, backup_dir: str):
    """Restore the pre-migration backup, leaving a clean v1 install."""
    # Drop every v2 artifact first.
    for p in (paths.keyinfo, paths.new_db,
              Path(str(paths.new_db) + "-wal"), Path(str(paths.new_db) + "-shm"),
              Path(str(paths.db) + "-wal"), Path(str(paths.db) + "-shm")):
        if p.exists():
            p.unlink()
    # Clear any half-written per-file temps.
    for base in (paths.attachments_dir, paths.assets_dir):
        if base.exists():
            for tmp in base.rglob("*.v2tmp"):
                tmp.unlink()
    # Restore v1 content (DB + all files) from the backup.
    _extract_backup(Path(backup_dir) / backup_filename, paths.data_root)
    v2._key_cache.clear()


def needs_migration(root=None) -> bool:
    """True for a v1 install that should be migrated (DB exists, not yet v2,
    and no interrupted migration pending — that case is recover_if_interrupted's)."""
    paths = _resolve_paths(root)
    return (paths.db.exists()
            and not v2.keyinfo_exists(path=paths.keyinfo)
            and not paths.marker.exists())


def migrate(password: str, root=None, backup_fn=None, progress_cb=None) -> dict:
    """Run the in-place v1 -> v2 migration. Returns a summary dict.

    On any failure, rolls back to the pre-migration backup and re-raises, so
    the caller is left on a clean v1 install. A hard crash (no rollback runs)
    is handled by recover_if_interrupted() at the next startup.
    """
    paths = _resolve_paths(root)
    if v2.keyinfo_exists(path=paths.keyinfo):
        return {"status": "already_v2", "files_migrated": 0}
    if backup_fn is None:
        backup_fn = _live_backup if root is None else (lambda: _zip_backup(paths))

    salt = v2.new_salt()
    db_key_hex, file_key = v2.derive_subkeys(v2.derive_master(password, salt))
    old_fernet = _old_fernet(password, paths.salt_file.read_bytes())

    # Checkpoint the old DB so the backup captures a complete .db file.
    try:
        c = sqlite3.connect(str(paths.db))
        c.execute(f"PRAGMA key = '{password.replace(chr(39), chr(39) * 2)}'")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass  # best-effort; the WAL sidecar is backed up regardless

    backup_info = backup_fn()
    _write_marker(paths, backup_info)
    try:
        files = _candidate_files(paths)
        migrated = 0
        for i, fp in enumerate(files):
            if _reencrypt_file(fp, old_fernet, file_key) == "migrated":
                migrated += 1
            if progress_cb:
                progress_cb(i + 1, len(files))
        _build_raw_keyed_db(paths, password, db_key_hex)
        _commit(paths, salt, file_key)
        paths.marker.unlink()
        v2._key_cache.clear()
        return {"status": "migrated", "files_migrated": migrated,
                "files_total": len(files)}
    except Exception:
        _rollback(paths, backup_info["filename"],
                  backup_info.get("backup_dir", str(paths.backups_dir)))
        if paths.marker.exists():
            paths.marker.unlink()
        raise


def recover_if_interrupted(root=None) -> str:
    """At startup: finalize a completed-but-uncleaned migration, or roll back an
    interrupted one. No password needed — .keyinfo is written only after the DB
    swap, so its presence proves the migration reached commit. Returns
    'finalized', 'rolled_back', or 'none'."""
    paths = _resolve_paths(root)
    if not paths.marker.exists():
        return "none"
    marker = json.loads(paths.marker.read_text())

    if v2.keyinfo_exists(path=paths.keyinfo):
        # Commit was reached; just finish the idempotent cleanup.
        if paths.new_db.exists():
            paths.new_db.unlink()
        for sfx in ("-wal", "-shm"):
            s = Path(str(paths.db) + sfx)
            if s.exists():
                s.unlink()
        paths.marker.unlink()
        return "finalized"

    _rollback(paths, marker["backup_filename"], marker["backup_dir"])
    paths.marker.unlink()
    return "rolled_back"
