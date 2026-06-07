#!/usr/bin/env python3
"""
One-off audit: report orphaned rows that would violate the schema's declared
FOREIGN KEY constraints.

Background (CODE_REVIEW.md, M2): the app never runs PRAGMA foreign_keys=ON,
so every FOREIGN KEY clause in the schema is currently decorative. Before
enabling enforcement, this script reports any existing orphaned rows so they
can be reviewed and cleaned up. It makes NO changes to the database (opens
read-only).

Usage:
    source venv/bin/activate
    python tools/audit_orphans.py            # audits the app's real database
    python tools/audit_orphans.py --db PATH  # audit a specific database file

Prompts for the master password (the database is SQLCipher-encrypted).
"""

import argparse
import getpass
import os
import sys

# Make core importable when run from the repo root or tools/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlcipher3


# Declared FOREIGN KEY relationships in core/database.py _initialize_schema().
# (child_table, child_column, parent_table, parent_column, nullable)
# "nullable" means NULL is a legitimate value (not an orphan) — e.g. ledger
# entries have no client_id, ungrouped client_links have no group_id.
DECLARED_FKS = [
    ('clients',            'type_id',            'client_types', 'id', False),
    ('entries',            'client_id',          'clients',      'id', True),
    ('client_links',       'client_id_1',        'clients',      'id', False),
    ('client_links',       'client_id_2',        'clients',      'id', False),
    ('client_links',       'group_id',           'link_groups',  'id', True),
    ('entry_links',        'entry_id_1',         'entries',      'id', False),
    ('entry_links',        'entry_id_2',         'entries',      'id', False),
    ('attachments',        'entry_id',           'entries',      'id', False),
    ('statement_portions', 'statement_entry_id', 'entries',      'id', False),
    ('statement_portions', 'client_id',          'clients',      'id', False),
]


def get_default_db_path():
    from core.config import DATA_DIR
    return str(DATA_DIR / 'edgecase.db')


def connect_readonly(db_path, password):
    conn = sqlcipher3.connect(f'file:{db_path}?mode=ro', uri=True)
    if password:
        escaped = password.replace("'", "''")
        conn.execute(f"PRAGMA key = '{escaped}'")
    # Verify the key/file is readable
    conn.execute("SELECT count(*) FROM sqlite_master")
    return conn


def audit_fk(cursor, child, col, parent, parent_col, nullable):
    """Return (total, nulls, empty_strings, orphans, sample_ids) for one FK."""
    cursor.execute(f"SELECT COUNT(*) FROM {child}")
    total = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM {child} WHERE {col} IS NULL")
    nulls = cursor.fetchone()[0]

    # Empty strings would also violate FK enforcement (they match no parent
    # id) and are known to occur via add_entry's None -> '' coercion (H5).
    cursor.execute(f"SELECT COUNT(*) FROM {child} WHERE {col} = ''")
    empties = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(*) FROM {child} c
        WHERE c.{col} IS NOT NULL AND c.{col} != ''
          AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{parent_col} = c.{col})
    """)
    orphans = cursor.fetchone()[0]

    sample_ids = []
    if orphans:
        cursor.execute(f"""
            SELECT c.id, c.{col} FROM {child} c
            WHERE c.{col} IS NOT NULL AND c.{col} != ''
              AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{parent_col} = c.{col})
            LIMIT 10
        """)
        sample_ids = cursor.fetchall()

    return total, nulls, empties, orphans, sample_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default=None, help='Path to database file '
                        '(default: the app\'s real database)')
    parser.add_argument('--password', default=None,
                        help='Master password (omit to be prompted securely)')
    args = parser.parse_args()

    db_path = args.db or get_default_db_path()
    if not os.path.exists(db_path):
        print(f"ERROR: database not found: {db_path}")
        return 1

    password = args.password
    if password is None:
        password = getpass.getpass('Master password (blank if unencrypted): ')

    try:
        conn = connect_readonly(db_path, password)
    except Exception as e:
        print(f"ERROR: could not open database (wrong password?): {e}")
        return 1

    cursor = conn.cursor()
    print(f"Auditing: {db_path}  (read-only)\n")
    print(f"{'child table.column':<48} {'rows':>7} {'NULL':>6} "
          f"{'empty':>6} {'ORPHANS':>8}")
    print('-' * 81)

    problem_total = 0
    details = []
    for child, col, parent, parent_col, nullable in DECLARED_FKS:
        total, nulls, empties, orphans, samples = audit_fk(
            cursor, child, col, parent, parent_col, nullable)
        label = f"{child}.{col} -> {parent}"
        flag = ''
        # NULLs are fine where the column is legitimately optional; empty
        # strings and orphans always block FK enforcement.
        problems = orphans + empties + (0 if nullable else nulls)
        if problems:
            flag = '  <-- needs cleanup'
            problem_total += problems
        print(f"{label:<48} {total:>7} {nulls:>6} {empties:>6} "
              f"{orphans:>8}{flag}")
        if samples:
            details.append((label, samples))

    if details:
        print("\nSample orphaned rows (child row id, dangling value), max 10 each:")
        for label, samples in details:
            print(f"  {label}:")
            for row_id, value in samples:
                print(f"    id={row_id}  ->  {value!r}")

    # Cross-check with SQLite's own validator (works even with the pragma
    # off, but only reports NOT-NULL dangling references, not empty strings).
    print("\nPRAGMA foreign_key_check cross-check:")
    cursor.execute("PRAGMA foreign_key_check")
    violations = cursor.fetchall()
    if violations:
        print(f"  {len(violations)} violation(s):")
        for table, rowid, parent, fkid in violations[:20]:
            print(f"    table={table} rowid={rowid} parent={parent} fk_index={fkid}")
        if len(violations) > 20:
            print(f"    ... and {len(violations) - 20} more")
    else:
        print("  none reported")

    print()
    if problem_total:
        print(f"RESULT: {problem_total} row(s) need cleanup before "
              f"PRAGMA foreign_keys=ON can be enabled safely.")
    else:
        print("RESULT: no orphaned rows found. Safe to consider enabling "
              "PRAGMA foreign_keys=ON (see CODE_REVIEW.md M2).")

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
