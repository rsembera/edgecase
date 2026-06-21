# Future Refinements

This document tracks architectural improvements and refactoring ideas that aren't urgent but would be worth doing if time permits or during a major version update.

---

## Stronger First-Run Password Policy

**Priority:** Medium (highest-value security item for *distributed* installs)  
**Effort:** Small (under an hour)  
**Status:** Documented, not scheduled — good candidate to ride along with the next .deb/.dmg rebuild

### Rationale

All of EdgeCase's encryption (SQLCipher database, encrypted attachments) derives its keys from the master password. The KDFs in use are sound (Argon2id on v2 installs since the June 2026 migration; PBKDF2 at 256k–480k iterations on legacy v1), but no KDF rescues a weak password: the current 8-character minimum allows passwords that fall to a GPU cracking rig regardless of derivation function. Password entropy dominates every other crypto parameter in this system. This costs nothing at runtime, requires no migration, and protects the users least likely to read security documentation.

### Proposed change

On the first-run (database creation) screen only:
- Raise the minimum to 12 characters, and/or
- Suggest a generated passphrase (e.g. four random words) with a one-line explanation that this password is the encryption key for all client data and cannot be recovered if lost.

Existing installs are unaffected (the check only runs at database creation).

---

## Argon2id for Attachment Encryption

**Status:** ✅ DONE (June 2026) — implemented and verified in production.

This was built as the **v2 encryption migration**: attachment / asset / statement-PDF
encryption moved from Fernet (PBKDF2 → AES-128-CBC/HMAC) to **Argon2id → HKDF →
AES-256-GCM**, with the encrypted file format versioned so legacy v1 files stay
readable. Notably, the "explicitly out of scope" note in the original proposal —
keeping the SQLCipher DB on its internal PBKDF2 — was **reversed**: SQLCipher is now
rekeyed to a raw Argon2id-derived key (`PRAGMA key = "x'...'"`) so the whole install
derives from one Argon2id master, with crash-safe migration and rollback. Existing v1
installs migrate automatically at the next login after upgrade.

Full design and rationale: the "Attachment Encryption v2" section of
`Architecture_Decisions.md`; current rollout state (stages 1–5 done, Stage 6 —
removing the v1 Fernet read path — deliberately deferred) in `EdgeCase_Project_Status.md`.

---

## Backup System: External State File

**Priority:** Low  
**Effort:** Medium (2-3 hours)  
**Status:** Documented, not scheduled

### Current State

EdgeCase's backup system uses frequency-first checking (`check_backup_needed()` checks `last_backup_check` timestamp before comparing hashes), which largely avoids the WAL checkpoint false-positive issue. However, the backup state is still stored in the manifest file alongside backup metadata.

MailRepo uses a `refresh_hash_baseline()` function that must be called after every `Database.checkpoint()`. This requires developer discipline - miss a checkpoint site and you get subtle bugs (as happened in MailRepo, February 2026).

See `docs/WAL_Checkpoint_Backup_Issue.md` for full background on the different approaches.

### Proposed Improvement

Adopt Libram's external state file pattern for both EdgeCase and MailRepo, which provides the cleanest architecture.

**Key changes:**

1. Create `data/.backup_state.json` to store:
   ```json
   {
     "last_backup_hash": "sha256...",
     "last_backup_check": "2026-02-16T15:30:00"
   }
   ```

2. Add helper functions in `utils/backup.py`:
   ```python
   def _get_backup_state_file():
       return DATA_DIR / '.backup_state.json'
   
   def _read_backup_state():
       state_file = _get_backup_state_file()
       if state_file.exists():
           with open(state_file, 'r') as f:
               return json.load(f)
       return {'last_backup_hash': None, 'last_backup_check': None}
   
   def _write_backup_state(state):
       with open(_get_backup_state_file(), 'w') as f:
           json.dump(state, f, indent=2)
   ```

3. Modify backup creation to capture hash *after* checkpoint:
   ```python
   # After backup creation and any database writes:
   # (checkpoint happens elsewhere, but timing no longer matters)
   final_hash = get_file_hash(DATA_DIR / 'edgecase.db')
   _write_backup_state({
       'last_backup_hash': final_hash,
       'last_backup_check': datetime.now().isoformat()
   })
   ```

4. Keep frequency-first checking in `check_backup_needed()` (EdgeCase already does this).

5. Remove `last_full_hashes` and `last_backup_check` from the manifest (or keep for backward compatibility during transition).

### Why This Is Better

- **Separation of concerns** - backup state separate from backup metadata
- **No manual coordination required** - no need for `refresh_hash_baseline()` calls
- **Avoids circular modification** - checking database state doesn't modify the database
- **Consistent across projects** - same pattern in EdgeCase, MailRepo, and Libram

### Why We Haven't Done It Yet

EdgeCase is production with real clients. The current frequency-first approach works fine. This is a "nice to have" architectural improvement for consistency across projects, not a bug fix.

### Reference Implementation

See Libram's backup system:
- `/Users/rick/Applications/libram/core/backup.py`
- `/Users/rick/Applications/libram/docs/WAL_Checkpoint_Backup_Handling.md`

---

## CSS Architecture Review

**Priority:** Low  
**Effort:** Low-Medium  
**Status:** Idea only

The December 2025 CSS consolidation reduced duplication by ~25%, but there may be further opportunities:

- Review component-specific CSS files for patterns that could move to base
- Consider CSS custom properties for remaining magic numbers
- Audit for any remaining inline styles in templates

---

## Test Coverage Expansion

**Priority:** Low  
**Effort:** Ongoing  
**Status:** Substantially advanced — suite grew 41 → 201 during the June 2026 refactors.

Current: 201 automated tests across 17 files (was 41). Much of the earlier wishlist is now covered: backup/restore round-trip (`test_backup_*`, plus a `TestBackupRestoreRoundTrip` class), link-group billing scenarios (`test_links_layer.py`, `test_statements_lifecycle.py`), and route/integration coverage for the entries and statements blueprints.

Still-thin areas worth adding if time permits:
- Calendar edge cases (timezone handling, recurring events)
- PDF generation validation (currently smoke-tested for status/content-type only, never byte-asserted by design)

---

*Last updated: June 21, 2026*
