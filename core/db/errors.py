"""Shared database-layer exceptions.

Leaf module: it imports nothing from core.database or the domain mixins, so both
the base Database class and the mixins (e.g. EntryMixin in core/db/entries.py)
can import these without creating an import cycle.
"""


class EntryLockedError(Exception):
    """Raised when update_entry is called on a locked entry without
    `allow_locked=True`. Locked clinical entries are immutable by design;
    edits to them must go through the route layer's lock-check + edit
    history flow, which then opts in via `allow_locked=True`.
    See CODE_REVIEW.md M11.
    """
    pass
