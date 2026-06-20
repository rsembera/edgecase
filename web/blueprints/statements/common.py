"""Shared state for the statements blueprint.

Owns statements_bp and the database handle (set by init_blueprint at login, read
via get_db). Route modules import these; this module imports nothing from them,
keeping the dependency direction acyclic.
"""
from flask import Blueprint

# Blueprint name MUST stay 'statements' — url_for('statements.<fn>') and the
# '/statements' url_prefix registration depend on it.
statements_bp = Blueprint('statements', __name__)

_db = None


def init_blueprint(database):
    """Set the database handle (called at login by init_all_blueprints)."""
    global _db
    _db = database


def get_db():
    """Return the live database handle (called once at the top of each handler)."""
    return _db
