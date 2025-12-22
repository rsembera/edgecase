"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import time
import os
from werkzeug.utils import secure_filename

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
app.config['SECRET_KEY'] = os.environ.get('EDGECASE_SECRET_KEY', os.urandom(24))

# Session cookie configuration (explicit settings for cross-browser compatibility)
app.config['SESSION_COOKIE_NAME'] = 'edgecase_session'  # Unique name to avoid conflicts
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set True if using HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours max cookie lifetime

# File upload limit (50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

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

@app.template_filter('close_tags')
def close_tags(html_string):
    """Ensure all HTML tags are properly closed to prevent DOM poisoning."""
    if not html_string:
        return html_string
    
    # Count unclosed tags
    open_strong = html_string.count('<strong>') - html_string.count('</strong>')
    open_del = html_string.count('<del>') - html_string.count('</del>')
    
    # Close any unclosed tags
    result = html_string
    for _ in range(max(0, open_strong)):
        result += '</strong>'
    for _ in range(max(0, open_del)):
        result += '</del>'
    
    return result

@app.errorhandler(413)
def file_too_large(e):
    """Handle file upload exceeding MAX_CONTENT_LENGTH."""
    # Check if this is an AJAX request
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': False, 'error': 'File too large. Maximum size is 50MB.'}), 413
    # For regular form submissions, flash and redirect back
    from flask import flash
    flash('File too large. Maximum size is 50MB.', 'error')
    return redirect(request.referrer or url_for('clients.index'))

@app.before_request
def require_login():
    """Redirect to login if not authenticated or session expired."""
    # Allow access to login page, static files, and session status endpoints without auth
    allowed_endpoints = ['auth.login', 'auth.logout', 'static', 'session_status', 'keepalive', 'heartbeat']
    if request.endpoint in allowed_endpoints:
        return
    
    # Helper to check if this is an API/AJAX request expecting JSON
    def is_api_request():
        # Check if request accepts JSON
        if request.accept_mimetypes.best == 'application/json':
            return True
        # Check if request has JSON content-type
        if request.content_type and 'application/json' in request.content_type:
            return True
        # Check if it's an API route
        if request.path.startswith('/api/'):
            return True
        return False
    
    # Check if database is connected (user is logged in)
    db = app.config.get('db')
    if not db:
        if is_api_request():
            return jsonify({'success': False, 'error': 'session_expired', 'message': 'Please log in again'}), 401
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
            # Session expired - clear everything
            session.clear()
            app.config['db'] = None
            if is_api_request():
                return jsonify({'success': False, 'error': 'session_expired', 'message': 'Session timed out. Please log in again'}), 401
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
# SESSION TIMEOUT WARNING API
# ============================================================================

@app.route('/api/session-status')
def session_status():
    """Return session timeout status for frontend warning system."""
    db = app.config.get('db')
    if not db:
        return jsonify({'logged_in': False})
    
    try:
        timeout_minutes = int(db.get_setting('session_timeout', '30'))
    except (ValueError, TypeError):
        timeout_minutes = 30
    
    # If timeout is 0 ("Never"), no warning needed
    if timeout_minutes == 0:
        return jsonify({
            'logged_in': True,
            'timeout_minutes': 0,
            'seconds_remaining': None,
            'warning_needed': False
        })
    
    last_activity = session.get('last_activity', time.time())
    elapsed = time.time() - last_activity
    timeout_seconds = timeout_minutes * 60
    seconds_remaining = max(0, timeout_seconds - elapsed)
    
    # Warning thresholds (proportional to timeout):
    # 15 min -> warn at 2 min (120s)
    # 30 min -> warn at 3 min (180s)
    # 60+ min -> warn at 5 min (300s)
    if timeout_minutes <= 15:
        warning_threshold = 120
    elif timeout_minutes <= 30:
        warning_threshold = 180
    else:
        warning_threshold = 300
    
    return jsonify({
        'logged_in': True,
        'timeout_minutes': timeout_minutes,
        'seconds_remaining': int(seconds_remaining),
        'warning_threshold': warning_threshold,
        'warning_needed': seconds_remaining <= warning_threshold and seconds_remaining > 0
    })


@app.route('/api/keepalive', methods=['POST'])
def keepalive():
    """Extend session when user clicks 'Stay Logged In'."""
    db = app.config.get('db')
    if not db:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    # Update last activity timestamp
    session['last_activity'] = time.time()
    return jsonify({'success': True})


@app.route('/api/heartbeat')
def heartbeat():
    """Simple endpoint to check if server is running."""
    return jsonify({'ok': True})


# ============================================================================
# RESTORE MESSAGE API
# ============================================================================

@app.route('/api/restore-message')
def get_restore_message():
    """Get and clear any pending restore completion message."""
    message = session.pop('restore_message', None)
    return jsonify({'message': message})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
