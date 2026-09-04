# Master-Key Rotation — Implementation Plan

**Status:** PLANNED 2026-09-03, deliberately NOT BUILT. Design settled; build
when a trigger appears. See "When to build this" before starting.

Reference implementation: MailRepo `core/master_rotation.py`,
`tests/test_master_rotation.py`, and the helpers in `core/password_change.py`
(`_rekey_file`, `_rekey_credentials`, `_iter_archive_files`,
`_atomic_write_file`, the interruption-marker functions). Read those first.
**Do not port it verbatim** — the two apps have opposite recovery
philosophies and different database-rekey strategies, both deliberately. The
differences are itemized below.

## The gap this closes

A password change or a recovery-key regeneration replaces a *wrapper*. The
master key underneath is untouched — which is why `_change_password_v3` is an
instant ~190-byte rewrap, and also why neither operation revokes anything
against someone holding a copy of the ciphertext.

Concretely: an old `.keyinfo` (from a backup zip, a synced cloud folder, a
stolen laptop) plus the old password derives the same master, and that master
still decrypts today's attachments and today's database. The same is true of
an old printed recovery key. **EdgeCase's two revocation features do not
revoke against an attacker who already has a copy of the data.**

Rotation is the only remedy: mint a fresh master, re-encrypt every attachment,
rebuild the database under a new key, and write a new key file. Afterwards
every earlier key file, password and recovery key opens nothing current.

## When to build this

Not on general principle. Build it when one of these appears:

- A lost or stolen machine, or a suspected compromise.
- A real password disclosure (shoulder-surfed, reused, phished).
- A security review conducted for a wider user base than one practitioner.

Rationale for waiting, recorded 2026-09-03: EdgeCase stores no live
credentials, so a compromise yields a *snapshot* of records as of the
attacker's copy — bounded, and not much improved by rotating afterwards, since
they already hold that snapshot. The scenario rotation genuinely helps is
narrow: someone holds an old backup *and* the password, has not used it yet,
and you rotate first.

**Do the documentation instead, now.** The limitation should be stated plainly
in the security docs and on the change-password screen: changing your password
protects against future disclosure; it does not lock out anyone who already
has both an old backup and your old password. VeraCrypt and Cryptomator both
document exactly this rather than implementing rotation. Bitwarden does
implement it ("rotate account encryption key"). One hour of work, and it makes
the app honest about what it does today.

## Where it runs — at login, not live

**Decision: perform rotation at login, before `Database` is constructed** —
the same slot as `migrate()` and `recover_if_interrupted()`.

Settings gets a "Rotate master key" action that *arms* it (writes a
`.rotate_pending` flag). The next launch performs it behind the progress
screen, then completes the login.

Why not live, from Settings, the way MailRepo does it: `core/database.py`
hands out **thread-local** connections created with sqlite3's default
`check_same_thread=True`. The rotation thread cannot close another thread's
connection — it cannot touch it. And because the database is *swapped*
(see below) rather than rekeyed in place, any connection still open across the
swap holds a descriptor to the old inode: its writes land in a deleted file
and vanish silently. That is the worst failure shape available here.

Making live rotation safe would need a connection registry or epoch counter
checked by every caller, a lock every database operation respects, and a rule
for the AI Scribe holding a connection mid-request. That is new concurrency
machinery in the one place where a mistake costs clinical records. The
login-time slot needs none of it and reuses a path already proven on real
data. Cost: rotation is not immediate — arm it, restart.

## Recovery philosophy — forward, not back

**This is the sharpest difference from MailRepo and needs care.**

- MailRepo rolls **forward**: interruption marker, resumable walk, re-run and
  already-converted files are skipped.
- EdgeCase rolls **back**: `migrate()` writes a marker naming a backup, and any
  exception triggers `_rollback()`, restoring that backup wholesale.
  `recover_if_interrupted()` runs at startup, needs no password, and its entire
  job is to undo.

**Decision: rotation rolls forward.** The gate accepts a backup up to 24 hours
old, so rolling back could discard a day of clinical notes to fix a key
problem.

Therefore `recover_if_interrupted()` **must learn to recognise
`kind="rotate_master"` and leave it alone** — deliberately, with a test —
rather than falling through to `_rollback()`. Without that, EdgeCase ends up
with two markers whose `kind` fields mean opposite things and a startup routine
that undoes a rotation halfway through. This is the single highest-risk
integration point in the whole change.

## Database rekey — export and verify, not `PRAGMA rekey`

MailRepo rekeys the live database in place. EdgeCase never has:
`_build_rekeyed_db_v2` goes through `_export_verify`, which builds a **new**
database file, runs `integrity_check` and row-count parity against the
original, and only then swaps. The original is untouched until it passes.

**Decision: keep EdgeCase's export-and-verify.** Giving up verification on the
one operation that rewrites every page of a database holding client records is
not a trade worth making. Cost: temporarily double disk for the database, and
a slower rekey.

## No credential step

MailRepo's `_rekey_credentials` exists because it stores IMAP passwords in
`accounts.credentials_encrypted`, encrypted under the file key. **EdgeCase has
no equivalent.** `v2.encrypt_bytes` appears in exactly two places: attachment
files, and the key wrappers in `encryption_v3.py`. Everything else sensitive is
inside SQLCipher and covered by the database rekey.

Do not write an empty `_rekey_credentials`. Omit the step; note the omission in
the module docstring so the next person comparing the two apps knows it was
considered.

## The file walk

**Reuse `_candidate_files()` from `core/migrate_crypto.py` unchanged.** It
takes every non-dotfile under `attachments/`, plus `logo` and `signature` from
`assets/`. That breadth is deliberate — the docstring notes it is the exact set
the backup covers.

**Do not filter by extension.** MailRepo's `_iter_archive_files()` filters on
`*.eml.enc`; the equivalent here would silently skip the readable-named
`Statement_*.pdf` files (see `Attachment_Filename_Fix_Plan.md`), and in a
rotation *skipped means stranded under a master key that no longer exists*.
Unrecoverable except from backup. **Write a test that plants a file with an
unexpected extension and asserts it gets rekeyed** — that is the assumption a
future refactor is most likely to break.

Dotfile skipping is what keeps macOS `.DS_Store` droppings from tripping the
corruption path. Keep it.

New helper needed: a rotation variant of `_reencrypt_file_v2` with the
**try-old-then-new** fallback. The existing one has no fallback — it decrypts
with the old key or raises — so it is not resumable in the sense rotation
needs. Semantics: old key succeeds → rekey and return `rekeyed`; old fails but
new succeeds → already converted, return `skipped`; both fail → corruption
error naming the path.

## Sequence

1. Refuse unless `install_crypto_version() == 3`. Rotation needs the v3
   envelope; a v2 install upgrades first.
2. Verify the current password (`v3.unwrap_with_password`).
3. **Backup gate.** 24 hours, built from `get_restore_points()` +
   `verify_backup()` + `created_at` age. If stale, take a full backup
   automatically (`create_full_backup`) and report it through the progress
   stream as its own phase — this can be slow and must not look like a hang.
4. **Rotation state.** `.master_rotation_state` = the new master encrypted
   under the **old** file key, written *before* the walk. On a re-run, load it
   and resume with the same new master rather than minting a second one and
   stranding the files converted by the first attempt.
5. Walk `_candidate_files()`, rekeying old → new. Progress callback per file.
6. Build the new database via `_export_verify` and verify it. Original still
   untouched at this point.
7. Set `.rk_pending` **before** the commit point (same reasoning as
   `migrate_to_v3`: no window where the install is rotated with no record that
   a recovery key is outstanding).
8. Write the marker (`kind="rotate_master"`), then the irreversible window:
   swap the verified database in, clear stale WAL, write the new `.keyinfo`
   (`v3.build_keyinfo(new_master, password, new_recovery_key)`).
   `.keyinfo` is the commit point.
9. Clear the rotation state, clear the marker, **`v2._key_cache.clear()`**.
   The cache clear is load-bearing, not hygiene — see the note in
   `_change_password_v3`.
10. Hand the new recovery key to the display screen.

## Recovery key display — peek, do not consume

MailRepo's done page pops the result on read, so a refresh loses the key.
**Do not port that.** `_peek_recovery_handoff` in `web/blueprints/auth.py`
reads *without* consuming, and its comment says why: the user is transcribing
a key by hand and a refresh or mistyped confirmation must not destroy the only
copy. Dropped on explicit acknowledgement, 30-minute TTL.

Reuse the existing handoff and the existing `auth.recovery_key` screen. Two
adjacent screens behaving oppositely for the same user, the same task and the
same kind of secret is the inconsistency worth avoiding.

## Progress reporting

Reuse the shape of `upgrading.html`: explanatory card, Begin button,
`EventSource`, working/complete/error.

For *real* progress rather than a spinner, port MailRepo's worker-thread +
`queue.Queue` pattern: work runs on a thread with `progress_cb=q.put`, the SSE
generator drains the queue. `migrate_stream` currently calls
`migrate_to_v3()` synchronously inside the generator, so it emits one message
and blocks — a generator cannot yield from inside a blocking call. That is why
the upgrade screen has no bar even though `migrate()` already calls
`progress_cb(i + 1, len(files))`.

Phases: `backing_up` → `counting` → `encrypting` (current/total, real bar) →
`database` → `finalizing` → `complete`.

**Honest limit:** the database phase has no granularity. `_export_verify` is
one `sqlcipher_export` plus `integrity_check` and row-count parity — nothing to
hang a percentage on. Label it plainly ("Verifying the database…") rather than
animating something fake.

**Follow-up, separate commit:** the same plumbing would give the v1→v3 upgrade
a real bar too, since its `progress_cb` is already being called. One extra call
site. Do not bundle it.

## Tests

Port and adapt MailRepo's, plus EdgeCase-specific ones:

- Before rotation, old key file + old password derives the live master and
  decrypts a live attachment — *the gap is real*.
- After rotation: live install still opens with the same password; every
  attachment decrypts; new recovery key works.
- After rotation: old key file + old password derives a master that decrypts
  **nothing** current, and the old recovery key is refused.
- Password can be changed in the same operation.
- Wrong password → refused, `.keyinfo` untouched, no state file left behind.
- Stale backup → refused, `.keyinfo` untouched.
- **Interrupted rotation resumes**: crash mid-window, assert marker and state
  both exist and `.keyinfo` is unchanged, then re-run and assert everything
  decrypts and both files are gone.
- **`recover_if_interrupted()` does NOT roll back a `rotate_master` marker.**
  The highest-value test in the set.
- A file with an unexpected extension is rekeyed, not skipped.
- `.DS_Store` and other dotfiles are ignored without raising.
- Database rekey is verified before the swap (corrupt the export, assert the
  original survives).

## Non-goals

- Live rotation from Settings while the app is running (see above).
- Rotating anything in `models/` — the Gemma weights are not encrypted and
  contain no practice data.
- **Retroactive protection of existing backups.** Rotation makes old key
  material useless against *current* data. A pre-rotation backup remains a
  complete, self-consistent snapshot that still opens with the old password —
  by design, since backups carry their own `.keyinfo`. Anyone wanting old
  backups gone must delete them. State this plainly in the UI: rotation is not
  a substitute for backup hygiene.
