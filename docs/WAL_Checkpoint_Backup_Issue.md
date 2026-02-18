# WAL Checkpoint and Backup Hash Baseline Issue

## Overview

This document describes a subtle issue that can cause backup systems to create unnecessary backups when using SQLite in WAL (Write-Ahead Logging) mode. Different projects handle this differently.

## The Problem

### SQLite WAL Mode Basics

SQLite's WAL mode improves concurrency by writing changes to a separate `-wal` file instead of directly to the main `.db` file. Periodically, these changes are "checkpointed" - merged back into the main database file.

### How This Affects Backups

Backup systems that use file hashes to detect changes can be fooled:
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

## Solutions by Project

### EdgeCase Approach: Frequency-First Checking

EdgeCase avoids this issue through its backup flow design:

1. `check_backup_needed(frequency)` checks the `last_backup_check` timestamp first
2. If a backup isn't due based on frequency settings, hash comparison never happens
3. After any backup attempt (successful or "no changes"), `record_backup_check()` updates the timestamp
4. The next check sees "already checked today" and skips entirely

This means WAL checkpoint timing doesn't matter - if we already checked/backed up today, we won't check again regardless of hash changes.

**Key function:** `record_backup_check()` in `utils/backup.py`

### MailRepo Approach: Hash Baseline Refresh

MailRepo uses an explicit `refresh_hash_baseline()` function that must be called after every `checkpoint()`:

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

This requires discipline - every `checkpoint()` call site needs a corresponding `refresh_hash_baseline()` call.

### Libram Approach: External State File (Best)

Libram stores backup state in an external JSON file (`data/.backup_state.json`) rather than in the manifest. This:
- Avoids circular modification (checking state doesn't change state)
- Checks frequency before comparing hashes
- Captures final hash after checkpoint automatically

See `/Users/rick/Applications/libram/docs/WAL_Checkpoint_Backup_Handling.md` for details.

## Comparison

| Aspect | EdgeCase | MailRepo | Libram |
|--------|----------|----------|--------|
| WAL protection | Frequency-first check | Manual refresh calls | External state file |
| Manual coordination | None needed | Required at each checkpoint | None needed |
| Failure mode | None (frequency check protects) | Missed refresh → extra backups | None |
| Complexity | Low | Medium (discipline required) | Low |

## History

| Date | Project | Issue | Resolution |
|------|---------|-------|------------|
| Feb 2026 | MailRepo | Backups more frequent than expected | Added `refresh_hash_baseline()` to auth.py and backups.py |
| Feb 2026 | EdgeCase | (No issue) | Frequency-first design prevents the problem |

## Key Insight

The fundamental issue is a **mismatch between logical state and binary representation**. SQLite WAL mode is excellent for performance and concurrency, but it means the `.db` file's binary content can change without any logical data changes.

Different solutions:
- **Refresh baseline after checkpoint** (MailRepo) - requires discipline
- **Check frequency before hashes** (EdgeCase) - avoids the comparison entirely
- **External state file** (Libram) - cleanest architecture, no coordination needed
