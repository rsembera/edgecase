"""
Master-key rotation for a v3 install.

A password change or a recovery-key regeneration replaces a *wrapper*. The
random master underneath — and so the database key and the file key derived
from it — is untouched. That is what makes those operations instant, and it
is also why neither revokes anything against someone who already holds a
copy of the ciphertext: an old `.keyinfo` (from a backup zip, a synced
folder, a stolen laptop) plus the old password, or an old printed recovery
key, still derives the master that opens today's attachments and today's
database.

Rotation is the remedy: mint a fresh master, re-encrypt every attachment,
rebuild the database under the new key, and write a new key file. After
that, every earlier key file, password and recovery key opens nothing
current. See docs/Master_Rotation_Plan.md for the design decisions; the ones
that shape this module are:

  * It runs AT LOGIN, before `Database` is constructed — the same slot as
    migrate() and recover_if_interrupted(). Settings only *arms* it (a
    `.rotate_pending` flag); the next launch performs it. Live rotation
    would have to swap a database out from under thread-local connections.

  * It ROLLS FORWARD, not back. The backup gate accepts a backup up to 24
    hours old, so rolling back could discard a day of clinical notes to fix
    a key problem. The new master is written to `.master_rotation_state`
    (encrypted under the OLD file key) before the walk; an interrupted run
    resumes with the same master, and every per-file step tolerates having
    already been done. recover_if_interrupted() recognises the
    `rotate_master` marker and leaves it alone.

  * The database is rebuilt through migrate_crypto._export_verify — a NEW
    file, integrity-checked and row-count-checked against the original
    before the swap — not `PRAGMA rekey` in place.

  * There is NO credential step. MailRepo rekeys IMAP passwords stored under
    its file key; EdgeCase stores nothing outside SQLCipher under the file
    key except attachment files and the wrappers in encryption_v3, so the
    file walk and the database rebuild cover everything. Considered and
    omitted, not forgotten.

  * The file walk is migrate_crypto._candidate_files(), unfiltered by
    extension: every non-dotfile under attachments/ plus the logo and
    signature in assets/. A skipped file in a rotation is a file stranded
    under a master that no longer exists.

Reference: MailRepo core/master_rotation.py. Not ported verbatim — the two
apps have opposite recovery philosophies and different database strategies.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import sqlcipher3 as sqlite3

from core import encryption_v2 as v2
from core import encryption_v3 as v3
from core import migrate_crypto as mc

MAX_BACKUP_AGE_HOURS = 24.0
MARKER_KIND = "rotate_master"


class RotationError(RuntimeError):
    """Rotation refused or could not proceed. Nothing irreversible happened
    unless the message says otherwise."""


class RotationCorruptionError(RotationError):
    """A candidate file decrypts under neither the old nor the new key."""

    def __init__(self, path, reason=""):
        self.path = str(path)
        detail = f" ({reason})" if reason else ""
        super().__init__(
            f"{path} could not be decrypted with the current key{detail}. "
            f"Rotation stopped before touching it; nothing has been changed "
            f"for this file. Restore it from a backup or remove it, then "
            f"log in again.")


# --- On-disk state -----------------------------------------------------------

def _state_path(paths) -> Path:
    """The new master, encrypted under the OLD file key, plus a verification
    token for the NEW file key and the backup the run is covered by.
    Written before the walk; its presence means a rotation is in flight."""
    return paths.data_dir / ".master_rotation_state"


def _flag_path(paths) -> Path:
    """Set by Settings to arm a rotation for the next login. Contains no
    secret — only the fact that one was requested."""
    return paths.data_dir / ".rotate_pending"


def _atomic_write(path: Path, data: bytes):
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _save_state(paths, new_master: bytes, old_file_key: bytes, backup_info: dict):
    _db, new_file_key = v2.derive_subkeys(new_master)
    data = {
        "wrapped": v2.encrypt_bytes(old_file_key, new_master).hex(),
        "token": v2.make_verification_token(new_file_key).hex(),
        "backup": {"filename": backup_info["filename"],
                   "backup_dir": backup_info["backup_dir"]},
    }
    _atomic_write(_state_path(paths), json.dumps(data).encode())


def _read_state(paths):
    p = _state_path(paths)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        bytes.fromhex(data["wrapped"])
        bytes.fromhex(data["token"])
        data["backup"]["filename"]
        return data
    except Exception:
        raise RotationError(
            "An interrupted rotation left a state file that cannot be read. "
            "Restore from backup rather than continuing.")


def _unwrap_state(state: dict, old_file_key: bytes) -> bytes:
    try:
        master = v2.decrypt_bytes(old_file_key, bytes.fromhex(state["wrapped"]))
    except Exception:
        raise RotationError(
            "An interrupted rotation left state that cannot be read with this "
            "password. Restore from backup rather than continuing.")
    if len(master) != v3.MASTER_KEY_LEN:
        raise RotationError("Interrupted rotation state is malformed.")
    return master


def _state_committed_under(state: dict, file_key: bytes) -> bool:
    """True if `file_key` is the NEW file key the state describes — i.e. the
    key file on disk already holds the rotated master."""
    return v2.check_verification_token(file_key, bytes.fromhex(state["token"]))


def _clear_state(paths):
    p = _state_path(paths)
    if p.exists():
        p.unlink()


def _rotate_marker(paths):
    """The marker dict if a rotate_master marker is present, else None."""
    if not paths.marker.exists():
        return None
    try:
        marker = json.loads(paths.marker.read_text())
    except Exception:
        return None
    return marker if marker.get("kind") == MARKER_KIND else None


# --- Public state queries (password-free) ------------------------------------

def arm_rotation(root=None) -> None:
    """Request a rotation at the next login. Called from Settings."""
    paths = mc._resolve_paths(root)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    _flag_path(paths).write_text("1")


def disarm_rotation(root=None) -> bool:
    """Withdraw an armed rotation. Refused (returns False) once a run has
    started: the state file means some files may already be under the new
    master, and forgetting it would strand them."""
    paths = mc._resolve_paths(root)
    if rotation_in_progress(root):
        return False
    flag = _flag_path(paths)
    if flag.exists():
        flag.unlink()
    return True


def rotation_armed(root=None) -> bool:
    return _flag_path(mc._resolve_paths(root)).exists()


def rotation_in_progress(root=None) -> bool:
    """A run started and did not finish: state file or rotate_master marker."""
    paths = mc._resolve_paths(root)
    return _state_path(paths).exists() or _rotate_marker(paths) is not None


def rotation_pending(root=None) -> bool:
    """Should the next login run (or resume) a rotation?"""
    return rotation_armed(root) or rotation_in_progress(root)


# --- Per-file rekey with try-old-then-new -------------------------------------

def _decrypt_old_or_new(path: Path, blob: bytes, old_key: bytes, new_key: bytes):
    """Returns (plaintext_or_None, 'old'|'new'). Raises RotationCorruptionError
    if the blob is not a v2 blob or opens under neither key."""
    if not v2.is_v2(blob):
        raise RotationCorruptionError(
            path, "not an encrypted EdgeCase file")
    try:
        return v2.decrypt_bytes(old_key, blob), "old"
    except Exception as old_err:
        try:
            v2.decrypt_bytes(new_key, blob)
            return None, "new"
        except Exception:
            raise RotationCorruptionError(path, type(old_err).__name__)


def _probe_file(path: Path, old_key: bytes, new_key: bytes) -> str:
    """Read-only preflight: which key opens this file. Raises on neither."""
    return _decrypt_old_or_new(path, path.read_bytes(), old_key, new_key)[1]


def _rekey_file_rotation(path: Path, old_key: bytes, new_key: bytes) -> str:
    """Re-encrypt one file old -> new, atomically. 'rekeyed' if converted,
    'skipped' if it was already under the new key (an interrupted earlier
    run got here first). Raises RotationCorruptionError if neither key opens
    it — never a silent skip."""
    blob = path.read_bytes()
    plain, which = _decrypt_old_or_new(path, blob, old_key, new_key)
    if which == "new":
        return "skipped"
    new_blob = v2.encrypt_bytes(new_key, plain)
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


# --- Database helpers ---------------------------------------------------------

def _db_opens_with(db_path: Path, key_hex: str) -> bool:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(f"PRAGMA key = \"x'{key_hex}'\"")
        con.execute("SELECT count(*) FROM sqlite_master")
        return True
    except Exception:
        return False
    finally:
        con.close()


def _db_key_state(paths, old_key_hex: str, new_key_hex: str) -> str:
    """'old' (normal), 'new' (an interrupted run already swapped the rebuilt
    database in but died before writing the key file), or raise."""
    if _db_opens_with(paths.db, old_key_hex):
        return "old"
    if _db_opens_with(paths.db, new_key_hex):
        return "new"
    raise RotationError(
        "The database opens under neither the current key nor the key of the "
        "interrupted rotation. Restore from backup.")


def _checkpoint(paths, key_hex: str):
    """Best-effort WAL checkpoint so a backup captures a complete .db file."""
    try:
        c = sqlite3.connect(str(paths.db))
        c.execute(f"PRAGMA key = \"x'{key_hex}'\"")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass


def _commit_rotation(paths, new_blob: bytes, swap_db: bool):
    """The irreversible window. With swap_db, this is migrate_crypto._commit_v3
    exactly: swap the verified database in, drop stale sidecars, write the
    key file. Without it (the database was already swapped by an interrupted
    run) only the key file remains to be written. `.keyinfo` is the commit
    point either way."""
    if swap_db:
        mc._commit_v3(paths, new_blob)
        return
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.db) + sfx)
        if s.exists():
            s.unlink()
    v3.write_keyinfo(new_blob, path=paths.keyinfo)
    os.chmod(str(paths.db), 0o600)


# --- Backup gate --------------------------------------------------------------

def _restore_points(paths, root):
    from utils import backup as backup_mod
    if root is None:
        return backup_mod.get_restore_points()
    manifest = paths.backups_dir / "manifest.json"
    if not manifest.exists():
        return []
    try:
        entries = json.loads(manifest.read_text()).get("backups", [])
    except Exception:
        return []
    return backup_mod.build_restore_points(entries, override_dir=paths.backups_dir)


def _point_age_hours(point):
    try:
        created = datetime.fromisoformat(point["created_at"])
    except Exception:
        return None
    return (datetime.now() - created).total_seconds() / 3600.0


def recent_verified_backup(root=None):
    """The newest restore point that is complete, verifies, and is no older
    than MAX_BACKUP_AGE_HOURS — as {'filename', 'backup_dir', 'created_at'}
    — or None. Password-free; verification is zip-level (utils.backup
    .verify_backup without a db handle), which is all that is possible
    before login."""
    from utils import backup as backup_mod
    paths = mc._resolve_paths(root)
    for point in _restore_points(paths, root):
        if point.get("broken") or not point.get("files_needed"):
            continue
        age = _point_age_hours(point)
        if age is None or age > MAX_BACKUP_AGE_HOURS:
            continue
        try:
            for f in point["files_needed"]:
                backup_mod.verify_backup(f)
        except Exception:
            continue
        newest = point["files_needed"][-1]
        return {"filename": os.path.basename(newest),
                "backup_dir": os.path.dirname(newest),
                "created_at": point["created_at"]}
    return None


def _default_backup_fn(paths, root):
    if root is None:
        return mc._live_backup
    return lambda: mc._zip_backup(paths)


def _backup_gate(paths, root, backup_fn, progress) -> dict:
    """Return backup_info for a verified backup at most 24h old, taking a
    fresh full backup if there is none. Refuses (RotationError) only if that
    backup cannot be made."""
    recent = recent_verified_backup(root)
    if recent is not None:
        return recent
    progress({"status": "backing_up",
              "message": "No backup from the last 24 hours — taking one "
                         "first. This can take a while for a large practice."})
    if backup_fn is None:
        backup_fn = _default_backup_fn(paths, root)
    try:
        info = backup_fn()
    except Exception as e:
        raise RotationError(
            f"Rotation refused: no verified backup from the last "
            f"{int(MAX_BACKUP_AGE_HOURS)} hours, and taking one failed ({e}). "
            f"Take a backup and try again.")
    if not info or "filename" not in info:
        raise RotationError(
            "Rotation refused: the safety backup did not complete. "
            "Take a backup and try again.")
    return {"filename": info["filename"],
            "backup_dir": info.get("backup_dir", str(paths.backups_dir))}


# --- The rotation ------------------------------------------------------------

def _finalize_committed(paths, root, password, progress) -> dict:
    """An earlier run passed the commit point (the key file already holds the
    rotated master) and died before cleaning up. Finish the idempotent
    cleanup. The recovery key that run minted never reached the user, so
    issue a fresh one — .rk_pending is still set from before the commit."""
    progress({"status": "finalizing", "message": "Finishing an interrupted rotation…"})
    if paths.new_db.exists():
        paths.new_db.unlink()
    for sfx in ("-wal", "-shm"):
        s = Path(str(paths.db) + sfx)
        if s.exists():
            s.unlink()
    _clear_state(paths)
    if paths.marker.exists():
        paths.marker.unlink()
    flag = _flag_path(paths)
    if flag.exists():
        flag.unlink()
    v2._key_cache.clear()
    recovery_key = mc.regenerate_recovery_key(password, root=root)
    progress({"status": "complete", "message": "Master key rotated."})
    return {"status": "finalized", "files_rekeyed": 0, "files_total": 0,
            "recovery_key": recovery_key}


def rotate_master(password: str, new_password: str = None, root=None,
                  backup_fn=None, progress_cb=None) -> dict:
    """Rotate the master key. Returns a summary dict including
    "recovery_key" — the ONLY time the new key exists in plaintext.

    `new_password` defaults to `password`. The old recovery key is dead after
    this regardless: it wrapped a master that no longer opens anything.

    Raises ValueError for a wrong password (nothing touched), RotationError
    when refused (not v3, no backup possible, unreadable state) and
    RotationCorruptionError when a candidate file opens under neither key
    (detected in a read-only preflight, before anything is written).

    Precondition: no SQLCipher connection to the database is open.
    """
    progress = progress_cb or (lambda event: None)
    paths = mc._resolve_paths(root)

    if mc.install_crypto_version(root) != 3:
        raise RotationError("Rotation needs the v3 envelope. Upgrade first.")

    # 1. The password must be the current one; it also yields the master.
    blob = v3.read_keyinfo(path=paths.keyinfo)
    try:
        current_master = v3.unwrap_with_password(blob, password)
    except ValueError:
        raise ValueError("Current password is incorrect.")
    cur_db_key_hex, cur_file_key = v2.derive_subkeys(current_master)

    # 2. Where did an earlier run get to?
    state = _read_state(paths)
    if state is not None and _state_committed_under(state, cur_file_key):
        return _finalize_committed(paths, root, password, progress)
    if state is None and _rotate_marker(paths) is not None:
        # State is cleared only after the commit; a marker without it is
        # post-commit residue.
        return _finalize_committed(paths, root, password, progress)

    old_master = current_master
    old_db_key_hex, old_file_key = cur_db_key_hex, cur_file_key
    resumed = state is not None
    if resumed:
        new_master = _unwrap_state(state, old_file_key)
    else:
        new_master = v3.new_master()
    new_db_key_hex, new_file_key = v2.derive_subkeys(new_master)
    if new_file_key == old_file_key or new_master == old_master:
        raise RotationError("Generated master collided with the current key.")

    recovery_key = v3.generate_recovery_key()
    pw = new_password if new_password else password
    new_blob = v3.build_keyinfo(new_master, pw, recovery_key)
    # Prove the new key file opens before it can ever replace the old one.
    if v3.unwrap_with_password(new_blob, pw) != new_master or \
            v3.unwrap_with_recovery_key(new_blob, recovery_key) != new_master:
        raise RotationError("New key file failed verification; aborting.")

    # 3. Backup gate — before anything is written. A resumed run is covered
    #    by the backup its state records; taking another now could snapshot
    #    a half-rotated install.
    if resumed:
        backup_info = state["backup"]
    else:
        _checkpoint(paths, old_db_key_hex)
        backup_info = _backup_gate(paths, root, backup_fn, progress)

    # 4. Count, then read-only preflight: every candidate must open under
    #    one of the two keys, and the database under one of the two, BEFORE
    #    the state file makes this run resumable rather than cancellable.
    progress({"status": "counting", "message": "Counting encrypted files…"})
    files = mc._candidate_files(paths)
    total = len(files)
    progress({"status": "checking", "total": total,
              "message": f"Checking {total} file{'s' if total != 1 else ''}…"})
    for fp in files:
        _probe_file(fp, old_file_key, new_file_key)
    db_state = _db_key_state(paths, old_db_key_hex, new_db_key_hex)

    # 5. Rotation state: from here the run resumes rather than restarts.
    if not resumed:
        _save_state(paths, new_master, old_file_key, backup_info)

    # 6. The walk.
    rekeyed = 0
    for i, fp in enumerate(files):
        if _rekey_file_rotation(fp, old_file_key, new_file_key) == "rekeyed":
            rekeyed += 1
        progress({"status": "encrypting", "current": i + 1, "total": total,
                  "message": f"Re-encrypting {i + 1} of {total}…"})

    # 7. The database: rebuilt as a separate file and verified, original
    #    untouched until it passes. No granularity to report honestly.
    progress({"status": "database", "message": "Verifying the database…"})
    swap_db = db_state == "old"
    if swap_db:
        mc._build_rekeyed_db_v2(paths, old_db_key_hex, new_db_key_hex)

    # 8. The pending flag BEFORE the commit point (as in migrate_to_v3): no
    #    window where the install is rotated with no record that a recovery
    #    key is outstanding. Then the marker, then the irreversible window.
    progress({"status": "finalizing", "message": "Writing the new key file…"})
    paths.rk_pending.write_text("1")
    mc._write_marker(paths, backup_info, kind=MARKER_KIND)
    _commit_rotation(paths, new_blob, swap_db=swap_db)

    # 9. Cleanup. The cache clear is load-bearing, not hygiene: the password
    #    string may be unchanged while every key below it has moved.
    _clear_state(paths)
    paths.marker.unlink()
    flag = _flag_path(paths)
    if flag.exists():
        flag.unlink()
    v2._key_cache.clear()

    progress({"status": "complete", "message": "Master key rotated."})
    return {"status": "rotated", "files_rekeyed": rekeyed, "files_total": total,
            "resumed": resumed, "recovery_key": recovery_key,
            "backup": backup_info}
