#!/usr/bin/env python3
"""
Crypto v2 migration — DRY RUN (read-only against your live data).

Copies a data root (data/, attachments/, assets/) into a scratch directory
and runs the entire v1 -> v2 migration THERE, verifying every step. It never
writes to the source; the only thing it reads from the live install is file
content and the .salt (needed to derive the old key). Prints a report and
exits non-zero on any failure.

Usage:
    python tools/migrate_crypto_dryrun.py [--source <data-root>] [--keep]

  --source  data root to copy from (default: live DATA_ROOT from core.config)
  --keep    keep the scratch dir for inspection (else removed at the end)

The master password is read from a secure prompt (getpass); it is never taken
as an argument and never printed.
"""
import argparse
import base64
import getpass
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import sqlcipher3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core import config          # noqa: E402
from core import encryption_v2 as v2   # noqa: E402


def _sql_escape(pw: str) -> str:
    return pw.replace("'", "''")


def _old_fernet(password: str, salt: bytes) -> Fernet:
    # Mirrors core.encryption._get_fernet exactly: PBKDF2-SHA256, 480k iters.
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=480000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode())))


def run(source: Path, keep: bool) -> bool:
    print(f"Source data root : {source}")
    for sub in ("data", "attachments", "assets"):
        print(f"  {sub:12} {'present' if (source / sub).exists() else 'absent'}")

    scratch = Path(tempfile.mkdtemp(prefix="edgecase_dryrun_"))
    print(f"Scratch dir      : {scratch}\n")
    for sub in ("data", "attachments", "assets"):
        if (source / sub).exists():
            shutil.copytree(source / sub, scratch / sub)

    sdata = scratch / "data"
    db_path = sdata / "edgecase.db"
    salt = (sdata / ".salt").read_bytes()

    password = getpass.getpass("Master password: ")
    print()

    # --- 1. Confirm the OLD password opens the database -------------------
    try:
        con = sqlcipher3.connect(str(db_path))
        con.execute(f"PRAGMA key = '{_sql_escape(password)}'")
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        old_counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                      for t in tables}
        con.close()
    except Exception as e:
        print(f"FAIL: old password did not open the database ({e!r})")
        if not keep:
            shutil.rmtree(scratch)
        return False
    print(f"[1] Old password opens DB: OK  ({len(tables)} tables, "
          f"{sum(old_counts.values())} rows total)")

    old_fernet = _old_fernet(password, salt)

    # --- 2. Derive NEW keys with production Argon2id params ---------------
    new_salt = v2.new_salt()
    t = time.time()
    master = v2.derive_master(password, new_salt)   # 256 MiB / t=6 / p=1
    argon_secs = time.time() - t
    db_key_hex, file_key = v2.derive_subkeys(master)
    print(f"[2] Argon2id derive (256 MiB, t=6, p=1): {argon_secs:.2f}s")

    # --- 3. Re-encrypt every v1 file to v2, verifying round-trip ----------
    migrated, bytes_total, skipped_v2, skipped_plain, failures = 0, 0, 0, 0, []
    for base in (scratch / "attachments", scratch / "assets"):
        if not base.exists():
            continue
        for fp in sorted(base.rglob("*")):
            if not fp.is_file() or fp.name == ".DS_Store":
                continue
            blob = fp.read_bytes()
            if v2.is_v2(blob):
                skipped_v2 += 1
                continue
            if not v2.is_v1(blob):
                skipped_plain += 1          # plain asset (icon, etc.)
                continue
            try:
                plain = old_fernet.decrypt(blob)
                fp.write_bytes(v2.encrypt_bytes(file_key, plain))
                if v2.decrypt_bytes(file_key, fp.read_bytes()) != plain:
                    raise ValueError("round-trip mismatch")
                migrated += 1
                bytes_total += len(plain)
            except Exception as e:
                failures.append((fp.name, repr(e)))
    print(f"[3] Files: {migrated} migrated ({bytes_total} bytes), "
          f"{skipped_v2} already-v2, {skipped_plain} plain/skipped, "
          f"{len(failures)} failed")
    for name, err in failures:
        print(f"      FAILED {name}: {err}")

    # --- 4. Rekey the DB copy via sqlcipher_export into a raw-keyed DB -----
    new_db = sdata / "edgecase_v2.db"
    if new_db.exists():
        new_db.unlink()
    con = sqlcipher3.connect(str(db_path))
    con.execute(f"PRAGMA key = '{_sql_escape(password)}'")
    con.execute(f"ATTACH DATABASE '{new_db}' AS v2db KEY \"x'{db_key_hex}'\"")
    con.execute("SELECT sqlcipher_export('v2db')")
    con.execute("DETACH DATABASE v2db")
    con.close()

    con2 = sqlcipher3.connect(str(new_db))
    con2.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    integrity = con2.execute("PRAGMA integrity_check").fetchone()[0]
    new_counts = {t: con2.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in tables}
    con2.close()
    counts_match = old_counts == new_counts
    print(f"[4] DB rekeyed to raw v2 key: integrity_check={integrity!r}, "
          f"row counts {'match' if counts_match else 'DIFFER'}")

    # --- 5. Write + verify the .keyinfo file ------------------------------
    token = v2.make_verification_token(file_key)
    keyinfo_path = sdata / ".keyinfo"
    v2.write_keyinfo(new_salt, token, path=keyinfo_path)
    rsalt, rtoken = v2.read_keyinfo(path=keyinfo_path)
    keyinfo_ok = rsalt == new_salt and v2.check_verification_token(file_key, rtoken)
    print(f"[5] .keyinfo written + verifies: {'OK' if keyinfo_ok else 'FAIL'}")

    ok = (not failures) and integrity == "ok" and counts_match and keyinfo_ok
    print("\n" + ("PASS — full migration round-trips on this data."
                  if ok else "FAIL — see lines above."))
    if keep:
        print(f"Scratch kept at: {scratch}")
    else:
        shutil.rmtree(scratch)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None,
                    help="data root to copy from (default: live DATA_ROOT)")
    ap.add_argument("--keep", action="store_true",
                    help="keep the scratch dir for inspection")
    args = ap.parse_args()
    source = Path(args.source) if args.source else Path(config.DATA_ROOT)
    sys.exit(0 if run(source, args.keep) else 1)


if __name__ == "__main__":
    main()
