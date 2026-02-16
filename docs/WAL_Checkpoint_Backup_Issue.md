# WAL Checkpoint and Backup Hash Baseline Issue

## Overview

This document describes a subtle but important issue that can cause backup systems to create unnecessary backups when using SQLite in WAL (Write-Ahead Logging) mode. The issue has been encountered and resolved in both EdgeCase Equalizer and MailRepo.

## The Problem

### SQLite WAL Mode Basics

SQLite's WAL mode improves concurrency by writing changes to a separate `-wal` file instead of directly to the main `.db` file. Periodically, these changes are "checkpointed" - merged back into the main database file.

### How This Affects Backups

Our backup systems use file hashes to detect changes:
1. After a backup, we store the SHA-256 hash of each file (including the `.db` file)
2. Before the next backup, we compare current hashes to stored hashes
3. If hashes differ, we know the file changed and needs backing up

The problem occurs in this sequence:
1. User makes changes → changes go to WAL file
2. Hash of `.db` file is recorded as `HASH_A`
3. Later, a WAL checkpoint occurs (merging WAL into `.db`)
4. The `.db` file's hash is now `HASH_B` - different binary content!
5. Backup system sees `HASH_A ≠ HASH_B` → "file changed!"
6. An unnecessary backup is created

**The logical data is identical, but the binary representation changed.**

## Symptoms

- Backups occurring more frequently than expected
- "Incremental" backups being created when no user changes were made
- Backup logs showing activity even during idle periods
- Multiple small backups accumulating with minimal actual changes

## The Solution

### The `refresh_hash_baseline()` Function

```python
def refresh_hash_baseline():
    """
    Update the hash baseline to current file state.
    
    Call this after checkpoint to ensure the baseline reflects
    post-checkpoint state, preventing false "changes" on next backup check.
    """
    manifest = load_manifest()
    if manifest['last_full_hashes']:  # Only if we have a baseline
        manifest['last_full_hashes'] = get_file_hashes()
        save_manifest(manifest)
```

This function recalculates and stores the current file hashes, effectively saying "the current state is the baseline - don't treat it as a change."

### Where to Call It

**Critical Rule:** Call `refresh_hash_baseline()` immediately after any `Database.checkpoint()` call, BEFORE any backup logic runs.

Typical locations that need this fix:

1. **Shutdown/cleanup handlers** - where checkpoint is called before exit
2. **Logout handlers** - where auto-backup runs on session end
3. **Manual backup endpoints** - where user triggers "Backup Now"
4. **Any scheduled backup job** - if it does checkpoint first

### Code Pattern

```python
# WRONG - will cause unnecessary backups
Database.checkpoint()
if backup.check_backup_needed(frequency):
    result = backup.create_backup(location)

# CORRECT - refresh baseline after checkpoint
Database.checkpoint()
backup.refresh_hash_baseline()  # ← Add this line
if backup.check_backup_needed(frequency):
    result = backup.create_backup(location)
```

## Implementation Checklist

When implementing or debugging this issue, check all these locations:

- [ ] `main.py` - shutdown handler / cleanup function
- [ ] Auth blueprint - logout route and auto-backup check
- [ ] Backups blueprint - manual "Backup Now" endpoint
- [ ] Any scheduled/cron backup tasks
- [ ] Any other code that calls `Database.checkpoint()`

### Search Commands

To find all checkpoint calls that might need the fix:
```bash
grep -rn "checkpoint()" --include="*.py" /path/to/project
```

To verify refresh_hash_baseline is being called:
```bash
grep -rn "refresh_hash_baseline" --include="*.py" /path/to/project
```

## Testing

To verify the fix is working:

1. Start the application fresh
2. Make a small change and let it back up
3. Wait for the backup frequency period (or trigger manually)
4. Check if a new backup was created
5. If no changes were made, the backup should report "No changes since last backup"

## History

| Date | Project | Issue | Resolution |
|------|---------|-------|------------|
| Dec 2025 | EdgeCase | Backups on every shutdown | Added refresh_hash_baseline() to main.py cleanup |
| Feb 2026 | MailRepo | Backups more frequent than expected | Added refresh_hash_baseline() to auth.py and backups.py |

## Related Files

### EdgeCase
- `utils/backup.py` - contains `refresh_hash_baseline()`
- `main.py` - shutdown handler

### MailRepo
- `utils/backup.py` - contains `refresh_hash_baseline()`
- `main.py` - shutdown handler
- `web/blueprints/auth.py` - logout and auto-backup
- `web/blueprints/backups.py` - manual backup endpoint

## Key Insight

The fundamental issue is a **mismatch between logical state and binary representation**. SQLite WAL mode is excellent for performance and concurrency, but it means the `.db` file's binary content can change without any logical data changes. Any hash-based change detection must account for this by refreshing its baseline after checkpoint operations.
