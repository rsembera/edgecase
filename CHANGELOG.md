# EdgeCase Equalizer - Changelog

All notable changes after the initial v1.0 release (March 2026) are documented here.

Format: Each entry includes date, version (if applicable), and description.

---

## [Unreleased]

### 2026-06-07 (continued)
- **H3 — Single-guardian billing clarified**: For a minor with only one guardian, `guardian1_pays_percent` was computed but ignored (statements billed the full total). Hid/disabled the "Pays (%)" field in the profile form when there's no second guardian — the percent is only meaningful when there's a G2 to share the bill. Billing logic now matches the displayed intent.
- **H5 — Stop coercing `None` → `''` in entry writes**: `add_entry` previously stored empty strings in INTEGER/REAL columns, breaking range filters, ORDER BY, and `IS NULL` checks (notably the redaction lock's `if statement_id is not None`). Now preserves `None`, and additionally coerces `''` → `None` for the new `TYPED_ENTRY_COLUMNS` set when stray empty strings come in from form posts. Same coercion applied to `update_entry`. Added `tools/audit_typed_columns.py` to find/optionally fix any pre-existing `''` values in typed columns on the real DB.
- **M11 — DB-layer lock enforcement**: `update_entry` now raises `EntryLockedError` if the target entry is locked unless the caller passes `allow_locked=True`. All existing callers updated: user-edit routes already check the lock and log to edit history (now opt in explicitly); `renumber_sessions` opts in as a system invariant; AI Scribe save opts in (edit history for AI Scribe is a known follow-up). Future callers can no longer silently update locked clinical entries.

### 2026-06-07 (later)
- **Ledger reports — silent receipt-dropping fix**: `pdf/ledger_report.py` was resolving `att['filepath']` against the process working directory rather than DATA_ROOT (same root cause as C1/C2). In dev mode CWD happened to equal DATA_ROOT so the bug never surfaced; in desktop/installed mode receipts were silently skipped. Promoted `resolve_attachment_path()` to `core/config.py` as a single source of truth, imported by both `client_export.py` and `ledger_report.py`.

<!-- TODO (CODE_REVIEW.md M2): tools/audit_orphans.py exists to audit
     orphaned rows against the schema's declared FOREIGN KEYs. Enabling
     PRAGMA foreign_keys=ON in core/database.py:connect() is pending review
     of the audit results against the real database. -->

### 2026-06-07
- **Code review remediation batch** (first pass from CODE_REVIEW.md; one commit per item):
  - **C1+C2 — PDF export attachments fixed**: Client-file exports were silently dropping every attachment — paths were rebuilt from the original filename instead of the stored UUID `.enc` path, and images were embedded without decryption. Exports now resolve `attachments.filepath` against the data root and decrypt before embedding; merged PDF attachments show their original filename on the header page.
  - **H1 — Restore safety**: `complete_restore()` now removes stale `edgecase.db-wal`/`-shm` sidecar files before copying the restored database, preventing SQLite from replaying old WAL frames into the restored file after a crash.
  - **M2 — FK orphan audit (audit only)**: Added `tools/audit_orphans.py`, a read-only script reporting rows that violate the schema's declared (but unenforced) FOREIGN KEYs, plus a `PRAGMA foreign_key_check` cross-check. The `foreign_keys=ON` flip is deliberately deferred pending audit results (see TODO above).
  - **M3 — Indexes**: Added `entries(client_id, class)`, `entries(ledger_type, ledger_date)`, `attachments(entry_id)`, and `statement_portions(client_id, status)` via `CREATE INDEX IF NOT EXISTS` in schema init — existing databases migrate automatically at startup.
  - **M12 — Atomic writes**: `encrypt_file()` and `save_manifest()` now write to a temp file and `os.replace()` instead of truncating in place; a crash mid-write can no longer destroy an attachment or corrupt the backup manifest.
  - **M14 — PDF crash on special characters fixed**: User-entered text (names, addresses, descriptions, payment instructions, attestation, attachment descriptions) is now XML-escaped before interpolation into ReportLab Paragraph markup. Previously a single `&`, `<`, or `>` in any field crashed statement/export/report generation.
  - **L10 — Shared JS utilities**: New `web/static/js/shared_utils.js` (loaded in `base.html`) consolidates `escapeHtml` (4 copies), textarea auto-resize (6 copies), the three-way fee calculation (6 copies), and the color palette; deleted dead `color_palette.js`. Page-level function names kept as thin delegates, so no template/handler changes.
  - All 43 automated tests pass; PDF fixes verified end-to-end against a test database (encrypted image + PDF attachments render in exports; statements/exports/reports generate with `&`, `<`, `>` in every user field).

### 2026-05-16
- **AI Scribe**: Refined Cancel button presentation. Removed the inline "Generating..." status indicator (which was causing column-width reflow) and replaced it with a dedicated Cancel button styled to match the action buttons, placed below them in the same column. Uses `visibility: hidden` to reserve layout space so action buttons no longer jump when Cancel appears or disappears.
- **AI Scribe**: Converted the "Loading AI model..." banner from an inline element to a centered modal overlay with dimmed backdrop. Previously the banner pushed page content down when shown and let it snap back when hidden; the overlay is now `position: fixed` so it never affects layout. The overlay also better reflects the actual user state — the page is unusable until the model loads.

### 2026-05-15
- **AI Scribe**: Added Cancel button to abort in-flight generation. Uses `AbortController` to terminate the SSE stream cleanly, releasing the model so a new action can be started immediately. Previously, hitting the bottom "Cancel" link navigated away but left the generation running on the backend, causing subsequent requests to hang waiting for the model lock.
- **AI Scribe**: Fixed pre-existing bug where the "Generating..." status indicator never appeared. The JS was using `classList.remove('hidden')` to show the status div, but the div was hidden via inline `style="display: none;"` and no `.hidden` CSS class exists. Switched to direct inline style manipulation.
- **AI Scribe**: Renamed bottom "Cancel" link to "Back" with standard styling (left-arrow icon, plain `.btn` class) to match the Back button convention used throughout the rest of the app.

### 2026-04-10
- **Security**: Added `Cache-Control: no-store` headers to attachment viewing and download endpoints. Prevents browsers from caching decrypted attachment content to disk. Decrypted attachments now exist only in memory during viewing/download.

### 2026-04-01
- **Scheduler**: Fixed natural language date parsing to prioritize explicit dates over day-of-week names. Previously, "Thursday April 9" would be interpreted as "next Thursday" (ignoring the explicit date). Now explicit month+day patterns are checked first, with day-of-week as a fallback.

### 2026-03-28
- **Scheduler**: Fixed AppleScript calendar integration failing when Calendar.app is not already running. The AppleScript now explicitly launches Calendar before attempting to create events, preventing the "Application isn't running" (-600) error.

### 2026-03-23
- **AI Scribe**: Updated system prompt to preserve clinician's language choices including profanity, slang, and colloquialisms. Previously, the model would sometimes substitute euphemisms (e.g., changing "shit" to "defecate") when proofreading notes that reflected client language. The prompt now explicitly instructs the model to respect the therapist's clinical judgment about what language to include.

---

## [1.0.0] - 2026-03-11
Initial public release.
