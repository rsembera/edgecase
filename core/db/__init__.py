"""Per-domain mixins for the Database class (core/database.py refactor, Step 3).

Each module here holds one cohesive slice of the former database.py god-object as
a mixin class. core.database.Database inherits from all of them plus the base
machinery (connection, schema, crypto keying), so callers still import a single
Database with the same public method names — the split is internal only, and the
185-test suite (data layer + routes) guards the behaviour.
"""
