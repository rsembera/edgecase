#!/usr/bin/env python3
"""
One-off recovery: restore attachment files that exist in a v1-era backup but
are missing from the live install, re-encrypting them under the current key.

Background
----------
Three of client 1's statement PDFs were deleted from disk between 2026-06-14
14:17 and 2026-06-15 17:55 (evidenced by incr_2026-06-15_175532.zip, whose
metadata lists exactly those three deletions). The `attachments` rows survived
intact -- audit_orphans reports 79 rows, 0 orphans -- so only the files are
gone. No EdgeCase code path produces that state; every in-app deletion removes
the row as well. The client is Inactive, not deleted, so the records fall under
the ten-year retention obligation and belong back in the install.

The source backup is v1-era: its attachment blobs are Fernet tokens (magic
'gAAA'), keyed by PBKDF2-SHA256/480k over the backup's own data/.salt and the
master password *as it was then*. The live install is v2/v3, so the files
cannot be copied back -- they must be decrypted under the old scheme and
re-encrypted under the current file key.

Restored files are written under a UUID name per the 2026-09-04 filename
privacy fix, and the matching attachments.filepath rows are updated in one
transaction.

Usage
-----
    source venv/bin/activate
    python tools/restore_missing_attachments.py                 # dry run
    python tools/restore_missing_attachments.py --apply         # write

    --backup PATH   backup zip to read (default: the preserved June 14 full)
    --apply         actually write files and update the database

Prompts for the current master password, and for the old one only if the
current password fails to decrypt the backup's blobs. Neither is echoed or
stored.
"""

import argparse
import base64
import getpass
import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import sqlcipher3

from core import encryption_v2 as v2
from core.config import ATTACHMENTS_DIR, DATA_DIR, DATA_ROOT

DEFAULT_BACKUP = (Path.home() / "EdgeCase_Incident_2026-06-15"
                  / "full_2026-06-14_135934.zip")

# The three files recorded as deleted in incr_2026-06-15_175532.zip.
TARGETS = [
    "attachments/1/50/Statement_20250901-JH_20260202.pdf",
    "attachments/1/124/Statement_20250901-JH_20260401.pdf",
    "attachments/1/244/Statement_20250901-JH_20260601.pdf",
]


def v1_fernet(password: str, salt: bytes) -> Fernet:
    """Rebuild the v1 Fernet from an explicit salt.

    core.encryption._get_fernet reads the *live* data/.salt; we need the
    backup's, so the KDF is repeated here rather than reused. Parameters must
    stay identical to core/encryption.py: PBKDF2-SHA256, 32 bytes, 480_000.
    """
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=480000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode())))


def open_db(password: str):
    db_key_hex, file_key = v2.get_keys(password)
    conn = sqlcipher3.connect(str(DATA_DIR / "edgecase.db"))
    conn.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    conn.execute("SELECT count(*) FROM sqlite_master")
    return conn, file_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup", default=str(DEFAULT_BACKUP))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    backup = Path(args.backup)
    if not backup.exists():
        print(f"ERROR: backup not found: {backup}")
        return 1

    z = zipfile.ZipFile(backup)
    names = set(z.namelist())
    missing_from_backup = [t for t in TARGETS if t not in names]
    if missing_from_backup:
        print("ERROR: backup does not contain:")
        for m in missing_from_backup:
            print("   ", m)
        return 1
    if "data/.salt" not in names:
        print("ERROR: backup has no data/.salt; cannot derive the v1 key.")
        return 1

    password = getpass.getpass("Current master password: ")
    try:
        conn, file_key = open_db(password)
    except Exception as e:
        print(f"ERROR: could not open the live database (wrong password?): {e}")
        return 1

    # The blobs may predate a password change; try the current password first.
    salt = z.read("data/.salt")
    probe = z.read(TARGETS[0])
    fernet = v1_fernet(password, salt)
    try:
        fernet.decrypt(probe)
    except InvalidToken:
        print("The current password does not decrypt the backup's files.")
        old = getpass.getpass("Master password as of June 2026: ")
        fernet = v1_fernet(old, salt)
        try:
            fernet.decrypt(probe)
        except InvalidToken:
            print("ERROR: that password does not decrypt them either. Stopping.")
            return 1

    cur = conn.cursor()
    plan = []
    for rel in TARGETS:
        plaintext = fernet.decrypt(z.read(rel))
        if not plaintext.startswith(b"%PDF"):
            print(f"ERROR: {rel} did not decrypt to a PDF. Stopping; "
                  f"nothing has been written.")
            return 1

        cur.execute("SELECT id, entry_id, filename, filepath FROM attachments "
                    "WHERE filepath = ? OR filepath = ?",
                    (rel, str(DATA_ROOT / rel)))
        rows = cur.fetchall()
        if len(rows) != 1:
            print(f"ERROR: expected exactly 1 attachments row for {rel}, "
                  f"found {len(rows)}. Stopping.")
            return 1
        att_id, entry_id, filename, old_path = rows[0]

        new_rel = f"attachments/1/{entry_id}/{uuid.uuid4()}.enc"
        plan.append({
            "src": rel, "att_id": att_id, "entry_id": entry_id,
            "filename": filename, "old_path": old_path,
            "new_rel": new_rel, "plaintext": plaintext,
        })

    print(f"\nSource: {backup.name}")
    print(f"Target: {DATA_ROOT}\n")
    for p in plan:
        print(f"  attachments.id={p['att_id']}  entry_id={p['entry_id']}  "
              f"{len(p['plaintext']):,} bytes")
        print(f"    display name : {p['filename']}")
        print(f"    old filepath : {p['old_path']}")
        print(f"    new filepath : {p['new_rel']}")

    if not args.apply:
        print("\nDRY RUN. Nothing written. Re-run with --apply to restore.")
        return 0

    written = []
    try:
        for p in plan:
            dest = DATA_ROOT / p["new_rel"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(v2.encrypt_bytes(file_key, p["plaintext"]))
            os.chmod(dest, 0o600)
            written.append(dest)

        # Verify each restored file round-trips before touching the database.
        for p, dest in zip(plan, written):
            back = v2.decrypt_bytes(file_key, dest.read_bytes())
            if back != p["plaintext"]:
                raise RuntimeError(f"round-trip mismatch on {dest}")

        cur.execute("BEGIN")
        for p in plan:
            cur.execute("UPDATE attachments SET filepath = ? WHERE id = ?",
                        (p["new_rel"], p["att_id"]))
        conn.commit()
    except Exception as e:
        conn.rollback()
        for dest in written:
            try:
                dest.unlink()
            except OSError:
                pass
        print(f"\nERROR: {e}\nRolled back; no files or rows were changed.")
        return 1

    print(f"\nRestored {len(plan)} file(s) and updated their rows.")
    print("Verify in the app: open the client file and each statement "
          "attachment should now open.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
