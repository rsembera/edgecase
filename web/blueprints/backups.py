# -*- coding: utf-8 -*-
"""
EdgeCase Backups Blueprint
Handles all backup and restore functionality
"""

from flask import Blueprint, render_template, request, jsonify
from pathlib import Path

from core.database import Database

# Initialize blueprint
backups_bp = Blueprint('backups', __name__)

# Database instance (set by init_blueprint)
db = None


def init_blueprint(database):
    """Initialize blueprint with database instance"""
    global db
    db = database


# ============================================================================
# BACKUPS PAGE
# ============================================================================

@backups_bp.route('/backups')
def backups_page():
    """Backups page."""
    return render_template('backups.html')


# ============================================================================
# BACKUP STATUS & SETTINGS
# ============================================================================

@backups_bp.route('/api/backup/status')
def backup_status():
    """Get current backup status."""
    from utils import backup
    
    status = backup.get_backup_status()
    
    # Get settings from database
    status['frequency'] = db.get_setting('backup_frequency', 'daily')
    status['retention'] = db.get_setting('backup_retention', 'forever')
    status['post_backup_command'] = db.get_setting('post_backup_command', '')
    
    # Return saved location, or empty string if using default
    location = db.get_setting('backup_location', '')
    status['location'] = location
    
    status['cloud_folders'] = backup.detect_cloud_folders()
    
    # Check if restore is pending
    pending = backup.check_restore_pending()
    status['restore_pending'] = pending is not None
    if pending:
        status['restore_point'] = pending.get('point_info', {}).get('display_name', 'Unknown')
    
    return jsonify(status)


@backups_bp.route('/api/backup/settings', methods=['POST'])
def save_backup_settings():
    """Save backup settings."""
    data = request.get_json()
    
    if 'frequency' in data:
        db.set_setting('backup_frequency', data['frequency'])
    
    if 'retention' in data:
        db.set_setting('backup_retention', data['retention'])
    
    if 'post_backup_command' in data:
        db.set_setting('post_backup_command', data['post_backup_command'])
    
    # Handle location
    if 'location' in data:
        location_value = data['location']
        if location_value:  # Non-empty string = custom location
            # Validate location exists or can be created
            location = Path(location_value)
            try:
                location.mkdir(parents=True, exist_ok=True)
                db.set_setting('backup_location', str(location))
            except Exception as e:
                return jsonify({'success': False, 'error': f'Cannot create backup folder: {e}'}), 400
        else:  # Empty string = clear custom location, use default
            db.set_setting('backup_location', '')
    
    return jsonify({'success': True})


# ============================================================================
# BACKUP OPERATIONS
# ============================================================================

@backups_bp.route('/api/backup/now', methods=['POST'])
def backup_now():
    """Trigger immediate backup. System auto-decides full vs incremental."""
    from utils import backup
    import subprocess
    
    # Checkpoint WAL to ensure all changes are in main database file
    db.checkpoint()
    
    location = db.get_setting('backup_location', '')
    if not location:
        location = None  # Use default
    
    try:
        # Use create_backup() which auto-decides full vs incremental
        result = backup.create_backup(location)
        
        if result is None:
            return jsonify({
                'success': True,
                'message': 'No changes since last backup',
                'backup': None
            })
        
        # Run retention cleanup
        retention = db.get_setting('backup_retention', 'forever')
        if retention != 'forever':
            backup.cleanup_old_backups(retention, location)
        
        # Run post-backup command if configured
        post_cmd = db.get_setting('post_backup_command', '')
        if post_cmd:
            try:
                subprocess.run(post_cmd, shell=True, timeout=300)
            except Exception as cmd_error:
                # Log but don't fail the backup
                print(f"Post-backup command error: {cmd_error}")
        
        return jsonify({
            'success': True,
            'message': 'Backup created',
            'backup': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@backups_bp.route('/api/backup/list')
def list_backups():
    """List all available backups."""
    from utils import backup
    
    backups_list = backup.list_backups()
    return jsonify({'backups': backups_list})


# ============================================================================
# RESTORE OPERATIONS
# ============================================================================

@backups_bp.route('/api/backup/restore-points')
def restore_points():
    """Get available restore points."""
    from utils import backup
    
    points = backup.get_restore_points()
    return jsonify({'restore_points': points})


@backups_bp.route('/api/backup/prepare-restore', methods=['POST'])
def prepare_restore():
    """Prepare restore from a specific point."""
    from utils import backup
    
    data = request.get_json()
    restore_point = data.get('restore_point') or data.get('restore_point_id')
    
    if not restore_point:
        return jsonify({'success': False, 'error': 'No restore point specified'}), 400
    
    try:
        staging_path = backup.prepare_restore(restore_point)
        return jsonify({
            'success': True,
            'message': 'Restore prepared. Close EdgeCase and reopen to complete.',
            'staging_path': staging_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@backups_bp.route('/api/backup/cancel-restore', methods=['POST'])
def cancel_restore():
    """Cancel pending restore."""
    from utils import backup
    
    cancelled = backup.cancel_restore()
    return jsonify({
        'success': True,
        'cancelled': cancelled
    })


# ============================================================================
# CLOUD FOLDERS
# ============================================================================

@backups_bp.route('/api/backup/cloud-folders')
def cloud_folders():
    """Detect available cloud sync folders."""
    from utils import backup
    
    folders = backup.detect_cloud_folders()
    return jsonify({'folders': folders})


# ============================================================================
# FOLDER PICKER
# ============================================================================

@backups_bp.route('/api/backup/list-folders')
def list_folders():
    """List folders at a given path for the folder picker modal.
    
    Query params:
        path: Directory path to list (defaults to home directory)
    
    Returns:
        JSON with:
            - current_path: The resolved absolute path
            - parent_path: Parent directory (null if at root)
            - folders: List of {name, path} for subdirectories
            - error: Error message if path is invalid
    """
    import os
    
    # Get requested path, default to home directory
    requested_path = request.args.get('path', '')
    
    # Default to home directory if no path provided
    if not requested_path:
        requested_path = str(Path.home())
    
    # Resolve to absolute path
    try:
        current_path = Path(requested_path).expanduser().resolve()
    except Exception as e:
        return jsonify({'error': f'Invalid path: {e}'}), 400
    
    # Check if path exists and is a directory
    if not current_path.exists():
        return jsonify({'error': 'Path does not exist'}), 400
    
    if not current_path.is_dir():
        return jsonify({'error': 'Path is not a directory'}), 400
    
    # Get parent path (null if at filesystem root)
    parent_path = None
    if current_path.parent != current_path:  # Not at root
        parent_path = str(current_path.parent)
    
    # List subdirectories, excluding hidden folders (starting with .)
    folders = []
    try:
        for item in sorted(current_path.iterdir()):
            # Skip hidden files/folders
            if item.name.startswith('.'):
                continue
            # Only include directories
            if item.is_dir():
                # Skip directories we can't access
                try:
                    list(item.iterdir())  # Test if we can read it
                    folders.append({
                        'name': item.name,
                        'path': str(item)
                    })
                except PermissionError:
                    # Include but mark as inaccessible
                    folders.append({
                        'name': item.name,
                        'path': str(item),
                        'inaccessible': True
                    })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403
    
    return jsonify({
        'current_path': str(current_path),
        'parent_path': parent_path,
        'folders': folders
    })
