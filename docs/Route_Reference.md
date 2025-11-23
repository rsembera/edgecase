# EdgeCase Equalizer - Route Reference

**Purpose:** Complete route listings organized by blueprint  
**Last Updated:** November 23, 2025

---

## OVERVIEW

EdgeCase has 30+ routes organized across 5 blueprints:

1. **clients_bp** - Client management and file viewing (11 routes)
2. **entries_bp** - Entry CRUD operations (14 routes)
3. **ledger_bp** - Income/Expense tracking (7 routes)
4. **types_bp** - Client type management (4 routes)
5. **settings_bp** - Settings and configuration (11 routes)

**Plus:** 2 placeholder routes in main app.py

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

**Key Features:**
- Active client count, sessions this week, pending invoices, billable this month
- Color-coded by client type
- Payment status indicators (green/yellow/red)
- Smart phone display based on preferred contact
- Link group detection (🔗 icon)

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

**Key Features:**
- Profile entry pinned at top
- Year/month grouping with expand/collapse
- Entry sorting by date, time (manual or created_at), created_at
- Session/consultation/absence counts
- Linked client groups displayed
- Real-time class filtering

**Sorting Logic:**
```python
def get_entry_sort_key(e):
    # Primary: date field
    # Secondary: manual time or created_at time
    # Tertiary: created_at timestamp
    return (date_val, time_val, created_val)
```

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
- Cleans up link groups with <2 members

**Returns:** Redirect to client_file or profile (depending on referrer)

---

### Add Client

```python
@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client()
```
**Purpose:** Create new client with auto-generated file number

**GET:** Show form with file number preview based on settings

**POST Form Data:**
- `first_name`, `middle_name`, `last_name`
- `type_id` (int)
- `session_offset` (int): Starting session number for migrated clients
- `file_number`: May be auto-generated based on format setting

**File Number Generation:**
- **Manual:** User provides file number
- **Date-Initials:** YYYYMMDD-ABC (auto-generated)
- **Prefix-Counter:** PREFIX-0001-SUFFIX (auto-incremented)

**Returns:** Redirect to client_file to create profile

---

### Link Group Management

```python
@clients_bp.route('/links')
def manage_links()
```
**Purpose:** Display all link groups  
**Returns:** `manage_links.html` with all groups and members

---

```python
@clients_bp.route('/links/add', methods=['GET', 'POST'])
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

```python
@clients_bp.route('/links/<int:group_id>/edit', methods=['GET', 'POST'])
def edit_link_group(group_id)
```
**Purpose:** Edit existing link group

**GET:** Show form with current group data

**POST JSON Data:** Same as add_link_group

**Returns:** 204 No Content on success

---

```python
@clients_bp.route('/links/<int:group_id>/delete', methods=['POST'])
def delete_link_group(group_id)
```
**Purpose:** Delete link group  
**Returns:** 204 No Content on success

---

## ENTRIES BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/entries.py`

**Pattern:** All entry types follow same structure:
- GET route shows form
- POST route creates/updates entry
- Uses shared utilities from `web/utils.py`

---

### Profile Entry

```python
@entries_bp.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])
def edit_profile(client_id)
```
**Purpose:** Create or edit client profile (always editable)

**POST Form Data:**
- Demographics: first_name, middle_name, last_name, date_of_birth, gender
- Contact: email, phone, home_phone, work_phone, text_number, address
- Preferences: preferred_contact, ok_to_leave_message
- Emergency: emergency_contact_name, emergency_contact_phone, emergency_contact_relationship
- Additional: referral_source, additional_info
- Fee Override: fee_override_base, fee_override_tax_rate, fee_override_total, default_session_duration
- Guardian: is_minor, guardian1_*, has_guardian2, guardian2_*

**Special Behavior:**
- Locks on first edit (not on creation)
- Updates client record (first_name, middle_name, last_name, file_number)
- Tracks ALL field changes including name and file number

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

**POST Form Data:**
- Date: year, month, day (converted by parse_date_from_form)
- Time: session_time (free text, e.g., "2:00 PM")
- Details: modality, format, service, duration
- Fees: base_fee, tax_rate, fee
- Clinical: mood, affect, risk_assessment
- Content: content (Markdown)
- Flags: is_consultation, is_pro_bono
- Draft: save_draft (if '1', entry not locked)

**Fee Calculation Sources (priority order):**
1. Profile Fee Override (if set)
2. Link Group fees (if format is couples/family/group)
3. Error if link group required but doesn't exist

**Special Behavior:**
- Auto-generates session_number (chronological order)
- Consultation: fee=0, excluded from numbering
- Pro Bono: fee=0, included in numbering, marked in description
- Renumbers all sessions after save to maintain order
- Locks on creation (unless draft save)
- Edit history tracks all changes with smart diff

**Returns:** Redirect to client_file

**Navigation:** Prev/Next buttons to adjacent sessions (by date)

---

### Communication Entry

```python
@entries_bp.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])
def create_communication(client_id)

@entries_bp.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])
def edit_communication(client_id, entry_id)
```
**Purpose:** Log emails, calls, administrative notes

**POST Form Data:**
- Date: year, month, day
- Time: comm_time (free text)
- Details: description, comm_recipient, comm_type
- Content: content (Markdown)

**Options:**
- comm_recipient: 'to_client', 'from_client', 'internal_note'
- comm_type: 'email', 'phone', 'text', 'administrative'

**Returns:** Redirect to client_file

**Navigation:** Prev/Next buttons to adjacent communications

---

### Absence Entry

```python
@entries_bp.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])
def create_absence(client_id)

@entries_bp.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])
def edit_absence(client_id, entry_id)
```
**Purpose:** Log cancellations and no-shows with optional fees

**POST Form Data:**
- Date: absence_date (YYYY-MM-DD string converted to timestamp)
- Time: absence_time (free text)
- Details: description
- Fees: base_price, tax_rate, fee (three-way calculation)
- Content: content (Markdown)

**Returns:** Redirect to client_file

---

### Item Entry

```python
@entries_bp.route('/client/<int:client_id>/item', methods=['GET', 'POST'])
def create_item(client_id)

@entries_bp.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])
def edit_item(client_id, entry_id)
```
**Purpose:** Billable items (books, letters, reports)

**POST Form Data:**
- Date: item_date (hidden field set by JS)
- Time: item_time (free text)
- Details: description
- Fees: base_price, tax_rate, fee (three-way calculation)
- Content: content (Markdown)

**Special:** Always billable, always locks on creation

**Returns:** Redirect to client_file

---

### Upload Entry

```python
@entries_bp.route('/client/<int:client_id>/upload', methods=['GET', 'POST'])
def create_upload(client_id)

@entries_bp.route('/client/<int:client_id>/upload/<int:entry_id>', methods=['GET', 'POST'])
def edit_upload(client_id, entry_id)
```
**Purpose:** Manage file attachments (consent forms, intake docs, etc.)

**POST Form Data:**
- Date: year, month, day
- Time: upload_time (free text)
- Details: description
- Content: content (Markdown)
- Files: files[] (list), file_descriptions[] (list)

**Special Behavior:**
- Never locked (always editable)
- Multiple file upload support
- Edit history tracks file additions/deletions
- Uses save_uploaded_files() utility

**Returns:** Redirect to client_file

---

### Attachment Operations

```python
@entries_bp.route('/attachment/<int:attachment_id>/download')
def download_attachment(attachment_id)
```
**Purpose:** Download attachment file  
**Returns:** File with as_attachment=True (browser saves to Downloads)

---

```python
@entries_bp.route('/attachment/<int:attachment_id>/view')
def view_attachment(attachment_id)
```
**Purpose:** View attachment in browser  
**Returns:** File with as_attachment=False (opens in browser if possible)

---

```python
@entries_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id)
```
**Purpose:** Delete attachment file and database record

**Special Behavior:**
- Deletes file from disk
- Deletes database record
- Adds to edit history (for Upload entries)

**Returns:** 200 OK (empty response for AJAX)

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

**Returns:** `ledger.html` with entries organized by year/month

**Key Features:**
- Income in green, expenses in red
- Year/month grouping
- Payee and category names resolved
- Attachment counts displayed

---

### Income Entry

```python
@ledger_bp.route('/ledger/income', methods=['GET', 'POST'])
def create_income()

@ledger_bp.route('/ledger/income/<int:entry_id>', methods=['GET', 'POST'])
def edit_income(entry_id)
```
**Purpose:** Track income received

**POST Form Data:**
- Date: year, month, day (converted by parse_date_from_form)
- Details: source (who paid)
- Amounts: total_amount, tax_amount
- Content: description, content (Markdown)
- Files: files[], file_descriptions[]

**Special Behavior:**
- client_id is NULL (not tied to client)
- ledger_type = 'income'
- Never locked (editable accounting)
- Uses save_uploaded_files() utility

**Returns:** Redirect to ledger

---

```python
@ledger_bp.route('/ledger/income/<int:entry_id>/delete', methods=['POST'])
def delete_income_entry(entry_id)
```
**Purpose:** Delete income entry and attachments

**Returns:** 200 OK on success, 500 on error

---

### Expense Entry

```python
@ledger_bp.route('/ledger/expense', methods=['GET', 'POST'])
def create_expense()

@ledger_bp.route('/ledger/expense/<int:entry_id>', methods=['GET', 'POST'])
def edit_expense(entry_id)
```
**Purpose:** Track business expenses

**POST Form Data:**
- Date: year, month, day
- Payee: payee_id (or 'new' with new_payee_name)
- Category: category_id (or 'new' with new_category_name)
- Amounts: total_amount, tax_amount
- Content: description, content (Markdown)
- Files: files[], file_descriptions[]

**Special Behavior:**
- Can create new payee/category on the fly
- client_id is NULL
- ledger_type = 'expense'
- Never locked
- Uses save_uploaded_files() utility

**Returns:** Redirect to ledger

---

```python
@ledger_bp.route('/ledger/expense/<int:entry_id>/delete', methods=['POST'])
def delete_expense_entry(entry_id)
```
**Purpose:** Delete expense entry and attachments

**Returns:** 200 OK on success, 500 on error

---

## TYPES BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/types.py`

### Manage Types

```python
@types_bp.route('/types')
def manage_types()
```
**Purpose:** Display all client types (locked and editable sections)

**Returns:** `manage_types.html` with locked_types and editable_types

---

### Add Type

```python
@types_bp.route('/add_type', methods=['GET', 'POST'])
def add_type()
```
**Purpose:** Create new client type

**POST Form Data:**
- name (max 9 chars)
- color, color_name, bubble_color
- retention_value, retention_unit (converted to days)

**Returns:** Redirect to /types

---

### Edit Type

```python
@types_bp.route('/edit_type/<int:type_id>', methods=['GET', 'POST'])
def edit_type(type_id)
```
**Purpose:** Edit existing client type

**Special:** Cannot edit locked types (Inactive, Deleted)

**POST Form Data:** Same as add_type

**Returns:** Redirect to /types

---

### Delete Type

```python
@types_bp.route('/types/<int:type_id>/delete', methods=['POST'])
def delete_type(type_id)
```
**Purpose:** Delete client type (AJAX)

**Validation:**
- Cannot delete if clients assigned
- Cannot delete locked types
- Cannot delete last editable type

**Returns:** JSON with success/error

---

## SETTINGS BLUEPRINT

**Prefix:** None (mounted at root)  
**File:** `~/edgecase/web/blueprints/settings.py`

### Settings Page

```python
@settings_bp.route('/settings')
def settings_page()
```
**Purpose:** Display settings page  
**Returns:** `settings.html`

---

### Practice Info

```python
@settings_bp.route('/api/practice_info', methods=['GET', 'POST'])
def practice_info()
```
**Purpose:** Get/save practice information (AJAX)

**GET Returns:** JSON with all practice settings

**POST JSON Data:**
- practice_name, therapist_name, credentials
- email, phone, address, website
- currency
- consultation_base_price, consultation_tax_rate, consultation_fee, consultation_duration

**Returns:** JSON with success status

---

### Logo Upload

```python
@settings_bp.route('/upload_logo', methods=['POST'])
def upload_logo()
```
**Purpose:** Upload practice logo

**Form Data:** `logo` (file)

**Validation:** png, jpg, jpeg, gif only

**Storage:** `~/edgecase/assets/logo.{ext}`

**Returns:** JSON with success and filename

---

```python
@settings_bp.route('/delete_logo', methods=['POST'])
def delete_logo()
```
**Purpose:** Delete practice logo  
**Returns:** JSON with success status

---

### Signature Upload

```python
@settings_bp.route('/upload_signature', methods=['POST'])
def upload_signature()
```
**Purpose:** Upload digital signature

**Form Data:** `signature` (file)

**Validation:** png, jpg, jpeg, gif only

**Storage:** `~/edgecase/assets/signature.{ext}`

**Returns:** JSON with success and filename

---

```python
@settings_bp.route('/delete_signature', methods=['POST'])
def delete_signature()
```
**Purpose:** Delete signature  
**Returns:** JSON with success status

---

### Background Images

```python
@settings_bp.route('/api/backgrounds')
def list_backgrounds()
```
**Purpose:** List available background images

**Returns:** JSON with system and user backgrounds

---

```python
@settings_bp.route('/upload_background', methods=['POST'])
def upload_background()
```
**Purpose:** Upload custom background

**Form Data:** `background` (file)

**Storage:** `~/edgecase/web/static/user_backgrounds/`

**Returns:** JSON with success and filename

---

```python
@settings_bp.route('/delete_background', methods=['POST'])
def delete_background()
```
**Purpose:** Delete user background

**JSON Data:** `filename`

**Security:** Can only delete from user_backgrounds directory

**Returns:** JSON with success status

---

### File Number Settings

```python
@settings_bp.route('/settings/file-number', methods=['GET', 'POST'])
def file_number_settings()
```
**Purpose:** Get/save file number format settings (AJAX)

**GET Returns:** JSON with format, prefix, suffix, counter

**POST JSON Data:**
- format: 'manual', 'date-initials', 'prefix-counter'
- prefix, suffix (optional)
- counter (for prefix-counter mode)

**Returns:** JSON with success status

---

## PLACEHOLDER ROUTES (app.py)

```python
@app.route('/scheduler')
def scheduler()
```
**Purpose:** Placeholder for future calendar/appointment features  
**Returns:** `scheduler.html`

---

```python
@app.route('/billing')
def billing()
```
**Purpose:** Placeholder for future invoicing/statement features  
**Returns:** `billing.html`

---

## SHARED UTILITIES (web/utils.py)

These functions are imported and used across blueprints:

### parse_date_from_form(form_data)

```python
def parse_date_from_form(form_data):
    """Convert year/month/day dropdowns to Unix timestamp."""
    year = form_data.get('year')
    month = form_data.get('month')
    day = form_data.get('day')
    
    if year and month and day:
        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return int(datetime.strptime(date_str, '%Y-%m-%d').timestamp())
    return None
```

**Used in:** All entry creation/edit routes (14 occurrences)

---

### get_today_date_parts()

```python
def get_today_date_parts():
    """Return dict with today's date components for form defaults."""
    today_dt = datetime.now()
    return {
        'today': today_dt.strftime('%Y-%m-%d'),
        'today_year': today_dt.year,
        'today_month': today_dt.month,
        'today_day': today_dt.day
    }
```

**Used in:** All entry creation GET routes (7 occurrences)

**Usage:** `return render_template(..., **date_parts)`

---

### save_uploaded_files(files, descriptions, entry_id, db, client_id=None)

```python
def save_uploaded_files(files, descriptions, entry_id, db, client_id=None):
    """Handle file uploads and create attachment records."""
    # Checks if files exist
    # Determines upload directory based on client_id
    # Saves files with secure_filename
    # Creates attachment database records
    # Returns list of added filenames
```

**Used in:** Upload, Income, Expense routes (6 occurrences)

**Storage:**
- Client entries: `~/edgecase/attachments/{client_id}/{entry_id}/`
- Ledger entries: `~/edgecase/attachments/ledger/{entry_id}/`

---

*For database schema, see Database_Schema.md*  
*For design decisions, see Architecture_Decisions.md*  
*For debugging help, see Debugging_Guide.md*

*Last updated: November 23, 2025*
