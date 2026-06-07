#!/usr/bin/env python3
"""
One-off audit: report entries with TEXT '' values in columns that the schema
declares as INTEGER or REAL.

Background (CODE_REVIEW.md, H5): add_entry historically coerced None to ''
for every column, so INTEGER/REAL columns can contain '' instead of NULL.
SQLite stores those as TEXT, which sorts above all numeric values and breaks
BETWEEN/range filters, ORDER BY, and `IS NULL` checks (e.g. redaction's
`if statement_id is not None` returns True for entries whose statement_id
is ''). The coercion has been fixed; this script reports the residue.

Usage:
    source venv/bin/activate
    python tools/audit_typed_columns.py
    python tools/audit_typed_columns.py --db PATH
    python tools/audit_typed_columns.py --fix          # also rewrites '' → NULL

The default mode is read-only. --fix runs an UPDATE per affected column.
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlcipher3
from core.database import Database


def get_default_db_path():
    from core.config import DATA_DIR
    return str(DATA_DIR / 'edgecase.db')


def connect(db_path, password, readonly=True):
    uri = f'file:{db_path}?mode=ro' if readonly else f'file:{db_path}'
    conn = sqlcipher3.connect(uri, uri=True)
    if password:
        escaped = password.replace("'", "''")
        conn.execute(f"PRAGMA key = '{escaped}'")
    conn.execute("SELECT count(*) FROM sqlite_master")  # verify
    return conn


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default=None,
                        help="Path to database file (default: app's real DB)")
    parser.add_argument('--password', default=None,
                        help='Master password (omit to be prompted)')
    parser.add_argument('--fix', action='store_true',
                        help="Rewrite '' to NULL in affected columns (writes!)")
    args = parser.parse_args()

    db_path = args.db or get_default_db_path()
    if not os.path.exists(db_path):
        print(f"ERROR: database not found: {db_path}")
        return 1

    password = args.password
    if password is None:
        password = getpass.getpass('Master password (blank if unencrypted): ')

    try:
        conn = connect(db_path, password, readonly=not args.fix)
    except Exception as e:
        print(f"ERROR: could not open database (wrong password?): {e}")
        return 1

    cursor = conn.cursor()
    mode = "READ-WRITE (--fix)" if args.fix else "read-only"
    print(f"Auditing: {db_path}  ({mode})\n")
    print(f"{'column':<32} {'rows w/ empty string':>22}")
    print('-' * 55)

    columns = sorted(Database.TYPED_ENTRY_COLUMNS)
    total_bad = 0
    affected = []
    for col in columns:
        cursor.execute(f"SELECT COUNT(*) FROM entries WHERE {col} = ''")
        n = cursor.fetchone()[0]
        if n:
            total_bad += n
            affected.append((col, n))
            print(f"{col:<32} {n:>22}")

    if not affected:
        print("(none — typed columns are clean)")

    print()
    if args.fix and affected:
        print("Applying fixes:")
        for col, n in affected:
            cursor.execute(f"UPDATE entries SET {col} = NULL WHERE {col} = ''")
            print(f"  {col}: rewrote {cursor.rowcount} row(s)")
        conn.commit()
        print("\nFix complete. Re-run without --fix to verify.")
    elif affected:
        print(f"RESULT: {total_bad} value(s) need cleanup. "
              f"Re-run with --fix to rewrite to NULL.")
    else:
        print("RESULT: typed columns are clean.")

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
