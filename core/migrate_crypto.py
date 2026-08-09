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
from core import encryption_v3 as v3


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

    @property
    def rk_pending(self):
        """Set before the v3 commit point, cleared only once the user has typed
        their recovery key back. Records ONLY that acknowledgement is
        outstanding — never the key itself, which is never stored anywhere."""
        return self.data_dir / ".rk_pending"


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


def _reencrypt_file_v2(path: Path, old_file_key: bytes, new_file_key: bytes) -> str:
    """Re-encrypt one v2 file from the old file key to the new one, atomically."""
    blob = path.read_bytes()
    if v2.is_v1(blob):
        return "skip_v1"  # unexpected on a v2 install; leave untouched
    if not v2.is_v2(blob):
        return "skip_plain"
    plain = v2.decrypt_bytes(old_file_key, blob)
    new_blob = v2.encrypt_bytes(new_file_key, plain)
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
    return "rekeyed"


def _export_verify(paths: _Paths, src_key_sql: str, dst_key_hex: str):
    """Open the source DB with src_key_sql, export it into a fresh DB keyed with
    the raw dst_key_hex (written to paths.new_db), and verify it (integrity_check
    + row-count parity). Leaves the original DB untouched until it passes."""
    src, dst = str(paths.db), str(paths.new_db)
    for p in (dst, dst + "-wal", dst + "-shm"):
        if os.path.exists(p):
            os.remove(p)

    con = sqlite3.connect(src)
    con.execute(src_key_sql)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]
    src_counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in tables}
    con.execute(f"ATTACH DATABASE '{dst}' AS newdb KEY \"x'{dst_key_hex}'\"")
    con.execute("SELECT sqlcipher_export('newdb')")
    con.execute("DETACH DATABASE newdb")
    con.close()

    ver = sqlite3.connect(dst)
    ver.execute(f"PRAGMA key = \"x'{dst_key_hex}'\"")
    integrity = ver.execute("PRAGMA integrity_check").fetchone()[0]
    dst_counts = {t: ver.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in tables}
    ver.close()
    for p in (dst + "-wal", dst + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    if integrity != "ok":
        raise RuntimeError(f"rebuilt DB failed integrity_check: {integrity!r}")
    if src_counts != dst_counts:
        raise RuntimeError("rebuilt DB row counts differ from source")


def _build_raw_keyed_db(paths: _Paths, password: str, db_key_hex: str):
    """v1 (passphrase) DB -> fresh raw-keyed DB. See _export_verify."""
    esc = password.replace("'", "''")
    _export_verify(paths, f"PRAGMA key = '{esc}'", db_key_hex)


def _build_rekeyed_db_v2(paths: _Paths, old_db_key_hex: str, new_db_key_hex: str):
    """v2 (old raw key) DB -> fresh DB under the new raw key. See _export_verify."""
    _export_verify(paths, f"PRAGMA key = \"x'{old_db_key_hex}'\"", new_db_key_hex)


def _backup_file_set(paths: _Paths):
    """{arcname-relative-to-data_root: absolute_path} — mirrors backup scope."""
    files = {}
    if paths.db.exists():
        files["data/edgecase.db"] = paths.db
    for name in ("edgecase.db-wal", ".salt", ".secret_key", ".keyinfo",
                 ".rk_pending"):
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


def _write_marker(paths: _Paths, backup_info: dict, kind: str = "migrate_v1v2",
                  new_salt: bytes = None):
    data = {
        "backup_filename": backup_info["filename"],
        "backup_dir": backup_info.get("backup_dir", str(paths.backups_dir)),
        "kind": kind,
    }
    if new_salt is not None:
        data["new_salt"] = new_salt.hex()
    paths.marker.write_text(json.dumps(data))


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


def _commit_v3(paths: _Paths, blob: bytes):
    """Swap in the rebuilt DB, then write the ECC3 key-info (the commit point).

    Identical in shape to _commit, but the key-info written is an envelope blob
    rather than salt + verification token. Ordering is what makes an interrupted
    run survivable: until v3.write_keyinfo lands, the install is still described
    by its OLD key-info, so a crash anywhere above leaves a rollback-able state
    rather than an unopenable database."""
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.new_db) + sfx)
        if s.exists():
            s.unlink()
    os.replace(str(paths.new_db), str(paths.db))
    # The old DB's stale sidecars would corrupt reads against the new file.
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.db) + sfx)
        if s.exists():
            s.unlink()
    # COMMIT POINT: once this is ECC3, the install is detected as v3.
    v3.write_keyinfo(blob, path=paths.keyinfo)
    os.chmod(str(paths.db), 0o600)


def _rollback(paths: _Paths, backup_filename: str, backup_dir: str):
    """Restore the pre-migration backup, leaving a clean install of whatever
    version preceded the attempt.

    Deleting .keyinfo unconditionally is correct for BOTH sources: a v1 install
    had none (and the backup carries none, so it stays absent), while a v2
    install's ECC2 file is in _backup_file_set and is restored by the extract
    below. The delete-then-restore ordering means a half-written ECC3 file can
    never survive a rollback."""
    if paths.rk_pending.exists():
        paths.rk_pending.unlink()
    # Drop every v2/v3 artifact first.
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


def _recover_rekey_v2(paths: _Paths, marker: dict) -> str:
    """Recovery for an interrupted v2 password change. The commit point is the
    new .keyinfo: if the on-disk .keyinfo salt matches the marker's new salt the
    rekey committed (finalize), otherwise it did not (roll back). Password-free."""
    committed = False
    if v2.keyinfo_exists(path=paths.keyinfo):
        try:
            cur_salt, _tok = v2.read_keyinfo(path=paths.keyinfo)
            committed = (cur_salt.hex() == marker.get("new_salt"))
        except Exception:
            committed = False
    if committed:
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


def _recover_migrate_v3(paths: _Paths, marker: dict) -> str:
    """Recovery for an interrupted v1/v2 -> v3 migration. Password-free.

    The commit point is unambiguous here in a way it is not for a v2 password
    change: ECC3 magic in the key-info file can only have been written by
    _commit_v3, which runs after the verified DB swap. So the magic alone
    decides, with no salt bookkeeping in the marker.

    Note the .rk_pending flag is deliberately NOT cleared on the finalize path.
    A crash between commit and the user recording their key is exactly the case
    it exists to survive; the banner must still appear at next login."""
    committed = False
    if v2.keyinfo_exists(path=paths.keyinfo):
        try:
            committed = v3.keyinfo_version(path=paths.keyinfo) == 3
        except Exception:
            committed = False
    if committed:
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


def recover_if_interrupted(root=None) -> str:
    """At startup: finalize a completed-but-uncleaned transition, or roll back an
    interrupted one. Password-free. Returns 'finalized', 'rolled_back', or 'none'.

    v1->v2 migration: .keyinfo is written only after the DB swap, so its presence
    proves commit. v2 password change (kind 'rekey_v2'): .keyinfo exists in both
    states, so the marker's new salt identifies the committed one."""
    paths = _resolve_paths(root)
    if not paths.marker.exists():
        return "none"
    marker = json.loads(paths.marker.read_text())

    if marker.get("kind") == "migrate_v3":
        return _recover_migrate_v3(paths, marker)

    if marker.get("kind") == "rekey_v2":
        return _recover_rekey_v2(paths, marker)

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


def change_password(current_password: str, new_password: str, root=None,
                    backup_fn=None, progress_cb=None) -> dict:
    """Crash-safe master-password change.

    Dispatches on key-info version. On v3 this is a 190-byte rewrap with no
    file walk and no rollback window (see _change_password_v3). On v2 it
    re-encrypts every file and rebuilds the DB under a new raw key, committing
    by writing a new .keyinfo, and rolls back to the pre-change backup on
    failure.

    Return shape is shared so callers need no branch: web.blueprints.auth reads
    result['files_rekeyed'], which is simply 0 on the v3 path.

    Precondition: a migrated install (.keyinfo present) and no open DB handle.
    """
    paths = _resolve_paths(root)
    if not v2.keyinfo_exists(path=paths.keyinfo):
        raise RuntimeError("change_password requires a migrated (v2 or v3) install")
    if install_crypto_version(root) == 3:
        return _change_password_v3(paths, current_password, new_password)
    if backup_fn is None:
        backup_fn = _live_backup if root is None else (lambda: _zip_backup(paths))

    old_salt, _old_tok = v2.read_keyinfo(path=paths.keyinfo)
    old_db_key_hex, old_file_key = v2.derive_subkeys(
        v2.derive_master(current_password, old_salt))
    new_salt = v2.new_salt()
    new_db_key_hex, new_file_key = v2.derive_subkeys(
        v2.derive_master(new_password, new_salt))

    # Checkpoint so the backup captures a complete .db file.
    try:
        c = sqlite3.connect(str(paths.db))
        c.execute(f"PRAGMA key = \"x'{old_db_key_hex}'\"")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass

    backup_info = backup_fn()
    _write_marker(paths, backup_info, kind="rekey_v2", new_salt=new_salt)
    try:
        files = _candidate_files(paths)
        done = 0
        for i, fp in enumerate(files):
            if _reencrypt_file_v2(fp, old_file_key, new_file_key) == "rekeyed":
                done += 1
            if progress_cb:
                progress_cb(i + 1, len(files))
        _build_rekeyed_db_v2(paths, old_db_key_hex, new_db_key_hex)
        _commit(paths, new_salt, new_file_key)
        paths.marker.unlink()
        v2._key_cache.clear()
        return {"status": "rekeyed", "files_rekeyed": done,
                "files_total": len(files)}
    except Exception:
        _rollback(paths, backup_info["filename"],
                  backup_info.get("backup_dir", str(paths.backups_dir)))
        if paths.marker.exists():
            paths.marker.unlink()
        raise


# ---------------------------------------------------------------------------
# v3 envelope migration
# ---------------------------------------------------------------------------
#
# Deliberately a SINGLE PASS from either source, not a chain through v2.
# migrate() (v1->v2) and change_password() (v2->v2') already share a shape:
# resolve how the old files decrypt, resolve how the old DB is keyed, mint new
# keys, checkpoint -> backup -> marker, walk files, _export_verify, commit,
# roll back on failure. Only the two "old" resolutions differ. So a v1 install
# goes straight to v3 with one file walk and one DB rebuild instead of two,
# halving the window in which a large attachment corpus is being rewritten.
#
# EdgeCase does NOT need the resume-state file MailRepo carries. MailRepo does
# an in-place PRAGMA rekey and so must be re-runnable; here the rebuilt DB is a
# separate file that is verified before the swap, and any failure restores the
# backup wholesale. Rollback-to-a-known-good is a stronger guarantee than
# resume, and it is already built.


def install_crypto_version(root=None) -> int:
    """Which crypto generation this install is on: 1, 2 or 3.

    v1 is "no key-info file at all", which is exactly what v2.keyinfo_exists()
    has always meant. That is why adding v3 did not change its meaning.
    """
    paths = _resolve_paths(root)
    if not v2.keyinfo_exists(path=paths.keyinfo):
        return 1
    return v3.keyinfo_version(path=paths.keyinfo)


def needs_v3_migration(root=None) -> bool:
    """True for an existing install that should be upgraded to the envelope.

    False when a migration is already pending — that case belongs to
    recover_if_interrupted(), which runs first and needs no password.
    """
    paths = _resolve_paths(root)
    if not paths.db.exists() or paths.marker.exists():
        return False
    return install_crypto_version(root) in (1, 2)


def recovery_key_pending(root=None) -> bool:
    """True if a recovery key was issued but never acknowledged by the user."""
    return _resolve_paths(root).rk_pending.exists()


def clear_recovery_key_pending(root=None) -> None:
    """Call ONLY after the user has typed their recovery key back correctly."""
    paths = _resolve_paths(root)
    if paths.rk_pending.exists():
        paths.rk_pending.unlink()


def _verify_current_password(paths: _Paths, password: str, version: int):
    """Confirm the password really is the current one before anything is
    touched. Cheap, and it turns "wrong password" into a clean refusal instead
    of a mid-walk failure that has to unwind through a rollback."""
    if version == 2:
        salt, token = v2.read_keyinfo(path=paths.keyinfo)
        _db, file_key = v2.derive_subkeys(v2.derive_master(password, salt))
        if not v2.check_verification_token(file_key, token):
            raise ValueError("Current password is incorrect.")
        return
    # v1: the passphrase keys SQLCipher directly, so a read proves it.
    con = sqlite3.connect(str(paths.db))
    try:
        con.execute(f"PRAGMA key = '{password.replace(chr(39), chr(39) * 2)}'")
        con.execute("SELECT count(*) FROM client_types")
    except Exception:
        raise ValueError("Current password is incorrect.")
    finally:
        con.close()


def migrate_to_v3(password: str, root=None, backup_fn=None,
                  progress_cb=None) -> dict:
    """Migrate a v1 or v2 install to the v3 envelope, in one pass.

    Returns a summary dict including "recovery_key" — the ONLY time that key
    exists in plaintext. It is never stored, so the caller MUST show it to the
    user. A `.rk_pending` flag is set before the commit point so that a crash
    during display still leaves evidence the key was never acknowledged; the UI
    nags until the user types it back, and regeneration is always available
    because they are logged in with a working password.

    On any failure this rolls back to the pre-migration backup and re-raises,
    leaving a clean install of whatever version it started from. A hard crash
    (no rollback runs) is handled by recover_if_interrupted() at next startup.

    Precondition: no other SQLCipher connection to the database is open.
    """
    paths = _resolve_paths(root)
    version = install_crypto_version(root)
    if version == 3:
        return {"status": "already_v3", "files_migrated": 0, "recovery_key": None}
    if backup_fn is None:
        backup_fn = _live_backup if root is None else (lambda: _zip_backup(paths))

    _verify_current_password(paths, password, version)

    # --- Resolve the source side. This is the ONLY place the two upgrade
    #     paths differ; everything below is shared. ---
    if version == 1:
        old_fernet = _old_fernet(password, paths.salt_file.read_bytes())
        old_db_key_hex = None
        esc = password.replace("'", "''")
        checkpoint_key_sql = f"PRAGMA key = '{esc}'"
    else:
        old_salt, _tok = v2.read_keyinfo(path=paths.keyinfo)
        old_db_key_hex, old_file_key = v2.derive_subkeys(
            v2.derive_master(password, old_salt))
        old_fernet = None
        checkpoint_key_sql = f"PRAGMA key = \"x'{old_db_key_hex}'\""

    # --- The destination is identical regardless of source. ---
    master = v3.new_master()
    recovery_key = v3.generate_recovery_key()
    new_db_key_hex, new_file_key = v2.derive_subkeys(master)
    blob = v3.build_keyinfo(master, password, recovery_key)

    # Checkpoint so the backup captures a complete .db file.
    try:
        c = sqlite3.connect(str(paths.db))
        c.execute(checkpoint_key_sql)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass  # best-effort; the WAL sidecar is backed up regardless

    backup_info = backup_fn()
    _write_marker(paths, backup_info, kind="migrate_v3")
    try:
        files = _candidate_files(paths)
        done = 0
        for i, fp in enumerate(files):
            if version == 1:
                outcome = _reencrypt_file(fp, old_fernet, new_file_key)
                converted = outcome == "migrated"
            else:
                outcome = _reencrypt_file_v2(fp, old_file_key, new_file_key)
                converted = outcome == "rekeyed"
            if converted:
                done += 1
            if progress_cb:
                progress_cb(i + 1, len(files))

        if version == 1:
            _build_raw_keyed_db(paths, password, new_db_key_hex)
        else:
            _build_rekeyed_db_v2(paths, old_db_key_hex, new_db_key_hex)

        # Set the pending flag BEFORE the commit point, not after. If it went
        # second there would be a window in which the install is already v3
        # with no record that a recovery key is outstanding — precisely the
        # crash this flag exists to catch.
        paths.rk_pending.write_text("1")

        _commit_v3(paths, blob)
        paths.marker.unlink()
        v2._key_cache.clear()
        return {"status": "migrated_to_v3", "from_version": version,
                "files_migrated": done, "files_total": len(files),
                "recovery_key": recovery_key}
    except Exception:
        _rollback(paths, backup_info["filename"],
                  backup_info.get("backup_dir", str(paths.backups_dir)))
        if paths.marker.exists():
            paths.marker.unlink()
        raise


def _change_password_v3(paths: _Paths, current_password: str,
                        new_password: str) -> dict:
    """Password change on a v3 install: rewrap the password wrapper only.

    No file walk, no database rebuild, no backup gate, no marker, no rollback
    window — the whole operation is one atomic key-file replacement, and
    v3.write_keyinfo validates the blob before it touches the real path. The
    master is unchanged, so db_key and file_key are unchanged, so every
    attachment and the database itself are untouched by construction.

    CLEARING THE KEY CACHE IS LOAD-BEARING HERE, not hygiene. Under v2 a new
    password derived new keys, so a stale cache entry was merely wasteful.
    Under v3 the derived keys are IDENTICAL before and after, so an entry left
    under the old password string would keep returning valid keys for the rest
    of the process lifetime — the crypto would be correct while the cache
    quietly kept the revoked password working.
    """
    blob = v3.read_keyinfo(path=paths.keyinfo)
    master = v3.unwrap_with_password(blob, current_password)

    new_blob = v3.rewrap_password(blob, master, new_password)
    # Prove the new wrapper opens before replacing the only copy of the old one.
    if v3.unwrap_with_password(new_blob, new_password) != master:
        raise RuntimeError("Rewrapped key file failed verification; aborting.")

    v3.write_keyinfo(new_blob, path=paths.keyinfo)
    v2._key_cache.clear()
    return {"status": "rewrapped", "files_rekeyed": 0, "files_total": 0}


def regenerate_recovery_key(password: str, root=None) -> str:
    """Issue a fresh recovery key, revoking the previous one.

    Same shape as the password rewrap and the same reasoning: a printed
    recovery key is a second full-access credential to clinical records, so it
    has to be revocable on its own without forcing a password change. Returns
    the new key in display format — the only time it exists in plaintext.

    Also the remedy when a recovery key was issued but never recorded, which is
    why .rk_pending can safely be a nag rather than a hard block.
    """
    paths = _resolve_paths(root)
    if install_crypto_version(root) != 3:
        raise RuntimeError("Recovery keys require a v3 install.")

    blob = v3.read_keyinfo(path=paths.keyinfo)
    master = v3.unwrap_with_password(blob, password)

    recovery_key = v3.generate_recovery_key()
    new_blob = v3.rewrap_recovery_key(blob, master, recovery_key)
    if v3.unwrap_with_recovery_key(new_blob, recovery_key) != master:
        raise RuntimeError("Rewrapped key file failed verification; aborting.")

    paths.rk_pending.write_text("1")
    v3.write_keyinfo(new_blob, path=paths.keyinfo)
    return recovery_key


def reset_password_with_recovery_key(recovery_key: str, new_password: str,
                                     root=None) -> None:
    """Open the install with the recovery key and set a new master password.

    This is the recovery door. It is deliberately a password RESET rather than
    a passwordless session: EdgeCase is password-keyed all the way down — the
    Flask session, Database(password=...), and the key cache all assume one
    exists — so minting a new password here is both simpler and better UX than
    plumbing a keyless unlock through those layers. Someone reaching for their
    recovery key has forgotten their password and needs a working one anyway.

    The recovery key is NOT rotated on use, which is a deliberate asymmetry
    with the password. If a key has genuinely leaked, an attacker who used it
    would otherwise be able to rotate it and lock the real owner out
    permanently; leaving it valid means the owner's own written copy still
    opens the install and they can rotate it themselves afterwards. Settings
    offers exactly that, and the screen says so.

    Raises RecoveryKeyError if the key is malformed, ValueError if it is
    well-formed but does not open this install.
    """
    paths = _resolve_paths(root)
    if install_crypto_version(root) != 3:
        raise RuntimeError(
            "This install predates recovery keys and can only be opened with "
            "its master password.")

    blob = v3.read_keyinfo(path=paths.keyinfo)
    master = v3.unwrap_with_recovery_key(blob, recovery_key)

    new_blob = v3.rewrap_password(blob, master, new_password)
    if v3.unwrap_with_password(new_blob, new_password) != master:
        raise RuntimeError("Rewrapped key file failed verification; aborting.")

    v3.write_keyinfo(new_blob, path=paths.keyinfo)
    # Load-bearing, as in _change_password_v3: the derived keys do not change,
    # so a stale entry would keep the forgotten password working until restart.
    v2._key_cache.clear()


def has_recovery_key(root=None) -> bool:
    """True if this install can be opened with a recovery key at all.

    Used to decide whether the login page offers the recovery route. Saying
    'that option does not exist here' up front is kinder than letting someone
    hunt for a key that could never have worked.
    """
    try:
        return install_crypto_version(root) == 3
    except Exception:
        return False
