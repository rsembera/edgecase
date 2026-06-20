"""entries blueprint package (split from the former entries.py god-file)."""
from web.blueprints.entries.common import entries_bp, init_blueprint  # noqa: F401

# Import route modules for their decorator side effects (registers routes).
from web.blueprints.entries import routes  # noqa: F401,E402
