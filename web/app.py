"""
EdgeCase Flask Application
Main web interface for EdgeCase Equalizer
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from pathlib import Path
import time
import os
from werkzeug.utils import secure_filename


def _get_secret_key() -> bytes:
    """Get or create persistent SECRET_KEY.
    
    Key is stored in data/.secret_key file. Generated once on first run,
    then reused for all subsequent app starts. This ensures:
    - Sessions persist across app restarts
    - Each installation has a unique key
    """
    from core.config import DATA_DIR
    secret_file = DATA_DIR / '.secret_key'
    
    # Check environment variable first (for advanced users)
    env_key = os.environ.get('EDGECASE_SECRET_KEY')
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key
    
    # Use persisted key if it exists
    if secret_file.exists():
        return secret_file.read_bytes()
    
    # Generate new key and persist it
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(24)
    secret_file.write_bytes(key)
    
    return key

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

from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config['SECRET_KEY'] = _get_secret_key()

# CSRF Protection - protects form submissions
# JSON API requests are exempt (protected by same-origin policy)
csrf = CSRFProtect(app)
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # We'll check manually for forms only

@app.before_request
def csrf_protect_forms():
    """Apply CSRF protection to form submissions, not JSON/fetch APIs."""
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        content_type = request.content_type or ''
        # Skip CSRF for JSON API requests (protected by same-origin policy)
        if 'application/json' in content_type:
            return
        # Skip CSRF for multipart/form-data from fetch (also same-origin protected)
        # These are file uploads via JavaScript fetch(), not traditional form submissions
        if 'multipart/form-data' in content_type:
            return
        # For traditional HTML form submissions, validate CSRF
        csrf.protect()

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
from core.config import DATA_DIR
DATA_DIR.mkdir(exist_ok=True)

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
    # Update desktop heartbeat on any request
    heartbeat_func = app.config.get('HEARTBEAT_CALLBACK')
    if heartbeat_func:
        heartbeat_func()
    
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
            # Session expired - run backup before clearing
            print("[Timeout] Session expired, running backup check...")
            try:
                from utils import backup
                import subprocess
                
                # Checkpoint WAL first so backup captures all changes
                db.checkpoint()
                
                frequency = db.get_setting('backup_frequency', 'daily')
                if backup.check_backup_needed(frequency):
                    print("[Timeout] Backup needed, creating...")
                    location = db.get_setting('backup_location', '')
                    if not location:
                        location = None
                    result = backup.create_backup(location)
                    if result:
                        print(f"[Timeout] Automatic backup completed: {result['filename']}")
                        # Run post-backup command if configured
                        post_cmd = db.get_setting('post_backup_command', '')
                        if post_cmd:
                            try:
                                import shlex
                                subprocess.run(shlex.split(post_cmd), timeout=300)
                                print("[Timeout] Post-backup command completed")
                            except Exception as cmd_error:
                                print(f"[Timeout] Post-backup command error: {cmd_error}")
                    else:
                        print("[Timeout] No changes to backup")
                    backup.record_backup_check()
                else:
                    print("[Timeout] Backup not needed (frequency check)")
            except Exception as e:
                print(f"[Timeout] Backup error: {e}")
            
            # Now clear everything
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


# Note: This file should not be run directly. Use main.py or `python -m edgecase`
# The CLI uses Waitress for production serving with proper security settings.
