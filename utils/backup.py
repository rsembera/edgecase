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
import zipfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Use config for all paths so EDGECASE_DATA override works
from core.config import DATA_ROOT, DATA_DIR, ATTACHMENTS_DIR, ASSETS_DIR, BACKUPS_DIR

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
    
    # Security files (salt and secret key - essential for decryption)
    salt_path = DATA_DIR / '.salt'
    if salt_path.exists():
        files['data/.salt'] = salt_path
    
    secret_key_path = DATA_DIR / '.secret_key'
    if secret_key_path.exists():
        files['data/.secret_key'] = secret_key_path
    
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


def save_manifest(manifest):
    """Save backup manifest to disk."""
    ensure_backup_dir()
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)


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


def create_backup(backup_dir=None):
    """
    Create a backup, automatically deciding between full and incremental.
    
    Decision logic:
    - No previous backups → full
    - Last full backup > 7 days old → full
    - Otherwise → incremental (only changed files)
    
    Args:
        backup_dir: Optional custom backup directory (for cloud folders)
    
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
        return create_full_backup(backup_dir)
    else:
        return create_incremental_backup(backup_dir)


def create_full_backup(backup_dir=None):
    """
    Create a full backup of all data.
    
    Args:
        backup_dir: Optional custom backup directory (for cloud folders)
    
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
    
    # Verify backup
    verify_backup(backup_path)
    
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


def create_incremental_backup(backup_dir=None):
    """
    Create an incremental backup (only changed files since last backup).
    
    Args:
        backup_dir: Optional custom backup directory
    
    Returns:
        dict with backup info, or None if no changes
    """
    manifest = load_manifest()
    
    if not manifest['last_full_hashes']:
        # No previous backup, need full backup first
        return create_full_backup(backup_dir)
    
    if backup_dir is None:
        backup_dir = BACKUPS_DIR
    else:
        backup_dir = Path(backup_dir)
    
    # Validate location before starting
    valid, error = validate_backup_location(backup_dir)
    if not valid:
        raise ValueError(error)
    
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
    
    # Verify backup
    verify_backup(backup_path)
    
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


def verify_backup(backup_path):
    """
    Verify backup zip integrity.
    Raises exception if corrupted.
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


def list_backups():
    """
    List all available backups with details.
    Returns list sorted by date (newest first).
    """
    manifest = load_manifest()
    backups = []
    
    for backup in manifest['backups']:
        # Check if file still exists
        backup_dir = Path(backup.get('backup_dir', BACKUPS_DIR))
        backup_path = backup_dir / backup['filename']
        
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
    backups = manifest['backups']
    
    # Group by chain
    chains = {}
    for backup in backups:
        chain_id = backup['chain_id']
        if chain_id not in chains:
            chains[chain_id] = {'full': None, 'incrementals': [], 'pre_restore': None}
        
        if backup['type'] == 'full':
            chains[chain_id]['full'] = backup
        elif backup['type'] == 'pre_restore':
            chains[chain_id]['pre_restore'] = backup
        else:
            chains[chain_id]['incrementals'].append(backup)
    
    # Build restore points
    restore_points = []
    
    for chain_id, chain in chains.items():
        # Handle pre_restore backups (standalone, not part of a chain)
        if chain_id == 'pre_restore' and chain.get('pre_restore'):
            backup = chain['pre_restore']
            backup_path = Path(backup.get('backup_dir', BACKUPS_DIR)) / backup['filename']
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
                    'chain_id': 'pre_restore',
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
        backup_path = Path(full_backup.get('backup_dir', BACKUPS_DIR)) / full_backup['filename']
        
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
            incr_path = Path(incr.get('backup_dir', BACKUPS_DIR)) / incr['filename']
            if incr_path.exists():
                files_needed = files_needed + [str(incr_path)]
                
                # Format date with time
                created = datetime.fromisoformat(incr['created_at'])
                display_time = created.strftime('%b %d, %Y at %I:%M %p').replace(' 0', ' ')
                
                restore_points.append({
                    'id': f"{chain_id}_incr_{i}",
                    'filename': incr['filename'],
                    'display_name': display_time,
                    'created_at': incr['created_at'],
                    'type': 'incremental',
                    'is_safety': False,
                    'chain_id': chain_id,
                    'dependent_count': 0,
                    'files_needed': files_needed.copy()
                })
    
    # Sort by date, newest first
    restore_points.sort(key=lambda x: x['created_at'], reverse=True)
    return restore_points


def prepare_restore(restore_point_id):
    """
    Prepare for restore by extracting to staging folder.
    Does NOT replace production files yet.
    
    Returns path to staging folder.
    """
    restore_points = get_restore_points()
    point = next((p for p in restore_points if p['id'] == restore_point_id), None)
    
    if not point:
        raise ValueError(f"Restore point not found: {restore_point_id}")
    
    # Create pre-restore backup first (safety net)
    create_pre_restore_backup()
    
    # Clear any existing staging
    if RESTORE_STAGING_DIR.exists():
        shutil.rmtree(RESTORE_STAGING_DIR)
    
    RESTORE_STAGING_DIR.mkdir(parents=True)
    
    # Track deleted files across incrementals
    deleted_files = set()
    
    # Extract backups in order (full first, then incrementals)
    for backup_path in point['files_needed']:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            # Check for metadata about deleted files
            if '_backup_metadata.json' in zf.namelist():
                metadata = json.loads(zf.read('_backup_metadata.json'))
                deleted_files.update(metadata.get('deleted_files', []))
            
            # Extract all other files (overwrites previous versions)
            for name in zf.namelist():
                if name != '_backup_metadata.json':
                    zf.extract(name, RESTORE_STAGING_DIR)
    
    # Remove files that were deleted in later backups
    for rel_path in deleted_files:
        staged_path = RESTORE_STAGING_DIR / rel_path
        if staged_path.exists():
            staged_path.unlink()
    
    # Write restore marker
    marker = {
        'restore_point_id': restore_point_id,
        'prepared_at': datetime.now().isoformat(),
        'point_info': point
    }
    with open(RESTORE_STAGING_DIR / '.restore_marker', 'w') as f:
        json.dump(marker, f)
    
    return str(RESTORE_STAGING_DIR)


def create_pre_restore_backup():
    """Create a backup of current state before restore (safety net)."""
    ensure_backup_dir()
    
    filename = f"pre_restore_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    backup_path = BACKUPS_DIR / filename
    
    files = get_all_backup_files()
    if not files:
        return None  # Nothing to back up
    
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path, abs_path in files.items():
            zf.write(abs_path, rel_path)
    
    verify_backup(backup_path)
    
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
        shutil.copy2(staged_db, target_db)
    
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
    
    return {
        'restored_at': datetime.now().isoformat(),
        'restore_point': marker['restore_point_id'],
        'original_date': marker['point_info']['created_at']
    }


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
    
    backup_path = Path(backup.get('backup_dir', BACKUPS_DIR)) / backup_filename
    
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
                incr_path = Path(incr.get('backup_dir', BACKUPS_DIR)) / incr['filename']
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
        custom_location: Optional custom backup directory
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
    backup_dir = Path(custom_location) if custom_location else BACKUPS_DIR
    
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
            incr_path = Path(incr.get('backup_dir', backup_dir)) / incr['filename']
            if incr_path.exists():
                incr_path.unlink()
            if incr in manifest['backups']:
                manifest['backups'].remove(incr)
        
        # Delete the full backup
        if chain['full']:
            full_path = Path(chain['full'].get('backup_dir', backup_dir)) / chain['full']['filename']
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
            backup_path = Path(backup.get('backup_dir', backup_dir)) / backup['filename']
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
    
    if frequency == 'startup':
        return True  # Legacy value, treat as session
    
    if frequency == 'session':
        return True  # Always backup on logout
    
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


def get_backup_location():
    """Get current backup location from settings or default."""
    # This will be called from routes with db access
    # For now, return default
    return str(BACKUPS_DIR)
