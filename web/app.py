"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import sys
import time
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# STARTUP RESTORE CHECK
# Must happen BEFORE database is opened
# ============================================================================

from utils import backup as backup_utils

_restore_result = None
_pending_restore = backup_utils.check_restore_pending()
if _pending_restore:
    try:
        _restore_result = backup_utils.complete_restore()
        print(f"✔ Restore completed from {_restore_result.get('original_date', 'unknown')[:10]}")
    except Exception as e:
        print(f"✗ Restore failed: {e}")
        backup_utils.cancel_restore()
        _restore_result = {'error': str(e)}

# ============================================================================
# FLASK APP SETUP
# ============================================================================

from web.blueprints.auth import auth_bp
from web.blueprints.settings import settings_bp
from web.blueprints.types import types_bp
from web.blueprints.links import links_bp
from web.blueprints.clients import clients_bp
from web.blueprints.entries import entries_bp
from web.blueprints.ledger import ledger_bp
from web.blueprints.scheduler import scheduler_bp
from web.blueprints.statements import statements_bp
from web.blueprints.backups import backups_bp
from web.blueprints.ai import ai_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'edgecase-dev-key-change-in-production'

# Database will be set after login
app.config['db'] = None

# Store restore result for display (if any)
if _restore_result and 'error' not in _restore_result:
    app.config['RESTORE_COMPLETED'] = _restore_result

def init_all_blueprints(db):
    """Initialize all blueprints with database instance after login."""
    from web.blueprints.clients import init_blueprint as init_clients
    from web.blueprints.entries import init_blueprint as init_entries
    from web.blueprints.ledger import init_blueprint as init_ledger
    from web.blueprints.statements import init_blueprint as init_statements
    from web.blueprints.scheduler import init_blueprint as init_scheduler
    from web.blueprints.types import init_blueprint as init_types
    from web.blueprints.settings import init_blueprint as init_settings
    from web.blueprints.links import init_blueprint as init_links
    from web.blueprints.backups import init_blueprint as init_backups
    from web.blueprints.ai import init_blueprint as init_ai
    
    init_clients(db)
    init_entries(db)
    init_ledger(db)
    init_statements(db)
    init_scheduler(db)
    init_types(db)
    init_settings(db)
    init_links(db)
    init_backups(db)
    init_ai(db)

# Ensure data directory exists
project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

# Register blueprints (but don't initialize with db yet - that happens after login)
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(types_bp)
app.register_blueprint(links_bp)
app.register_blueprint(clients_bp)
app.register_blueprint(entries_bp)
app.register_blueprint(ledger_bp)
app.register_blueprint(scheduler_bp)
app.register_blueprint(statements_bp, url_prefix='/statements')
app.register_blueprint(backups_bp)
app.register_blueprint(ai_bp)

from datetime import datetime         

@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to readable date."""
    if not timestamp:
        return '-'
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

@app.before_request
def require_login():
    """Redirect to login if not authenticated or session expired."""
    # Allow access to login page and static files without auth
    allowed_endpoints = ['auth.login', 'auth.logout', 'static']
    if request.endpoint in allowed_endpoints:
        return
    
    # Check if database is connected (user is logged in)
    db = app.config.get('db')
    if not db:
        return redirect(url_for('auth.login'))
    
    # Get session timeout from database (default 30 minutes)
    try:
        timeout_minutes = int(db.get_setting('session_timeout', '30'))
        if timeout_minutes == 0:  # "Never" option
            session['last_activity'] = time.time()
            return
        session_timeout = timeout_minutes * 60
    except (ValueError, TypeError):
        session_timeout = 30 * 60
    
    # Check session timeout
    last_activity = session.get('last_activity')
    now = time.time()
    
    if last_activity:
        elapsed = now - last_activity
        if elapsed > session_timeout:
            # Session expired - clear everything and redirect to login
            session.clear()
            app.config['db'] = None
            return redirect(url_for('auth.login', timeout=1))
    
    # Update last activity timestamp
    session['last_activity'] = now
    
    # Check for restore completion message (show once)
    if 'restore_shown' not in session:
        restore_info = app.config.pop('RESTORE_COMPLETED', None)
        if restore_info:
            session['restore_shown'] = True
            session['restore_message'] = f"Restored from backup: {restore_info['original_date'][:10]}"


# ============================================================================
# AUTO-BACKUP CHECK (called after login)
# ============================================================================

@app.route('/api/check-auto-backup', methods=['POST'])
def check_auto_backup():
    """
    Check if auto-backup should run after login.
    Called by frontend after successful authentication.
    """
    from utils import backup
    
    db = app.config.get('db')
    if not db:
        return jsonify({'backup_performed': False, 'error': 'Not logged in'})
    
    frequency = db.get_setting('backup_frequency', 'daily')
    
    needed = backup.check_backup_needed(frequency)
    
    if needed:
        location = db.get_setting('backup_location', '')
        if not location:
            location = None  # Use default BACKUPS_DIR
        try:
            # Use create_backup() which auto-decides full vs incremental
            result = backup.create_backup(location)
            
            return jsonify({
                'backup_performed': True,
                'result': result
            })
        except Exception as e:
            return jsonify({
                'backup_performed': False,
                'error': str(e)
            })
    
    return jsonify({'backup_performed': False, 'reason': 'not_needed'})


# ============================================================================
# RESTORE MESSAGE API
# ============================================================================

@app.route('/api/restore-message')
def get_restore_message():
    """Get and clear any pending restore completion message."""
    message = session.pop('restore_message', None)
    return jsonify({'message': message})


# ============================================================================
# PLACEHOLDER ROUTES
# ============================================================================

@app.route('/scheduler')
def scheduler():
    """Scheduler page - placeholder for future calendar/appointment features"""
    return render_template('scheduler.html')

@app.route('/billing')
def billing():
    """Billing page - placeholder for future invoicing/statement features"""
    return render_template('billing.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
