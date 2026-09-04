"""Columns that must never leave the application in an export.

The two-note system stores the practitioner's process notes in
`entries.reflections`. They are part of the record — a PHIPA access request,
a CRPO investigation or a production order can reach them, and the duty to
disclose their existence sits with the practitioner — but they are not part
of routine exports, which is the practice a two-note system exists to support.

The export generators name their fields explicitly, so today they exclude
`reflections` by construction. Construction changes. `strip_private()` makes
the exclusion a deliberate step at the data boundary, with a test behind it,
rather than a property that happens to hold.
"""

PRIVATE_ENTRY_COLUMNS = frozenset({'reflections'})


def strip_private(rows):
    """Drop private columns from an entry dict or a list of them.

    Accepts and returns whatever it is given (dict, list, None) so it can be
    dropped in front of an existing call without changing its shape.
    """
    if rows is None:
        return None
    if isinstance(rows, dict):
        return {k: v for k, v in rows.items()
                if k not in PRIVATE_ENTRY_COLUMNS}
    return [strip_private(row) for row in rows]
