"""Drop the inert entries.reflections column left by 2.0.2.

One-off maintenance for a database that ran 2.0.2. The 2.0.3 fold migration
has already moved any text out of the column; this removes the column
itself. It is not part of the app because DROP COLUMN on a stranger's
encrypted database is not a risk the app should take on their behalf — but
on your own machine, with a backup taken first, it is a two-second job.

Usage (from the repo root, with the app NOT running):

    venv/bin/python tools/drop_reflections_column.py

Prompts for the master password; refuses to proceed if the column still
holds any text (i.e. 2.0.3 has not opened this database yet).
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import DATA_DIR  # noqa: E402
from core.database import Database  # noqa: E402


def main():
    db_path = Path(DATA_DIR) / "edgecase.db"
    if not db_path.exists():
        sys.exit(f"No database at {db_path}")
    print(f"Database: {db_path}")
    print("Take a backup before continuing if you have not already.")
    password = getpass.getpass("Master password: ")

    db = Database(str(db_path), password=password)
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM client_types")  # proves the password

    cur.execute("PRAGMA table_info(entries)")
    if 'reflections' not in {r[1] for r in cur.fetchall()}:
        print("entries.reflections is not present. Nothing to do.")
        return

    cur.execute("SELECT count(*) FROM entries "
                "WHERE reflections IS NOT NULL AND reflections != ''")
    (pending,) = cur.fetchone()
    if pending:
        sys.exit(f"{pending} entries still hold reflections text; open the "
                 "app under 2.0.3 first so the fold migration runs.")

    cur.execute("ALTER TABLE entries DROP COLUMN reflections")
    conn.commit()

    cur.execute("PRAGMA table_info(entries)")
    assert 'reflections' not in {r[1] for r in cur.fetchall()}
    cur.execute("PRAGMA integrity_check")
    print("integrity_check:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM entries")
    print("entries:", cur.fetchone()[0])
    db.close()
    print("Dropped entries.reflections.")


if __name__ == "__main__":
    main()
