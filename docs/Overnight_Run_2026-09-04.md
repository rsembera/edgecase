# Overnight Run — 2026-09-04

Scheduled run implementing `Attachment_Filename_Fix_Plan.md` and
`Master_Rotation_Plan.md`. Branch: `filename-fix-and-master-rotation`
(eight commits on top of `8b67d82`, main untouched, nothing pushed).
Suite: **676 passing before → 739 passing after**, ruff clean, at every
commit. Nothing was run against the live install; the fictional test
install was exercised through a copy — with one mishap, corrected and
described below under "What went wrong".

## Read this first

1. **One incident to know about.** The first integration run against a
   copy of `edgecase-testing` renamed six files *inside the original
   fixture* and overwrote the `manifest.json` sidecar in your iCloud
   "EdgeCase Backups" folder. Both were restored the same hour and
   verified; the causes became a code fix and a test. Details under
   "What went wrong" — please read that section even if nothing else.
2. **Highest-risk diffs**, in order: `core/migrate_crypto.py`
   (`recover_if_interrupted` guard, 9 lines), `core/master_rotation.py`
   (`_commit_rotation` and the swap window around step 8), and the
   `_route_into_rotation` branch in `web/blueprints/auth.py` (login
   verifies against the key file, not the database, when a rotation is
   pending). Then `core/attachment_names.py`, which is the only code that
   will actually touch your real files at next login.
3. **Two decisions went beyond the plans** and are easy to drop if you
   disagree: the rename pass heals absolute paths from a previous install
   location (commit `b21f627`), and `rotate_master` runs a read-only
   preflight before writing its state file (in `e1d6152`).

## Plan 1 — attachment filenames

**Fix** (`0c40d6b`): `delivery.py` now stores generated statements as
`<uuid>.enc`, exactly as `web/utils.py` does; `pdf_filename` stays the
display name and `send_file` download name. Ledger receipt uploads were
verified to route through `save_uploaded_files` (lines 185/232/331/393);
`ledger.py:269, 451` are the delete paths, not writers.

**Invariant test** (`tests/test_attachment_filename_privacy.py`, red
first — both delivery tests failed with
`Statement_20251102-KL_20260904.pdf` before the fix): drives the upload
route and the mark-sent route, then asserts every file under
`ATTACHMENTS_DIR` is `<uuid>.enc` and contains none of the file number,
initials, surname, "Statement" or "Intake". Also pins the display name and
that download still uses it.

**Rename pass** (`81ff8f0`, `b21f627`): `core/attachment_names.py`.
UPDATE (uncommitted) → `os.rename` → COMMIT; a failed commit moves the
file back. Idempotent (UUID-named rows cost one SELECT). Files with no row
and rows with no file are reported, never guessed. Dotfiles ignored. Wired
through `auth._post_open_maintenance(db)`, called from every path that
completes a login with an open database (plain login, the upgrade stream,
the rotation stream); never raises. Runs every login rather than tracking
a "done" flag — the second pass on the test copy took 0.8 s for 47 rows.

Against a copy of `edgecase-testing` (47 rows, 30 files): 26 renamed, 4
already anonymized, 8 relocated (see below), 17 "missing" — all of those
are client 1's attachments, whose folder is absent from the fixture
itself, or rows pointing at `/Users/rick/apps/…` paths whose files do not
exist anywhere. 0 orphans, 0 failures. Every remaining row decrypts through
`decrypt_file_to_bytes` after the pass. Display names unchanged.

### Beyond the plan (Plan 1)

- **Relocation of absolute paths.** The old writer stored *absolute*
  paths. The fixture has rows pointing at `/Users/rick/apps/edgecase-testing/…`
  and `/Users/rick/Applications/edgecase-testing/…` — i.e. every generated
  statement became "Attachment file is missing from disk" the moment the
  install moved, and would again after a restore onto another machine.
  When the same `attachments/<client>/<entry>/<name>` tail exists under
  the current tree, the pass now adopts it (exact tail match only) and
  stores the path relative to `DATA_ROOT` from then on. Your live rows
  were written in place so they will simply rename; this matters for
  restores. `delivery.py` now stores relative paths too (absolute fallback
  only when tests redirect `ATTACHMENTS_DIR` outside `DATA_ROOT`).
- **Never leave the tree.** The pass refuses to rename any file outside
  this install's `attachments/` folder however a row points at it
  (`outside_tree` in the summary). This is the incident fix.

## Plan 2 — master-key rotation

**Core** (`e1d6152`): `core/master_rotation.py`, `rotate_master(password,
new_password=None, root=None, backup_fn=None, progress_cb=None)`. Every
settled decision as written: login-time only; roll-forward with
`.master_rotation_state` (new master under the OLD file key, plus a
verification token for the new file key and the covering backup); export-
and-verify DB rekey via `_build_rekeyed_db_v2`; no credential step (module
docstring says why); `_candidate_files()` reused unfiltered; try-old-then-
new per-file rekey that raises `RotationCorruptionError` naming the path
on neither; backup gate = newest complete restore point ≤ 24 h verified
with `verify_backup()` (zip-level, no password before login), else a full
backup first, reported as its own `backing_up` phase; `.rk_pending` before
the marker before the commit; `.keyinfo` is the commit point;
`v2._key_cache.clear()` after. Marker `kind="rotate_master"`.

**Guard** (`d23a716`): `recover_if_interrupted()` returns
`"rotation_pending"` for a `rotate_master` marker and touches nothing.
`tests/test_rotation_recovery_guard.py` snapshots every file, spies on
`_rollback`, and asserts byte-identity plus that the rotation still
completes.

**UI** (`47d8e6b`): Settings › Security › "Rotate Master Key" (password
required) arms `.rotate_pending`; Settings shows armed/in-progress state
with Cancel (refused once a run has started). Login: `_route_into_rotation`
runs before `Database` is constructed, verifies the password against the
key file, and renders `rotating.html` (resume wording when interrupted).
`/rotate/stream`: worker thread + `queue.Queue`, real per-file bar,
`"Verifying the database…"` labelled plainly, worker's own `complete`
swallowed until the rotated DB is open and the key is parked in the
existing peek-not-consume handoff → existing `auth.recovery_key` screen.
`auth.rotate_stream` added to `require_login`'s allow-list.

**Tests** (42): the gap before; closed after (old key file + old password
decrypts nothing, old recovery key refused); password change in the same
operation; cache clear; wrong password / non-v3 / stale-and-unbackupable
refusals leave `.keyinfo` untouched with no state; stale backup → fresh
one taken and reported; fresh backup not retaken; corrupt zip does not
satisfy the gate; unexpected extension rekeyed; `assets/logo.png` covered;
`.DS_Store` ignored; corrupt file refuses before anything is written;
resume from every crash window (mid-walk with the same master; after the
DB swap but before the key file; after the key file but before cleanup →
finalize, no second rotation); DB verification before swap (stubbed and
real `_export_verify` with a tampered page); progress phases in order with
a real bar and no key in the stream; three end-to-end logins through the
real routes against a synthetic install pointed at by the live code paths.

Against the test copy (real Argon2id parameters, 31 candidate files, 9
clients, 146 entries): arm → rotate with `_commit_rotation` forced to
crash (backup taken because the fixture's newest was 36 h old; marker and
state present, `.keyinfo` unchanged, `.rk_pending` set) →
`recover_if_interrupted()` returned `rotation_pending` and changed zero
bytes → re-run resumed with `files_rekeyed=0`, `files_total=31`, wrote the
key file → all 31 files decrypt under the new master and none under the
old; DB opens with the new key only; row counts identical through
`Database()`; new recovery key verifies; no residue files. Each half took
~2 s.

### Beyond the plan (Plan 2)

- **Read-only preflight** (`checking` phase, between `counting` and
  `encrypting`). Every candidate is decrypted once under old-or-new and
  the database probed under old-or-new *before* the state file is
  written. Reason: rotation runs at login and rolls forward, so a file
  that opens under neither key would otherwise strand the user at the
  rotation screen with a state file that forbids cancelling. With the
  preflight the refusal names the path, nothing is written, and Settings
  can still cancel. Cost: one extra decrypt pass (AES-GCM, ~2 s for the
  fixture's 11 MB).
- **Stale backup: take one, or refuse?** The plan's sequence says "take a
  full backup automatically"; its test list says "stale backup → refused".
  Built as: take one; refuse only if that fails. The test for the refusal
  passes a `backup_fn` that raises.
- **Resumed runs skip the gate** and reuse the backup their state records.
  A fresh backup mid-rotation could snapshot a half-rotated install (in the
  DB-swapped window it would be unrestorable with its own key file).
- **Committed-but-uncleaned re-run** regenerates a recovery key (the dead
  run's never reached the user) rather than rotating again.
- **Non-v2 blobs** (plaintext, Fernet) under `attachments/` are treated as
  the plan's "neither key" case and refuse the rotation by name, not
  skipped. Your live tree has none (plan 1 verified every file is `0x02`).
- `disarm_rotation()` is refused while a run is in progress; `rotation_pending()`
  is flag ∨ state ∨ marker, so a lost flag cannot orphan a started run.

## What went wrong

The first integration run used `EDGECASE_DATA=/tmp/ec-rotation-test`, a
copy of `edgecase-testing`, and two things reached outside it:

1. **The rename pass followed absolute paths.** Eight fixture rows point
   at `/Users/rick/Applications/edgecase-testing/attachments/…` — the
   fixture's *real* location. Six of those files existed there, so the
   pass renamed them in the original fixture (the copy's database was
   updated; the original's was not). Restored by hand from the initial
   listing I had taken — `mv` back to the exact names, content untouched
   (rename only; mtimes preserved), 30 files verified name-for-name
   against the pre-run listing. The fixture's own `edgecase.db`, `.keyinfo`
   and `state/` were never touched.
   → Fix: `_under()` check; the pass never renames outside
   `ATTACHMENTS_DIR`. Test: `test_never_renames_a_file_outside_this_installs_tree`.
2. **`save_manifest` sidecars follow `backup_dir`.** The copy's manifest
   carried the original entries' absolute `backup_dir`s, including your
   iCloud "EdgeCase Backups" folder (the live install's destination, 345
   entries). The rotation's automatic full backup appended one entry and
   wrote that 101-entry *test* manifest over the live sidecar there, and
   over the fixture's own `backups/manifest.json`.
   → Restored the iCloud sidecar by copying the live install's canonical
   `backups/manifest.json` (an index of filenames, hashes and sizes — no
   clinical content; the only file I read under the live `backups/`, and
   only to undo my own damage; byte-identical to what `save_manifest`
   writes there). Restored the fixture manifest by dropping the `/tmp`
   entry, resetting `current_chain_id` to `20260902_171723`, and
   recomputing `last_full_hashes` from the 2026-09-02 full zip (36 files,
   matching the recorded `file_count`).
   → Second and third runs neutralised the copy's manifest (every
   `backup_dir` rewritten to the copy) and ran under a tripwire that
   stat-snapshots the whole fixture plus the iCloud manifest before and
   after: **clean**.

Your live install's next backup will rewrite the iCloud sidecar anyway;
until then it is the 2026-09-03 21:23 state, which is what it was.

Please spot-check: `ls /Users/rick/Applications/edgecase-testing/attachments/2/117`
should show `Statement_20251209-BB_20260309.pdf`; the iCloud
`manifest.json` should be 141,318 bytes with 345 entries.

## Other observations (not acted on)

- `ledger.py:682` writes `Payment_Record_<file_number>_…pdf` unencrypted
  into the shared system temp dir under a predictable name and never
  deletes it — the same shape delivery.py fixed with `_private_pdf_dir()`.
  Out of scope tonight; worth a look.
- `verify_backup()` deletes a zip that fails CRC. The gate calls it as the
  plan says; a corrupt backup in the last 24 h would be removed by the
  gate, which is its existing contract but worth knowing.
- The 2.0.2 release notes and version bump are not done (`pyproject.toml`
  still `2.0.1`).
- The follow-up the plan names — giving the v1→v3 upgrade a real bar with
  the same plumbing — is untouched, as instructed.

## Commits

```
40186f3 CHANGELOG: statement filename disclosure and master-key rotation
b21f627 Rename pass: never leave the install's tree; heal absolute paths that moved
47d8e6b Master-key rotation UI: arm from Settings, run at login with real progress
d23a716 recover_if_interrupted: leave a rotate_master marker alone
e1d6152 Master-key rotation core: core/master_rotation.py
81ff8f0 Attachments: one-time rename pass for readable filenames, run at login
0c40d6b Statement PDFs: store under a UUID, not the client file number
```

plus this document and the Route_Reference / plan-status edits.

## Files

New: `core/master_rotation.py`, `core/attachment_names.py`,
`web/templates/rotating.html`, `web/templates/rotate_master_key.html`,
`tests/test_master_rotation.py`, `tests/test_rotation_recovery_guard.py`,
`tests/test_rotation_routes.py`, `tests/test_attachment_rename_pass.py`,
`tests/test_attachment_filename_privacy.py`.
Modified: `core/migrate_crypto.py`, `web/blueprints/auth.py`,
`web/blueprints/settings.py`, `web/blueprints/statements/delivery.py`,
`web/app.py`, `web/templates/settings.html`, `CHANGELOG.md`,
`docs/Route_Reference.md`, both plan docs (status line).
