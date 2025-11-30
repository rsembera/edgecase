# EdgeCase Equalizer - Route Reference

**Purpose:** Complete route listings organized by blueprint  
**Last Updated:** November 29, 2025 - Phase 1 Complete

---

## OVERVIEW

EdgeCase has 50+ routes organized across 7 blueprints:

1. **clients_bp** - Client management, file viewing, export, session reports (15 routes)
2. **entries_bp** - Entry CRUD operations (14 routes)
3. **ledger_bp** - Income/Expense tracking and reports (10 routes)
4. **statements_bp** - Statement generation, PDF, email, payments (9 routes)
5. **scheduler_bp** - Calendar integration (2 routes)
6. **types_bp** - Client type management (4 routes)
7. **settings_bp** - Settings and configuration (11 routes)

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
**Returns:** `client_file.html` with entries organized by year/month

---

### Session Summary Report (NEW)

```python
@clients_bp.route('/client/<int:client_id>/session-report', methods=['GET'])
def session_report(client_id)
```
**Purpose:** Generate PDF summary of sessions for a date range

**GET (no params):** Show form with date range selectors

**GET (with params):** Generate PDF
- `start_year`, `start_month`, `start_day`: Start date
- `end_year`, `end_month`, `end_day`: End date
- `include_fees`: 'on' to include fees in report

**Returns:** PDF file or form template

**Use Cases:**
- Client needs attendance record
- Insurance/employer verification
- Summary without financial details

---

### Export Entries

```python
@clients_bp.route('/client/<int:client_id>/export')
def export_entries(client_id)
```
**Purpose:** Show export form with entry selection

**Returns:** `export.html` with date range and format options

---

```python
@clients_bp.route('/client/<int:client_id>/export/pdf', methods=['POST'])
def export_entries_pdf(client_id)
```
**Purpose:** Generate PDF export of selected entries

**Form Data:**
- `start_*`, `end_*`: Date range
- `entry_classes[]`: Which entry types to include
- `include_attachments`: Whether to append attachments

**Returns:** PDF file with entries and attachments

---

```python
@clients_bp.route('/client/<int:client_id>/export/markdown', methods=['POST'])
def export_entries_markdown(client_id)
```
**Purpose:** Generate Markdown export of selected entries

**Returns:** .md file download

---

### Link Group Management

```python
@clients_bp.route('/links')
def manage_links()

@clients_bp.route('/links/add', methods=['GET', 'POST'])
def add_link_group()

@clients_bp.route('/links/<int:group_id>/edit', methods=['GET', 'POST'])
def edit_link_group(group_id)

@clients_bp.route('/links/<int:group_id>/delete', methods=['POST'])
def delete_link_group(group_id)
```

---

### Other Client Routes

```python
@clients_bp.route('/client/<int:client_id>/change_type', methods=['POST'])
def change_client_type(client_id)

@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client()
```

---

## ENTRIES BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/entries.py`

### Entry Routes (all follow same pattern)

```python
# Profile (always editable, locks on first edit)
@entries_bp.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
def edit_profile(client_id)

# Session (locks on creation)
@entries_bp.route('/client/<int:client_id>/session', methods=['GET', 'POST'])
def create_session(client_id)

@entries_bp.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])
def edit_session(client_id, entry_id)

# Communication (locks on creation)
@entries_bp.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id)

@entries_bp.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])
def edit_communication(client_id, entry_id)

# Absence (locks on creation)
@entries_bp.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id)

@entries_bp.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id)

# Item (locks on creation)
@entries_bp.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id)

@entries_bp.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])
def edit_item(client_id, entry_id)

# Upload (never locks)
@entries_bp.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id)

@entries_bp.route('/client/<int:client_id>/upload/<int:entry_id>', methods=['GET', 'POST'])
def edit_upload(client_id, entry_id)
```

### Attachment Routes

```python
@entries_bp.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id)

@entries_bp.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id)

@entries_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id)
```

---

## LEDGER BLUEPRINT

**Prefix:** /ledger  
**File:** `~/edgecase/web/blueprints/ledger.py`

### Main View

```python
@ledger_bp.route('/ledger')
def ledger()
```
**Purpose:** Display all income and expense entries by year/month

---

### Income CRUD

```python
@ledger_bp.route('/ledger/income', methods=['GET', 'POST'])
def create_income()

@ledger_bp.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id)

@ledger_bp.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id)
```

---

### Expense CRUD

```python
@ledger_bp.route('/ledger/expense', methods=['GET', 'POST'])
def create_expense()

@ledger_bp.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id)

@ledger_bp.route('/ledger/expense/<int:entry_id>/delete', methods=['POST'])
def delete_expense_entry(entry_id)
```

---

### Financial Reports (NEW)

```python
@ledger_bp.route('/ledger/report')
def ledger_report()
```
**Purpose:** Show report form with date range selection

**Features:**
- From/To date selectors
- Quick buttons: Previous Year, Current Year, Year to Date
- Checkbox: Include transaction details

---

```python
@ledger_bp.route('/ledger/report/calculate')
def calculate_report()
```
**Purpose:** Calculate totals for preview (AJAX)

**Query Params:** `start_date`, `end_date`

**Returns:** JSON with totals by category

---

```python
@ledger_bp.route('/ledger/report/pdf')
def generate_report_pdf()
```
**Purpose:** Generate financial report PDF

**Query Params:**
- `start_date`, `end_date`: Date range
- `include_details`: Include transaction table

**Returns:** PDF file

---

## STATEMENTS BLUEPRINT

**Prefix:** /statements  
**File:** `~/edgecase/web/blueprints/statements.py`

### Outstanding Statements

```python
@statements_bp.route('/statements')
def outstanding_statements()
```
**Purpose:** Display statements needing action

---

### Statement Generation

```python
@statements_bp.route('/statements/find-unbilled')
def find_unbilled()
```
**Purpose:** Find clients with unbilled entries (AJAX)

---

```python
@statements_bp.route('/statements/generate', methods=['POST'])
def generate_statements()
```
**Purpose:** Generate statement entries and portions

**JSON Data:** `client_ids` (list)

---

### Statement Actions

```python
@statements_bp.route('/statements/mark-sent/<int:portion_id>', methods=['POST'])
def mark_sent(portion_id)
```
**Purpose:** Generate PDF, create Communication entry, trigger email

**Query Param:** `skip_email=1` to view PDF without sending

---

```python
@statements_bp.route('/statements/view-pdf/<int:portion_id>')
def view_pdf(portion_id)
```
**Purpose:** View statement PDF in browser without sending

---

```python
@statements_bp.route('/statements/pdf/<int:portion_id>')
def download_pdf(portion_id)
```
**Purpose:** Download statement PDF

---

```python
@statements_bp.route('/statements/mark-paid', methods=['POST'])
def mark_paid()
```
**Purpose:** Record payment (full or partial)

**JSON Data:**
- `portion_id`: Which portion
- `amount`: Payment amount
- `date`: Payment date
- `method`: Payment method

---

```python
@statements_bp.route('/statements/write-off', methods=['POST'])
def write_off()
```
**Purpose:** Write off unpaid statement

**JSON Data:**
- `portion_id`: Which portion
- `reason`: uncollectible, waived, billing_error, other
- `notes`: Optional explanation

---

```python
@statements_bp.route('/statements/send-applescript-email', methods=['POST'])
def send_applescript_email()
```
**Purpose:** Send email via AppleScript with PDF attachment

---

## SCHEDULER BLUEPRINT

**Prefix:** None  
**File:** `~/edgecase/web/blueprints/scheduler.py`

```python
@scheduler_bp.route('/client/<int:client_id>/schedule', methods=['GET', 'POST'])
def schedule_appointment(client_id)
```
**Purpose:** Create calendar event for client

**GET:** Show scheduling form with:
- Natural language date/time input
- Date/time fields
- Duration, meet link
- Repeat pattern, alerts
- Notes

**POST:** Generate event
- AppleScript: Add directly to Calendar app
- Fallback: Download .ics file

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

---

## SETTINGS BLUEPRINT

**Prefix:** None  
**File:** `~/edgecase/web/blueprints/settings.py`

```python
@settings_bp.route('/settings')
def settings_page()

@settings_bp.route('/api/practice_info', methods=['GET', 'POST'])
def practice_info()

@settings_bp.route('/upload_logo', methods=['POST'])
def upload_logo()

@settings_bp.route('/delete_logo', methods=['POST'])
def delete_logo()

@settings_bp.route('/upload_signature', methods=['POST'])
def upload_signature()

@settings_bp.route('/delete_signature', methods=['POST'])
def delete_signature()

@settings_bp.route('/api/backgrounds')
def list_backgrounds()

@settings_bp.route('/upload_background', methods=['POST'])
def upload_background()

@settings_bp.route('/delete_background', methods=['POST'])
def delete_background()

@settings_bp.route('/settings/file-number', methods=['GET', 'POST'])
def file_number_settings()
```

---

## SHARED UTILITIES (web/utils.py)

```python
def parse_date_from_form(form_data):
    """Convert year/month/day dropdowns to Unix timestamp."""

def get_today_date_parts():
    """Return dict with today's date components for form defaults."""

def save_uploaded_files(files, descriptions, entry_id, db, client_id=None):
    """Handle file uploads and create attachment records."""
```

---

*For database schema, see Database_Schema.md*  
*For design decisions, see Architecture_Decisions.md*  
*For debugging help, see Debugging_Guide.md*

*Phase 1 Complete - November 29, 2025*
