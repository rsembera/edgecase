# EdgeCase Equalizer - Route Reference

**Purpose:** Complete route listings organized by blueprint  
**Last Updated:** December 28, 2025

---

## OVERVIEW

EdgeCase has 98 routes organized across 12 blueprints:

1. **ai_bp** - AI Scribe functionality (9 routes)
2. **auth_bp** - Login/logout, session management (4 routes)
3. **backups_bp** - Backup/restore operations (9 routes)
4. **clients_bp** - Client management and file viewing (11 routes)
5. **entries_bp** - Entry CRUD operations (14 routes)
6. **ledger_bp** - Income/Expense tracking (13 routes)
7. **links_bp** - Link group management (4 routes)
8. **statements_bp** - Statement generation (9 routes)
9. **scheduler_bp** - Calendar integration (1 route)
10. **types_bp** - Client type management (4 routes)
11. **settings_bp** - Settings and configuration (16 routes)
12. **Main app.py** - Session/restore APIs (4 routes)

---

## AI BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/ai.py`

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
**Purpose:** Process text with AI (Write Up, Proofread, Expand, Contract)

**POST JSON Data:**
- `action` (str): 'write_up', 'proofread', 'expand', or 'condense'
- `text` (str): Input text to process

**Returns:** SSE stream with generated output

---

### AI Scribe Page

```python
@ai_bp.route('/ai/scribe/<int:entry_id>')
def ai_scribe(entry_id)
```
**Purpose:** Display AI Scribe interface for a specific session entry

**Returns:** `ai_scribe.html`

---

### Save AI Scribe Result

```python
@ai_bp.route('/ai/scribe/<int:entry_id>/save', methods=['POST'])
def ai_scribe_save(entry_id)
```
**Purpose:** Save AI-generated content back to session entry

**Returns:** Redirect to client file

---

## AUTH BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/auth.py`

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

## BACKUPS BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/backups.py`

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

## LINKS BLUEPRINT (EXTRACTED)

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/links.py`

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
**File:** `~/edgecase/web/blueprints/clients.py`

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
def export_entries(client_id)
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
def export_calculate(client_id)
```
**Purpose:** Calculate entry data for export preview

**Returns:** JSON with entry data

---

### Export to PDF

```python
@clients_bp.route('/client/<int:client_id>/export/pdf')
def export_pdf(client_id)
```
**Purpose:** Generate PDF of selected entries

**Returns:** PDF file

---

## ENTRIES BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/entries.py`

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

## LEDGER BLUEPRINT

**Prefix:** /ledger  
**File:** `~/edgecase/web/blueprints/ledger.py`

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
def ledger_report_page()

@ledger_bp.route('/ledger/report/calculate')
def calculate_report()

@ledger_bp.route('/ledger/report/pdf')
def generate_report_pdf()
```
**Purpose:** Generate financial reports

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
**File:** `~/edgecase/web/blueprints/statements.py`

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
@statements_bp.route('/statements/generate', methods=['POST'])
def generate_statements()
```
**Purpose:** Generate statements for unbilled entries

---

### Mark Sent / View PDF

```python
@statements_bp.route('/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id)

@statements_bp.route('/pdf/<int:portion_id>')
def get_pdf(portion_id)

@statements_bp.route('/view-pdf/<int:portion_id>')
def view_pdf(portion_id)
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
@statements_bp.route('/mark-paid', methods=['POST'])
def mark_paid()

@statements_bp.route('/write-off', methods=['POST'])
def write_off()
```
**Purpose:** Record payment or write off

---

## SCHEDULER BLUEPRINT

**Prefix:** None  
**File:** `~/edgecase/web/blueprints/scheduler.py`

```python
@scheduler_bp.route('/client/<int:client_id>/schedule', methods=['GET', 'POST'])
def schedule(client_id)
```
**Purpose:** Create calendar events

---

## TYPES BLUEPRINT

**Prefix:** None  
**File:** `~/edgecase/web/blueprints/types.py`

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
**File:** `~/edgecase/web/blueprints/settings.py`

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

## MAIN APP ROUTES

**File:** `~/edgecase/web/app.py`

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

*Last updated: December 28, 2025*
