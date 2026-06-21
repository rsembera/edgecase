# EdgeCase — Comprehensive Code Review

**Date:** 2026-06-07
**Scope:** Full first-party codebase (~16k lines Python, ~9.6k lines JS, templates, tests). Vendored libraries (`venv/`, `choices.min.js`, `lucide.min.js`) and the built `dist/` app were excluded.
**Context applied to severity:** EdgeCase is a single-user, local-only (localhost-bound) desktop app for one psychotherapist. Remote-attack vectors are therefore weighted lower; **data integrity, encryption correctness, backup/restore reliability, and privacy of client (PHI) data are weighted highest.** Classic multi-user web vulns (CSRF, session fixation, stored XSS) are noted but down-graded to reflect the threat model — with the caveat that several of them become real the moment LAN mode is enabled.

---

> **STATUS — historical snapshot (updated June 21, 2026).** This is the review *as written on 2026-06-07*; the findings below are preserved verbatim as the record that drove remediation. **Most Critical / High / Medium items have since been fixed** — e.g. C1+C2 (client-export attachments now resolve + decrypt), H1 (WAL/SHM unlinked on restore), H2 (master password out of the session cookie), H3 (single-guardian billing), H5 (typed-column `None` preserved), M1 (money on `Decimal`/cents via `core/money.py`), M2 (foreign keys enforced, gated on an orphan-integrity check), M11 (lock enforced in the data layer), M14 (ReportLab XML-escaping), plus the duplicated-helper and dead-code cleanups. See `CHANGELOG.md` and the "Recent Accomplishments" in `EdgeCase_Project_Status.md` for the per-item remediation record.
>
> **Two caveats when reading below:** (1) every file:line reference predates the June 2026 refactors — `core/database.py` is now a facade over `core/db/` mixins, and `entries.py`/`statements.py` are now packages — so the line numbers no longer resolve. (2) The encryption descriptions ("Fernet", "PBKDF2 480k") and the testing assessment ("~940 lines, no money/backup coverage") describe the June-7 state; encryption is now Argon2id → AES-256-GCM (v2) and the suite is 201 tests across 17 files. Items still **deferred with documented rationale:** L1 (macOS data-root detection), L13 (naive local-time timestamps), M5 (home-page N+1).

---

## Executive summary

EdgeCase is a well-architected application with genuinely thoughtful security foundations: real SQLCipher encryption with a sound key-derivation setup, an authenticated-encryption (Fernet) scheme for attachments with no nonce-reuse risk, a two-phase restore with a pre-restore safety backup, a fully local AI model that sends no client data anywhere, and parameterized SQL with column whitelists throughout. The bones are good.

The most important problems are **not** in the security primitives — they're in correctness and data-handling details that can silently lose or misstate client data:

1. **Client-file PDF exports silently drop every attachment** (wrong path + no decryption). For a clinical/legal export this is silent data loss.
2. **Restore leaves stale WAL/SHM sidecar files**, risking corruption of the restored database — and crash-recovery is exactly when restore is used.
3. **Single-guardian minor statements bill the full total**, ignoring the computed guardian-pays-percent.
4. **The master password is round-tripped through the Flask session cookie** during password change.
5. **All money is handled as binary floats** across statements, ledger, and reports.
6. **`add_entry` coerces `None` to `''`** for typed columns, so an entry's semantics depend on which code path wrote it.

None of these are remotely exploitable, but #1, #2, #3, and #6 can corrupt or lose the data this app exists to protect. They should be fixed first.

The findings below are organized by severity. Each item lists file, line(s), a short explanation, and (where useful) a code excerpt. All high-impact findings were verified directly against the source.

---

## Critical

### C1. Client-file PDF export drops all attachments — wrong on-disk path
`pdf/client_export.py:838-840` (and the identical block at `924-926`)

Attachments are stored as encrypted, UUID-named files with the real relative path in `att['filepath']` (`web/utils.py:219,243`). The export instead reconstructs a path that never existed:

```python
filename = att['filename'].lower()
filepath = os.path.join(get_attachments_path(),
                        str(client['id']), str(entry['id']), att['filename'])
```

`os.path.exists(filepath)` is always False, so every image renders "(file not found)" and every PDF attachment is skipped at the merge step (`:1152`). The export looks complete but is missing all attachments — silent data loss in a document that may be used for legal/clinical disclosure. Fix: use `att['filepath']` resolved against `DATA_ROOT`, mirroring `resolve_attachment_path` in `web/blueprints/entries.py`.

### C2. Client-file export embeds attachment images without decrypting
`pdf/client_export.py:850, 936`

Even with the path fixed, images load via `Image(filepath)` directly. Stored files are encrypted `.enc` blobs, so ReportLab receives ciphertext and the `except` swallows it as "(could not embed image)". The correct pattern already exists elsewhere — `pdf/ledger_report.py:472-477` and `pdf/generator.py:537-541` call `decrypt_file_to_bytes(...)` first. Combined with C1, attachment embedding in client exports is fully non-functional whenever encryption is on (i.e. always).

---

## High

### H1. Restore leaves stale SQLite WAL/SHM files beside the replaced DB — corruption risk
`utils/backup.py:640-647` (`complete_restore`)

```python
target_db = DATA_DIR / 'edgecase.db'
if target_db.exists():
    target_db.unlink()
shutil.copy2(staged_db, target_db)
```

Only `edgecase.db` is replaced; the previous database's `edgecase.db-wal` / `-shm` are left in place. On next open SQLite may replay old WAL frames into the restored file, mixing pre-/post-restore states. The normal exit path checkpoints (`web/cli.py`), but after a crash the WAL persists — and crash recovery is the main reason to restore. Fix: unlink `-wal`/`-shm` before copying.

### H2. Master password stored in the Flask session cookie during password change
`web/blueprints/auth.py:210-213`

```python
session['password_change_current'] = current_password
session['password_change_new'] = new_password
session.modified = True
```

Flask's default session is signed but **not encrypted** (base64-readable), so both master passwords are serialized into the `Set-Cookie` header and stored client-side until popped. For an app whose entire security model is the encryption password, this is the wrong place to stash it. Fix: hold them in a short-lived server-side dict keyed by a random token, or perform the rekey synchronously without the SSE round-trip.

### H3. Single-guardian minor statements bill the full total, ignoring guardian-pays-percent
`web/blueprints/statements.py:384-423`

For a minor with one guardian, `g1_amount` is computed honoring `guardian1_pays_percent` (`:391`) but then ignored — the inserted portion uses the full `total` (`:423`):

```python
else:
    # Single guardian pays full amount
    cursor.execute("""... VALUES (?, ?, 1, ?, 0, 'ready', ?)""",
                   (statement_id, client_id, total, now))  # should be g1_amount
```

If `guardian1_pays_percent < 100`, the guardian is over-billed and the percentage setting silently does nothing. If billing the full amount to a sole guardian is the intended behavior, the percent field should be disabled in that case and the dead computation removed; otherwise insert `g1_amount`. Either way the current state is an inconsistency between computed and billed amounts.

### H4. Missing incremental in a backup chain is silently skipped — wrong restored data, no error
`utils/backup.py:505-524` (`get_restore_points`)

If a middle incremental file is missing (cloud-sync gap, deletion), it's quietly dropped but later incrementals still build restore points on the broken chain. `prepare_restore` then applies an incomplete sequence; any file whose only copy lived in the missing zip is silently restored from an older version. Clinical records can be rolled back with no warning. Fix: a gap should invalidate all later points in that chain (or at minimum surface a prominent warning).

### H5. `add_entry` coerces `None` to `''`, polluting typed columns
`core/database.py:1300-1307`

```python
value = entry_data[field]
if value is None:
    value = ''      # comment says "Convert empty strings to empty strings (not None)"
values.append(value)
```

SQLite stores `''` as TEXT even in REAL/INTEGER columns (`fee`, `session_date`, `ledger_date`, `statement_id`…). Consequences: `BETWEEN`/range filters exclude rows (TEXT sorts above numbers), `ORDER BY` misorders, and `redact_entry` (`:894`, `if statement_id is not None: return False`) wrongly refuses to redact entries whose `statement_id` was inserted as `''`. This is the opposite of `update_entry`, which stores `None` as NULL — so an entry's semantics depend on which path wrote it. Fix: preserve `None`, or coerce per column type.

### H6. Attachment files deleted from disk before the DB transaction commits
`core/database.py:2036-2053` (`archive_and_delete_client`)

```python
if os.path.exists(client_attachments_dir):
    shutil.rmtree(client_attachments_dir)
...
conn.commit()
```

If a later DELETE fails, the `except` rolls back the DB (`:2056-2059`) — but the files are already gone, leaving rows pointing at nothing. File deletion must happen only after a successful commit. The method also never deletes the client's `statement_portions`, `client_links`, or `entry_links` rows; orphaned portions permanently inflate `count_pending_invoices()` (`:766-780`), which has no JOIN to confirm the client still exists.

### H7. Backups zip a live database with no lock; zip-CRC verification gives false confidence
`utils/backup.py:241-245` (`create_full_backup`)

Callers checkpoint first (`web/blueprints/backups.py:108`), but `backup.py` itself doesn't enforce it and the app stays live during zipping, so a concurrent write produces a torn DB image. `verify_backup` (`:372-386`) only checks zip CRCs — a torn but internally-consistent-as-bytes copy passes verification and fails only at restore time. The WAL file is never included in `get_all_backup_files` (`:47-50`), and the recorded hash is computed from disk *after* `zf.write`, so it can differ from the zipped bytes. Fix: enforce checkpoint inside the backup function, snapshot via SQLite backup API or a copied immutable file, and validate the DB with `PRAGMA integrity_check` post-zip.

### H8. No rollback on exceptions in multi-statement writes — half-applied work can commit later
`core/database.py:1209-1231` (`update_link_group`) is the clearest case; same pattern in `create_link_group` (`:995-1016`), `delete_link_group` (`:1248-1253`)

Only `archive_and_delete_client` (`:2056`) has a rollback. Because connections are thread-local and long-lived, if an INSERT raises mid-method the implicit transaction stays open and the *next* unrelated `conn.commit()` on that thread commits the partial work (e.g. group-fee data lost). Fix: wrap multi-statement methods in try/except with `conn.rollback()`, or use the connection as a context manager.

---

## Medium

### M1. All money handled as binary floats
`web/blueprints/statements.py:308-335,391-397,655-681`; `web/blueprints/ledger.py:173,228,328,400`; `pdf/generator.py:397-438`; `pdf/ledger_report.py:103-106`

Statement totals, per-entry tax (`fee - base_fee`), pro-rata tax, accumulated `amount_paid`, and report subtotals are all float arithmetic. Rounding error accumulates in financial records (note the `<= 0.01` fudge at `statements.py:661` that papers over a balance that never quite reaches zero). For billing and tax-filing data, use `decimal.Decimal` or integer cents end to end.

### M2. Foreign keys are never enabled — every `FOREIGN KEY` clause is decorative
`core/database.py:39-53` (`connect`) — verified: no `PRAGMA foreign_keys=ON` anywhere

Dangling `entries.client_id`, `attachments.entry_id`, `statement_portions.client_id` etc. are accepted silently, which is the mechanism behind the orphans in H6. Fix: `PRAGMA foreign_keys=ON` on every connection (and audit existing data for orphans first).

### M3. Zero indexes on a schema queried constantly by client_id / class / type / date
`core/database.py:83-367` — verified: no `CREATE INDEX` statements

Every `get_client_entries`, `get_payment_status`, ledger query, and retention sweep is a full scan of the wide `entries` table. Fine today; increasingly sluggish over years of notes. Cheap wins: indexes on `entries(client_id, class)`, `entries(ledger_type, ledger_date)`, `attachments(entry_id)`, `statement_portions(client_id, status)`.

### M4. CSRF exemption covers multipart/form-data
`web/app.py:85-98`

CSRF is skipped for `application/json` *and* `multipart/form-data`. Multipart is a CORS "simple" content type submittable cross-origin from a plain `<form>` with no preflight, so every file-upload route is unprotected (JSON genuinely requires preflight, so exempting it is defensible). Localhost binding limits impact today, but this becomes real under `--lan`. Fix: keep CSRF on for multipart; exempt only true JSON.

### M5. `clients.index` loads most of the database on the home page (N+1)
`web/blueprints/clients.py:153-205,215-287`

Loops every type, then every client calling `get_client_entries` twice (sessions-this-month and billable-this-month) plus `get_profile_entry`, `get_last_session_date`, `get_payment_status`, `is_client_linked`. That's many queries × client count on every main-view load. Fix: compute stats with a few aggregate SQL queries.

### M6. Edit routes don't verify the entry belongs to the URL's client
`web/blueprints/entries.py:604-625,962-979,1216-1233,1465-1483`

`edit_session`/`edit_communication`/`edit_absence`/`edit_item` check `entry['class']` but never `entry['client_id'] == client_id` (redaction routes at `:1881,1913` *do* check). A mismatched `client_id` updates the entry and then calls `renumber_sessions(client_id)` on the wrong client, corrupting session numbering. Fix: assert ownership consistently.

### M7. Decrypted PHI written to predictable temp locations
`desktop.py:59-74`; `web/blueprints/statements.py:528-534,771-839`

`Api.open_file` writes statements/exports (full plaintext notes) to `tempfile.gettempdir()/<predictable name>` and never deletes them; statements use predictable names in shared `/tmp`. On a multi-user OS these are readable by other accounts and persist after the app closes. Fix: write to a per-user `0700` dir with randomized names and delete after the viewer launches.

### M8. Login rate-limiter trusts client-supplied `X-Forwarded-For`
`web/blueprints/auth.py:26-31`

`_get_client_ip` returns the first `X-Forwarded-For` value if present, and lockout is keyed on it — so rotating the header defeats the 5-attempt lockout. There's no reverse proxy here, so the header shouldn't be trusted at all. Fix: use `request.remote_addr` directly.

### M9. `portion_count` query crashes when no statements were generated
`web/blueprints/statements.py:446-450`

If client IDs were supplied but none were billable, `generated` is `[]` and the query becomes `... IN ()`, raising `OperationalError` before the `if generated else 0` guard. A no-op turns into a 500. Fix: guard the empty case before building the query.

### M10. Retention sweep keyed to the literal type name `'Inactive'`; rename not guarded in the DB layer
`core/database.py:1882-1889` (`WHERE ct.name = 'Inactive'`) and `:491-515` (`update_client_type` doesn't check `is_system`/`is_system_locked`)

If the locked type is ever renamed, retention-based destruction silently stops matching and files are kept past their legal destruction date with no error. Fix: match on `is_system = 1`, and guard the rename in `update_client_type` (as `delete_client_type` already guards deletion at `:524-527`).

### M11. `update_entry` doesn't enforce the lock its docstring promises
`core/database.py:1365-1394` — `"""Update entry (adds to edit history if locked)."""` with no `locked` check and no edit-history call

Immutability of locked clinical entries relies entirely on every route remembering to check. The DB layer is the natural single chokepoint and should enforce it.

### M12. `encrypt_file` truncates in place — crash mid-write destroys the attachment
`core/encryption.py:49-59` (`open(filepath, 'wb')` truncates first)

A crash between truncate and write leaves a zero-byte/partial file with the plaintext already gone. Same non-atomic pattern in `save_manifest` (`utils/backup.py:113-117`) — a corrupt write there resets the entire backup catalog (`load_manifest` starts fresh, `:92-110`). Fix: write to a temp file and `os.replace()`.

### M13. Several oversized functions and substantial duplicated logic (Python)
`web/blueprints/entries.py:94-436` (`edit_profile` ~340 lines), `:604-911` (`edit_session`)

The "link-group fees by format" query block is copy-pasted across `create_session`/`edit_session`/`create_absence`/`edit_absence` (`:562-577,872-887,1192-1206,1368-1382`) and `scheduler.py:292-314`; the "get-or-create category/payee" block is duplicated in `statements.py` `mark_paid` (`:713-734`) and `write_off` (`:1072-1095`); currency helpers are triplicated across the three PDF modules (`generator.py:135-149`, `ledger_report.py:19-34`, `client_export.py:170-184`, with inconsistent thousands-separator behavior). Extract shared helpers.

### M14. Unescaped user content injected into ReportLab Paragraph markup → build crashes
`pdf/client_export.py:322-348,462,680-758`; `pdf/generator.py:267,320,843-848`; `pdf/ledger_report.py:457`

Free-text fields (names, addresses, descriptions, emails) are interpolated straight into `Paragraph("<b>...{value}...")` with no XML escaping. A single `&`, `<`, or `>` (e.g. address "Apt 5 & 6", description "fee < $50") raises a parse error, and these field-level calls have no try/except fallback, so `doc.build()` throws and the whole export/statement fails. Fix: pass user content through `xml.sax.saxutils.escape` before placing it in Paragraph markup.

### M15. AI generation isn't serialized — concurrent calls can crash the model
`ai/assistant.py:286-337`

`load_model`/`unload_model` use `_llm_lock`, but `generate()` streams from `_llm` with no lock. `llama_cpp` is not safe for concurrent `create_chat_completion`, and the app polls other endpoints during a streaming generation; an overlapping generate (or an `unload_model` racing a stream) can segfault. Fix: hold a lock across generation and guard against unload during streaming.

### M16. Thread-local connections leak; SQLCipher KDF runs on every request
`core/database.py:33,39-53`

Werkzeug spawns a thread per request, so each request opens a fresh connection (paying expensive SQLCipher key derivation) that's only closed if that exact thread calls `close()` — which request threads never do. Connections and WAL handles leak until thread GC. Fix: a connection pool, or close-on-teardown via Flask's `teardown_appcontext`.

### M17. Stored content rendered as HTML in the edit-history diff path
`web/utils.py:145-154` (`generate_content_diff`); `web/app.py:193-210` (`close_tags` filter)

Diff output interpolates raw user content into `<del>`/`<strong>` without escaping and is emitted unescaped. Note text containing markup corrupts the edit-history display (and could execute in-origin). Self-entered, so low attack risk, but it's an escaping/data-integrity bug. Fix: HTML-escape before adding diff tags.

### M18. No single-instance / port-in-use handling in the desktop wrapper
`desktop.py:135` (`PORT = 8080`), `:39-50`, `:145`

The wrapper always binds 8080 with no fallback and no running-instance check; a conflict makes `waitress.serve` raise inside a daemon thread (invisible) and the webview loads a dead URL. A fixed `time.sleep(1.5)` replaces polling for readiness. Note the desktop path bypasses `web/cli.py` entirely, so its heartbeat monitor/signal handlers never apply — backup-on-exit relies solely on the `closing` event + atexit. Fix: probe/fallback the port and poll for server readiness.

---

## Low

These are worth a cleanup pass but are not urgent.

- **L1. macOS installed-mode detection is fragile** — `core/config.py:41-45,103-104` only matches `.app/Contents/`; run from a plain folder (as this install is), all PHI lives inside the app folder and moving/renaming/repackaging makes the app start with an empty DB. Document or harden the data-root resolution.
- **L2. Only the most recent pre-restore safety backup is reachable** — `utils/backup.py:437-443`; all `pre_restore` backups share one chain_id and overwrite each other in `get_restore_points`, hiding earlier safety nets that still exist on disk.
- **L3. `cleanup_old_backups` directory inconsistency** — `utils/backup.py:856,864,878` use the custom `backup_dir` while `delete_backup` (`:710`) / `list_backups` (`:399`) default to `BACKUPS_DIR`; legacy entries can orphan a zip (with PHI) on disk while removing it from the manifest.
- **L4. PBKDF2 (480k iterations) re-derived on every encrypt/decrypt** — `core/encryption.py:37-46`; PDF exports that decrypt many attachments in a loop pay hundreds of ms each. Cache the Fernet per password in memory.
- **L5. N+1 query patterns in the DB layer** — `get_all_link_groups` (`:1079-1111`, near-verbatim duplicate of `get_link_group`), `get_clients_due_for_deletion` (`:1897-1928`, 3 queries per client). Trivially JOIN-able.
- **L6. Money-movement routes lack double-submit protection** — `outstanding_statements.js` `generateStatements`/`confirmPayment`/`confirmWriteOff`/`markSent` (`:333,547,650,390`) don't disable their trigger button before `fetch`, risking duplicate statements/payments. `backups.js:387` and `settings.js:1544` do this correctly — copy that pattern. `mark_sent` (`statements.py:553-602`) is also non-transactional and can duplicate a communication entry on double-click.
- **L7. Stored XSS via unescaped category name** — `web/static/js/ledger_report.js:166-170` interpolates `cat.name` raw into `innerHTML` where every sibling path uses `escapeHtml`.
- **L8. Per-instance document click listeners leak in pickers** — `pickers.js:339,716`; each `DatePicker`/`TimePicker` adds a permanent `document` listener never removed, accumulating on pages that re-init pickers.
- **L9. Retention modal show/hide mechanism mismatch** — `main_view.js:424` opens with a class, `:433` closes with inline `style.display='none'`, so it can't reopen within a page load (masked only because `confirmDeletion` reloads).
- **L10. Duplicated frontend utilities** — `escapeHtml` (4 copies), three-way fee calc (6 copies), `createAutocomplete` (~140 lines in both `income.js` and `expense.js`), `autoResize` (6 copies), color palette (`color_palette.js` is entirely dead, re-implemented in `main_view.js:10-28`). Consolidate into a shared module.
- **L11. Refund tax not reversed in the ledger** — `web/blueprints/statements.py:708-757`; a negative payment records `tax_amount=0` while the original recorded pro-rata tax, overstating net tax-collected after refunds.
- **L12. Input validation gaps that surface as raw 500s** — `clients.py:350-354` (`request.form['first_name'][0]` → `IndexError` on empty), `entries.py:1144,1245,1415,1495` (`strptime` with no try/except on malformed dates).
- **L13. Naive local-time timestamps** — `web/utils.py:38,54` and widespread `int(datetime(...).timestamp())`; date-only values stored as local-midnight epoch can shift by an hour around DST/timezone changes, affecting "this month" boundaries. Store `YYYY-MM-DD` or UTC-noon.
- **L14. `search_clients` doesn't escape LIKE wildcards** — `core/database.py:693-704`; a search for `100%` or `_` matches unexpectedly (parameterized, so not injectable — just wrong results).
- **L15. Packaging inconsistencies** — `psutil` is imported (`ai/assistant.py:87,172`) and in `pyproject.toml` but missing from `requirements.txt`; AI deps are optional in pyproject but unconditionally pinned in requirements; `pytest` is a runtime requirement in requirements.txt; pyproject and requirements pin different versions/sources for `sqlcipher3`/`pypdf`. Make one source of truth.
- **L16. Dead code** — `pdf/client_export.py` `build_communication_entry`/`build_upload_entry`/`format_currency` (~140 lines, unreferenced); `backups.js` `renderFullBackup` unused param; `base.html:694` `fetchWithCSRF` defined but unused; redundant local `import sqlcipher3` in several DB methods; `get_backup_location()` stub (`backup.py:1070-1074`).
- **L17. Served attachments are inline under a CSP allowing inline scripts** — `entries.py:1783-1823` serves uploads `as_attachment=False`; `app.py:121-132` CSP uses `script-src 'self' 'unsafe-inline'`, so an uploaded HTML file would execute in-origin. Self-uploaded only. Force `Content-Disposition: attachment` for non-previewable types.
- **L18. `verify_password` leaks its test connection on failure and masks error causes** — `core/database.py:72-81`; no try/finally and a bare `except Exception: return False` makes "wrong password" indistinguishable from "file corrupt/locked".

---

## Testing assessment

The suite (`tests/test_edgecase.py`, ~940 lines) has correct isolation — per-test temp DBs with teardown (`:34-45`), no test touches a real user database — and includes genuinely strong encryption tests that verify SQLCipher rejects wrong/absent passwords via `sqlcipher3` directly (`:871-929`). That part is exemplary.

The gaps are in the highest-stakes areas:

- **No coverage of any money-movement or backup/restore path.** Statement generation, mark-paid, write-off, payment recording, and backup/restore have zero tests — these are exactly the operations where a bug costs money or data. Payment-status tests insert `statement_portions` via raw SQL (`:352-357,409-413`) instead of calling the app's payment code, so the real logic is untested.
- **Fee-calculation tests are tautological** (`:79-118,213-224,249-265`) — they re-implement the formula in the test and assert against it, so they can't catch a regression. The real three-way fee math lives in JS (six copies) and the guardian-split rounding (remainder to G2) — the odd-cent edge cases that matter — is never tested anywhere.

Highest-value additions: end-to-end statement generation (especially the guardian-split and single-guardian cases — see H3), a backup→restore round-trip asserting data equality (and WAL handling — see H1), and the redaction lock rules.

---

## What's done well

- **Encryption fundamentals are correct** — random 32-byte per-install salt stored `0600`, PBKDF2-HMAC-SHA256 at 480k iterations, Fernet authenticated encryption with a fresh IV per file (no nonce-reuse possible), and the salt included in backups so attachments remain recoverable on a new machine.
- **Parameterized SQL throughout**, with column-name whitelists (`ALLOWED_CLIENT_COLUMNS`/`ALLOWED_ENTRY_COLUMNS`) guarding the only dynamic identifier fragments. No injectable surface was found. PRAGMA key/rekey (which can't be parameterized) is correctly quote-escaped.
- **The restore architecture is sound** — pre-restore safety backup, staging directory, `.restore_marker`, and completion at startup before the DB opens. H1/H2/H4 are fixable details inside a good design.
- **The AI is genuinely local and private** — a local `llama_cpp` GGUF model; the only network call is the one-time model download. No client data leaves the machine, with sensible resource auto-tuning to RAM/platform.
- **Localhost-only by default** with an explicit, commented LAN opt-in (`web/cli.py:205-208`); the Flask secret key is persisted once, unique per install, `chmod 0600`, with env override.
- **Attachment storage hygiene** — UUID `.enc` filenames keep client info out of the filesystem, files are encrypted at rest, and the password-change re-encryption is atomic (decrypt-to-temp-then-`os.replace`, with cleanup in `finally`).
- **The redaction design is thoughtful** — refuses unlocked/billed entries, clears fee fields so redacted entries can't be re-invoiced, and keeps confidential content out of `edit_history`.

---

## Suggested fix order

1. **C1 + C2** — restore attachment embedding in client-file exports (path + decryption). Silent PHI loss.
2. **H1** — unlink WAL/SHM on restore. Corruption risk in the recovery path.
3. **H5 + M2** — stop coercing `None` to `''`, enable foreign keys (audit orphans first). Data-integrity foundation.
4. **H3** — resolve the single-guardian billing discrepancy.
5. **H2** — get the master password out of the session cookie.
6. **M1** — move money to `Decimal`/cents (touches statements, ledger, PDF reports).
7. **H6 + H7 + H8** — transaction safety: commit-before-delete, integrity-check backups, rollback on error.
8. Then work through the remaining Medium items and the Low cleanup pass; backfill tests for statements and backup/restore alongside the fixes.
