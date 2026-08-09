#!/usr/bin/env python3
"""Snapshot financially-significant data, to compare before and after the
crypto v3 migration.

_export_verify already checks integrity_check and per-table row-count parity
before the rebuilt database is swapped in, and sqlcipher_export is a verbatim
bulk copy rather than a per-row transform. That is a sound guard against gross
failure — but it is not a field-by-field diff, and "the money is all still
there" is worth being able to demonstrate rather than infer, on records that
are both clinical and CRA-facing.

Usage:

    # BEFORE migrating
    venv/bin/python tools/verify_migration_data.py before.json

    # ... run the upgrade via the app ...

    # AFTER migrating
    venv/bin/python tools/verify_migration_data.py after.json
    venv/bin/python tools/verify_migration_data.py --compare before.json after.json

Reads only. Never writes to the database. Point it at the testing instance
with EDGECASE_DATA, exactly as the app is run.
"""
import getpass
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def snapshot(password):
    from core.database import Database
    from core.config import DATA_DIR

    db = Database(str(DATA_DIR / "edgecase.db"), password=password)
    con = db.connect()
    cur = con.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    out = {"tables": {}, "money": {}, "statements": []}

    for t in tables:
        out["tables"][t] = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]

    # Totals that would matter if anything drifted.
    def scalar(sql):
        v = cur.execute(sql).fetchone()[0]
        return round(float(v), 2) if v is not None else 0.0

    out["money"]["income_total"] = scalar(
        "SELECT SUM(total_amount) FROM entries WHERE ledger_type='income'")
    out["money"]["expense_total"] = scalar(
        "SELECT SUM(total_amount) FROM entries WHERE ledger_type='expense'")
    out["money"]["tax_total"] = scalar(
        "SELECT SUM(tax_amount) FROM entries WHERE tax_amount IS NOT NULL")
    out["money"]["portions_due"] = scalar(
        "SELECT SUM(amount_due) FROM statement_portions")
    out["money"]["portions_paid"] = scalar(
        "SELECT SUM(amount_paid) FROM statement_portions")
    out["money"]["outstanding"] = scalar(
        "SELECT SUM(amount_due - amount_paid) FROM statement_portions "
        "WHERE status IN ('sent','partial')")

    # Every outstanding statement, individually — the thing actually asked
    # about. Ordered so the comparison is stable.
    for row in cur.execute(
        "SELECT id, client_id, guardian_number, amount_due, amount_paid, status "
        "FROM statement_portions ORDER BY id"
    ):
        out["statements"].append({
            "id": row[0], "client_id": row[1], "guardian": row[2],
            "due": round(float(row[3] or 0), 2),
            "paid": round(float(row[4] or 0), 2),
            "status": row[5],
        })

    # Attachment inventory: the files the migration re-encrypts.
    out["attachments"] = cur.execute(
        "SELECT COUNT(*) FROM attachments").fetchone()[0]

    db.close()
    return out


def compare(a_path, b_path):
    a = json.load(open(a_path))
    b = json.load(open(b_path))
    problems = []

    for key in ("tables", "money"):
        for name in sorted(set(a[key]) | set(b[key])):
            av, bv = a[key].get(name), b[key].get(name)
            if av != bv:
                problems.append(f"  {key}.{name}: {av!r} -> {bv!r}")

    if a.get("attachments") != b.get("attachments"):
        problems.append(
            f"  attachments: {a.get('attachments')!r} -> {b.get('attachments')!r}")

    if a["statements"] != b["statements"]:
        by_id_a = {s["id"]: s for s in a["statements"]}
        by_id_b = {s["id"]: s for s in b["statements"]}
        for sid in sorted(set(by_id_a) | set(by_id_b)):
            if by_id_a.get(sid) != by_id_b.get(sid):
                problems.append(
                    f"  statement portion {sid}: {by_id_a.get(sid)} -> {by_id_b.get(sid)}")

    if problems:
        print("DIFFERENCES FOUND:\n" + "\n".join(problems))
        print("\nYour pre-migration backup is in the backups folder.")
        return 1

    print("IDENTICAL — every table count, every money total, and every "
          "statement portion matches.")
    print(f"  tables checked      : {len(a['tables'])}")
    print(f"  statement portions  : {len(a['statements'])}")
    print(f"  outstanding balance : {a['money']['outstanding']}")
    print(f"  attachments         : {a.get('attachments')}")
    return 0


def main():
    args = sys.argv[1:]
    if args and args[0] == "--compare":
        if len(args) != 3:
            print("usage: --compare BEFORE.json AFTER.json", file=sys.stderr)
            return 2
        return compare(args[1], args[2])

    if len(args) != 1:
        print(__doc__)
        return 2

    password = os.environ.get("EDGECASE_PASSWORD") or getpass.getpass(
        "Master password: ")
    data = snapshot(password)
    with open(args[0], "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print(f"Wrote {args[0]}")
    print(f"  statement portions  : {len(data['statements'])}")
    print(f"  outstanding balance : {data['money']['outstanding']}")
    print(f"  attachments         : {data.get('attachments')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
