# Attachment Filenames — Privacy Fix Plan

**Status:** PLANNED 2026-09-03. Not started. Do this before the master-key
rotation work — it is smaller, it addresses a live disclosure rather than a
hardening measure, and doing it first means the rotation walk runs once over
correctly-named files.

## The defect

Two code paths write into `ATTACHMENTS_DIR`. Only one anonymizes the on-disk
filename.

- `web/utils.py:436` — **correct.** User uploads get
  `stored_filename = f"{uuid.uuid4()}.enc"`, with the original name kept in
  `attachments.filename` for display. The comment there states the rule:
  "Use UUID for stored filename (privacy: no client info in filesystem)".
- `web/blueprints/statements/delivery.py:165, 208-217` — **defective.**
  Generated statement PDFs are written as
  `Statement_{portion['file_number']}_{date}.pdf` into
  `attachments/<client_id>/<comm_entry_id>/`, encrypted in place, and that
  same readable name is stored as both `attachments.filename` and
  `attachments.filepath`.

Also confirm `web/blueprints/ledger.py:269, 451` (ledger receipt uploads).
These route through `web/utils.py` and are believed correct — verify rather
than assume.

## What is and is not exposed

File **contents are encrypted** and were never at risk: every affected file
begins with `0x02`, the v2 AES-GCM format byte. Verified 2026-09-03.

What leaks is the **filename**. With Rick's `YYYYMMDD-II` file-number scheme,
`Statement_20251102-KL_20260302.pdf` discloses initials, intake date and a
billing month. A directory listing therefore yields caseload size, per-client
initials, intake dates and billing history without decrypting anything.

**The scheme is user-chosen, and that is what matters for other
practitioners.** `delivery.py` interpolates `file_number` verbatim. Nothing in
EdgeCase stops someone using client surnames as file numbers, in which case
their backups leak full names. Rick's own exposure sits at the mild end of
that range.

**Backups carry it.** `create_full_backup` writes a plain
`zipfile.ZipFile(..., ZIP_DEFLATED)` with no password (flag bits verified
`0x0`). Contents inside are ciphertext, but a zip's central directory stores
entry names in the clear, so `unzip -l` on a cloud-synced backup prints the
listing. This is not a backup-system bug — the unencrypted container is what
lets `verify_backup` and the disaster-recovery path read a manifest without a
password. Fix the filenames and the container's transparency stops mattering.

## Current state of the live install (2026-09-03)

- `attachments/`: 80 files, 11 MB — 59 UUID `.enc` (correct), 17 readable
  `.pdf` (defective), 4 `.DS_Store`.
- Of the 17: **16 are `Statement_*` from the live `delivery.py` path**, newest
  2026-09-01. Two — `attachments/2/6/2025-12-KL.pdf` and
  `attachments/ledger/7/2025-12-KL.pdf` — are on entry IDs 6 and 7 and are
  genuinely pre-UUID uploads.
- 5 backups in `backups/`; the 2026-08-09 full contains 14 readable names.

## The fix

1. **`delivery.py`:** store under `f"{uuid.uuid4()}.enc"`, exactly as
   `web/utils.py` does. Keep `pdf_filename` as the display name in
   `attachments.filename` and as `send_file`'s `download_name`. Only
   `filepath` changes.
2. **One-time rename pass** for existing files: rename on disk and
   `UPDATE attachments SET filepath = ?` in the **same transaction**. Must be
   idempotent (skip anything already UUID-named) and must not touch files with
   no matching `attachments` row — log those instead of guessing.
3. **Pin the invariant with a test covering both paths.** The rule currently
   exists only as a comment in `web/utils.py`, which is why a second writer
   could violate it silently. Assert that no file under `ATTACHMENTS_DIR` has
   a name derived from client data, after exercising *both* the upload path
   and the statement-delivery path. Write it red-first against current
   `delivery.py`.

## Known limits — do not over-scope

- **Existing backups keep the old listing.** Not rewritable. Take a fresh full
  backup after the rename, then decide whether to delete the five older ones
  (retention will otherwise age them out). Rick's call; it costs restore depth.
- **`attachments/<client_id>/<entry_id>/` still leaks caseload size.** Much
  weaker signal, much larger change. Out of scope unless Rick asks.

## Disclosure

CHANGELOG and the 2.0.2 release notes. Plain and accurate, not an advisory
with a scary header: generated statement PDFs were stored under filenames
containing the client file number; contents were never exposed; upgrading
renames them. Note that practitioners whose file numbers contain names should
check their cloud-synced backups.

## Root cause, for the record

Same shape as the `ledger_date` defect fixed earlier the same day: a correct
decision made in one place, never propagated to a second writer, with no test
pinning the invariant. The remedy in both cases is the test, not the fix.
