# EdgeCase Equalizer - Route Reference

**Purpose:** Complete route listings organized by blueprint  
**Last Updated:** August 9, 2026

---

## OVERVIEW

EdgeCase has 111 routes: 107 across 11 blueprints, plus 4 app-level routes registered directly on the Flask app.

1. **ai_bp** - AI Scribe functionality (10 routes)
2. **auth_bp** - Login/logout, session management, crypto migration, recovery keys (10 routes)
3. **backups_bp** - Backup/restore operations (10 routes)
4. **clients_bp** - Client management and file viewing (11 routes)
5. **entries_bp** - Entry CRUD operations (16 routes)
6. **ledger_bp** - Income/Expense tracking (13 routes)
7. **links_bp** - Link group management (4 routes)
8. **statements_bp** - Statement generation, payment allocation (11 routes)
9. **scheduler_bp** - Calendar integration (1 route)
10. **types_bp** - Client type management (4 routes)
11. **settings_bp** - Settings and configuration (17 routes)

Plus **app.py** - Session/restore APIs (4 app-level routes, not a blueprint).

Note: `entries_bp` and `statements_bp` are now packages (`web/blueprints/entries/` and `web/blueprints/statements/`) rather than single files; the blueprint names and all route-function names are unchanged from the pre-split layout.

---

## AI BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/ai.py`

### AI Status

```python
@ai_bp.route('/api/ai/status')
def ai_status()
```
**Purpose:** Get current AI model status (loaded/not loaded, platform detection)

**Returns:** JSON with model state and platform info

---

### AI Capability Check

```python
@ai_bp.route('/api/ai/capability')
def ai_capability()
```
**Purpose:** Check if system can run AI

**Returns:** JSON with capability status and message

---

### Download Model

```python
@ai_bp.route('/api/ai/download', methods=['POST'])
def ai_download()
```
**Purpose:** Download AI model with SSE progress tracking

**Returns:** SSE stream with download progress

---

### Delete Model

```python
@ai_bp.route('/api/ai/delete', methods=['POST'])
def ai_delete()
```
**Purpose:** Delete downloaded AI model

**Returns:** JSON with success status

---

### Load Model

```python
@ai_bp.route('/api/ai/load', methods=['POST'])
def ai_load()
```
**Purpose:** Load AI model into memory

**Returns:** JSON with success status

---

### Unload Model

```python
@ai_bp.route('/api/ai/unload', methods=['POST'])
def ai_unload()
```
**Purpose:** Unload AI model from memory

**Returns:** JSON with success status

---

### Process Text

```python
@ai_bp.route('/api/ai/process', methods=['POST'])
def ai_process()
```
**Purpose:** Process text with AI (Write Up, Proofread, Expand, Condense)

**POST JSON Data:**
- `action` (str): 'write_up', 'proofread', 'expand', or 'condense'
- `text` (str): Input text to process

**Returns:** SSE stream with generated output

---

```python
@ai_bp.route('/api/ai/diff', methods=['POST'])
def ai_diff()
```
**Purpose:** Word-level diff between original and generated text for the Scribe "Show Changes" overlay. Pure text transform — no database, no model.

**POST JSON Data:**
- `original` (str): The original note text
- `generated` (str): The AI-generated text

**Returns:** JSON `{html}` — HTML-escaped diff string containing only `<del>`/`<strong>` markup (413 if either text exceeds 200k chars)

---

### AI Scribe Page

```python
@ai_bp.route('/ai/scribe/<int:entry_id>')
def scribe_page(entry_id)
```
**Purpose:** Display AI Scribe interface for a specific session entry

**Returns:** `ai_scribe.html`

---

### Save AI Scribe Result

```python
@ai_bp.route('/ai/scribe/<int:entry_id>/save', methods=['POST'])
def scribe_save(entry_id)
```
**Purpose:** Save AI-generated content back to session entry

**Returns:** Redirect to client file

---

## AUTH BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/auth.py`

### Login

```python
@auth_bp.route('/login', methods=['GET', 'POST'])
def login()
```
**Purpose:** Authenticate user and unlock encrypted database

**GET:** Show login form (different UI for first run vs returning user)

**POST Form Data:**
- `password` (str): Master password
- `confirm_password` (str): Only on first run

**First Run Behavior:**
- Requires password confirmation
- Minimum 8 characters
- Creates new encrypted database

**Returning User:**
- Validates password against existing database
- Initializes all blueprints with database connection
- Triggers auto-backup check

**Returns:** 
- Success: Redirect to main view
- Failure: Re-render with error message

---

### Logout

```python
@auth_bp.route('/logout')
def logout()
```
**Purpose:** Close database and clear session

**Returns:** Redirect to login

---

### Change Password

```python
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password()
```
**Purpose:** Change master password (SQLCipher PRAGMA rekey)

**POST Form Data:**
- `current_password` (str)
- `new_password` (str): Minimum 8 characters
- `confirm_password` (str)

**Returns:** 
- Success: Redirect to settings with flash message
- Failure: Re-render with error

---

### Change Password Progress

```python
@auth_bp.route('/change-password-progress')
def change_password_progress()
```
**Purpose:** SSE endpoint for password change progress updates

**Returns:** SSE stream with progress events

---

### Migrate Stream

```python
@auth_bp.route('/migrate/stream')
def migrate_stream()
```
**Purpose:** SSE endpoint that runs the v1→v2 encryption migration during login (Argon2id / AES-256-GCM upgrade), driving the `upgrading.html` interstitial and completing the login once migration finishes. Only reached when an existing v1 install is detected at login.

**Returns:** SSE stream with migration progress events

### Rotate Stream

```python
@auth_bp.route('/rotate/stream')
def rotate_stream()
```
**Purpose:** SSE endpoint that performs (or resumes) a master-key rotation
during login and then completes the login, driving `rotating.html`. Reached
only when `core.master_rotation.rotation_pending()` is true at login (armed
from Settings, or a run was interrupted); the login POST verifies the
password against the key file — not by opening the database — and hands it
over through the same single-use server-side token as `/migrate/stream`.
The rotation runs on a worker thread with `progress_cb=queue.put`; this
generator drains the queue, so the screen gets a real per-file bar. Its own
`complete` event is emitted only after the rotated database is open and the
new recovery key is parked in the handoff; the redirect goes to
`/recovery-key`.

**Returns:** SSE stream — `backing_up` / `counting` / `checking` /
`encrypting` (current/total) / `database` / `finalizing` / `complete`, or
`error` with `in_progress` saying whether the run will resume at next login.

### Rotate Master Key (arm)
```python
@auth_bp.route('/rotate-master-key', methods=['GET', 'POST'])
@login_required
def rotate_master_key():
```
Settings → Security. **Requires the master password.** Arms a rotation for
the next login by writing `.rotate_pending`; nothing else changes now. The
screen states what rotation revokes and that it does not protect
pre-rotation backups. v3 installs only (redirects to Settings otherwise).

### Cancel Master-Key Rotation
```python
@auth_bp.route('/rotate-master-key/cancel', methods=['POST'])
@login_required
def cancel_master_key_rotation():
```
Withdraws an armed rotation. Refused once a run has started (state file or
`rotate_master` marker present): the state may already describe files under
the new master, and forgetting it would strand them. Settings shows the
resulting state either way.

---

## BACKUPS BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/backups.py`


### Recovery Key (display + acknowledgement)
```python
@auth_bp.route('/recovery-key', methods=['GET', 'POST'])
@login_required
def recovery_key():
```
Shows a freshly issued recovery key and takes the user's acknowledgement.
Reached from `/migrate/stream` after a v3 migration, and from
`/recovery-key/regenerate`. The key is held server-side (never in the signed
session cookie) and read **without** consuming, so a refresh does not destroy
the only copy. Acknowledgement is a checkbox, validated server-side; ticking
it clears `.rk_pending`.

### Regenerate Recovery Key
```python
@auth_bp.route('/recovery-key/regenerate', methods=['GET', 'POST'])
@login_required
def regenerate_recovery_key():
```
Issues a fresh recovery key, retiring the previous one. **Requires the master
password** — it mints a new full-access credential, so an unattended session
must not be able to do it. Redirects into `/recovery-key` for display.
Reachable from Settings → Security and from the pending banner.

### Verify Recovery Key
```python
@auth_bp.route('/recovery-key/verify', methods=['GET', 'POST'])
@login_required
def verify_recovery_key():
```
Checks whether a key opens the install, **changing nothing** — no rewrap, no
write, no cache clear. Session-gated rather than password-gated: it writes
nothing and reveals nothing an attacker gains from, so gating it harder would
only discourage the checking it exists to encourage. Reachable from Settings →
Security.

### Recover (recovery-key login)
```python
@auth_bp.route('/recover', methods=['GET', 'POST'])
```
**Unauthenticated by necessity** — the route for someone who cannot log in.
In `require_login`'s allowed list; gated by the recovery key itself plus the
same rate limiter as `/login`. A *malformed* key does not spend an attempt; a
well-formed but wrong key does. Offered on the login page only when the
install actually has a recovery key.

### Recover — Set New Password
```python
@auth_bp.route('/recover/reset', methods=['GET', 'POST'])
```
Sets a new master password after a verified recovery key. Requires the
server-side handoff token issued by `/recover`, so the key check cannot be
skipped. Warns before committing and offers Cancel. Does **not** auto-login:
the user has typed the new password exactly twice, so signing in with it is
the cheapest confirmation it is what they think it is. The recovery key is
deliberately left valid.

### Backups Page

```python
@backups_bp.route('/backups')
def backups_page()
```
**Purpose:** Display backup management interface

**Returns:** `backups.html`

---

### Backup Status

```python
@backups_bp.route('/api/backup/status')
def backup_status()
```
**Purpose:** Get current backup status and settings

**Returns:** JSON with:
- `last_full`, `last_incremental` timestamps
- `frequency` setting
- `location` (empty = default)
- `cloud_folders` list
- `restore_pending` boolean

---

### Save Backup Settings

```python
@backups_bp.route('/api/backup/settings', methods=['POST'])
def save_backup_settings()
```
**Purpose:** Save backup frequency and location

**POST JSON Data:**
- `frequency` (str): 'daily', 'weekly', 'manual'
- `location` (str): Path or empty for default

**Returns:** JSON with success status

---

### Backup Now

```python
@backups_bp.route('/api/backup/now', methods=['POST'])
def backup_now()
```
**Purpose:** Trigger immediate backup (auto-decides full vs incremental)

**Returns:** JSON with:
- `success` boolean
- `message` string
- `backup` object or null if no changes

---

### List Backups

```python
@backups_bp.route('/api/backup/list')
def list_backups()
```
**Purpose:** List all backup files

**Returns:** JSON with `backups` array

**Note:** Backup deletion is handled automatically via retention settings. Old backup chains are cleaned up based on the configured retention period (1 month, 6 months, 1 year, or forever).

---

### Restore Points

```python
@backups_bp.route('/api/backup/restore-points')
def restore_points()
```
**Purpose:** Get available restore points

**Returns:** JSON with `restore_points` array (includes valid restore chains)

---

### Prepare Restore

```python
@backups_bp.route('/api/backup/prepare-restore', methods=['POST'])
def prepare_restore()
```
**Purpose:** Stage restore files (completes on next app start)

**POST JSON Data:**
- `restore_point` or `restore_point_id` (str)

**Returns:** JSON with success status and staging path

---

### Cancel Restore

```python
@backups_bp.route('/api/backup/cancel-restore', methods=['POST'])
def cancel_restore()
```
**Purpose:** Cancel pending restore

**Returns:** JSON with success status

---

### Cloud Folders

```python
@backups_bp.route('/api/backup/cloud-folders')
def cloud_folders()
```
**Purpose:** Detect available cloud sync folders

**Returns:** JSON with `folders` array (iCloud, Dropbox, Google Drive)

---

### List Folders (Folder Picker)

```python
@backups_bp.route('/api/backup/list-folders')
def list_folders()
```
**Purpose:** List folders at a given path for the folder picker modal

**Query Params:**
- `path` (str): Directory path to list (defaults to home directory)

**Returns:** JSON with:
- `current_path`: The resolved absolute path
- `parent_path`: Parent directory (null if at root)
- `folders`: List of {name, path, inaccessible?} for subdirectories
- `error`: Error message if path is invalid

**Notes:** Excludes hidden folders (dotfiles). Used by the backup location folder picker UI.

---

## LINKS BLUEPRINT (EXTRACTED)

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/links.py`

### Manage Links

```python
@links_bp.route('/links')
def manage_links()
```
**Purpose:** Display all link groups

**Returns:** `manage_links.html` with all groups and members

---

### Add Link Group

```python
@links_bp.route('/links/add', methods=['GET', 'POST'])
def add_link_group()
```
**Purpose:** Create new link group

**GET:** Show form with active clients (excludes Inactive/Deleted)

**POST JSON Data:**
- `client_ids` (list): Member IDs (min 2)
- `format` (str): 'couples', 'family', or 'group'
- `session_duration` (int): Default duration
- `member_fees` (dict): {client_id: {base, tax, total}}

**Returns:** 204 No Content on success

---

### Edit Link Group

```python
@links_bp.route('/links/<int:group_id>/edit', methods=['GET', 'POST'])
def edit_link_group(group_id)
```
**Purpose:** Edit existing link group

**GET:** Show form with current group data

**POST JSON Data:** Same as add_link_group

**Returns:** 204 No Content on success

---

### Delete Link Group

```python
@links_bp.route('/links/<int:group_id>/delete', methods=['POST'])
def delete_link_group(group_id)
```
**Purpose:** Delete link group

**Returns:** 204 No Content on success

---

## CLIENTS BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/clients.py`

### Main View

```python
@clients_bp.route('/')
def index()
```
**Purpose:** Display client list with filtering, sorting, searching

**Query Params:**
- `type` (list): Filter by client type IDs
- `sort` (str): Sort field (file_number, last_name, first_name, created, last_session)
- `order` (str): Sort order (asc, desc)
- `search` (str): Search term
- `view` (str): View mode (detailed, compact)

**Returns:** `main_view.html` with client list and stats

---

### Client File View

```python
@clients_bp.route('/client/<int:client_id>')
def client_file(client_id)
```
**Purpose:** Display client's entry timeline grouped by year/month

**Query Params:**
- `class` (list): Filter by entry classes

**Returns:** `client_file.html` with entries organized by year/month

---

### Change Client Type

```python
@clients_bp.route('/client/<int:client_id>/change_type', methods=['POST'])
def change_client_type(client_id)
```
**Purpose:** Change client's type via dropdown

**Form Data:**
- `type_id` (int): New type ID

**Special Behavior:**
- If changing to "Inactive", removes client from all link groups

**Returns:** Redirect to client_file or profile

---

### Add Client

```python
@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client()
```
**Purpose:** Create new client with auto-generated file number

**POST Form Data:**
- `first_name`, `middle_name`, `last_name`
- `type_id` (int)
- `session_offset` (int): Starting session number
- `file_number`: May be auto-generated

**Returns:** Redirect to client_file to create profile

---

### Retention Check

```python
@clients_bp.route('/api/retention-check')
def retention_check()
```
**Purpose:** Check for clients with expired retention periods

**Returns:** JSON with clients ready for deletion

---

### Retention Delete

```python
@clients_bp.route('/api/retention-delete', methods=['POST'])
def retention_delete()
```
**Purpose:** Archive and delete client after retention expires

**Returns:** JSON with success status

---

### Deleted Clients

```python
@clients_bp.route('/deleted-clients')
def deleted_clients()
```
**Purpose:** View soft-deleted clients

**Returns:** `deleted_clients.html`

---

### Export Entries

```python
@clients_bp.route('/client/<int:client_id>/export')
def export_client(client_id)
```
**Purpose:** Show export options

**Returns:** `export.html`

---

### Session Report

```python
@clients_bp.route('/client/<int:client_id>/session-report', methods=['GET'])
def session_report(client_id)
```
**Purpose:** Generate PDF summary of sessions

**Query Params:**
- `start_date`, `end_date`
- `include_fees` (bool)

**Returns:** PDF file or form

---

### Export Calculate

```python
@clients_bp.route('/client/<int:client_id>/export/calculate')
def calculate_export(client_id)
```
**Purpose:** Calculate entry data for export preview

**Returns:** JSON with entry data

---

### Export to PDF

```python
@clients_bp.route('/client/<int:client_id>/export/pdf')
def export_client_pdf(client_id)
```
**Purpose:** Generate PDF of selected entries

**Returns:** PDF file

---

## ENTRIES BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/Applications/edgecase/web/blueprints/entries/` (package: common + per-type modules)

### Profile Entry

```python
@entries_bp.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
def edit_profile(client_id)
```
**Purpose:** Create or edit client profile

**POST Form Data:**
- Demographics, contact info, emergency contact
- Session fee fields (base, tax rate, total)
- Guardian billing fields (for minors)

**Returns:** Redirect to client_file

---

### Session Entry

```python
@entries_bp.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id)

@entries_bp.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])
def edit_session(client_id, entry_id)
```
**Purpose:** Create/edit therapy session

**Returns:** Redirect to client_file

---

### Communication Entry

```python
@entries_bp.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id)

@entries_bp.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])
def edit_communication(client_id, entry_id)
```
**Purpose:** Log communications

**Returns:** Redirect to client_file

---

### Absence Entry

```python
@entries_bp.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id)

@entries_bp.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id)
```
**Purpose:** Log cancellations/no-shows

**Returns:** Redirect to client_file

---

### Item Entry

```python
@entries_bp.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id)

@entries_bp.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])
def edit_item(client_id, entry_id)
```
**Purpose:** Billable items

**Returns:** Redirect to client_file

---

### Upload Entry

```python
@entries_bp.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id)

@entries_bp.route('/client/<int:client_id>/upload/<int:entry_id>', methods=['GET', 'POST'])
def edit_upload(client_id, entry_id)
```
**Purpose:** Manage file attachments

**Returns:** Redirect to client_file

---

### Attachment Operations

```python
@entries_bp.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id)

@entries_bp.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id)

@entries_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id)
```
**Purpose:** Download, view, delete attachments

---

### Entry Redaction

```python
@entries_bp.route('/client/<int:client_id>/redact/<int:entry_id>', methods=['POST'])
def redact_entry(client_id, entry_id)
```
**Purpose:** Permanently redact entry content for privacy protection

**POST Form Data:**
- `reason` (str): Reason for redaction (required, min 10 chars)

**Requirements:**
- Entry must be locked
- Entry must not be billed (statement_id is NULL)
- Entry must not already be redacted

**Clears:** content, mood, affect, risk_assessment, comm_recipient, additional_info, session_number, duration, all fee fields

**Returns:** Redirect to client_file

---

```python
@entries_bp.route('/client/<int:client_id>/redacted/<int:entry_id>')
def view_redacted_entry(client_id, entry_id)
```
**Purpose:** View redacted entry metadata

**Returns:** `view_redacted.html` showing entry type, entry date, created date, redaction details

---

## LEDGER BLUEPRINT

**Prefix:** /ledger  
**File:** `~/Applications/edgecase/web/blueprints/ledger.py`

### Ledger Main View

```python
@ledger_bp.route('/ledger')
def ledger()
```
**Purpose:** Display all income and expense entries

**Returns:** `ledger.html`

---

### Income Entry

```python
@ledger_bp.route('/ledger/income', methods=['GET', 'POST'])
def create_income()

@ledger_bp.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id)

@ledger_bp.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id)
```
**Purpose:** Track income

---

### Expense Entry

```python
@ledger_bp.route('/ledger/expense', methods=['GET', 'POST'])
def create_expense()

@ledger_bp.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id)

@ledger_bp.route('/ledger/expense/<int:entry_id>/delete', methods=['POST'])
def delete_expense_entry(entry_id)
```
**Purpose:** Track expenses

---

### Financial Report

```python
@ledger_bp.route('/ledger/report')
def ledger_report()

@ledger_bp.route('/ledger/report/calculate')
def calculate_report()

@ledger_bp.route('/ledger/report/pdf')
def generate_report_pdf()
```
**Purpose:** Generate financial reports

**Query Params (for /pdf):**
- `start_date`, `end_date` - Date range
- `include_income`, `include_expenses` - Filter by type
- `attachments` - Include receipt/invoice appendix (1 or 0)

---

### Autocomplete Suggestion Removal

```python
@ledger_bp.route('/ledger/suggestion/payee/remove', methods=['POST'])
def remove_payee_suggestion()

@ledger_bp.route('/ledger/suggestion/category/remove', methods=['POST'])
def remove_category_suggestion()

@ledger_bp.route('/ledger/suggestion/payor/remove', methods=['POST'])
def remove_payor_suggestion()
```
**Purpose:** Remove autocomplete suggestions from dropdowns

---

## STATEMENTS BLUEPRINT

**Prefix:** /statements  
**File:** `~/Applications/edgecase/web/blueprints/statements/` (package: common + views/generation/payments/delivery)

### Outstanding Statements

```python
@statements_bp.route('/')
def outstanding_statements()
```
**Purpose:** View all statements with payment status

**Returns:** `outstanding_statements.html`

---

### Find Unbilled Entries

```python
@statements_bp.route('/find-unbilled', methods=['GET'])
def find_unbilled()
```
**Purpose:** Find clients with unbilled entries for statement generation

**Returns:** JSON with unbilled clients and entries

---

### Generate Statements

```python
@statements_bp.route('/generate', methods=['POST'])
def generate_statements()
```
**Purpose:** Generate statements for unbilled entries

---

### Mark Sent / View PDF

```python
@statements_bp.route('/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id)

@statements_bp.route('/pdf/<int:portion_id>')
def download_statement_pdf(portion_id)

@statements_bp.route('/view-pdf/<int:portion_id>')
def view_statement_pdf(portion_id)
```
**Purpose:** Mark statement as sent, generate PDF, or view PDF in browser

---

### Send via AppleScript

```python
@statements_bp.route('/send-applescript-email', methods=['POST'])
def send_applescript_email()
```
**Purpose:** Send statement email via AppleScript (Mac only)

---

### Payment Operations

```python
@statements_bp.route('/payment-proposal', methods=['GET'])
def payment_proposal()

@statements_bp.route('/record-payment', methods=['POST'])
def record_payment()

@statements_bp.route('/write-off', methods=['POST'])
def write_off_statement()
```
**Purpose:** Record a payment against a payer, or write off a statement

`payment-proposal` (query: `portion_id`, optional `amount`) resolves the
payer behind a portion and returns every open statement for them, oldest
first, with a proposed split. The modal calls it again whenever the amount
changes, so the oldest-first arithmetic lives only in
`core/billing.propose_allocation` and never in JavaScript.

`record-payment` takes `portion_id` (any portion of the payer),
`payment_amount`, optional `payment_date` (YYYY-MM-DD, defaults to today),
optional `notes`, and an optional `allocations` list of
`{portion_id, amount}`. Omitting `allocations` applies the oldest-first
proposal. It writes ONE income entry plus a `payment_allocations` row per
statement settled, and holds any remainder as credit — all in one
transaction. Allocations naming another payer's portion, another client's
portion, an unsent statement, or more than that statement has outstanding
are rejected before anything is written.

**Removed 2026-08-09:** `mark-paid` / `mark_paid`. It could only express a
payment against a single statement, which was the defect `record_payment`
exists to fix; keeping both would have meant two UIs for one operation. Its
never-reachable negative-amount refund branch went with it — see
`docs/Payment_Allocation_Plan.md`.

---

## SCHEDULER BLUEPRINT

**Prefix:** None  
**File:** `~/Applications/edgecase/web/blueprints/scheduler.py`

```python
@scheduler_bp.route('/client/<int:client_id>/schedule', methods=['GET', 'POST'])
def schedule_for_client(client_id)
```
**Purpose:** Create calendar events for appointments

**GET:** Shows schedule form with:
- Client's default session duration from profile
- Link group durations for couples/family/group formats
- Consultation duration from settings
- Meeting link from client profile (auto-populates for videoconference)

**POST Form Data:**
- `date`, `appointment_time` - When
- `modality` - in-person, videoconference, telephone
- `format` - individual, couples, family, group
- `is_consultation` - Consultation checkbox
- `duration` - Session length in minutes
- `meet_link` - Video conferencing URL (only used for videoconference modality)
- `repeat` - none, weekly, biweekly, monthly
- `alert1`, `alert2` - Reminder settings
- `notes` - Additional notes for calendar event

**Returns:** .ics file download or AppleScript Calendar addition

---

## TYPES BLUEPRINT

**Prefix:** None  
**File:** `~/Applications/edgecase/web/blueprints/types.py`

```python
@types_bp.route('/types')
def manage_types()

@types_bp.route('/add_type', methods=['GET', 'POST'])
def add_type()

@types_bp.route('/edit_type/<int:type_id>', methods=['GET', 'POST'])
def edit_type(type_id)

@types_bp.route('/types/<int:type_id>/delete', methods=['POST'])
def delete_type(type_id)
```
**Purpose:** Manage client types

---

## SETTINGS BLUEPRINT

**Prefix:** None  
**File:** `~/Applications/edgecase/web/blueprints/settings.py`

### Settings Page

```python
@settings_bp.route('/settings')
def settings_page()
```
**Purpose:** Display settings page

---

### File Number Settings

```python
@settings_bp.route('/settings/file-number', methods=['GET', 'POST'])
def file_number_settings()
```
**Purpose:** Configure file number format (manual, date-initials, prefix-counter)

---

### Practice Info

```python
@settings_bp.route('/api/practice_info', methods=['GET', 'POST'])
def practice_info()
```
**Purpose:** Get/save practice information (name, address, credentials, etc.)

---

### Background Images

```python
@settings_bp.route('/api/backgrounds')
def list_backgrounds()

@settings_bp.route('/upload_background', methods=['POST'])
def upload_background()

@settings_bp.route('/delete_background', methods=['POST'])
def delete_background()
```
**Purpose:** Manage background images for main view

---

### Logo and Signature

```python
@settings_bp.route('/view_logo')
def view_logo()

@settings_bp.route('/view_signature')
def view_signature()

@settings_bp.route('/upload_logo', methods=['POST'])
def upload_logo()

@settings_bp.route('/upload_signature', methods=['POST'])
def upload_signature()

@settings_bp.route('/delete_logo', methods=['POST'])
def delete_logo()

@settings_bp.route('/delete_signature', methods=['POST'])
def delete_signature()
```
**Purpose:** Manage practice logo and signature images for PDFs

---

### Calendar Settings

```python
@settings_bp.route('/api/calendar_settings', methods=['GET', 'POST'])
def calendar_settings()
```
**Purpose:** Configure calendar integration (method, calendar name)

---

### Statement Settings

```python
@settings_bp.route('/api/statement_settings', methods=['GET', 'POST'])
def statement_settings()
```
**Purpose:** Configure statement email body and payment instructions

---

### Security Settings

```python
@settings_bp.route('/api/security_settings', methods=['GET', 'POST'])
def security_settings()
```
**Purpose:** Configure session timeout

---

### Time Format

```python
@settings_bp.route('/api/time_format', methods=['GET', 'POST'])
def time_format()
```
**Purpose:** Configure 12h/24h time display format

---

### Reset Database

```python
@settings_bp.route('/api/reset_database', methods=['POST'])
def reset_database()
```
**Purpose:** Wipe and re-initialise the database from scratch. Destructive admin action — requires the master password and the user typing "RESET" to confirm.

**Returns:** JSON with success status

---

## MAIN APP ROUTES

**File:** `~/Applications/edgecase/web/app.py`

### Session Status

```python
@app.route('/api/session-status')
def session_status()
```
**Purpose:** Get current session status and timeout info

---

### Keepalive

```python
@app.route('/api/keepalive', methods=['POST'])
def keepalive()
```
**Purpose:** Reset session timeout on user activity

---

### Heartbeat

```python
@app.route('/api/heartbeat')
def heartbeat()
```
**Purpose:** Check if session is still active

---

### Restore Message

```python
@app.route('/api/restore-message')
def get_restore_message()
```
**Purpose:** Get pending restore completion message

---

## SHARED UTILITIES (web/utils.py)

```python
def parse_date_from_form(form_data)
def get_today_date_parts()
def save_uploaded_files(files, descriptions, entry_id, db, client_id=None)
```

---

*For database schema, see Database_Schema.md*  
*For design decisions, see Architecture_Decisions.md*

*Last updated: June 21, 2026*
