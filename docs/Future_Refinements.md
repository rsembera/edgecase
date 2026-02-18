# Future Refinements

This document tracks architectural improvements and refactoring ideas that aren't urgent but would be worth doing if time permits or during a major version update.

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
**Status:** Idea only

Current: 41 automated tests covering core functionality.

Potential additions:
- Backup/restore cycle tests
- Calendar edge cases (timezone handling, recurring events)
- PDF generation validation
- Link group billing scenarios

---

*Last updated: February 2026*
