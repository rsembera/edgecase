"""
EdgeCase Equalizer - Backup System
Handles full and incremental backups with encryption support.

User-facing simplification:
- Single "Backup Now" button (system auto-decides full vs incremental)
- All backups are valid restore points
- No exposed complexity about backup chains
"""

import os
import json
import hashlib
import re
import zipfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Use config for all paths so EDGECASE_DATA override works
from core.config import DATA_ROOT, DATA_DIR, ATTACHMENTS_DIR, ASSETS_DIR, BACKUPS_DIR

# Application identity, stamped into every manifest EdgeCase writes.
# EdgeCase and MailRepo backups are byte-for-byte the same shape — same
# filename convention, same `data/.salt` and `data/.secret_key` paths —
# and the only structural difference is the database name inside a full
# zip. Restoring one app's backups into the other would overwrite key
# material while finding no database to go with it, so each app marks
# what is its own rather than inferring it later. MailRepo already
# refuses EdgeCase folders on this basis; the stamp and the checks below
# are the mirror image.
APP_ID = 'edgecase'

# Backup filenames as written by generate_backup_filename:
#   full_2026-08-15_143000.zip / incr_.../ pre_restore_...
# The optional trailing group tolerates a future collision suffix.
_BACKUP_FILENAME_RE = re.compile(
    r'^(full|incr|pre_restore)_(\d{4}-\d{2}-\d{2})_(\d{6})(?:_(\d+))?\.zip$')

_TYPE_FROM_PREFIX = {
    'full': 'full',
    'incr': 'incremental',
    'pre_restore': 'pre_restore',
}

RESTORE_STAGING_DIR = DATA_ROOT / '.restore_staging'
MANIFEST_FILE = BACKUPS_DIR / 'manifest.json'


def ensure_backup_dir():
    """Create backups directory if it doesn't exist."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def get_file_hash(filepath):
    """Calculate SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def resolve_backup_dir(backup):
    """Resolve the directory a manifest backup entry lives in.

    Single source of truth for the fallback: entries without a recorded
    'backup_dir' (legacy manifests) always resolve to BACKUPS_DIR — the
    default location those entries were written to. Never fall back to a
    *current* custom location: looking legacy entries up in the wrong
    folder removes them from the manifest while orphaning the real zip
    (with PHI) on disk (CODE_REVIEW L3).
    """
    return Path(backup.get('backup_dir') or BACKUPS_DIR)


def _checkpoint_db(db):
    """Best-effort WAL checkpoint before zipping the database.

    backup.py cannot open the SQLCipher-encrypted database itself (it has
    no password), so callers pass their live Database handle and we call
    its checkpoint(). When no handle is provided we proceed without a
    checkpoint; any leftover edgecase.db-wal is then included in the
    backup instead (see get_all_backup_files), so committed data is not
    silently lost.
    """
    if db is None:
        return
    try:
        db.checkpoint()
    except Exception as e:
        print(f"Warning: WAL checkpoint before backup failed: {e}")


def get_all_backup_files():
    """
    Get list of all files that should be backed up.
    Returns dict: {relative_path: absolute_path}
    """
    files = {}
    
    # Database
    db_path = DATA_DIR / 'edgecase.db'
    if db_path.exists():
        files['data/edgecase.db'] = db_path

    # WAL sidecar: after a checkpoint this normally doesn't exist, but if
    # it does (no db handle available, checkpoint failed or returned busy)
    # it holds committed data not yet merged into edgecase.db — back it up
    # so the restored database isn't missing recent writes (CODE_REVIEW H7).
    wal_path = DATA_DIR / 'edgecase.db-wal'
    if wal_path.exists():
        files['data/edgecase.db-wal'] = wal_path

    # Security files (salt and secret key - essential for decryption)
    salt_path = DATA_DIR / '.salt'
    if salt_path.exists():
        files['data/.salt'] = salt_path
    
    secret_key_path = DATA_DIR / '.secret_key'
    if secret_key_path.exists():
        files['data/.secret_key'] = secret_key_path

    # Key-info file (Argon2id salt + verification token): essential to derive
    # the v2 raw key. Without it a restored v2 install cannot be opened, just
    # as .salt is essential for v1. Absent on un-migrated (v1) installs.
    keyinfo_path = DATA_DIR / '.keyinfo'
    if keyinfo_path.exists():
        files['data/.keyinfo'] = keyinfo_path

    # Recovery-key acknowledgement flag: contains no secrets, only the fact
    # that a recovery key was issued and never typed back (see
    # migrate_crypto, which likewise treats it as part of key state in its
    # rollback file set). Backed up so a restore reinstates the
    # acknowledgement nag alongside the keyinfo it refers to.
    rk_pending_path = DATA_DIR / '.rk_pending'
    if rk_pending_path.exists():
        files['data/.rk_pending'] = rk_pending_path
    
    # Attachments (all subdirectories)
    if ATTACHMENTS_DIR.exists():
        for filepath in ATTACHMENTS_DIR.rglob('*'):
            if filepath.is_file() and not filepath.name.startswith('.'):
                rel_path = filepath.relative_to(DATA_ROOT)
                files[str(rel_path)] = filepath
    
    # Assets (logo and signature only)
    if ASSETS_DIR.exists():
        for filepath in ASSETS_DIR.iterdir():
            if filepath.is_file() and not filepath.name.startswith('.'):
                # Only include logo and signature files
                if filepath.stem in ('logo', 'signature'):
                    rel_path = filepath.relative_to(DATA_ROOT)
                    files[str(rel_path)] = filepath
    
    return files


def get_file_hashes():
    """
    Calculate hashes for all backup files.
    Returns dict: {relative_path: hash}
    """
    files = get_all_backup_files()
    hashes = {}
    for rel_path, abs_path in files.items():
        hashes[rel_path] = get_file_hash(abs_path)
    return hashes


def load_manifest():
    """Load backup manifest from disk."""
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            # Manifest corrupted - backup the bad file and start fresh
            corrupted_path = MANIFEST_FILE.with_suffix('.json.corrupted')
            shutil.copy(MANIFEST_FILE, corrupted_path)
            print(f"Warning: manifest.json was corrupted, backed up to {corrupted_path.name}")
            # Return fresh manifest - existing backup files still exist,
            # they just won't appear in the UI until next full backup
    return {
        'backups': [],
        'last_full_hashes': {},
        'current_chain_id': None,
        'last_backup_check': None
    }


def _atomic_write_text(path, text):
    """Write text to path via temp-file + os.replace (crash-safe)."""
    path = Path(path)
    tmp_path = f'{path}.tmp'
    try:
        with open(tmp_path, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def save_manifest(manifest):
    """Save backup manifest to disk (atomic, crash-safe write).

    Also drops a copy into every directory the manifest's backups live
    in. The canonical manifest sits under DATA_ROOT, so a loss that
    takes the data root takes the index with it — leaving the zips
    intact in iCloud and undiscoverable, because nothing remaining on
    disk knows which zip belongs to which chain. A sidecar makes each
    backup destination a self-describing unit: the folder plus its
    manifest is everything needed to rebuild. Written here rather than
    at each call site so anything mutating the manifest — new backup,
    retention pruning — keeps the copies current without remembering to.

    The manifest is stamped with this application's identity before it
    is written anywhere, so every folder EdgeCase touches says whose it
    is (see APP_ID).

    Sidecar and location-record failures are logged, never raised. A
    backup that succeeded must not be reported as failed because a cloud
    folder was briefly unwritable; the canonical manifest is already
    safely written by then.
    """
    ensure_backup_dir()

    manifest = dict(manifest)
    manifest['app'] = APP_ID

    payload = json.dumps(manifest, indent=2)
    _atomic_write_text(MANIFEST_FILE, payload)
    record_backup_location(BACKUPS_DIR)

    for destination in manifest_destinations(manifest):
        try:
            destination.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(destination / 'manifest.json', payload)
            record_backup_location(destination)
        except Exception as e:
            print(f"Warning: could not write manifest sidecar to {destination}: {e}")


def manifest_destinations(manifest):
    """Every distinct directory this manifest's backups actually live in.

    Excludes the canonical location, which save_manifest writes anyway.
    """
    canonical = BACKUPS_DIR.resolve()
    destinations = {}

    for entry in manifest.get('backups', []):
        raw = entry.get('backup_dir')
        if not raw:
            continue
        try:
            resolved = Path(raw).resolve()
        except Exception:
            continue
        if resolved == canonical:
            continue
        destinations[resolved] = True

    return list(destinations)


def _backup_locations_file():
    """Path to the backup-locations record (kept outside DATA_ROOT)."""
    from core.config import get_backup_locations_file
    return get_backup_locations_file()


def get_known_locations():
    """Folders EdgeCase has recorded sending backups to.

    Read on disaster recovery BEFORE any filesystem guesswork. Entries
    whose folder no longer exists are dropped from the result but left
    in the file — an external drive that is merely unplugged should not
    be forgotten.
    """
    path = _backup_locations_file()
    if not path.exists():
        return []

    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"Warning: could not read backup locations file: {e}")
        return []

    locations = []
    for entry in data.get('locations', []):
        raw = entry.get('path')
        if not raw:
            continue
        try:
            if Path(raw).is_dir():
                locations.append(entry)
        except OSError:
            continue

    locations.sort(key=lambda e: e.get('last_written', ''), reverse=True)
    return locations


def record_backup_location(folder):
    """Remember that backups were written here.

    Stored outside DATA_ROOT (see core.config.get_state_dir), because
    the data root is gone in the situation this exists for. This is the
    difference between EdgeCase knowing where its backups are and
    scanning the disk hoping to recognise them.
    """
    folder = Path(folder)
    path = _backup_locations_file()

    try:
        existing = {}
        if path.exists():
            with open(path, 'r') as f:
                data = json.load(f)
            for entry in data.get('locations', []):
                if entry.get('path'):
                    existing[entry['path']] = entry

        existing[str(folder)] = {
            'path': str(folder),
            'last_written': datetime.now().isoformat(),
            'app': APP_ID,
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(
            path,
            json.dumps({'app': APP_ID, 'locations': list(existing.values())},
                       indent=2))
    except Exception as e:
        # Never fail a backup over bookkeeping.
        print(f"Warning: could not record backup location {folder}: {e}")


def generate_backup_filename(backup_type):
    """Generate unique backup filename."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    return f"{backup_type}_{timestamp}.zip"


def validate_backup_location(backup_dir):
    """
    Validate that backup location is accessible and writable.
    Returns (success, error_message) tuple.
    """
    backup_dir = Path(backup_dir)
    
    # Check if it's a cloud folder
    cloud_indicators = ['iCloud', 'CloudDocs', 'Dropbox', 'Google Drive', 'OneDrive', 'CloudStorage']
    is_cloud = any(indicator in str(backup_dir) for indicator in cloud_indicators)
    
    try:
        # Try to create directory
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to write a test file
        test_file = backup_dir / '.write_test'
        try:
            test_file.write_text('test')
            test_file.unlink()
        except PermissionError:
            if is_cloud:
                return False, "Cannot write to cloud folder. Please check that the cloud service is running and you're signed in."
            return False, "Permission denied. Cannot write to this location."
        except OSError as e:
            if is_cloud:
                return False, f"Cloud folder not accessible. Please check your internet connection and that {backup_dir.parts[-2] if len(backup_dir.parts) > 1 else 'the cloud service'} is online."
            return False, f"Cannot write to backup location: {e}"
        
        return True, None
        
    except PermissionError:
        if is_cloud:
            return False, "Cannot access cloud folder. Please check that the cloud service is running and you're signed in."
        return False, "Permission denied. Cannot access this location."
    except OSError as e:
        if is_cloud:
            return False, "Cloud folder not accessible. Please check your internet connection."
        return False, f"Cannot access backup location: {e}"


def create_backup(backup_dir=None, db=None):
    """
    Create a backup, automatically deciding between full and incremental.

    Decision logic:
    - No previous backups → full
    - Last full backup > 7 days old → full
    - Otherwise → incremental (only changed files)

    Args:
        backup_dir: Optional custom backup directory (for cloud folders)
        db: Optional live Database handle, used to checkpoint the WAL
            before zipping and to integrity-check the zipped database

    Returns:
        dict with backup info, or None if no changes (for incremental)
    """
    manifest = load_manifest()
    
    # Decide: full or incremental?
    need_full = False
    
    if not manifest['backups']:
        need_full = True  # No backups exist
    elif not manifest['last_full_hashes']:
        need_full = True  # No hash baseline
    else:
        # Check age of last full backup (calendar days, not hours)
        full_backups = [b for b in manifest['backups'] if b['type'] == 'full']
        if full_backups:
            last_full = max(full_backups, key=lambda x: x['created_at'])
            last_full_date = datetime.fromisoformat(last_full['created_at']).date()
            if (datetime.now().date() - last_full_date).days >= 7:
                need_full = True
        else:
            need_full = True  # No full backup exists
    
    if need_full:
        return create_full_backup(backup_dir, db=db)
    else:
        return create_incremental_backup(backup_dir, db=db)


def create_full_backup(backup_dir=None, db=None):
    """
    Create a full backup of all data.

    Args:
        backup_dir: Optional custom backup directory (for cloud folders)
        db: Optional live Database handle (WAL checkpoint + DB verification)

    Returns:
        dict with backup info or raises exception
    """
    if backup_dir is None:
        backup_dir = BACKUPS_DIR
    else:
        backup_dir = Path(backup_dir)
    
    # Validate location before starting
    valid, error = validate_backup_location(backup_dir)
    if not valid:
        raise ValueError(error)
    
    filename = generate_backup_filename('full')
    backup_path = backup_dir / filename

    # Flush WAL into the main database file before snapshotting it
    _checkpoint_db(db)

    files = get_all_backup_files()
    if not files:
        raise ValueError("No files to backup")
    
    # Calculate hashes before backup
    hashes = {}
    total_size = 0
    
    # Create zip archive
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel_path, abs_path in files.items():
                zf.write(abs_path, rel_path)
                hashes[rel_path] = get_file_hash(abs_path)
                total_size += abs_path.stat().st_size
    except OSError as e:
        # Clean up partial backup
        if backup_path.exists():
            backup_path.unlink()
        raise ValueError(f"Failed to create backup: {e}")

    # Verify backup (zip CRCs + DB integrity_check when db provided)
    verify_backup(backup_path, db=db)

    # Update manifest
    manifest = load_manifest()
    chain_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    backup_info = {
        'filename': filename,
        'type': 'full',
        'chain_id': chain_id,
        'created_at': datetime.now().isoformat(),
        'file_count': len(files),
        'original_size': total_size,
        'backup_size': backup_path.stat().st_size,
        'backup_dir': str(backup_dir)
    }
    
    manifest['backups'].append(backup_info)
    manifest['last_full_hashes'] = hashes
    manifest['current_chain_id'] = chain_id
    save_manifest(manifest)
    
    return backup_info


def create_incremental_backup(backup_dir=None, db=None):
    """
    Create an incremental backup (only changed files since last backup).

    Args:
        backup_dir: Optional custom backup directory
        db: Optional live Database handle (WAL checkpoint + DB verification)

    Returns:
        dict with backup info, or None if no changes
    """
    manifest = load_manifest()

    if not manifest['last_full_hashes']:
        # No previous backup, need full backup first
        return create_full_backup(backup_dir, db=db)

    if backup_dir is None:
        backup_dir = BACKUPS_DIR
    else:
        backup_dir = Path(backup_dir)

    # Validate location before starting
    valid, error = validate_backup_location(backup_dir)
    if not valid:
        raise ValueError(error)

    # Flush WAL into the main database file before hashing/snapshotting
    _checkpoint_db(db)

    # Get current state
    current_hashes = get_file_hashes()
    previous_hashes = manifest['last_full_hashes']
    
    # Find changes
    changed_files = {}
    files = get_all_backup_files()
    
    for rel_path, current_hash in current_hashes.items():
        if rel_path not in previous_hashes or previous_hashes[rel_path] != current_hash:
            changed_files[rel_path] = files[rel_path]
    
    # Check for deleted files (track in manifest but don't include in zip)
    deleted_files = [p for p in previous_hashes if p not in current_hashes]
    
    if not changed_files and not deleted_files:
        # No changes - update baseline anyway to prevent WAL checkpoint
        # hash differences from appearing as false positives next time
        manifest['last_full_hashes'] = current_hashes
        save_manifest(manifest)
        return None
    
    filename = generate_backup_filename('incr')
    backup_path = backup_dir / filename
    
    total_size = 0
    
    # Create zip with only changed files
    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel_path, abs_path in changed_files.items():
                zf.write(abs_path, rel_path)
                total_size += abs_path.stat().st_size
            
            # Include a metadata file listing deleted files
            if deleted_files:
                metadata = {'deleted_files': deleted_files}
                zf.writestr('_backup_metadata.json', json.dumps(metadata))
    except OSError as e:
        # Clean up partial backup
        if backup_path.exists():
            backup_path.unlink()
        raise ValueError(f"Failed to create backup: {e}")

    # Verify backup (zip CRCs + DB integrity_check when db provided)
    verify_backup(backup_path, db=db)

    # Update manifest
    backup_info = {
        'filename': filename,
        'type': 'incremental',
        'chain_id': manifest['current_chain_id'],
        'created_at': datetime.now().isoformat(),
        'file_count': len(changed_files),
        'deleted_count': len(deleted_files),
        'original_size': total_size,
        'backup_size': backup_path.stat().st_size,
        'backup_dir': str(backup_dir)
    }
    
    manifest['backups'].append(backup_info)
    # Update hashes to current state
    manifest['last_full_hashes'] = current_hashes
    save_manifest(manifest)
    
    return backup_info


def verify_backup(backup_path, db=None):
    """
    Verify backup zip integrity. Raises ValueError (and deletes the
    partial backup) if verification fails.

    Always checks zip CRCs. When a live Database handle is provided, also
    extracts the zipped edgecase.db to a temp dir and runs SQLCipher's
    PRAGMA integrity_check on it using db.password — zip CRCs only prove
    the zip matches what was written, not that the database copy is sane;
    a torn copy of a live DB passes CRC but fails only at restore time
    (CODE_REVIEW H7). Without a db handle we cannot decrypt the copy, so
    CRC checking is the fallback.
    """
    try:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file:
                # Delete corrupted backup
                os.remove(backup_path)
                raise ValueError(f"Backup verification failed: {bad_file} is corrupted")
    except zipfile.BadZipFile:
        os.remove(backup_path)
        raise ValueError("Backup file is corrupted")

    if db is not None:
        _verify_zipped_database(backup_path, db)


def _verify_zipped_database(backup_path, db):
    """Run PRAGMA integrity_check on the database copy inside a backup zip.

    Deletes the backup and raises ValueError if the copy is unreadable or
    fails the integrity check. No-op if the zip contains no database
    (e.g. an incremental with only attachment changes).
    """
    import tempfile

    db_arcname = 'data/edgecase.db'
    wal_arcname = 'data/edgecase.db-wal'

    with zipfile.ZipFile(backup_path, 'r') as zf:
        names = zf.namelist()
        if db_arcname not in names:
            return  # No database in this backup; nothing to check

        tmp_dir = tempfile.mkdtemp(prefix='edgecase_backup_verify_')
        try:
            extracted_db = zf.extract(db_arcname, tmp_dir)
            if wal_arcname in names:
                # Extract the WAL alongside so SQLite verifies the
                # database with its pending frames replayed
                zf.extract(wal_arcname, tmp_dir)

            result = None
            error = None
            try:
                import sqlcipher3
                conn = sqlcipher3.connect(str(extracted_db), timeout=10.0)
                try:
                    if db.password:
                        # A migrated (v2) install keys SQLCipher with the raw
                        # Argon2id-derived key, exactly as core.database does;
                        # a v1 install keys with the passphrase.
                        from core import encryption_v2
                        if encryption_v2.keyinfo_exists():
                            db_key_hex, _ = encryption_v2.get_keys(db.password)
                            conn.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
                        else:
                            # Same escaping as core.database.Database.connect
                            escaped = db.password.replace("'", "''")
                            conn.execute(f"PRAGMA key = '{escaped}'")
                    row = conn.execute('PRAGMA integrity_check').fetchone()
                    result = row[0] if row else None
                finally:
                    conn.close()
            except Exception as e:
                error = str(e)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if error is not None or result is None or str(result).lower() != 'ok':
        # Torn/corrupt database copy — remove the bad backup and fail loudly
        if os.path.exists(backup_path):
            os.remove(backup_path)
        detail = error if error is not None else (result or 'no result')
        raise ValueError(
            f"Backup verification failed: backed-up database failed "
            f"integrity check ({detail}). The backup was discarded — "
            f"please try again."
        )


def list_backups():
    """
    List all available backups with details.
    Returns list sorted by date (newest first).
    """
    manifest = load_manifest()
    backups = []
    
    for backup in manifest['backups']:
        # Check if file still exists
        backup_path = resolve_backup_dir(backup) / backup['filename']
        
        if backup_path.exists():
            backups.append({
                'filename': backup['filename'],
                'type': backup['type'],
                'chain_id': backup['chain_id'],
                'created_at': backup['created_at'],
                'file_count': backup['file_count'],
                'backup_size': backup['backup_size'],
                'backup_size_mb': round(backup['backup_size'] / (1024 * 1024), 2),
                'path': str(backup_path)
            })
    
    # Sort by date, newest first
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return backups


def get_restore_points():
    """
    Get available restore points.
    
    ALL backups are valid restore points:
    - Full backups restore directly
    - Incremental backups restore by applying chain (full + incrementals)
    - Pre-restore backups are also valid restore points
    
    Returns list of restore points with display info.
    """
    manifest = load_manifest()
    return build_restore_points(manifest['backups'])


def build_restore_points(backups, override_dir=None):
    """Build restore points from a list of manifest entries.

    Split out of get_restore_points so the disaster-recovery path can
    reuse it against a manifest found IN a backup folder rather than the
    local one. `override_dir` resolves every entry's file against that
    folder instead of its recorded backup_dir — a recovered folder is
    rarely at the path it was written from (different machine, different
    home directory, iCloud mounted elsewhere).
    """
    def resolve(entry):
        if override_dir is not None:
            return Path(override_dir) / entry['filename']
        return resolve_backup_dir(entry) / entry['filename']

    # Group by chain
    chains = {}
    for backup in backups:
        # A manifest entry missing chain_id is malformed (hand-edited, or
        # a foreign/damaged sidecar). Skip it rather than raising — a
        # KeyError here would take down the whole restore screen.
        chain_id = backup.get('chain_id')
        if not chain_id:
            print(f"Warning: skipping manifest entry without chain_id: "
                  f"{backup.get('filename', '?')}")
            continue
        if chain_id not in chains:
            chains[chain_id] = {'full': None, 'incrementals': [], 'pre_restore': []}

        if backup['type'] == 'full':
            chains[chain_id]['full'] = backup
        elif backup['type'] == 'pre_restore':
            # Collect ALL safety backups — they share chain_id
            # 'pre_restore', and a single slot would hide every safety
            # backup but the last one (CODE_REVIEW L2)
            chains[chain_id]['pre_restore'].append(backup)
        else:
            chains[chain_id]['incrementals'].append(backup)

    # Build restore points
    restore_points = []

    for chain_id, chain in chains.items():
        # Handle pre_restore backups (standalone, not part of a chain).
        # Each safety backup is its own restore point; give each a unique
        # chain_id so the UI's chain grouping renders every one of them.
        if chain_id == 'pre_restore':
            for backup in chain['pre_restore']:
                backup_path = resolve(backup)
                if backup_path.exists():
                    # Format date with time
                    created = datetime.fromisoformat(backup['created_at'])
                    display_time = created.strftime('%b %d, %Y at %I:%M %p').replace(' 0', ' ')

                    restore_points.append({
                        'id': f"pre_restore_{backup['filename']}",
                        'filename': backup['filename'],
                        'display_name': f"{display_time} (Safety backup)",
                        'created_at': backup['created_at'],
                        'type': 'pre_restore',
                        'is_safety': True,
                        'chain_id': f"pre_restore_{backup['filename']}",
                        'dependent_count': 0,
                        'files_needed': [str(backup_path)]
                    })
            continue

        if not chain['full']:
            continue  # Skip orphaned incrementals

        # Sort incrementals by date
        chain['incrementals'].sort(key=lambda x: x['created_at'])

        # Count dependents for this chain's full backup
        dependent_count = len(chain['incrementals'])

        # Full backup as restore point
        full_backup = chain['full']
        backup_path = resolve(full_backup)

        # Track the first gap in the chain. A missing zip anywhere in the
        # chain breaks every LATER restore point: prepare_restore would
        # silently apply an incomplete sequence and any file whose only
        # copy lived in the missing zip gets restored from an older
        # version (CODE_REVIEW H4). Points after the gap are flagged
        # 'broken' instead of being offered as restorable.
        missing_file = None if backup_path.exists() else full_backup['filename']

        if backup_path.exists():
            # Format date with time
            created = datetime.fromisoformat(full_backup['created_at'])
            display_time = created.strftime('%b %d, %Y at %I:%M %p').replace(' 0', ' ')

            restore_points.append({
                'id': f"{chain_id}_full",
                'filename': full_backup['filename'],
                'display_name': display_time,
                'created_at': full_backup['created_at'],
                'type': 'full',
                'is_safety': False,
                'chain_id': chain_id,
                'dependent_count': dependent_count,
                'files_needed': [str(backup_path)]
            })

        # Each incremental in the chain is also a restore point
        files_needed = [str(backup_path)]
        for i, incr in enumerate(chain['incrementals']):
            incr_path = resolve(incr)

            if not incr_path.exists():
                # Gap in the chain: this zip is gone, so it can't be a
                # restore point itself, and everything after it is broken
                if missing_file is None:
                    missing_file = incr['filename']
                continue

            # Format date with time
            created = datetime.fromisoformat(incr['created_at'])
            display_time = created.strftime('%b %d, %Y at %I:%M %p').replace(' 0', ' ')

            point = {
                'id': f"{chain_id}_incr_{i}",
                'filename': incr['filename'],
                'display_name': display_time,
                'created_at': incr['created_at'],
                'type': 'incremental',
                'is_safety': False,
                'chain_id': chain_id,
                'dependent_count': 0,
            }

            if missing_file is not None:
                # On a broken chain: surface it so the UI can explain why
                # it's unavailable, but expose no files to restore from
                point['broken'] = True
                point['missing_file'] = missing_file
                point['files_needed'] = []
            else:
                files_needed = files_needed + [str(incr_path)]
                point['files_needed'] = files_needed.copy()

            restore_points.append(point)
    
    # Sort by date, newest first
    restore_points.sort(key=lambda x: x['created_at'], reverse=True)

    # Annotate which credentials each point would need (Daybook's fix).
    # The live key-info is read ONCE here rather than per point.
    try:
        from core import encryption_v2
        keyinfo_path = Path(encryption_v2.KEYINFO_FILE)
        current_blob = (keyinfo_path.read_bytes()
                        if keyinfo_path.exists() else None)
    except Exception:
        current_blob = None

    for point in restore_points:
        creds = describe_restore_point_credentials(
            point.get('files_needed', []), current_blob)
        point['credential_status'] = creds['status']
        point['credential_note'] = creds['note']

    return restore_points


def prepare_restore(restore_point_id, db=None):
    """
    Prepare for restore by extracting to staging folder.
    Does NOT replace production files yet.

    Args:
        restore_point_id: ID of the restore point to prepare
        db: Optional live Database handle, passed to the safety backup

    Returns path to staging folder.
    """
    restore_points = get_restore_points()
    point = next((p for p in restore_points if p['id'] == restore_point_id), None)

    if not point:
        raise ValueError(f"Restore point not found: {restore_point_id}")

    if point.get('broken'):
        # Defense in depth: the UI shouldn't offer broken points, but
        # never restore from a chain with a missing link (CODE_REVIEW H4)
        raise ValueError(
            f"Cannot restore this backup: its chain is missing "
            f"'{point.get('missing_file', 'a backup file')}'. "
            f"Choose an earlier restore point."
        )

    return prepare_restore_from_point(point, db=db)


def prepare_restore_from_point(point, db=None):
    """Stage a restore from an already-resolved restore point.

    Same work as prepare_restore, minus the manifest lookup. The
    disaster-recovery path has its point in hand from a folder scan and
    cannot look it up by id, because the local manifest that ids refer
    to is exactly what is missing.
    """
    # Create pre-restore backup first (safety net)
    create_pre_restore_backup(db=db)

    # Clear any existing staging
    if RESTORE_STAGING_DIR.exists():
        shutil.rmtree(RESTORE_STAGING_DIR)

    RESTORE_STAGING_DIR.mkdir(parents=True)

    # Replay the chain in order. Deletions are applied PER ZIP, straight
    # after that zip's own extraction — not accumulated and applied at
    # the end. Accumulating them loses delete-then-recreate: a file
    # deleted in incremental N and recreated in N+1 gets extracted
    # correctly by N+1 and then removed by N's stale tombstone, so the
    # restore reports success while reconstructing a state that never
    # existed. Real for EdgeCase: delete the practice logo, later upload
    # a new one at the same `assets/logo.png` path, and the old sequence
    # restored a practice with no logo at all. Per-zip ordering is
    # unambiguous because a path cannot be both changed and deleted
    # within a single backup.
    for backup_path in point['files_needed']:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            names = zf.namelist()

            for name in names:
                if name != '_backup_metadata.json':
                    zf.extract(name, RESTORE_STAGING_DIR)

            if '_backup_metadata.json' in names:
                metadata = json.loads(zf.read('_backup_metadata.json'))
                for rel_path in metadata.get('deleted_files', []):
                    staged_path = RESTORE_STAGING_DIR / rel_path
                    if staged_path.exists():
                        staged_path.unlink()

    # Write restore marker
    marker = {
        'restore_point_id': point['id'],
        'prepared_at': datetime.now().isoformat(),
        'point_info': point
    }
    with open(RESTORE_STAGING_DIR / '.restore_marker', 'w') as f:
        json.dump(marker, f)

    return str(RESTORE_STAGING_DIR)


def create_pre_restore_backup(db=None):
    """Create a backup of current state before restore (safety net).

    Args:
        db: Optional live Database handle (WAL checkpoint + DB verification)
    """
    ensure_backup_dir()

    filename = f"pre_restore_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    backup_path = BACKUPS_DIR / filename

    # Flush WAL into the main database file before snapshotting it
    _checkpoint_db(db)

    files = get_all_backup_files()
    if not files:
        return None  # Nothing to back up

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path, abs_path in files.items():
            zf.write(abs_path, rel_path)

    verify_backup(backup_path, db=db)
    
    # Add to manifest
    manifest = load_manifest()
    manifest['backups'].append({
        'filename': filename,
        'type': 'pre_restore',
        'chain_id': 'pre_restore',
        'created_at': datetime.now().isoformat(),
        'file_count': len(files),
        'backup_size': backup_path.stat().st_size,
        'backup_dir': str(BACKUPS_DIR)
    })
    save_manifest(manifest)
    
    return str(backup_path)


def check_restore_pending():
    """Check if there's a pending restore to complete."""
    marker_path = RESTORE_STAGING_DIR / '.restore_marker'
    if marker_path.exists():
        with open(marker_path, 'r') as f:
            return json.load(f)
    return None


def complete_restore():
    """
    Complete a pending restore by replacing production files.
    Should be called at startup before database is opened.
    
    Returns dict with restore info or None if no restore pending.
    """
    marker = check_restore_pending()
    if not marker:
        return None
    
    # Replace database
    staged_db = RESTORE_STAGING_DIR / 'data' / 'edgecase.db'
    if staged_db.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        target_db = DATA_DIR / 'edgecase.db'
        if target_db.exists():
            target_db.unlink()
        # Remove stale WAL/SHM sidecars from the previous database.
        # If they survive (e.g. after a crash, when no clean-exit
        # checkpoint ran), SQLite may replay old WAL frames into the
        # freshly restored file and corrupt it.
        for suffix in ('-wal', '-shm'):
            sidecar = DATA_DIR / f'edgecase.db{suffix}'
            if sidecar.exists():
                sidecar.unlink()
        shutil.copy2(staged_db, target_db)
        # If the backup captured a WAL sidecar (taken without a
        # checkpoint), restore it alongside the database so SQLite
        # replays its committed frames instead of losing them
        staged_wal = RESTORE_STAGING_DIR / 'data' / 'edgecase.db-wal'
        if staged_wal.exists():
            shutil.copy2(staged_wal, DATA_DIR / 'edgecase.db-wal')

    # Replace key material (.salt, .secret_key, .keyinfo) so the restored
    # database is paired with the key files it was encrypted under. The
    # backup deliberately captures these (see get_all_backup_files);
    # restoring the database WITHOUT them leaves an old database sitting
    # under the CURRENT key files, which cannot be opened after any
    # intervening password change or crypto migration. Key state is
    # MIRRORED, not merged: a key file absent from the backup is deleted
    # from disk, so restoring a pre-migration (v1) backup does not leave a
    # stale .keyinfo behind that would misroute key derivation at login
    # (keyinfo_exists() would select the v2/v3 path for a v1 database).
    # The .rk_pending acknowledgement flag is mirrored for the same
    # reason: it describes the keyinfo being restored, not the one being
    # replaced. The pre-restore safety backup created in prepare_restore
    # holds the current key files if they are ever needed again.
    #
    # Consequence for the user: after restoring, log in with the password
    # that was in effect WHEN THE BACKUP WAS TAKEN.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    staged_data = RESTORE_STAGING_DIR / 'data'
    for name in ('.salt', '.secret_key', '.keyinfo', '.rk_pending'):
        staged = staged_data / name
        target = DATA_DIR / name
        if staged.exists():
            shutil.copy2(staged, target)
        elif target.exists():
            target.unlink()

    # Replace attachments
    staged_attachments = RESTORE_STAGING_DIR / 'attachments'
    if staged_attachments.exists():
        if ATTACHMENTS_DIR.exists():
            shutil.rmtree(ATTACHMENTS_DIR)
        shutil.copytree(staged_attachments, ATTACHMENTS_DIR)
    
    # Replace assets (logo, signature)
    staged_assets = RESTORE_STAGING_DIR / 'assets'
    if staged_assets.exists():
        for filepath in staged_assets.iterdir():
            if filepath.is_file() and filepath.stem in ('logo', 'signature'):
                target = ASSETS_DIR / filepath.name
                # Remove any existing logo/signature with different extension
                for existing in ASSETS_DIR.glob(f'{filepath.stem}.*'):
                    existing.unlink()
                shutil.copy2(filepath, target)
    
    # Clean up staging
    shutil.rmtree(RESTORE_STAGING_DIR)

    # Mark the restore UNVERIFIED until someone proves they can open it.
    # From this moment the data on disk is data nobody has vouched for:
    # if the backup's password turns out to be lost, the login screen is
    # a wall and — without this marker — the recovery routes are dead
    # too, because a database now exists. The marker keeps the recovery
    # door open (see auth's _recovery_gate_json) so the user can go back
    # and restore a DIFFERENT backup, including the pre-restore safety
    # backup. The first successful login deletes it, which is also what
    # closes the door — so a running practice, which by definition has
    # logged in since its last restore, is never exposed by it.
    #
    # Neither sibling has this yet: Daybook and MailRepo stop at warning
    # before the restore. The warning is right but not sufficient in the
    # disaster case, where there is no live key material to fingerprint
    # against and the note can only say "the password of the day" —
    # which the user may sincerely believe they know until they type it.
    set_restore_unverified()

    return {
        'restored_at': datetime.now().isoformat(),
        'restore_point': marker['restore_point_id'],
        'original_date': marker['point_info']['created_at'],
        # Carried from the point the user chose (Daybook's fix): the
        # login screen after the restart is the one place that can say
        # which password the restored practice wants — without it, a
        # perfectly correct restore is indistinguishable from a rejected
        # password. .get() because markers staged by older builds carry
        # no note.
        'credential_note': marker['point_info'].get('credential_note', ''),
    }


def _restore_unverified_marker():
    """Path of the unverified-restore marker. In DATA_DIR beside the key
    files it describes; NOT in get_all_backup_files, so it never rides
    into a backup."""
    return DATA_DIR / '.restore_unverified'


def set_restore_unverified():
    """Record that the data on disk came from a restore no one has
    opened yet. Failure is logged, never raised — refusing to finish a
    restore over a bookkeeping file would be worse than the gap."""
    try:
        marker = _restore_unverified_marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            'restored_at': datetime.now().isoformat(),
        }))
    except Exception as e:
        print(f"Warning: could not write restore-unverified marker: {e}")


def restore_unverified():
    """True if the last restore has not yet been opened successfully."""
    try:
        return _restore_unverified_marker().exists()
    except OSError:
        return False


def clear_restore_unverified():
    """A successful login vouches for the restored data; the recovery
    door closes behind it."""
    try:
        _restore_unverified_marker().unlink(missing_ok=True)
    except OSError as e:
        print(f"Warning: could not clear restore-unverified marker: {e}")


def cancel_restore():
    """Cancel a pending restore (remove staging folder)."""
    if RESTORE_STAGING_DIR.exists():
        shutil.rmtree(RESTORE_STAGING_DIR)
        return True
    return False


def delete_backup(backup_filename):
    """
    Delete a specific backup.
    
    Protection rules:
    - Full backups: Can delete if a newer full backup exists (cascades to its incrementals)
    - Full backups: Cannot delete if it's the only/newest full backup with incrementals
    - Incrementals: Cannot delete if later incrementals in the same chain depend on it
    
    Args:
        backup_filename: The filename of the backup to delete
    
    Returns:
        dict with success status and any warnings
    
    Raises:
        ValueError: If backup not found or deletion would break restore chain
    """
    manifest = load_manifest()
    
    # Find the backup
    backup = next((b for b in manifest['backups'] if b['filename'] == backup_filename), None)
    if not backup:
        raise ValueError("Backup not found")
    
    backup_path = resolve_backup_dir(backup) / backup_filename
    
    warnings = []
    
    # Check if it's a safety backup
    if backup['type'] == 'pre_restore':
        warnings.append("This is a safety backup created before a restore operation.")
    
    # Check if deleting a full backup
    if backup['type'] == 'full':
        chain_id = backup['chain_id']
        backup_date = backup['created_at']
        
        # Find incrementals in this chain
        incrementals_in_chain = [b for b in manifest['backups'] 
                                  if b['chain_id'] == chain_id and b['type'] == 'incremental']
        
        if incrementals_in_chain:
            # Check if there's a newer full backup
            newer_full_exists = any(
                b for b in manifest['backups'] 
                if b['type'] == 'full' and b['created_at'] > backup_date
            )
            
            if not newer_full_exists:
                raise ValueError(f"Cannot delete: {len(incrementals_in_chain)} backup(s) depend on this, and no newer full backup exists.")
            
            # Newer full exists - cascade delete the incrementals
            for incr in incrementals_in_chain:
                incr_path = resolve_backup_dir(incr) / incr['filename']
                if incr_path.exists():
                    incr_path.unlink()
                manifest['backups'].remove(incr)
            warnings.append(f"Also deleted {len(incrementals_in_chain)} dependent incremental backup(s).")
    
    # Check if deleting an incremental would break later incrementals
    if backup['type'] == 'incremental':
        chain_id = backup['chain_id']
        backup_date = backup['created_at']
        
        # Find incrementals in the same chain that are newer
        later_incrementals = [b for b in manifest['backups'] 
                              if b['chain_id'] == chain_id 
                              and b['type'] == 'incremental'
                              and b['created_at'] > backup_date]
        
        if later_incrementals:
            raise ValueError(f"Cannot delete: {len(later_incrementals)} later backup(s) depend on this. Delete them first.")
    
    # Delete the file
    if backup_path.exists():
        backup_path.unlink()
    
    # Remove from manifest
    manifest['backups'].remove(backup)
    save_manifest(manifest)
    
    return {
        'success': True,
        'warnings': warnings
    }


def cleanup_old_backups(retention, custom_location=None):
    """
    Delete backups older than the retention period.
    
    Retention periods:
    - '1_month': 30 days
    - '6_months': 180 days  
    - '1_year': 365 days
    - 'forever': no deletion
    
    Rules:
    - Always keep at least one valid restore point
    - Delete entire chains when their newest incremental exceeds retention
    - Only delete if a newer chain exists
    
    Args:
        retention: The retention period setting
        custom_location: Unused (kept for call-site compatibility). Each
            backup's directory comes from its own manifest entry via
            resolve_backup_dir(); falling back to a custom location for
            legacy entries deleted manifest records while orphaning the
            actual zips in BACKUPS_DIR (CODE_REVIEW L3).
    """
    if retention == 'forever':
        return
    
    # Convert retention to days
    retention_days = {
        '1_month': 30,
        '6_months': 180,
        '1_year': 365
    }.get(retention)
    
    if not retention_days:
        return
    
    manifest = load_manifest()

    cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
    
    # Group backups by chain
    chains = {}
    safety_backups = []  # Track safety backups separately
    for backup in manifest['backups']:
        if backup['type'] == 'pre_restore':
            safety_backups.append(backup)  # Collect for separate cleanup
            continue
        chain_id = backup.get('chain_id')
        if chain_id:
            if chain_id not in chains:
                chains[chain_id] = {'full': None, 'incrementals': []}
            if backup['type'] == 'full':
                chains[chain_id]['full'] = backup
            else:
                chains[chain_id]['incrementals'].append(backup)
    
    # Sort chains by the full backup date (oldest first)
    sorted_chain_ids = sorted(chains.keys(), 
                              key=lambda cid: chains[cid]['full']['created_at'] if chains[cid]['full'] else '')
    
    # Always keep the newest chain
    if len(sorted_chain_ids) <= 1:
        return  # Only one chain, keep it
    
    chains_to_delete = []
    
    # Check each chain except the newest
    for chain_id in sorted_chain_ids[:-1]:
        chain = chains[chain_id]
        if not chain['full']:
            continue
        
        # Find the newest backup in this chain
        all_in_chain = [chain['full']] + chain['incrementals']
        newest_date = max(b['created_at'] for b in all_in_chain)
        
        # If the newest backup in the chain is older than retention, mark for deletion
        if newest_date < cutoff_date:
            chains_to_delete.append(chain_id)
    
    # Delete marked chains
    for chain_id in chains_to_delete:
        chain = chains[chain_id]
        
        # Delete all incrementals first
        for incr in chain['incrementals']:
            incr_path = resolve_backup_dir(incr) / incr['filename']
            if incr_path.exists():
                incr_path.unlink()
            if incr in manifest['backups']:
                manifest['backups'].remove(incr)

        # Delete the full backup
        if chain['full']:
            full_path = resolve_backup_dir(chain['full']) / chain['full']['filename']
            if full_path.exists():
                full_path.unlink()
            if chain['full'] in manifest['backups']:
                manifest['backups'].remove(chain['full'])
    
    if chains_to_delete:
        save_manifest(manifest)
        print(f"Retention cleanup: Deleted {len(chains_to_delete)} old backup chain(s)")
    
    # Clean up old safety backups
    safety_deleted = 0
    for backup in safety_backups:
        if backup['created_at'] < cutoff_date:
            backup_path = resolve_backup_dir(backup) / backup['filename']
            if backup_path.exists():
                backup_path.unlink()
            if backup in manifest['backups']:
                manifest['backups'].remove(backup)
            safety_deleted += 1
    
    if safety_deleted:
        save_manifest(manifest)
        print(f"Retention cleanup: Deleted {safety_deleted} old safety backup(s)")


def check_backup_needed(frequency='daily'):
    """
    Check if an automatic backup should run.
    
    Uses CALENDAR DATE comparison against last check date, not hours:
    - 'daily': check if last check was on a different calendar date
    - 'weekly': check if last check was 7+ calendar days ago
    
    This prevents repeated backup attempts when there are no changes -
    we track when we last checked, not when we last created a backup.
    
    Args:
        frequency: 'startup', 'daily', 'weekly', or 'manual'
    
    Returns:
        True if backup should run, False otherwise
    """
    if frequency == 'manual':
        return False
    
    manifest = load_manifest()
    backups = manifest['backups']
    
    if not backups:
        return True  # No backups exist
    
    # Find most recent backup
    all_backups = [b for b in backups if b['type'] in ('full', 'incremental')]
    
    if not all_backups:
        return True
    
    if frequency in ('startup', 'session'):
        # Always backup on logout ('startup' is the legacy value for 'session')
        return True

    now = datetime.now()
    today = now.date()
    
    # Use last_backup_check if available, otherwise fall back to last backup date
    last_check = manifest.get('last_backup_check')
    if last_check:
        last_date = datetime.fromisoformat(last_check).date()
    else:
        # Legacy: no check recorded, use last backup date
        last_any = max(all_backups, key=lambda x: x['created_at'])
        last_date = datetime.fromisoformat(last_any['created_at']).date()
    
    # Use calendar date comparison
    if frequency == 'daily' and today > last_date:
        return True
    elif frequency == 'weekly' and (today - last_date).days >= 7:
        return True
    
    return False


def record_backup_check():
    """
    Record that we checked for backup today.
    Called after backup attempt (whether successful or no changes).
    """
    manifest = load_manifest()
    manifest['last_backup_check'] = datetime.now().isoformat()
    save_manifest(manifest)


def get_backup_status():
    """
    Get current backup status for display.
    Uses CALENDAR DATE for "Today" comparison, not hours.
    
    Returns dict with status info.
    """
    manifest = load_manifest()
    backups = [b for b in manifest['backups'] if b['type'] in ('full', 'incremental')]
    
    if not backups:
        return {
            'has_backups': False,
            'last_backup': None,
            'last_backup_display': 'Never',
            'backup_count': 0
        }
    
    last = max(backups, key=lambda x: x['created_at'])
    last_datetime = datetime.fromisoformat(last['created_at'])
    last_date = last_datetime.date()
    
    # Format for display using CALENDAR DATE comparison
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    
    time_str = last_datetime.strftime('%I:%M %p').lstrip('0')
    
    if last_date == today:
        # Actually today
        diff_seconds = (now - last_datetime).total_seconds()
        if diff_seconds < 60:
            display = "Just now"
        elif diff_seconds < 3600:
            minutes = int(diff_seconds // 60)
            display = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            display = f"Today at {time_str}"
    elif last_date == yesterday:
        display = f"Yesterday at {time_str}"
    else:
        days_ago = (today - last_date).days
        if days_ago < 7:
            display = f"{days_ago} days ago"
        else:
            display = last_datetime.strftime('%B %d, %Y')
    
    return {
        'has_backups': True,
        'last_backup': last['created_at'],
        'last_backup_display': display,
        'last_backup_type': last['type'],
        'backup_count': len(backups)
    }


def detect_cloud_folders():
    """
    Detect available cloud sync folders.
    Returns list of {name, path} dicts.
    """
    home = Path.home()
    cloud_folders = []
    
    # iCloud Drive
    icloud = home / 'Library' / 'Mobile Documents' / 'com~apple~CloudDocs'
    if icloud.exists():
        cloud_folders.append({
            'name': 'iCloud Drive',
            'path': str(icloud / 'EdgeCase Backups')
        })
    
    # Dropbox
    dropbox = home / 'Dropbox'
    if dropbox.exists():
        cloud_folders.append({
            'name': 'Dropbox',
            'path': str(dropbox / 'Apps' / 'EdgeCase Backups')
        })
    
    # Google Drive (new location)
    google_drive_new = home / 'Library' / 'CloudStorage'
    if google_drive_new.exists():
        for folder in google_drive_new.iterdir():
            if folder.name.startswith('GoogleDrive'):
                cloud_folders.append({
                    'name': 'Google Drive',
                    'path': str(folder / 'My Drive' / 'EdgeCase Backups')
                })
                break
    
    # Google Drive (old location)
    google_drive_old = home / 'Google Drive'
    if google_drive_old.exists() and not any(c['name'] == 'Google Drive' for c in cloud_folders):
        cloud_folders.append({
            'name': 'Google Drive',
            'path': str(google_drive_old / 'EdgeCase Backups')
        })
    
    # OneDrive
    onedrive = home / 'OneDrive'
    if onedrive.exists():
        cloud_folders.append({
            'name': 'OneDrive',
            'path': str(onedrive / 'EdgeCase Backups')
        })
    
    return cloud_folders


# ============================================================================
# DISASTER RECOVERY
#
# Everything below exists for one situation: the database (and possibly
# the whole data root) is gone, so the local manifest, the settings, and
# the login itself are gone with it. These functions find backups from
# nothing but a folder on disk — the record of known locations first,
# EdgeCase's own default folder second, a user-chosen folder last —
# and stage a restore that complete_restore() finishes at next startup.
# ============================================================================


def read_folder_stamp(folder):
    """Read the application stamp from a backup folder's sidecar, or None."""
    sidecar = Path(folder) / 'manifest.json'
    if not sidecar.exists():
        return None
    try:
        with open(sidecar, 'r') as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        return None

    if not isinstance(manifest, dict) or 'app' not in manifest:
        return None
    return manifest


def _looks_like_backup_folder(names):
    """True if this directory's file names look like a backup set
    (EdgeCase's or a sibling application's — the two are identical by
    name)."""
    if 'manifest.json' in names:
        return True
    return any(_BACKUP_FILENAME_RE.match(name) for name in names)


def folder_holds_edgecase_backups(folder):
    """Confirm a folder holds THIS application's backups.

    Checked in order of authority:

    1. The stamp in the sidecar manifest. save_manifest marks every
       folder EdgeCase writes to, so its own backups identify
       themselves.
    2. Failing that, the contents of a full backup. Folders written
       before stamping existed carry no marker, and refusing those
       would make recovery useless to the person who has been backing
       up diligently all along — exactly the person it is for.

    The fallback stays narrow: the database filename inside a full zip
    is the only thing that separates an EdgeCase backup from a MailRepo
    one (see APP_ID). Restoring a MailRepo backup here would overwrite
    key material while providing no database.
    """
    folder = Path(folder)

    stamp = read_folder_stamp(folder)
    if stamp is not None:
        return stamp.get('app') == APP_ID

    try:
        candidates = sorted(
            (p for p in folder.iterdir()
             if p.is_file() and p.name.startswith('full_')),
            reverse=True,
        )
    except OSError:
        return False

    for candidate in candidates[:3]:
        try:
            with zipfile.ZipFile(candidate, 'r') as zf:
                names = zf.namelist()
        except Exception:
            continue

        if any(name.endswith('data/edgecase.db') or name == 'edgecase.db'
               for name in names):
            return True

        # A readable full backup that is definitively something else.
        # Stop rather than hoping an older one disagrees.
        return False

    return False


def reconstruct_manifest_entries(folder):
    """Rebuild manifest entries from the zips in a folder, by filename.

    The last resort, for when a backup folder survived but its manifest
    did not. Backup filenames carry type and a sortable timestamp, and
    the writer only ever appends to the newest chain, so the structure
    is recoverable: each `full_` opens a chain, every `incr_` after it
    joins that chain, and `pre_restore_` files stand alone.

    This is inference, not a record. It is wrong if two machines wrote
    to one folder, since their chains would interleave by time and get
    stitched into one. Entries are marked `reconstructed` so the caller
    can say so plainly rather than presenting a guess as a fact.
    """
    folder = Path(folder)
    entries = []

    try:
        names = [p.name for p in folder.iterdir() if p.is_file()]
    except OSError as e:
        print(f"Warning: could not read backup folder {folder}: {e}")
        return entries

    # Parse first, then sort CHRONOLOGICALLY. Sorting the filenames
    # directly does not work: the type prefix leads, so every "full_"
    # sorts ahead of every "incr_" regardless of date, and a folder
    # holding two chains gets stitched into one with all the fulls at
    # the front. Timestamp order is the whole basis for inferring which
    # full an incremental belongs to.
    parsed = []
    for name in names:
        match = _BACKUP_FILENAME_RE.match(name)
        if not match:
            continue

        prefix, date_part, time_part, suffix = match.groups()
        try:
            created = datetime.strptime(
                f"{date_part} {time_part}", '%Y-%m-%d %H%M%S')
        except ValueError:
            continue

        parsed.append((created, suffix or '', name, _TYPE_FROM_PREFIX[prefix]))

    parsed.sort(key=lambda item: (item[0], item[1], item[2]))

    current_chain = None

    for created, _suffix, name, backup_type in parsed:
        if backup_type == 'pre_restore':
            # EdgeCase's own manifests give every safety backup the
            # literal chain_id 'pre_restore' (see create_pre_restore_backup),
            # and build_restore_points keys its standalone handling on
            # exactly that value. Reconstruction must match the writer.
            chain_id = 'pre_restore'
        elif backup_type == 'full':
            current_chain = created.strftime('%Y%m%d_%H%M%S')
            chain_id = current_chain
        else:
            if current_chain is None:
                # Incremental with no preceding full: an orphan. Kept out
                # rather than invented a chain for — build_restore_points
                # drops orphaned incrementals anyway.
                continue
            chain_id = current_chain

        size = 0
        try:
            size = (folder / name).stat().st_size
        except OSError:
            pass

        entries.append({
            'filename': name,
            'type': backup_type,
            'chain_id': chain_id,
            'created_at': created.isoformat(),
            'backup_size': size,
            'backup_dir': str(folder),
            'reconstructed': True,
        })

    return entries


def discover_restore_points_in(folder):
    """Find restore points in a folder that is not the local backups dir.

    The recovery entry point: the user knows where their backups are,
    and nothing on this machine does. Prefers the manifest sidecar
    written alongside the zips; falls back to filename reconstruction
    when there isn't one.

    Returns (points, source) where source is "manifest", "reconstructed",
    or "empty" — the caller needs to tell the user which, because a
    reconstructed chain deserves a second look at the dates before
    anyone overwrites anything with it.
    """
    folder = Path(folder)

    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")

    # Refuse another application's backups outright. MailRepo's are
    # byte-for-byte plausible here — same filenames, same key-file paths
    # — and restoring one would overwrite this install's key files while
    # finding no database to go with them. Checked on the manual path as
    # well as the search path, or the folder picker becomes the hole the
    # search was careful to close.
    if not folder_holds_edgecase_backups(folder):
        try:
            names = {p.name for p in folder.iterdir() if p.is_file()}
        except OSError:
            names = set()
        if _looks_like_backup_folder(names):
            raise ValueError(
                "That folder holds backups from a different application, "
                "not EdgeCase.")
        return [], 'empty'

    sidecar = folder / 'manifest.json'
    if sidecar.exists():
        try:
            with open(sidecar, 'r') as f:
                manifest = json.load(f)
            points = build_restore_points(
                manifest.get('backups', []), override_dir=folder)
            if points:
                return points, 'manifest'
            # A sidecar listing nothing that is actually present is worse
            # than no sidecar — fall through and look at real files.
            print(f"Warning: manifest in {folder} matched no files on disk; "
                  f"reconstructing")
        except (json.JSONDecodeError, ValueError, OSError) as e:
            print(f"Warning: could not read manifest in {folder}: {e}")

    entries = reconstruct_manifest_entries(folder)
    if not entries:
        return [], 'empty'

    points = build_restore_points(entries, override_dir=folder)
    for point in points:
        point['reconstructed'] = True

    return points, ('reconstructed' if points else 'empty')


def verify_restore_point_files(restore_point):
    """Verify every file a restore point depends on is actually usable.

    A manifest entry is a claim, not evidence. This opens each file in
    the chain, which is what proves the claim:

      - exists() catches a deleted or moved backup
      - a zero size catches a truncated write
      - opening the zip forces cloud-storage materialization, so an
        iCloud-evicted placeholder fails here instead of at restore time
      - testzip() catches silent corruption

    Returns a list of human-readable problems. Empty list means the
    whole chain is verified good.
    """
    problems = []

    for path_str in restore_point.get('files_needed', []):
        path = Path(path_str)
        name = path.name

        if not path.exists():
            problems.append(f"{name}: missing from disk")
            continue

        try:
            size = path.stat().st_size
        except OSError as e:
            problems.append(f"{name}: cannot stat ({e})")
            continue

        if size == 0:
            problems.append(f"{name}: zero bytes")
            continue

        try:
            with zipfile.ZipFile(path, 'r') as zf:
                bad_file = zf.testzip()
        except zipfile.BadZipFile:
            problems.append(f"{name}: not a readable zip (corrupt or truncated)")
            continue
        except OSError as e:
            # Cloud-evicted files and permission failures land here.
            problems.append(f"{name}: unreadable ({e})")
            continue

        if bad_file:
            problems.append(f"{name}: fails integrity check ({bad_file})")

    return problems


# ----------------------------------------------------------------------------
# Which credentials will open a restore point (Daybook's fix, ported)
#
# A backup carries its key material as it stood, so a restored practice
# opens with the master password (and recovery key) of the moment the
# backup was TAKEN — not whatever is in use today. Restoring a backup
# whose credentials you no longer hold locks you out of your own data,
# and the login screen cannot tell that apart from a typo. Daybook's
# ruling: say which credentials a backup needs BEFORE anyone clicks
# Restore, beside the specific backup it is true of, and again on the
# login screen after the restore lands.
#
# The fingerprint works without trying a single password. The ECC3
# key-info file is two independent halves — (salt_pw + wrapped_pw) and
# (salt_rk + wrapped_rk) — and every rewrap mints a fresh salt and
# touches exactly one half (see core.encryption_v3.rewrap_password /
# rewrap_recovery_key). So hashing the halves separately says which
# credential has changed since the backup, byte-comparison only.
# ----------------------------------------------------------------------------


def keyinfo_fingerprint(blob):
    """Identify which credentials a key-info file belongs to, without
    using them. Returns {version, password_id, recovery_id} or None for
    a blob that is not a recognisable key-info file."""
    if not blob or len(blob) < 4:
        return None

    magic = blob[:4]

    if magic == b'ECC2':
        # v2: password wrap only, no recovery key, no split to hash.
        return {'version': 2, 'password_id': None, 'recovery_id': None}

    if magic != b'ECC3':
        return None

    # Offsets rebuilt from core.encryption_v3's public constants rather
    # than importing its private _OFF_* names. Imported lazily so
    # utils.backup keeps no module-scope crypto dependency — backup code
    # runs in contexts where the archive is locked.
    from core.encryption_v3 import (
        KEYINFO_MAGIC_V3, KEYINFO_LEN_V3, SALT_LEN_V3, WRAPPED_LEN)

    if len(blob) != KEYINFO_LEN_V3:
        return None

    off_pw = len(KEYINFO_MAGIC_V3)
    off_rk = off_pw + SALT_LEN_V3 + WRAPPED_LEN

    return {
        'version': 3,
        'password_id': hashlib.sha256(blob[off_pw:off_rk]).hexdigest()[:16],
        'recovery_id': hashlib.sha256(blob[off_rk:]).hexdigest()[:16],
    }


def read_restore_point_key_material(files_needed):
    """The key material a restore point would actually land on disk.

    Incrementals only carry files that changed, so most contain no key
    files at all. The effective key-info is the one from the LAST backup
    in the chain that has it — that is what extraction leaves behind.

    Returns (keyinfo_blob_or_None, saw_salt). `saw_salt` distinguishes a
    v1-era backup (salt and secret key, but no key-info file existed
    yet) from a chain carrying no key material at all.
    """
    keyinfo = None
    saw_salt = False

    for path_str in files_needed:
        try:
            with zipfile.ZipFile(path_str, 'r') as zf:
                names = zf.namelist()
                if 'data/.keyinfo' in names:
                    keyinfo = zf.read('data/.keyinfo')
                if 'data/.salt' in names:
                    saw_salt = True
        except Exception:
            continue

    return keyinfo, saw_salt


def describe_restore_point_credentials(files_needed, current_blob=None):
    """What credentials would open this restore point, versus today's.

    Returns {'status': ..., 'note': ...}; the note is written for
    someone about to click Restore. Never raises — a restore screen that
    will not render because a fingerprint failed is worse than one that
    says nothing, so every unknown collapses to a quiet empty note.
    """
    unknown = {'status': 'unknown', 'note': ''}

    try:
        if current_blob is None:
            # The live key-info path is owned by core.encryption_v2 (v3
            # defers to it); read at call time so test overrides hold.
            from core import encryption_v2
            keyinfo_path = Path(encryption_v2.KEYINFO_FILE)
            current_blob = (keyinfo_path.read_bytes()
                            if keyinfo_path.exists() else None)

        current = keyinfo_fingerprint(current_blob)
        backup_blob, saw_salt = read_restore_point_key_material(files_needed)
        backed_up = keyinfo_fingerprint(backup_blob)

        if backed_up is None:
            if saw_salt:
                # v1 vintage: key material but no key-info file. Still
                # restorable — login auto-upgrades the encryption — but
                # only the password of the day opens it.
                return {
                    'status': 'predates_recovery_keys',
                    'note': ('Opens with the master password in use when '
                             'this backup was made. It predates recovery '
                             'keys, so no recovery key will open it.'),
                }
            return unknown

        if backed_up['version'] == 2:
            return {
                'status': 'predates_recovery_keys',
                'note': ('Opens with the master password in use when this '
                         'backup was made. It predates recovery keys, so '
                         'no recovery key will open it. EdgeCase will '
                         'offer a new recovery key after you log in.'),
            }

        if current is None:
            # No key-info on this machine at all — the disaster case,
            # and the one place this matters most. Nothing to compare
            # against, but silence is the wrong answer: the user is
            # about to type a password and needs to know which one.
            return {
                'status': 'no_current_key',
                'note': ('Opens with the master password or recovery key '
                         'that were in use when this backup was made — '
                         'not any you have set since. If you have '
                         'neither, do not restore this one.'),
            }

        if current['version'] != 3:
            return unknown

        password_changed = backed_up['password_id'] != current['password_id']
        recovery_rotated = backed_up['recovery_id'] != current['recovery_id']

        if password_changed and recovery_rotated:
            return {
                'status': 'both_changed',
                'note': ('Both your master password and your recovery key '
                         'have changed since this backup. It opens ONLY '
                         'with the ones in use at the time. If you have '
                         'neither, do not restore this one — you would be '
                         'locked out of it.'),
            }
        if password_changed:
            return {
                'status': 'password_changed',
                'note': ('Your master password has changed since this '
                         'backup. It opens with the password you used '
                         'then, not your current one. Your current '
                         'recovery key still works.'),
            }
        if recovery_rotated:
            return {
                'status': 'recovery_key_rotated',
                'note': ('Your recovery key has been replaced since this '
                         'backup. It opens with the earlier key, or with '
                         'your current master password.'),
            }

        return {'status': 'current', 'note': ''}
    except Exception as e:
        print(f"Warning: could not fingerprint restore point credentials: {e}")
        return unknown


def find_backup_locations():
    """Where this install's backups are, without guessing.

    Two checks, both certain:

    1. The record. EdgeCase notes every folder it writes backups to, in
       a file outside the data root (see record_backup_location), so it
       survives the loss that makes it necessary.
    2. EdgeCase's own default backups folder — the one place backups go
       when the user never chose a location, and the one place worth
       checking when the record itself is gone.

    There is deliberately no filesystem search beyond these. Guessing at
    cloud-provider paths surfaces MailRepo's byte-identical backup
    folders and breaks when providers move their mount points. A user
    who put backups somewhere of their own choosing knows where — the
    folder picker on the recovery screen covers that case without a
    single assumption.

    Results carry `known=True` when they came from the record.
    """
    results = []
    seen = set()

    for entry in get_known_locations():
        directory = Path(entry['path'])
        try:
            resolved = directory.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue

        if not folder_holds_edgecase_backups(directory):
            continue

        try:
            points, source = discover_restore_points_in(directory)
        except Exception as e:
            print(f"Warning: recorded location {directory} could not be read: {e}")
            continue

        if not points:
            continue

        seen.add(resolved)
        results.append({
            'path': str(directory),
            'label': _describe_location(directory),
            'source': source,
            'known': True,
            'last_written': entry.get('last_written'),
            'restore_point_count': len(points),
            'newest': points[0]['created_at'],
            'newest_display': points[0]['display_name'],
            'restore_points': points,
        })

    if results:
        return results

    # No usable record. Check the one folder EdgeCase itself owns before
    # giving up — an install that predates the location record, or a
    # default setup whose backups folder survived, lands here.
    try:
        if BACKUPS_DIR.is_dir() and folder_holds_edgecase_backups(BACKUPS_DIR):
            points, source = discover_restore_points_in(BACKUPS_DIR)
            if points:
                results.append({
                    'path': str(BACKUPS_DIR),
                    'label': _describe_location(BACKUPS_DIR),
                    'source': source,
                    'known': False,
                    'restore_point_count': len(points),
                    'newest': points[0]['created_at'],
                    'newest_display': points[0]['display_name'],
                    'restore_points': points,
                })
    except Exception as e:
        print(f"Warning: default backups folder could not be read: {e}")

    return results


def _describe_location(path):
    """A human label for where a backup folder lives."""
    path = Path(path)
    text = str(path)
    home = str(Path.home())

    if 'com~apple~CloudDocs' in text:
        return f"iCloud Drive — {path.name}"
    if '/Dropbox/' in text or text.endswith('/Dropbox'):
        return f"Dropbox — {path.name}"
    if '/OneDrive' in text:
        return f"OneDrive — {path.name}"
    if 'Google Drive' in text or 'GoogleDrive' in text:
        return f"Google Drive — {path.name}"
    if text.startswith('/Volumes/') or text.startswith('/media/') or text.startswith('/mnt/'):
        return f"External drive — {path.name}"
    if text.startswith(home):
        return f"This computer — {path.name}"
    return str(path)


def picker_shortcuts(home=None, volumes_root=None, media_roots=None):
    """Places a backup plausibly lives, for the recovery folder picker.

    The picker's empty-state text tells the user their backups may be on
    "an external disk" — so the picker must be able to REACH one without
    the user knowing that /Volumes exists or that '..' climbs a level.
    Overridable roots keep this testable without a real mounted drive.

    Returns a list of {'name', 'path'} dicts; every path exists.
    """
    home = Path(home) if home else Path.home()
    shortcuts = []

    def add(name, path):
        try:
            if path.is_dir():
                shortcuts.append({'name': name, 'path': str(path)})
        except OSError:
            pass

    add('Home', home)
    add('Desktop', home / 'Desktop')
    add('Documents', home / 'Documents')
    add('iCloud Drive',
        home / 'Library' / 'Mobile Documents' / 'com~apple~CloudDocs')

    # External drives. macOS mounts under /Volumes (the boot volume appears
    # there too, as a link back to / — skip it; "Macintosh HD" is not where
    # anyone's backup drive lives). Linux mounts under /media/<user> and
    # /run/media/<user>.
    roots = []
    if volumes_root is not None:
        roots.append(Path(volumes_root))
    elif os.path.isdir('/Volumes'):
        roots.append(Path('/Volumes'))
    if media_roots is not None:
        roots.extend(Path(r) for r in media_roots)
    else:
        user = os.environ.get('USER', '')
        for base in (f'/media/{user}', f'/run/media/{user}'):
            if os.path.isdir(base):
                roots.append(Path(base))

    seen = {s['path'] for s in shortcuts}
    for root in roots:
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
                if entry.resolve() == Path('/').resolve():
                    continue  # the boot volume's link back to /
            except OSError:
                continue
            if str(entry) not in seen:
                add(entry.name, entry)
                seen.add(str(entry))

    return shortcuts
