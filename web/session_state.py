"""Which browser sessions count as logged in, and when one has expired.

The unlocked database is app-global; the cookie is what says "this client
logged in". Three rules live here (found in the 2026-11-11 review):

1. A cookie is only good for the unlock it was issued under. Each time
   the practice is unlocked from a locked state a fresh EPOCH is minted,
   stored in app config and in the cookie. A cookie from an earlier
   unlock (another browser, yesterday's session, a device that never
   logged out) no longer matches and is simply not logged in — it cannot
   keep itself alive, and it cannot close the practice on someone else.

2. Expiry is decided on the server, in one place, so /api/keepalive
   cannot revive a session that has already timed out.

3. When a session times out while ANOTHER session is in active use (the
   iPad left open while work continues on the Mac), only the idle one is
   ended. Closing the database then would throw away whatever is unsaved
   in the active one. Activity is tracked per session id for this.

A second login while the practice is already unlocked joins the current
epoch rather than replacing it, so two devices can be used side by side.
"""
import secrets
import time

from flask import current_app, session


def ensure_epoch():
    """Mint a new epoch if the practice is currently locked.

    Call BEFORE config['db'] is assigned on a login path, and before
    start_session on the paths that attach the database later (the
    encryption-upgrade and rotation streams).
    """
    config = current_app.config
    if config.get('db') is None or not config.get('SESSION_EPOCH'):
        config['SESSION_EPOCH'] = secrets.token_hex(16)
        config['SESSION_ACTIVITY'] = {}
    return config['SESSION_EPOCH']


def start_session():
    """Mark this browser as logged in under the current epoch."""
    config = current_app.config
    epoch = config.get('SESSION_EPOCH') or ensure_epoch()
    now = time.time()
    session.clear()
    session.permanent = True  # Use PERMANENT_SESSION_LIFETIME
    session['authenticated'] = True
    session['epoch'] = epoch
    session['sid'] = secrets.token_hex(8)
    session['login_time'] = int(now)
    session['last_activity'] = now  # set immediately to prevent timeout race
    session.modified = True
    _activity()[session['sid']] = now


def session_is_current() -> bool:
    """True if this cookie was issued under the current unlock."""
    if not session.get('authenticated'):
        return False
    epoch = current_app.config.get('SESSION_EPOCH')
    if epoch is None:
        # No login has happened in this process. Only the test harness
        # reaches here with a database attached (it injects one directly).
        return bool(current_app.config.get('TESTING'))
    return session.get('epoch') == epoch


def timeout_seconds(db):
    """The idle timeout in seconds, or None for "Never"."""
    try:
        minutes = int(db.get_setting('session_timeout', '30'))
    except (ValueError, TypeError):
        minutes = 30
    return None if minutes == 0 else minutes * 60


def session_expired(db, now=None) -> bool:
    limit = timeout_seconds(db)
    if limit is None:
        return False
    last = session.get('last_activity')
    if not last:
        return False
    return (now or time.time()) - last > limit


def touch(now=None):
    """Record activity for this session."""
    now = now or time.time()
    session['last_activity'] = now
    _activity()[session.get('sid')] = now


def another_session_active(db, now=None) -> bool:
    """Is some OTHER session still inside its timeout?"""
    now = now or time.time()
    limit = timeout_seconds(db)
    mine = session.get('sid')
    activity = _activity()
    if limit is not None:
        for sid in [s for s, ts in activity.items() if now - ts > limit]:
            if sid != mine:
                del activity[sid]
    return any(sid != mine for sid in activity)


def forget_session():
    """Drop this session's activity record and clear its cookie."""
    _activity().pop(session.get('sid'), None)
    session.clear()


def _activity() -> dict:
    return current_app.config.setdefault('SESSION_ACTIVITY', {})
