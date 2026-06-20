"""Shared state and helpers for the entries blueprint.

Owns the entries_bp blueprint object, the database handle (set by init_blueprint
at login, read via get_db), and the helpers used across the per-type route
modules. Route modules import from here; this module imports nothing from them,
which keeps the dependency direction acyclic.
"""
import os

from flask import Blueprint

from core.config import DATA_ROOT
from core.money import money_float

# Blueprint name MUST stay 'entries' — url_for('entries.<fn>') is used throughout
# the templates, so the endpoint prefix cannot change.
entries_bp = Blueprint('entries', __name__)

_db = None


def init_blueprint(database):
    """Set the database handle (called at login by init_all_blueprints)."""
    global _db
    _db = database


def get_db():
    """Return the live database handle. Route handlers call this once at the top
    (``db = get_db()``); reading at call time keeps the handle live across the
    split modules (a plain ``from common import db`` would bind None forever)."""
    return _db


def safe_float(value, default=None):
    """Safely convert form value to float, returning default if invalid."""
    if not value:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_money(value, default=None):
    """Safely convert a form value to a cent-quantized float for storage.

    Like safe_float, but for monetary amounts: the value is quantized to
    cents via Decimal (core.money) so stored fees are always exact cent
    quantities (CODE_REVIEW.md M1).
    """
    if not value:
        return default
    try:
        return money_float(value)
    except (ValueError, TypeError, ArithmeticError):
        return default


def safe_int(value, default=None):
    """Safely convert form value to int, returning default if invalid."""
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def resolve_attachment_path(filepath):
    """Resolve attachment filepath, handling both absolute and relative paths."""
    if os.path.isabs(filepath):
        return filepath
    return str(DATA_ROOT / filepath)


def renumber_sessions(client_id):
    """Recalculate session numbers for a client based on chronological order."""
    db = get_db()
    # Get client to check for session offset
    client = db.get_client(client_id)
    offset = client.get('session_offset', 0)

    # Get all non-consultation, non-redacted sessions with dates
    all_sessions = db.get_client_entries(client_id, 'session')
    dated_sessions = [s for s in all_sessions
                      if s.get('session_date')
                      and not s.get('is_consultation')
                      and not s.get('is_redacted')]

    # Sort by date, then by ID
    dated_sessions.sort(key=lambda s: (s['session_date'], s['id']))

    # Renumber sessions starting from (offset + 1)
    for i, sess in enumerate(dated_sessions, start=offset + 1):
        if sess['session_number'] != i:
            db.update_entry(sess['id'], {
                'session_number': i,
                'description': f"Session {i}"
            }, allow_locked=True)  # System invariant; not user-initiated.
