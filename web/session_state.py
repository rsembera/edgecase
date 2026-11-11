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

from flask import current_app, request, session


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


# ---------------------------------------------------------------------------
# Desktop file tickets
#
# In the packaged app, "View PDF" and "Download" do not go through the
# webview: desktop.py fetches the file with a plain Python request and hands
# it to the system viewer or the Downloads folder. That request carries no
# session cookie (the cookie is HttpOnly inside the webview), so once
# sessions became per-client it was redirected to the login page — and the
# login page's HTML was what got saved and opened. A ticket is the desktop
# shell vouching for one such fetch: minted in-process by desktop.py (never
# over HTTP), single-use, short-lived, GET-only and loopback-only.
# ---------------------------------------------------------------------------

DESKTOP_TICKET_HEADER = 'X-EdgeCase-Desktop-Ticket'
DESKTOP_TICKET_TTL = 30  # seconds


def issue_desktop_ticket(app) -> str:
    """Mint a ticket for one file fetch. `app` is the Flask app object:
    this is called from the desktop shell, outside any request."""
    tickets = app.config.setdefault('DESKTOP_TICKETS', {})
    now = time.time()
    for stale in [t for t, expiry in tickets.items() if expiry < now]:
        del tickets[stale]
    ticket = secrets.token_urlsafe(32)
    tickets[ticket] = now + DESKTOP_TICKET_TTL
    return ticket


def redeem_desktop_ticket() -> bool:
    """True if this request carries a valid ticket (which is then spent)."""
    ticket = request.headers.get(DESKTOP_TICKET_HEADER)
    if not ticket or request.method != 'GET':
        return False
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return False
    expiry = current_app.config.setdefault('DESKTOP_TICKETS', {}).pop(ticket, None)
    return expiry is not None and expiry >= time.time()
