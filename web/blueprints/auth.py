"""
EdgeCase Authentication Blueprint
Handles login/logout and database encryption
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, make_response, Response
from pathlib import Path
from functools import wraps
import time
import json

auth_bp = Blueprint('auth', __name__)

# ============================================================================
# RATE LIMITING
# Simple in-memory rate limiting for login attempts.
# Tracks failed attempts by IP address with automatic lockout.
# ============================================================================

_login_attempts = {}  # {ip: {'count': int, 'first_attempt': timestamp, 'locked_until': timestamp}}

# Configuration
MAX_ATTEMPTS = 5          # Max failed attempts before lockout
LOCKOUT_DURATION = 300    # Lockout duration in seconds (5 minutes)
ATTEMPT_WINDOW = 600      # Window to count attempts (10 minutes)


def _get_client_ip():
    """Get client IP address, accounting for proxies."""
    # Check X-Forwarded-For header (if behind proxy/load balancer)
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    # Check X-Real-IP header (nginx)
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    # Fall back to direct IP
    return request.remote_addr or 'unknown'


def _check_rate_limit():
    """
    Check if the client IP is rate limited.
    
    Returns:
        (allowed: bool, message: str, retry_after: int or None)
    """
    ip = _get_client_ip()
    now = time.time()
    
    if ip not in _login_attempts:
        return True, None, None
    
    record = _login_attempts[ip]
    
    # Check if currently locked out
    if record.get('locked_until') and now < record['locked_until']:
        retry_after = int(record['locked_until'] - now)
        minutes = retry_after // 60
        seconds = retry_after % 60
        if minutes > 0:
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            time_str = f"{seconds} second{'s' if seconds != 1 else ''}"
        return False, f"Too many failed attempts. Please try again in {time_str}.", retry_after
    
    # Clear old attempts outside the window
    if now - record.get('first_attempt', 0) > ATTEMPT_WINDOW:
        del _login_attempts[ip]
        return True, None, None
    
    return True, None, None


def _record_failed_attempt():
    """Record a failed login attempt for rate limiting."""
    ip = _get_client_ip()
    now = time.time()
    
    if ip not in _login_attempts:
        _login_attempts[ip] = {
            'count': 1,
            'first_attempt': now,
            'locked_until': None
        }
    else:
        record = _login_attempts[ip]
        
        # Reset if outside window
        if now - record['first_attempt'] > ATTEMPT_WINDOW:
            _login_attempts[ip] = {
                'count': 1,
                'first_attempt': now,
                'locked_until': None
            }
        else:
            record['count'] += 1
            
            # Trigger lockout if max attempts exceeded
            if record['count'] >= MAX_ATTEMPTS:
                record['locked_until'] = now + LOCKOUT_DURATION
                print(f"[Security] IP {ip} locked out after {record['count']} failed login attempts")


def _clear_failed_attempts():
    """Clear failed attempts after successful login."""
    ip = _get_client_ip()
    if ip in _login_attempts:
        del _login_attempts[ip]

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_app.config.get('db'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def is_first_run():
    """Check if this is first run (no database exists)."""
    from core.config import DATA_DIR
    db_path = Path(DATA_DIR) / "edgecase.db"
    return not db_path.exists()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - unlock the encrypted database."""
    from core.database import Database
    
    first_run = is_first_run()
    
    # Check rate limiting before processing POST
    if request.method == 'POST':
        allowed, error_msg, retry_after = _check_rate_limit()
        if not allowed:
            return render_template('login.html', 
                                 first_run=first_run, 
                                 error=error_msg)
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        if first_run:
            # Creating new database - verify password confirmation
            confirm = request.form.get('confirm_password', '')
            if password != confirm:
                return render_template('login.html', 
                                     first_run=True, 
                                     error="Passwords don't match")
            if len(password) < 8:
                return render_template('login.html', 
                                     first_run=True, 
                                     error="Password must be at least 8 characters")
        
        # Try to open/create database with this password
        from core.config import DATA_DIR
        db_path = Path(DATA_DIR) / "edgecase.db"
        
        try:
            db = Database(str(db_path), password=password)
            # Test that password works by running a query
            conn = db.connect()
            conn.execute("SELECT count(*) FROM client_types")
            
            # Success! Store db in app config
            current_app.config['db'] = db
            
            # Clear failed login attempts on success
            _clear_failed_attempts()
            
            # Clear any old session data first, then set new values
            session.clear()
            session.permanent = True  # Use PERMANENT_SESSION_LIFETIME
            session['authenticated'] = True
            session['login_time'] = int(time.time())
            session['last_activity'] = time.time()  # Set immediately to prevent timeout race
            session.modified = True
            
            # Initialize all blueprints with the database
            from web.app import init_all_blueprints
            init_all_blueprints(db)
            
            # Use make_response to ensure cookie is properly set before redirect
            response = make_response(redirect(url_for('clients.index')))
            return response
            
        except Exception as e:
            # Record failed attempt for rate limiting
            _record_failed_attempt()
            
            error_msg = str(e)
            if 'file is not a database' in error_msg or 'encrypted' in error_msg.lower():
                error = "Incorrect password"
            else:
                error = f"Database error: {error_msg}"
            return render_template('login.html', first_run=first_run, error=error)
    
    return render_template('login.html', first_run=first_run)


def _run_auto_backup_check(db):
    """
    Check if automatic backup should run on logout.
    Runs silently - errors are logged but don't affect logout.
    """
    print("[Backup] Running logout backup check...")
    try:
        from utils import backup
        import subprocess
        
        frequency = db.get_setting('backup_frequency', 'daily')
        # Migrate legacy 'startup' to 'session'
        if frequency == 'startup':
            frequency = 'session'
            db.set_setting('backup_frequency', 'session')
        print(f"[Backup] Frequency setting: {frequency}")
        
        if backup.check_backup_needed(frequency):
            print("[Backup] Backup needed, creating...")
            location = db.get_setting('backup_location', '')
            if not location:
                location = None  # Use default BACKUPS_DIR
            result = backup.create_backup(location)
            if result:
                print(f"[Backup] Automatic backup completed: {result['filename']}")
                
                # Run post-backup command if configured
                post_cmd = db.get_setting('post_backup_command', '')
                if post_cmd:
                    try:
                        subprocess.run(post_cmd, shell=True, timeout=300)
                        print(f"[Backup] Post-backup command completed")
                    except Exception as cmd_error:
                        print(f"[Backup] Post-backup command error: {cmd_error}")
            else:
                print("[Backup] No changes to backup")
            
            # Record that we checked today (whether backup created or not)
            backup.record_backup_check()
        else:
            print("[Backup] Backup not needed (frequency check)")
    except Exception as e:
        # Log and store for user notification
        error_msg = str(e)
        print(f"[Backup] Auto-backup failed: {error_msg}")
        session['backup_warning'] = error_msg


@auth_bp.route('/logout')
def logout():
    """Logout - run backup check and close database connection."""
    db = current_app.config.get('db')
    if db:
        # Run automatic backup check before closing
        _run_auto_backup_check(db)
        db.checkpoint()  # Ensure WAL is flushed
        db.close()
    current_app.config['db'] = None
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change the master password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            return render_template('change_password.html', error="New passwords don't match")
        
        if len(new_password) < 8:
            return render_template('change_password.html', error="Password must be at least 8 characters")
        
        db = current_app.config.get('db')
        if not db:
            return redirect(url_for('auth.login'))
        
        # Verify current password first
        try:
            conn = db.connect()
            conn.execute("SELECT 1")  # Verify we can read with current password
        except Exception as e:
            return render_template('change_password.html', error="Current password is incorrect")
        
        # Store passwords in session for SSE route to use
        session['password_change_current'] = current_password
        session['password_change_new'] = new_password
        session.modified = True
        
        # Render template with trigger to start SSE
        return render_template('change_password.html', start_change=True)
    
    return render_template('change_password.html')


@auth_bp.route('/change-password-progress')
@login_required
def change_password_progress():
    """SSE endpoint for password change progress."""
    # Get passwords from session BEFORE entering generator (request context issue)
    current_password = session.get('password_change_current')
    new_password = session.get('password_change_new')
    db = current_app.config.get('db')
    
    def generate():
        if not current_password or not new_password:
            yield f"data: {json.dumps({'error': 'Missing password data'})}\n\n"
            return
        
        if not db:
            yield f"data: {json.dumps({'error': 'Database not available'})}\n\n"
            return
        
        try:
            # Step 1: Count total files
            yield f"data: {json.dumps({'status': 'counting', 'message': 'Counting files...'})}\n\n"
            
            total_files = _count_encrypted_files(db)
            
            # Step 2: Re-encrypt all files with progress
            yield f"data: {json.dumps({'status': 'encrypting', 'total': total_files, 'current': 0, 'message': 'Re-encrypting files...'})}\n\n"
            
            for progress in _reencrypt_all_files_with_progress(db, current_password, new_password, total_files):
                yield f"data: {json.dumps(progress)}\n\n"
            
            # Step 3: Rekey the database
            yield f"data: {json.dumps({'status': 'database', 'message': 'Updating database encryption...'})}\n\n"
            
            conn = db.connect()
            conn.execute(f"PRAGMA rekey = '{new_password}'")
            
            # Step 4: Update the Database object's password
            db.password = new_password
            
            # Step 5: Verify new password works
            test_conn = db.connect()
            test_conn.execute("SELECT 1")
            
            # Success!
            yield f"data: {json.dumps({'status': 'complete', 'message': 'Password changed successfully!'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


def _count_encrypted_files(db) -> int:
    """Count total encrypted files to process."""
    from pathlib import Path
    from core.config import ASSETS_DIR
    import os
    
    count = 0
    
    # Count attachments
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM attachments")
    for row in cursor.fetchall():
        if row[0] and os.path.exists(row[0]):
            count += 1
    
    # Count logo
    logo_filename = db.get_setting('logo_filename', '')
    if logo_filename:
        logo_path = ASSETS_DIR / logo_filename
        if logo_path.exists():
            count += 1
    
    # Count signature
    sig_filename = db.get_setting('signature_filename', '')
    if sig_filename:
        sig_path = ASSETS_DIR / sig_filename
        if sig_path.exists():
            count += 1
    
    return count


def _reencrypt_all_files_with_progress(db, old_password: str, new_password: str, total_files: int):
    """Re-encrypt all attachments and assets with new password, yielding progress."""
    from core.encryption import decrypt_file_to_bytes, encrypt_file
    from core.config import ASSETS_DIR
    from pathlib import Path
    import os
    
    current_file = 0
    
    # Re-encrypt attachments from database
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, filepath FROM attachments")
    
    for row in cursor.fetchall():
        filepath = row[1]
        if filepath and os.path.exists(filepath):
            try:
                current_file += 1
                filename = os.path.basename(filepath)
                
                # Decrypt with old password
                data = decrypt_file_to_bytes(filepath, old_password)
                # Write decrypted, then encrypt with new password
                with open(filepath, 'wb') as f:
                    f.write(data)
                encrypt_file(filepath, new_password)
                
                # Yield progress
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': filename,
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt {filepath}: {e}")
    
    # Re-encrypt logo if exists
    logo_filename = db.get_setting('logo_filename', '')
    if logo_filename:
        logo_path = ASSETS_DIR / logo_filename
        if logo_path.exists():
            try:
                current_file += 1
                data = decrypt_file_to_bytes(str(logo_path), old_password)
                with open(logo_path, 'wb') as f:
                    f.write(data)
                encrypt_file(str(logo_path), new_password)
                
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'logo',
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt logo: {e}")
    
    # Re-encrypt signature if exists
    sig_filename = db.get_setting('signature_filename', '')
    if sig_filename:
        sig_path = ASSETS_DIR / sig_filename
        if sig_path.exists():
            try:
                current_file += 1
                data = decrypt_file_to_bytes(str(sig_path), old_password)
                with open(sig_path, 'wb') as f:
                    f.write(data)
                encrypt_file(str(sig_path), new_password)
                
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'signature',
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt signature: {e}")
