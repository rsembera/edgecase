# EdgeCase Equalizer - Project Status

**Owner:** Richard  
**Development Partner:** Claude  
**Last Updated:** June 20, 2026  
**Status:** ALL PHASES COMPLETE ✅ - In Production Use Since January 3, 2026

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists, built using AI-assisted development. The system uses an entry-based architecture where all client records are stored as unified entries in SQLite with SQLCipher encryption.

**Philosophy:** Every practice is an edge case - this software is built specifically for solo practitioners who need complete control, flexibility, and data ownership.

---

## CURRENT WORK IN PROGRESS

### Attachment Encryption v2 (Argon2id / AES-256-GCM) — started June 14, 2026

A post-launch security enhancement (does **not** change the "all phases complete
/ in production" status): migrating attachment, asset, and statement-PDF
encryption from Fernet to Argon2id → HKDF → AES-256-GCM, with SQLCipher rekeyed
to a raw Argon2id-derived key. Full rationale in `Architecture_Decisions.md`;
packaging implications in the Mac/Linux packaging guides.

**Stages:**
1. ✅ v2 primitives module + 16 unit tests (`core/encryption_v2.py`) — committed 2026-06-14
2. ✅ Dry-run migration harness — validated on real data (39 files, 364 rows, integrity ok, 0.74s derive, PASS) 2026-06-14
3. ✅ SQLCipher raw-key keying in `database.py` — gated on `.keyinfo`; v1 installs open unchanged (full suite 100 passed) 2026-06-14
4. ✅ Migration runner + login-flow wiring (4a + 4b, 2026-06-14). Runner `core/migrate_crypto.py` (crash-safe finalize/rollback, 5 tests). `login()` runs `recover_if_interrupted()` first, then after password verification migrates an existing v1 install via an `upgrading.html` interstitial + `/migrate/stream` SSE route that completes the login. 5 wiring tests. Full suite 110 passed.
5. ✅ Password-change flow updated for v2 (2026-06-14). `migrate_crypto.change_password()` re-encrypts files with a new file key and rebuilds the DB under a new raw key, committing with a new `.keyinfo` — crash-safe via the same marker + rollback machinery as the migration (recovery for a `rekey_v2` marker compares the on-disk `.keyinfo` salt to the marker's new salt). `change_password_progress` runs it for v2 installs and forces a fresh login. Also fixed: backups now include `.keyinfo` (essential to open a restored v2 install). 6 new tests. Full suite 116 passed.
6. ⬜ Remove v1 Fernet path — DEFERRED across a release cycle or two (distributed-user safety; see `Architecture_Decisions.md`)

The migration is now wired into login: on the next app **restart** followed by a
login, an existing v1 install is automatically migrated to v2 (full backup first,
crash-safe, rolls back on any failure). A currently-running instance is unaffected
until it restarts. A migrated install is now fully functional, password change
included (Stage 5). What remains is Stage 6 — removing the v1 Fernet read path —
which is deliberately deferred across a release cycle or two for distributed-user
safety.

**Post-launch (2026-06-14):** stages 1–5 plus three first-migration fixes (`.keyinfo` in backups, backup-verify keying, and the `core.encryption` v2 read/write dispatch) are committed, and the migration was verified end-to-end on a real install — attachments, logo, signature, statements, and backups all working on v2.

### Next-release checklist (when the distributed artifacts are rebuilt)

- **Bump the version + codename** in all five hand-synced places: `pyproject.toml`, `setup_app.py` (`CFBundleVersion` and `CFBundleShortVersionString`), the About modal in `web/templates/settings.html`, and the `.deb` control `Version` in `docs/Linux_Packaging_Guide.md`. Current: **1.0.0 / "v1.0 Simak"**.
- **Settings → About** updated as part of that bump (version + codename; the "Coded by …" credit line lives there too).
- **Website** — review and update edgecaseequalizer.ca and lightinextension.ca: the encryption description (now **Argon2id → HKDF → AES-256-GCM** for files and a raw Argon2id-derived SQLCipher key, previously PBKDF2/Fernet), the version, and any security/feature claims the v2 work changes.
- **Packaging** — per the Mac/Linux guides: py2app needs `core.encryption_v2` and `core.migrate_crypto` in `includes`, and `argon2` + `_argon2_cffi_bindings` in `packages`; the `.deb` picks up `argon2-cffi` from `requirements.txt` automatically.
- **Tag** the release once built.
- Optional: make `tools/audit_orphans.py` / `tools/audit_typed_columns.py` v2-aware (raw key when `.keyinfo` exists) so the maintenance scripts work on migrated installs.
- Stage 6 (remove the v1 Fernet read path) stays deferred for now.

---

## NEXT UP: DATA-LAYER REFACTOR (core/database.py)

**Status:** planned — *safety net landed June 14, 2026*; the refactor itself is not started.

`core/database.py` is the one real piece of structural debt: a ~2,350-line,
60-public-method god-object that nearly every blueprint imports. It works and is
well-behaved, so this is a maintainability tidy-up, **not** a fix for any bug.
Sequencing matters: do it as its own focused session, and only after the v2
crypto migration has had real-world runtime — refactoring the file the new DB
keying lives in, right after a risky landing, is the wrong order.

**Step 1 (done, 2026-06-14):** add a data-layer safety net so a behaviour-changing
refactor gets caught. `tests/test_database_layer.py` — 31 round-trip/behavioural
tests covering the previously-untested client lifecycle, client-type CRUD (incl.
the system-type rename/delete guards), the PHIPA retention/deletion lifecycle,
and the ledger queries. Full suite now 152.

**Step 2 (done — see completion record below):** widen coverage at the route/integration level for the larger
blueprints (entries, statements) — currently the thinnest spot — so the split is
done against a net that exercises the data layer end-to-end, not just in isolation.

*Concrete plan (mapped 2026-06-18):*

- **Prerequisite — route-test harness.** No `conftest.py` / Flask `test_client`
  exists yet; the whole suite drives a `db` object directly. Add `tests/conftest.py`
  with a `client` fixture: import the module-level `app` from `web.app`; set
  `TESTING=True` and `WTF_CSRF_ENABLED=False` (the CSRF gate is a `before_request`
  calling `csrf.protect()`); build a temp-file test DB (reuse the `db` fixture setup
  in `test_edgecase.py`) and inject it as `app.config['db']` — routes read the live
  DB straight from there, so this sidesteps master-password/key derivation; mark the
  session authenticated in a `session_transaction()` block (`authenticated`,
  `login_time`, `last_activity`). Then each test is `client.get/post(...)` + assert
  status + DB side-effect.
- **Target A — `entries`** (highest value; runner-up god-object and a split seam).
  Exercise the `entries/edit-history` and `retention/deletion` methods through real
  routes: create→edit round trip per type (session, communication, absence, item,
  profile); locked-session no-op save leaves `modified_at`/amendment trail untouched
  while a real edit appends exactly one edit-history row; session numbering and
  consultation-exclusion end-to-end; redaction POST then redacted view; attachment
  upload→download→delete; one missing-required-field POST asserts the in-app error,
  not a silent dead save.
- **Target B — `statements`** (the statements/portions seam). Drive the billing
  lifecycle through routes: `find-unbilled` → `generate` → `mark-sent/<id>` →
  `mark-paid`, asserting status transitions (unbilled → pending → paid); partial
  payment stays pending; `write-off` resolves the portion; PDF routes (`/pdf`,
  `/view-pdf`) assert 200 + `application/pdf` (don't parse the body).
- **Breadth (quick wins).** Parametrized smoke test GETting every read-only route
  (client file, statements index, ledger, settings) asserting 200 — catches
  import/registration breakage from the split immediately.
- **Skip/stub:** `send-applescript-email` (mock the AppleScript call); AI-Scribe
  (not a split seam); never assert on PDF contents.
- **Order:** harness → entries create/edit round trips → lock/amendment → statements
  lifecycle → redaction/attachments → breadth. Harness + entries lifecycle +
  statements lifecycle alone is a real net; the rest is gravy. Adds files under
  `tests/` only, so the production checkout stays usable throughout.

**Step 2 — DONE (2026-06-19 → 06-20).** Suite 152 → 185, all green. Landed under
`tests/` only (production checkout untouched throughout):
`conftest.py` (authenticated `client` + temp-DB `app_db` fixtures),
`test_routes_smoke.py`, `test_entries_lifecycle.py` (session create/lock/no-op/
amendment, redaction, consultation-exclusion numbering),
`test_entry_types_roundtrip.py` (communication/absence/item/profile create→edit),
`test_statements_lifecycle.py` (find-unbilled → generate → mark-paid full/partial →
write-off ×3 → mark-sent), `test_attachments_lifecycle.py`
(upload→download→view→delete), `test_routes_breadth.py` (read-only pages render 200).

*Corrections to the mapped plan, worth knowing before Step 3:*

- **CSRF:** `WTF_CSRF_ENABLED=False` does **not** work — flask-wtf 1.2.2
  `csrf.protect()` (called manually in a `before_request`) ignores the flag, so form
  POSTs 400. The `client` fixture instead no-ops `validate_csrf` via a function-scoped
  monkeypatch.
- **Blueprint DB wiring:** blueprints capture `db` via `init_blueprint` at login, so
  the fixture also calls `init_all_blueprints(app_db)`; setting `app.config['db']`
  alone is not enough.
- **Portion statuses** are `ready → sent → paid` (plus `written_off`), not "pending";
  partial payment leaves a positive `amount_owing`.
- **mark-sent** is tested with `ATTACHMENTS_DIR` redirected to a temp tree and PDF
  generation stubbed (it writes a real attachment otherwise). Under `skip_email=1` the
  AppleScript email step is frontend-only and does not run, so no email mock was needed.
- A bare local `client` fixture already existed in `test_migrate_wiring.py`; the
  conftest fixture shadows cleanly (local wins), no collision.

*Follow-up pass (2026-06-20):* `test_links_layer.py` adds the mutating link
operations `test_edgecase.py` missed (`update_link_group`, `delete_link_group`,
`get_all_link_groups`). The other flagged seam, "backups/maintenance", is **not**
in `database.py` — that code lives in the backup module + `migrate_crypto`, both
already tested — so no additions were needed there. The data-layer net now covers
every domain block in `database.py`.

**Step 3:** split `database.py` by domain. Candidate seams (each already a clear
comment-delimited block in the file): client types, clients, entries/edit-history,
ledger, statements/portions, retention/deletion, links, backups/maintenance. Likely
shape is a thin `Database` facade delegating to per-domain mixins/modules while
preserving the existing public method names, so callers don't change in lockstep.

No forcing function — this is a watch-item, not a fire. `entries.py` (~1,924 lines)
is the runner-up and can follow the same pattern afterwards.

---

## PHASE STATUS

### Phase 1: Core Functionality ✅ COMPLETE (Nov 29, 2025)
- All 8 entry types (Profile, Session, Communication, Absence, Item, Upload, Income, Expense)
- Statement system with PDF generation and email
- Ledger system with financial reports
- Calendar integration (.ics + AppleScript)
- Export to PDF
- Billing features (profile fees, guardian splits, link groups)

### Phase 2: Professional Features ✅ COMPLETE (Dec 1, 2025)

| Feature | Status | Notes |
|---------|--------|-------|
| SQLCipher Encryption | ✅ Complete | Database fully encrypted |
| Attachment Encryption | ✅ Complete | Fernet encryption for all uploads |
| Master Password | ✅ Complete | Login system with session management |
| Password Change | ✅ Complete | Settings page |
| Session Timeout | ✅ Complete | 15/30/60/120 min or never |
| File Retention | ✅ Complete | Auto-prompts for expired inactive clients |
| Backup System | ✅ Complete | Full/incremental, auto-backup, restore, cloud folders |
| Performance | ✅ Complete | Persistent connections (4s → 100ms) |
| Code Quality | ✅ Complete | JSDoc comments, CSS deduplication |

### Phase 3: AI Integration ✅ COMPLETE (Dec 2, 2025)

| Feature | Status | Notes |
|---------|--------|-------|
| Local LLM Integration | ✅ Complete | llama-cpp-python with Hermes 3 8B |
| AI Scribe UI | ✅ Complete | Integrated into Session form |
| Write Up Action | ✅ Complete | Point-form to prose |
| Proofread Action | ✅ Complete | Grammar/spelling fixes |
| Expand Action | ✅ Complete | Add clinical detail |
| Condense Action | ✅ Complete | Make concise |
| Model Download | ✅ Complete | Progress tracking via SSE |
| Platform Detection | ✅ Complete | Auto-configures for Mac/Windows/Linux |
| Model Management | ✅ Complete | Download/unload in Settings |

---

## DEVELOPMENT STATISTICS

| Metric | Value |
|--------|-------|
| Development Period | Nov 7 - Dec 2, 2025 (26 days) |
| Total Lines of Code | ~30,000 |
| Python Lines | ~9,400 |
| HTML Lines | ~6,500 |
| JavaScript Lines | ~6,200 |
| CSS Lines | ~5,700 |
| Blueprints | 12 |
| Database Tables | 13 |
| Templates | 32 |
| Entry Types | 8 |
| Routes | 102 |
| Automated Tests | 43 |

---

## RECENT ACCOMPLISHMENTS

### June 10–12, 2026

**Session Form Hardening + AI Scribe Change Review**
- No-change saves of locked sessions are true no-ops (modified_at stays coherent with the amendment trail); "Save Changes" disabled until the form is genuinely dirty; Cancel relabelled "Back" on locked entries
- Unsaved-changes protection: custom modal on in-app navigation (window-capture guard preempting the base disconnect handler — the root cause of a multi-browser native-dialog misfire), native warning restored for tab close/reload after its three misfire causes were fixed
- Silently-blocked form submissions made visible: invalid hidden (Choices-managed) required fields now raise an in-app modal naming the fields instead of a dead Save button
- AI Scribe "Show Changes": word-level diff overlay (red deletions / green insertions, punctuation-level) via new `generate_full_content_diff` + `POST /api/ai/diff`, sharing the amendment-history diff engine
  - June 13: overlay diff now preserves line/paragraph breaks (newline runs tokenized and rendered as `<br>`); the history diff stays single-line by design
  - June 15: overlay height now mirrors the AI Result textarea's live height (dropped auto-grow `min/max-height`; set inline from `offsetHeight`) so Show/Hide Changes no longer resizes the panel
- New verification practice: jsdom harness with base-template scripts included, and Playwright against live instances (real Chromium, real layout); per-restart static cache-busting (`?v=`)
- Tests: 77 → 83

### June 7, 2026 (second batch)

**Code Review Remediation — Completion Pass**
- Money arithmetic migrated to Decimal end-to-end (`core/money.py`, `core/billing.py`): exact-cent payment status (no epsilon fudge), per-line guardian splits that sum exactly, pro-rata tax reversal on refunds, 20 new non-tautological money tests (63 total)
- Master password no longer passes through the session cookie during password change
- Client deletion is transaction-safe (files deleted only after commit; related rows cleaned up); link-group writes roll back on error
- Backup system: broken incremental chains detected and refused, encrypted-DB integrity check after zipping, WAL handling, safety backups all visible
- CSRF on multipart uploads, entry-ownership checks on edit routes, rate-limiter spoofing fix, edit-history diff escaping, validation 500s fixed
- Decrypted PDFs moved to private 0700 temp dirs; desktop wrapper gets port fallback + readiness probe; AI generation properly locked; per-password KDF cache
- Shared helpers (link-group fees, payee/category get-or-create, currency formatting), packaging reconciled, dead code removed, attachment inline-rendering allowlist
- Deferred with documented rationale: L1 data-root detection, L13 timestamp storage, M5 dashboard N+1; M2 PRAGMA flip pending orphan audit

### June 7, 2026 (afternoon — H3, H5, M11)

**Three High-tier fixes from CODE_REVIEW.md**
- **H3**: Single-guardian minor billing inconsistency resolved by clarifying the UI — the "Pays (%)" field is now hidden when there's no second guardian, and the billing-side comment makes the intended behaviour explicit
- **H5**: Stopped coercing `None` → `''` in entry writes; added `TYPED_ENTRY_COLUMNS` set and `''` → `None` coercion for numeric/date/boolean columns in both `add_entry` and `update_entry`; added `tools/audit_typed_columns.py` to find and optionally fix any pre-existing `''` pollution in the live database
- **M11**: `update_entry` now raises `EntryLockedError` on locked entries unless the caller passes `allow_locked=True`; all existing callers updated explicitly so future code can no longer silently mutate locked clinical entries
- 43 tests still passing

### June 7, 2026 (follow-up)

**Ledger Report Receipt-Dropping Fix**
- Caught while reviewing the Cowork batch: `pdf/ledger_report.py` had the same path-resolution bug as C1/C2 — `att['filepath']` resolved against process CWD instead of DATA_ROOT, causing receipts to silently disappear from ledger reports in desktop/installed mode
- Promoted `resolve_attachment_path()` to `core/config.py` so both PDF modules share one implementation
- 43 tests still pass

### June 7, 2026

**Code Review Remediation — First Batch (CODE_REVIEW.md)**
- Fixed client-file PDF exports silently dropping all attachments (wrong on-disk path + missing decryption) — exports now include images inline and merge PDF attachments correctly
- Fixed PDF generation crashing on `&`, `<`, or `>` in any user-entered field (names, addresses, descriptions, payment instructions) — all user content now XML-escaped before ReportLab markup
- Restore now removes stale WAL/SHM sidecar files before replacing the database, eliminating a post-crash corruption risk
- `encrypt_file()` and the backup manifest now use atomic write-temp-then-replace, so a crash mid-write can't destroy an attachment or reset the backup catalog
- Added database indexes for the most common query patterns (auto-migrates existing databases at startup)
- Added `tools/audit_orphans.py` to audit foreign-key orphans ahead of a future `PRAGMA foreign_keys=ON` flip (deliberately deferred)
- Consolidated duplicated frontend utilities (escapeHtml ×4, autoResize ×6, three-way fee calc ×6, color palette) into new `shared_utils.js`; deleted dead `color_palette.js`
- All 43 automated tests passing; PDF fixes verified end-to-end with hostile test data

### May 16, 2026

**AI Scribe: Layout Polish**
- Removed the inline "Generating..." status indicator in favour of a Cancel button styled to match the action buttons
- Cancel button uses `visibility: hidden` to reserve layout space, eliminating jumpiness when it appears/disappears
- Converted the "Loading AI model..." banner from an inline element (which shifted page content) into a centered modal overlay with dimmed backdrop

### May 15, 2026

**AI Scribe: Cancel Button & Status Visibility Fix**
- Added Cancel button inside the AI Scribe modal that aborts in-flight generation via `AbortController`
- Resolves a hang where cancelling mid-stream (by navigating away) left the model locked, causing the next action to wait indefinitely
- Fixed pre-existing bug where the "Generating..." spinner never appeared — JS was using `classList.remove('hidden')` against a div hidden with inline `style="display: none;"`
- Renamed bottom "Cancel" link to "Back" with standard left-arrow styling to match the rest of the app

### March 28, 2026

**Scheduler: Calendar App Launch Fix**
- Fixed AppleScript calendar integration failing when Calendar.app not running
- Added explicit `launch` command with delay before creating events
- Prevents "Application isn't running" (-600) error

### March 23, 2026

**AI Scribe: Preserve Clinician Language**
- Updated system prompt to preserve profanity, slang, and colloquialisms
- Model was incorrectly substituting euphemisms (e.g., "shit" → "defecate")
- Prompt now explicitly instructs model to respect therapist's word choices

### March 9, 2026

**Simplified Email Options (Linux)**
- Removed Thunderbird/Betterbird email integration
- Linux now uses mailto: links only (same as fallback on all platforms)
- Reduces complexity and packaging issues with desktop mode
- Mac users retain Apple Mail integration with auto-attach PDF

### February 17, 2026

**Code Quality & Security Hardening**
- Extracted `_run_shutdown_backup()` in cli.py - eliminates duplicated backup logic across three shutdown paths (atexit, SIGINT/SIGTERM, session timeout). Single function, consistent behaviour, ~50 lines removed.
- Added `_atomic_reencrypt()` in auth.py - password change no longer writes plaintext to original file path. Uses temp file + `os.replace()` for atomicity; original encrypted file untouched if anything fails.
- Fixed broken safety backup in password change flow: was calling `create_backup()` with incorrect keyword arguments (would TypeError on first use). Now correctly calls `create_pre_restore_backup()`.
- Completed logout backup refactor: removed redundant `_run_auto_backup_check()` from auth.py, logout now uses shared `_run_shutdown_backup()`. All four shutdown paths unified.
- 43 tests passing, no regressions. Password change flow verified working in production.

### February 15, 2026

**Statement Email Font Consistency**
- Fixed inconsistent font rendering in Apple Mail statement emails
- Salutation ("Dear Name,") was rendering in different font than body text when exported
- Changed AppleScript email generation from plain text `content` to `html content`
- All text now wrapped in styled divs with explicit Helvetica font family

### February 5, 2026

**Code Review & Cleanup (Opus 4.6)**
- Comprehensive code review of full codebase — no critical issues found
- Removed 10 redundant in-method imports in database.py (json, time already imported at top level)
- Renamed `session` variable to `session_entry` in entries.py to avoid shadowing Flask's session import
- 43 tests passing, no regressions

### January 21, 2026

**View PDF Button for Sessions**
- Added View PDF button (eye icon) to locked Session entries
- Generates single-session PDF for sharing with supervisors or documentation
- Uses same format as client file export (practice header, signature, edit history)
- Button appears in entry header next to Redact button

### February 1, 2026

**Financial Report Enhancements**
- Added attachment appendix option to Financial Reports
- Receipts and invoices attached to ledger entries can now be included in tax reports
- Images rendered inline in appendix, PDFs merged at end of report

### January 6-7, 2026

**Backup System Improvements**
- Backup now runs on session timeout (not just explicit logout)
- Post-backup command (rsync) now runs on all shutdown paths: logout, Ctrl+C, atexit
- WAL checkpoint happens BEFORE backup (was after), ensuring recent changes are captured
- Renamed backup frequency `startup` → `session` to reflect logout-based backup behavior

**Desktop Mode Enhancements**
- Implemented Libram-style heartbeat monitoring for packaged apps
- Server auto-terminates after 30s without browser requests when `EDGECASE_DESKTOP=1`
- Repurposed existing `/api/session-status` polling (already runs every 30s)

**UI Consistency**
- Moved Back button to top-right in Settings and Backups pages
- Changed restore dropdown from chain hierarchy to flat reverse-chronological list

### December 27-30, 2025

**Security Hardening**
- Replaced fixed encryption salt with per-installation unique salts
- Added PRAGMA password escaping to prevent SQL injection
- Implemented persistent SECRET_KEY generation
- Created comprehensive input validators
- Added login rate limiting (5 attempts → 5-minute lockout)
- Replaced deprecated PyPDF2 with pypdf
- Created SECURITY.md for open-source release

**App Relocatability**
- Fixed hardcoded paths throughout codebase
- Added EDGECASE_DATA environment variable support
- Server port now configurable via --port flag or EDGECASE_PORT
- Added --help flag with usage information

**Theme System**
- Added Ink, Slate, Parchment themes (from Synesius)
- Removed underused themes (Ocean Breeze, Sunset Glow, Garden Path, Warm Stone)
- Final theme set: EdgeCase (default), Ink, Slate, Parchment, Tutti-Frutti

**Production Readiness**
- Server disconnect overlay when heartbeat fails
- Client names removed from page titles (browser history privacy)
- Canadian spelling preserved in AI Scribe prompts
- Database reset feature in Settings (requires password + typing "RESET")

### December 14-16, 2025

**Comprehensive Testing Complete**
- Completed comprehensive testing of all features
- Created fictional test dataset (8 clients covering all scenarios)
- Tested all entry types, billing workflows, statements, exports, backups
- Fixed 7 minor UX/logic issues discovered during testing
- All 41 automated tests passing
- System verified production-ready for January 2026 launch

**Final Polish**
- Updated info card logic (Active Clients count, Sessions This Month)
- Improved Main View column order (Created / Last Session)
- Fixed link group validation (switched from alerts to styled modals)
- Session timeout client-side protection (activity tracking, keepalive pings)
- Date dropdown arrow alignment fix (Choices.js CSS override)

### December 5, 2025

**Bug Investigation Complete**
- Systematic review of 41 potential issues from checklist
- 38 items confirmed resolved (fixed, handled, or by design)
- 3 minor theoretical edge cases that fail gracefully
- Created Bug_Investigation_Log.md for reference

**Double-Login Fix**
- Fixed Safari/Firefox requiring two logins
- Root cause: session cookie race condition on redirect

**Ledger Autocomplete Refactor**
- Unified architecture for all three autocomplete fields
- Added income_payors table to schema

### December 2, 2025

**AI Scribe Feature**
- Local LLM integration using llama-cpp-python
- Hermes 3 Llama 3.1 8B model (Q4_K_M quantization)
- Four text processing actions with SSE streaming

---

## ARCHITECTURE SUMMARY

### Blueprints (12)
1. **ai** - AI Scribe functionality
2. **auth** - Login/logout, session management
3. **backups** - Backup/restore system
4. **clients** - Client management, file viewing, session reports
5. **entries** - Entry CRUD (6 types)
6. **ledger** - Income/Expense, financial reports
7. **links** - Link group management
8. **statements** - Statement generation, PDF, email, payments
9. **scheduler** - Calendar integration
10. **types** - Client type management
11. **settings** - Practice configuration
12. **app.py routes** - Auto-backup, restore messages, filters

### Key Files
| File | Lines | Purpose |
|------|-------|---------|
| core/database.py | ~1,930 | Database operations |
| utils/backup.py | ~1,060 | Backup/restore system |
| web/blueprints/entries.py | ~1,780 | Entry CRUD |
| ai/assistant.py | ~335 | LLM model management |
| web/blueprints/ai.py | ~330 | AI Scribe routes |
| web/app.py | ~290 | Flask initialization |
| web/utils.py | ~270 | Shared utilities |
| web/static/css/shared.css | ~2,360 | Common CSS patterns |

---

## SUCCESS CRITERIA - ALL MET ✅

### Functional Requirements
- ✅ Manage clients via web interface
- ✅ Create and customize client types
- ✅ Create all entry types (6 client + 2 ledger)
- ✅ Link clients for couples/family therapy
- ✅ Generate invoices and track payments
- ✅ Track income and expenses
- ✅ Generate financial reports
- ✅ Export entries as PDF
- ✅ Calendar integration
- ✅ Encrypted database (SQLCipher)
- ✅ Encrypted attachments (Fernet)
- ✅ Backup/restore system
- ✅ Session timeout for security
- ✅ File retention compliance
- ✅ AI-assisted note writing

### Quality Requirements
- ✅ Clean, modular codebase (12 blueprints)
- ✅ External CSS/JS (no inline code)
- ✅ JSDoc documentation for IDE support
- ✅ Consistent naming conventions
- ✅ Professional UI with responsive design
- ✅ Automated tests for critical business logic (43 tests)

---

## KNOWN ISSUES

None critical. System is in active production use.

### Features Not Yet Tested with Real Data

The following features were extensively tested with test data during development but have not yet been used in production with real clients:

- **Guardian billing / split payments** - For billing minors' guardians separately
- **Link groups** - Couples, family, and group therapy billing
- **Tax calculations** - HST/GST on session fees (current practice doesn't charge tax)

These features passed all automated tests and manual testing in December 2025. First real-world use should be verified carefully.

---

## PRODUCTION MILESTONES

- **January 3, 2026:** First real client session using EdgeCase
- **AI Scribe:** Working well in production, generating quality session notes
- **Backups:** Running reliably on logout with rsync to Sentinel server

---

## GIT STATUS

**Branch:** main  
**Total Commits:** 651 (as of Feb 5, 2026)

**Recent Commits:**
```
ed69ce6 Cleanup: move json import to top-level, remove 10 redundant in-method imports (database.py), rename session variable to session_entry to avoid shadowing Flask session (entries.py)
0dcc0ff Remove keepalive debug logging
9a29479 Adjust warning thresholds +15s to compensate for 30s poll interval
```

---

## ACCESS

- **Mac:** http://localhost:8080
- **iPad (same WiFi):** http://richards-macbook.local:8080

### Start Server
```bash
cd ~/apps/edgecase
source venv/bin/activate
python main.py
```

---

## DOCUMENTATION

| Document | Purpose |
|----------|---------|
| EdgeCase_Navigation_Map_v5_4.md | Quick reference, directory structure |
| EdgeCase_Project_Status.md | This file - current state |
| Database_Schema.md | Table definitions |
| Route_Reference.md | All routes by blueprint |
| Architecture_Decisions.md | Design rationale |
| CSS_Architecture.md | CSS organization |
| Bug_Investigation_Log.md | Production readiness audit |
| Flask_Double_Login_Fix.md | Technical reference |

---

*EdgeCase Equalizer - Practice Management for Solo Therapists*  
*"Every practice is an edge case"*  
*All Phases Complete: December 2, 2025*  
*In Production: January 3, 2026*
