"""statements blueprint package (split from the former statements.py)."""
from web.blueprints.statements.common import statements_bp, init_blueprint  # noqa: F401

# Import route modules for their decorator side effects (registers routes).
from web.blueprints.statements import (  # noqa: F401,E402
    views, generation, payments, delivery,
)
