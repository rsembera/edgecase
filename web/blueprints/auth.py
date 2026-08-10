"""
EdgeCase Authentication Blueprint
Handles login/logout and database encryption
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash, make_response, Response
from pathlib import Path
from functools import wraps
import secrets
import time
import json
import os
import tempfile

auth_bp = Blueprint('auth', __name__)

# Minimum master-password length, enforced at every point a password can be
# SET: first-run database creation, change password, and the recovery-key
# reset. Deliberately NOT checked on login — verify_password only cares
# whether the password opens the install, so raising this never locks anyone
# out of an existing shorter password. It applies to the next change.
#
# Templates read these via the min_password_length context processor rather
# than hardcoding the number, so the rule and the message it produces cannot
# drift apart across the three screens.
MIN_PASSWORD_LENGTH = 12
PASSWORD_LENGTH_ERROR = (
    f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


# ============================================================================
# PASSWORD-CHANGE HANDOFF (server-side, never the session cookie)
# ============================================================================
# The change-password POST verifies the current password, then the SSE
# progress route performs the re-encryption. The passwords are handed
# between the two requests via this in-process dict keyed by a random
# single-use token — NOT via the Flask session, which is signed but not
# encrypted and would serialize the master password into the cookie
# (CODE_REVIEW.md H2). Single-user app: at most one entry at a time.

_password_change_handoff = {}
_HANDOFF_TTL_SECONDS = 300  # token expires after 5 minutes


def _store_password_handoff(current_password, new_password):
    """Store passwords server-side; returns a single-use token."""
    _password_change_handoff.clear()  # never keep stale credentials
    token = secrets.token_urlsafe(32)
    _password_change_handoff[token] = {
        'current': current_password,
        'new': new_password,
        'created': time.time(),
    }
    return token


def _pop_password_handoff(token):
    """Retrieve and delete the handoff entry. Returns (current, new) or None."""
    entry = _password_change_handoff.pop(token, None) if token else None
    if not entry:
        return None
    if time.time() - entry['created'] > _HANDOFF_TTL_SECONDS:
        return None
    return entry['current'], entry['new']


_migration_handoff = {}


def _store_migration_handoff(password):
    """Store the verified password server-side for the migration SSE route;
    returns a single-use token. Never the session cookie (CODE_REVIEW.md H2)."""
    _migration_handoff.clear()
    token = secrets.token_urlsafe(32)
    _migration_handoff[token] = {'password': password, 'created': time.time()}
    return token


def _pop_migration_handoff(token):
    """Retrieve and delete the migration handoff. Returns the password or None."""
    entry = _migration_handoff.pop(token, None) if token else None
    if not entry:
        return None
    if time.time() - entry['created'] > _HANDOFF_TTL_SECONDS:
        return None
    return entry['password']


# A freshly issued recovery key, held between the migration SSE route and the
# screen that displays it. Same reasoning as the handoffs above — the key is a
# full-access credential and must never be serialized into the signed-but-not-
# encrypted session cookie.
#
# Unlike those, this one is NOT single-use on read: the user has to be able to
# refresh, or mistype the confirmation, without the key vanishing off the
# screen mid-transcription. It is dropped explicitly on acknowledgement, and
# expires on the same TTL regardless. If it does expire, nothing is lost that
# regenerating from Settings cannot replace — which is the whole reason
# .rk_pending can be a nag rather than a hard block.

_recovery_key_handoff = {}
_RECOVERY_TTL_SECONDS = 1800  # 30 minutes; writing a key down is not a 5-minute job


def _store_recovery_handoff(recovery_key):
    _recovery_key_handoff.clear()
    token = secrets.token_urlsafe(32)
    _recovery_key_handoff[token] = {'key': recovery_key, 'created': time.time()}
    return token


def _peek_recovery_handoff(token):
    """Read WITHOUT consuming, so a refresh or a mistyped confirmation does not
    destroy the only copy of the key."""
    entry = _recovery_key_handoff.get(token) if token else None
    if not entry:
        return None
    if time.time() - entry['created'] > _RECOVERY_TTL_SECONDS:
        _recovery_key_handoff.pop(token, None)
        return None
    return entry['key']


def _drop_recovery_handoff(token):
    _recovery_key_handoff.pop(token, None)


# A recovery key that has been verified, held between /recover and
# /recover/reset. Short TTL: the user is mid-flow with the key in front of
# them, so there is no reason for this to outlive a single sitting.

_recovery_reset_handoff = {}


def _store_recovery_reset_handoff(recovery_key):
    _recovery_reset_handoff.clear()
    token = secrets.token_urlsafe(32)
    _recovery_reset_handoff[token] = {'key': recovery_key, 'created': time.time()}
    return token


def _peek_recovery_reset_handoff(token):
    entry = _recovery_reset_handoff.get(token) if token else None
    if not entry:
        return None
    if time.time() - entry['created'] > _HANDOFF_TTL_SECONDS:
        _recovery_reset_handoff.pop(token, None)
        return None
    return entry['key']


def _drop_recovery_reset_handoff(token):
    _recovery_reset_handoff.pop(token, None)


# ============================================================================
# LOGIN RATE LIMITING
# ============================================================================

# Track failed login attempts: {ip_address: {'count': N, 'lockout_until': timestamp}}
_login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes


def _get_client_ip():
    """Get the client IP address for login rate-limiting.

    Uses request.remote_addr directly. This deployment has no reverse
    proxy (waitress/werkzeug listen directly), so X-Forwarded-For is
    client-supplied and must not be trusted: honoring it would let an
    attacker rotate the header to bypass the 5-attempt lockout
    (CODE_REVIEW M8).
    """
    return request.remote_addr or '127.0.0.1'


def _check_rate_limit():
    """Check if client IP is rate-limited. Returns (is_blocked, seconds_remaining)."""
    ip = _get_client_ip()
    now = time.time()
    
    if ip in _login_attempts:
        attempt_info = _login_attempts[ip]
        
        # Check if currently locked out
        if attempt_info.get('lockout_until', 0) > now:
            remaining = int(attempt_info['lockout_until'] - now)
            return True, remaining
        
        # Clear old lockout if expired
        if attempt_info.get('lockout_until', 0) <= now:
            attempt_info['lockout_until'] = 0
    
    return False, 0


def _record_failed_attempt():
    """Record a failed login attempt and potentially trigger lockout."""
    ip = _get_client_ip()
    now = time.time()
    
    if ip not in _login_attempts:
        _login_attempts[ip] = {'count': 0, 'lockout_until': 0, 'first_attempt': now}
    
    attempt_info = _login_attempts[ip]
    
    # Reset count if first attempt was more than lockout period ago
    if now - attempt_info.get('first_attempt', now) > LOCKOUT_SECONDS:
        attempt_info['count'] = 0
        attempt_info['first_attempt'] = now
    
    attempt_info['count'] += 1
    
    # Trigger lockout if max attempts exceeded
    if attempt_info['count'] >= MAX_ATTEMPTS:
        attempt_info['lockout_until'] = now + LOCKOUT_SECONDS
        return True  # Lockout triggered
    
    return False


def _clear_failed_attempts():
    """Clear failed attempts for current IP after successful login."""
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

    # Heal any interrupted v1->v2 migration before the database is opened.
    # No password needed; a no-op when nothing is pending.
    try:
        from core import migrate_crypto
        outcome = migrate_crypto.recover_if_interrupted()
        if outcome != 'none':
            print(f"[Migration] startup recovery: {outcome}")
    except Exception as e:
        print(f"[Migration] recovery check error: {e}")
    
    first_run = is_first_run()
    
    # Check rate limiting before processing POST
    is_blocked, seconds_remaining = _check_rate_limit()
    if is_blocked:
        return render_template('login.html', 
                             first_run=first_run, 
                             lockout_seconds=seconds_remaining)
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        if first_run:
            # Creating new database - verify password confirmation
            confirm = request.form.get('confirm_password', '')
            if password != confirm:
                return render_template('login.html', 
                                     first_run=True, 
                                     error="Passwords don't match")
            if len(password) < MIN_PASSWORD_LENGTH:
                return render_template('login.html', 
                                     first_run=True, 
                                     error=PASSWORD_LENGTH_ERROR)
        
        # Try to open/create database with this password
        from core.config import DATA_DIR
        db_path = Path(DATA_DIR) / "edgecase.db"
        
        try:
            db = Database(str(db_path), password=password)
            # Test that password works by running a query
            conn = db.connect()
            conn.execute("SELECT count(*) FROM client_types")

            # Existing v1 or v2 install: upgrade encryption to the v3
            # envelope before completing login. Single pass from either
            # version. The runner needs no DB handle open, so close ours;
            # /migrate/stream re-opens the now-v3 DB and finishes the login.
            if not first_run:
                from core import migrate_crypto
                if migrate_crypto.needs_v3_migration():
                    db.close()
                    _clear_failed_attempts()
                    migrate_token = _store_migration_handoff(password)
                    session.clear()
                    session.permanent = True
                    session['authenticated'] = True
                    session['login_time'] = int(time.time())
                    session['last_activity'] = time.time()
                    session.modified = True
                    return render_template(
                        'upgrading.html',
                        migrate_token=migrate_token,
                        from_version=migrate_crypto.install_crypto_version())

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
            # Record failed attempt (may trigger lockout)
            _record_failed_attempt()
            
            error_msg = str(e)
            if 'file is not a database' in error_msg or 'encrypted' in error_msg.lower():
                error = "Incorrect password"
            else:
                error = f"Database error: {error_msg}"
            return render_template('login.html', first_run=first_run, error=error)
    
    return render_template('login.html', first_run=first_run)


@auth_bp.route('/migrate/stream')
def migrate_stream():
    """SSE endpoint that runs the v1->v2 encryption migration and then completes
    the login. Reachable without config['db'] (it is in require_login's allowed
    endpoints) and gated instead by the single-use token from the verified
    login POST."""
    from pathlib import Path
    from core.config import DATA_DIR

    password = _pop_migration_handoff(request.args.get('token'))
    db_path = str(Path(DATA_DIR) / "edgecase.db")
    app_obj = current_app._get_current_object()
    redirect_url = url_for('clients.index')
    # Resolved HERE, not inside the generator. Flask pops the application
    # context before the generator is consumed, so url_for() inside it raises
    # "Working outside of application context" — after the migration has
    # already committed.
    recovery_key_url = url_for('auth.recovery_key')

    def generate():
        if not password:
            yield "data: " + json.dumps({'status': 'error', 'message': 'Your upgrade session expired. Please log in again.'}) + "\n\n"
            return
        try:
            yield "data: " + json.dumps({'status': 'working', 'message': 'Creating a safety backup and upgrading your encryption. This one-time step can take a little while for a large practice \u2014 please do not close the app.'}) + "\n\n"

            from core import migrate_crypto
            from core.database import Database
            from web.app import init_all_blueprints

            result = migrate_crypto.migrate_to_v3(password)

            # Committed (.keyinfo written, marker cleared). Open the now-v3
            # database and complete the login exactly as auth.login does.
            db = Database(db_path, password=password)
            db.connect().execute("SELECT count(*) FROM client_types")
            app_obj.config['db'] = db
            init_all_blueprints(db)

            # The recovery key exists in plaintext exactly once, as this return
            # value — it is never stored. Route to the screen that shows it
            # instead of straight to the client list; .rk_pending is already
            # set on disk, so even a crash here leaves evidence the key was
            # never recorded.
            rk_token = _store_recovery_handoff(result.get('recovery_key'))
            destination = f"{recovery_key_url}?token={rk_token}"

            yield "data: " + json.dumps({'status': 'complete', 'message': 'Encryption upgraded.', 'files': result.get('files_migrated', 0), 'redirect': destination}) + "\n\n"
        except Exception as e:
            # Do NOT assume the data is untouched. Everything after the commit
            # point — opening the new DB, wiring blueprints, building the
            # redirect — can fail with the migration already committed, and
            # telling the user nothing happened would leave them with exactly
            # the wrong mental model. Ask the disk instead of guessing.
            try:
                from core import migrate_crypto
                committed = migrate_crypto.install_crypto_version() == 3
            except Exception:
                committed = False

            if committed:
                message = ('Your encryption was upgraded, but EdgeCase could not '
                           'finish opening it: ' + str(e) + '. Your records are '
                           'safe and your password is unchanged \u2014 please log in '
                           'again. You will be prompted to set up a recovery key.')
            else:
                message = ('The upgrade did not complete: ' + str(e) + '. Your data '
                           'is unchanged and still on the previous encryption \u2014 '
                           'please try logging in again.')
            yield "data: " + json.dumps({'status': 'error', 'message': message}) + "\n\n"

    return Response(generate(), mimetype='text/event-stream')


@auth_bp.route('/recovery-key', methods=['GET', 'POST'])
@login_required
def recovery_key():
    """Show a freshly issued recovery key and take the user's acknowledgement.

    Acknowledgement is a checkbox, not a typed copy of the key. Typing it back
    looks stronger but is not: the page also offers Copy to clipboard, so the
    check could be satisfied by paste without the key ever reaching anything
    durable. It only ever verified transcription for the subset of users who
    copied by hand, while implying a guarantee it could not make.

    What actually protects the user is that the key cannot be shown again and
    .rk_pending keeps nagging until acknowledged — plus regeneration always
    being available, since they are logged in with a working password.

    The key is held server-side and read WITHOUT consuming, so a refresh does
    not destroy the only copy.
    """
    from core import migrate_crypto

    token = request.args.get('token') or request.form.get('token', '')
    key = _peek_recovery_handoff(token)

    if not key:
        # Expired, already acknowledged, or a stale link. Nothing is lost that
        # regenerating cannot replace, so say so plainly rather than erroring.
        return render_template('recovery_key.html', expired=True,
                               pending=migrate_crypto.recovery_key_pending())

    if request.method == 'POST':
        # `required` on the input is a browser hint only; anything can POST.
        if not request.form.get('confirm_saved'):
            return render_template(
                'recovery_key.html', recovery_key=key, token=token,
                error="Please confirm you've saved your recovery key.")

        migrate_crypto.clear_recovery_key_pending()
        _drop_recovery_handoff(token)
        return redirect(url_for('clients.index'))

    return render_template('recovery_key.html', recovery_key=key, token=token)


@auth_bp.route('/recovery-key/regenerate', methods=['GET', 'POST'])
@login_required
def regenerate_recovery_key():
    """Issue a fresh recovery key, retiring the previous one.

    Requires the master password — the operation grants a new full-access
    credential, so an unattended session must not be able to mint one. Routes
    into the same display-and-confirm screen as the migration path.
    """
    from core import migrate_crypto

    if migrate_crypto.install_crypto_version() != 3:
        return render_template('recovery_key.html', expired=True, pending=False)

    if request.method == 'POST':
        password = request.form.get('password', '')
        db = current_app.config.get('db')
        if not db or not db.verify_password(password):
            return render_template('recovery_key_regenerate.html',
                                   error="That password is incorrect.")
        try:
            new_key = migrate_crypto.regenerate_recovery_key(password)
        except Exception as e:
            return render_template('recovery_key_regenerate.html',
                                   error=f"Could not issue a new key: {e}")
        token = _store_recovery_handoff(new_key)
        return redirect(url_for('auth.recovery_key', token=token))

    return render_template('recovery_key_regenerate.html')


@auth_bp.route('/recover', methods=['GET', 'POST'])
def recover():
    """Open the install with a recovery key, then set a new master password.

    Unauthenticated, so it carries the same rate limiting as login. 160 bits of
    uniform entropy makes guessing hopeless on its own, but the limiter also
    covers the malformed-input path and keeps this route from being a way to
    sidestep the lockout on /login.

    Success hands a server-side token to /recover/reset — never the key itself
    in a cookie, and never the master in the session.
    """
    from core import migrate_crypto

    if not migrate_crypto.has_recovery_key():
        return render_template('recover.html', unavailable=True)

    is_blocked, seconds_remaining = _check_rate_limit()
    if is_blocked:
        return render_template('recover.html', lockout_seconds=seconds_remaining)

    if request.method == 'POST':
        key = request.form.get('recovery_key', '')
        try:
            migrate_crypto.v3.unwrap_with_recovery_key(
                migrate_crypto.v3.read_keyinfo(), key)
        except migrate_crypto.v3.RecoveryKeyError as e:
            # Malformed — a typo, not a wrong key. Say which, and don't spend
            # an attempt on it.
            return render_template('recover.html', error=str(e))
        except Exception:
            _record_failed_attempt()
            return render_template(
                'recover.html',
                error="That recovery key does not open this practice file.")

        _clear_failed_attempts()
        token = _store_recovery_reset_handoff(key)
        return redirect(url_for('auth.recover_reset', token=token))

    return render_template('recover.html')


@auth_bp.route('/recover/reset', methods=['GET', 'POST'])
def recover_reset():
    """Set a new master password after a verified recovery key."""
    from core import migrate_crypto

    token = request.args.get('token') or request.form.get('token', '')
    key = _peek_recovery_reset_handoff(token)
    if not key:
        return redirect(url_for('auth.recover'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if new_password != confirm:
            return render_template('recover_reset.html', token=token,
                                   error="Passwords don't match")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return render_template('recover_reset.html', token=token,
                                   error=PASSWORD_LENGTH_ERROR)

        try:
            migrate_crypto.reset_password_with_recovery_key(key, new_password)
        except Exception as e:
            return render_template('recover_reset.html', token=token,
                                   error=f"Could not reset the password: {e}")

        _drop_recovery_reset_handoff(token)
        # Deliberately does NOT log the user in. They just chose a password
        # they have typed exactly twice; using it once more now is the cheapest
        # possible confirmation that it is what they think it is, while the
        # recovery key is still in their hand.
        return render_template('recover_reset.html', done=True)

    return render_template('recover_reset.html', token=token)


@auth_bp.route('/recovery-key/verify', methods=['GET', 'POST'])
@login_required
def verify_recovery_key():
    """Check a recovery key without changing anything.

    The counterpart to /recover, which always resets the password. Testing a
    key should not cost you your password, and a key that has never been
    tested is one you are only assuming works.

    Requires an existing session rather than the master password: this proves
    nothing an attacker gains from and writes nothing, so gating it harder
    would only discourage the checking it exists to encourage.
    """
    from core import migrate_crypto

    if migrate_crypto.install_crypto_version() != 3:
        return redirect(url_for('settings.settings_page'))

    if request.method == 'POST':
        key = request.form.get('recovery_key', '')
        try:
            if migrate_crypto.verify_recovery_key(key):
                return render_template('recovery_key_verify.html', verified=True)
            return render_template(
                'recovery_key_verify.html',
                error="That key does not open this practice file. If it's the "
                      "one you have on file, issue a new one and replace it.")
        except migrate_crypto.v3.RecoveryKeyError as e:
            return render_template('recovery_key_verify.html', error=str(e))

    return render_template('recovery_key_verify.html')


@auth_bp.route('/logout')
def logout():
    """Logout - run backup check and close database connection."""
    db = current_app.config.get('db')
    if db:
        from web.cli import _run_shutdown_backup
        _run_shutdown_backup(db, label="Logout")
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
        
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return render_template('change_password.html', error=PASSWORD_LENGTH_ERROR)
        
        db = current_app.config.get('db')
        if not db:
            return redirect(url_for('auth.login'))
        
        # Verify current password with fresh decryption test
        if not db.verify_password(current_password):
            return render_template('change_password.html', error="Current password is incorrect")
        
        # Hand the passwords to the SSE route via a server-side,
        # single-use token — never the session cookie (CODE_REVIEW.md H2)
        change_token = _store_password_handoff(current_password, new_password)

        # Render template with trigger to start SSE
        return render_template('change_password.html', start_change=True,
                               change_token=change_token)
    
    return render_template('change_password.html')


def _change_password_v2(db, app_obj, current_password, new_password):
    """SSE generator: change the master password on a v2 install. Closes the
    live DB handle, runs the crash-safe v2 rekey, and forces a fresh login (the
    handle is stale either way; a failure has already rolled back to the old
    password)."""
    from core import migrate_crypto
    yield f"data: {json.dumps({'status': 'backup', 'message': 'Creating safety backup and upgrading encryption...'})}\n\n"
    try:
        try:
            db.close()
        except Exception:
            pass
        app_obj.config['db'] = None
        result = migrate_crypto.change_password(current_password, new_password)
        yield f"data: {json.dumps({'status': 'complete', 'message': 'Password changed successfully!', 'files': result.get('files_rekeyed', 0)})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"


@auth_bp.route('/change-password-progress')
@login_required
def change_password_progress():
    """SSE endpoint for password change progress."""
    # Get passwords from the server-side handoff BEFORE entering the
    # generator (request context issue). The token is single-use and
    # expires after 5 minutes; the passwords never touch the cookie.
    handoff = _pop_password_handoff(request.args.get('token'))
    current_password, new_password = handoff if handoff else (None, None)
    db = current_app.config.get('db')
    from core import encryption_v2 as _v2
    is_v2 = _v2.keyinfo_exists()
    app_obj = current_app._get_current_object()
    
    def generate():
        if not current_password or not new_password:
            yield f"data: {json.dumps({'error': 'Missing password data'})}\n\n"
            return
        
        if not db:
            yield f"data: {json.dumps({'error': 'Database not available'})}\n\n"
            return

        if is_v2:
            yield from _change_password_v2(db, app_obj, current_password, new_password)
            return
        
        try:
            # Step 0: Create safety backup before making any changes
            yield f"data: {json.dumps({'status': 'backup', 'message': 'Creating safety backup...'})}\n\n"
            
            # Checkpoint WAL to ensure all changes are in main database file
            db.checkpoint()
            
            try:
                from utils.backup import create_pre_restore_backup
                
                # create_pre_restore_backup() always does a full backup of
                # current state; db enables checkpoint + integrity check
                backup_path = create_pre_restore_backup(db=db)
                if backup_path:
                    import os
                    backup_filename = os.path.basename(backup_path)
                    yield f"data: {json.dumps({'status': 'backup', 'message': f'Safety backup created: {backup_filename}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'backup', 'message': 'Safety backup created (no files to back up)'})}\n\n"
            except Exception as e:
                # Backup failed - abort password change
                yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to create safety backup: {e}. Password change aborted.'})}\n\n"
                return
            
            # Step 1: Count total files
            yield f"data: {json.dumps({'status': 'counting', 'message': 'Counting files...'})}\n\n"
            
            total_files = _count_encrypted_files(db)
            
            # Step 2: Re-encrypt all files with progress
            yield f"data: {json.dumps({'status': 'encrypting', 'total': total_files, 'current': 0, 'message': 'Re-encrypting files...'})}\n\n"
            
            failed_files = []
            for progress in _reencrypt_all_files_with_progress(db, current_password, new_password, total_files):
                yield f"data: {json.dumps(progress)}\n\n"
                # Capture failed files from final yield
                if progress.get('failed_files'):
                    failed_files = progress['failed_files']
            
            # Step 3: Rekey the database
            yield f"data: {json.dumps({'status': 'database', 'message': 'Updating database encryption...'})}\n\n"
            
            conn = db.connect()
            # Escape single quotes in password for PRAGMA (can't use parameterized query)
            escaped_password = new_password.replace("'", "''")
            conn.execute(f"PRAGMA rekey = '{escaped_password}'")
            
            # Step 4: Update the Database object's password
            db.password = new_password
            
            # Step 5: Verify new password works
            test_conn = db.connect()
            test_conn.execute("SELECT 1")
            
            # Success - but warn if any files failed
            if failed_files:
                file_names = [f['file'] for f in failed_files]
                yield f"data: {json.dumps({'status': 'complete_with_warnings', 'message': 'Password changed, but some files failed to re-encrypt', 'failed_files': file_names})}\n\n"
            else:
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


def _atomic_reencrypt(filepath: str, old_password: str, new_password: str) -> None:
    """Re-encrypt a single file atomically - plaintext never touches the original path.
    
    Strategy:
    1. Decrypt to a temp file in the same directory (same filesystem = atomic rename)
    2. Encrypt the temp file in place with new password
    3. Atomically replace the original with the newly encrypted temp file
    
    If anything fails, the original encrypted file is untouched.
    """
    from core.encryption import decrypt_file_to_bytes, encrypt_file
    
    original = Path(filepath)
    parent_dir = original.parent
    
    # Write to a temp file in the same directory so os.replace() is atomic
    fd, tmp_path = tempfile.mkstemp(dir=parent_dir, suffix='.tmp')
    try:
        # Decrypt old content and write to temp file
        data = decrypt_file_to_bytes(filepath, old_password)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        fd = None  # fdopen took ownership
        
        # Encrypt temp file in place with new password
        encrypt_file(tmp_path, new_password)
        
        # Atomically replace original with newly encrypted temp file
        os.replace(tmp_path, filepath)
        tmp_path = None  # os.replace succeeded, nothing to clean up
        
    finally:
        # Clean up temp file if anything went wrong
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _reencrypt_all_files_with_progress(db, old_password: str, new_password: str, total_files: int):
    """Re-encrypt all attachments and assets with new password, yielding progress.
    
    Uses atomic re-encryption so plaintext never touches the original file path.
    Yields progress dicts. Final yield includes 'failed_files' list if any failures occurred.
    """
    from core.config import ASSETS_DIR
    
    current_file = 0
    failed_files = []
    
    # Re-encrypt attachments from database
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, filepath FROM attachments")
    
    for row in cursor.fetchall():
        filepath = row[1]
        if filepath and os.path.exists(filepath):
            current_file += 1
            filename = os.path.basename(filepath)
            
            try:
                _atomic_reencrypt(filepath, old_password, new_password)
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': filename,
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt {filepath}: {e}")
                failed_files.append({'file': filename, 'error': str(e)})
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': filename,
                    'warning': f'Failed to re-encrypt {filename}',
                    'message': f'Processing {current_file} of {total_files}...'
                }
    
    # Re-encrypt logo if exists
    logo_filename = db.get_setting('logo_filename', '')
    if logo_filename:
        logo_path = ASSETS_DIR / logo_filename
        if logo_path.exists():
            current_file += 1
            try:
                _atomic_reencrypt(str(logo_path), old_password, new_password)
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'logo',
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt logo: {e}")
                failed_files.append({'file': 'logo', 'error': str(e)})
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'logo',
                    'warning': 'Failed to re-encrypt logo',
                    'message': f'Processing {current_file} of {total_files}...'
                }
    
    # Re-encrypt signature if exists
    sig_filename = db.get_setting('signature_filename', '')
    if sig_filename:
        sig_path = ASSETS_DIR / sig_filename
        if sig_path.exists():
            current_file += 1
            try:
                _atomic_reencrypt(str(sig_path), old_password, new_password)
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'signature',
                    'message': f'Processing {current_file} of {total_files}...'
                }
            except Exception as e:
                print(f"[Password Change] Failed to re-encrypt signature: {e}")
                failed_files.append({'file': 'signature', 'error': str(e)})
                yield {
                    'status': 'encrypting',
                    'total': total_files,
                    'current': current_file,
                    'filename': 'signature',
                    'warning': 'Failed to re-encrypt signature',
                    'message': f'Processing {current_file} of {total_files}...'
                }
    
    # Final yield with any failures
    if failed_files:
        yield {
            'status': 'files_complete',
            'failed_files': failed_files,
            'message': f'{len(failed_files)} file(s) failed to re-encrypt'
        }
