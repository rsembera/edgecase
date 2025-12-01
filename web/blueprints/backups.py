# -*- coding: utf-8 -*-
"""
EdgeCase Backups Blueprint
Handles all backup and restore functionality
"""

from flask import Blueprint, render_template, request, jsonify
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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


@backups_bp.route('/api/backup/delete', methods=['POST'])
def delete_backup():
    """Delete a specific backup."""
    from utils import backup
    
    data = request.get_json()
    backup_id = data.get('backup_id')
    
    if not backup_id:
        return jsonify({'success': False, 'error': 'No backup specified'}), 400
    
    try:
        # Get restore points to find the backup
        points = backup.get_restore_points()
        point = next((p for p in points if p['id'] == backup_id), None)
        
        if not point:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404
        
        # Get the filename from the last file in files_needed
        # For full backups, this is the only file
        # For incrementals, we delete just the incremental
        backup_path = Path(point['files_needed'][-1])
        filename = backup_path.name
        
        result = backup.delete_backup(filename)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
