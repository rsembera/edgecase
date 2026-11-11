"""Desktop file tickets.

In the packaged app, "View PDF" and "Download" do not go through the
webview: desktop.py fetches the file with a plain Python request and hands
it to the system viewer or the Downloads folder. That request carries no
session cookie (the cookie is HttpOnly inside the webview), so once sessions
became per-client (2026-06-09) it was redirected to the login page — and the
login page's HTML was what got saved and opened. Every desktop build from
2.0.0 to 2.0.4 has this.

A ticket is the desktop shell vouching for one such fetch: minted in-process
by desktop.py (never over HTTP), single-use, short-lived, GET-only and
loopback-only.
"""
import secrets
import time

from flask import current_app, request

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
