# EdgeCase Equalizer - Navigation Map v1.2

**Purpose:** Quick reference for finding code, understanding architecture, and debugging  
**Created:** November 8, 2025 (Week 1, Day 2)  
**Last Updated:** November 10, 2025 (Week 3, Day 2)

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. It uses an **Entry-based architecture** where all client records (profiles, sessions, communications, etc.) are stored as entries in a unified database table.

**Tech Stack:**
- Backend: Python 3.13, Flask
- Frontend: HTML, CSS (inline), Vanilla JavaScript
- Database: SQLite (will add SQLCipher encryption in Phase 2)
- No external frameworks: Pure Python/Flask/SQLite

**Current State (Week 3, Day 2):**
- Entry-based database with 8 tables
- Flask web interface with 15 routes
- 5 of 6 entry types implemented:
  - âœ… Profile (client demographics)
  - âœ… Session (therapy notes with clinical fields)
  - âœ… Communication (emails, calls, administrative notes)
  - âœ… Absence (cancellations, no-shows with fees)
  - âœ… Item (billable items with smart tax calculation)
  - âŒ Statement (auto-generated invoices - Week 4)
- Client list view with filtering, sorting, search
- Client file view with year/month grouping and entry filtering
- Client type management with clickable badges
- Muted color palette UI throughout

---

## DIRECTORY STRUCTURE

```
~/edgecase/
â"œâ"€â"€ main.py                      # Application entry point (launches Flask)
â"œâ"€â"€ requirements.txt             # Python dependencies
â"œâ"€â"€ core/                        # Core business logic
â"‚   â"œâ"€â"€ __init__.py
â"‚   â"œâ"€â"€ database.py              # Database class, all CRUD operations
â"‚   â"œâ"€â"€ client.py                # (Placeholder for future)
â"‚   â"œâ"€â"€ entry.py                 # (Placeholder for future)
â"‚   â"œâ"€â"€ encryption.py            # (Phase 2 - SQLCipher)
â"‚   â""â"€â"€ ...
â"œâ"€â"€ web/                         # Flask web application
â"‚   â"œâ"€â"€ __init__.py
â"‚   â"œâ"€â"€ app.py                   # Flask routes and application logic
â"‚   â"œâ"€â"€ auth.py                  # (Phase 3 - Authentication)
â"‚   â"œâ"€â"€ templates/               # Jinja2 HTML templates
â"‚   â"‚   â"œâ"€â"€ base.html           # Base layout (header, nav, styling)
â"‚   â"‚   â"œâ"€â"€ main_view.html      # Client list with filters
â"‚   â"‚   â"œâ"€â"€ client_file.html    # Client entry timeline
â"‚   â"‚   â"œâ"€â"€ add_client.html     # New client form
â"‚   â"‚   â"œâ"€â"€ manage_types.html   # Client types management
â"‚   â"‚   â"œâ"€â"€ settings.html       # Settings page
â"‚   â"‚   â""â"€â"€ entry_forms/
â"‚   â"‚       â"œâ"€â"€ profile.html    # Profile entry form
â"‚   â"‚       â"œâ"€â"€ session.html    # Session entry form
â"‚   â"‚       â"œâ"€â"€ communication.html # Communication entry form
â"‚   â"‚       â"œâ"€â"€ absence.html    # Absence entry form
â"‚   â"‚       â""â"€â"€ item.html       # Item entry form
â"‚   â""â"€â"€ static/                 # Static assets (future)
â"‚       â"œâ"€â"€ css/
â"‚       â"œâ"€â"€ js/
â"‚       â""â"€â"€ img/
â"œâ"€â"€ pdf/                         # PDF generation (Phase 1, Week 4)
â"œâ"€â"€ ai/                          # AI features (Phase 2, Week 7)
â"œâ"€â"€ utils/                       # Utility functions
â""â"€â"€ assets/                      # User uploads (logo, signature)
```

---

## DATABASE SCHEMA

**Location:** `~/edgecase/core/database.py` (lines 38-198 in `_initialize_schema()`)

### Tables

#### 1. `client_types` (Customizable client categories)
```sql
- id: Primary key
- name: Type name ("Active", "Inactive", etc.)
- color: Hex color for UI (#00AA88)
- code: 3-4 letter abbreviation (ACT, INA)
- file_number_style: How to generate file numbers
- file_number_prefix/suffix: Optional text
- file_number_counter: Auto-increment counter
- session_fee: Default session fee
- session_duration: Default duration (minutes)
- retention_period: Days to retain after inactive
- is_system: 1 for Active/Inactive (can't delete)
- created_at, modified_at: Unix timestamps
```

**Default Types:** Active (green), Inactive (yellow) - created automatically on first run

#### 2. `clients` (Client records)
```sql
- id: Primary key
- file_number: Unique identifier (YYYYMMDD-III format)
- first_name, middle_name, last_name: Name fields
- type_id: Foreign key to client_types
- created_at, modified_at: Unix timestamps
- is_deleted: Soft delete flag (0 = active, 1 = deleted)
```

#### 3. `entries` (Unified entry table - THE CORE)
**This is the heart of the system.** All entry types share this table.

```sql
- id: Primary key
- client_id: Foreign key to clients
- class: Entry type ('profile', 'session', 'communication', 'absence', 'item', 'statement')
- created_at, modified_at: Unix timestamps

-- Common fields (all entries)
- description: Entry title/summary
- content: Main content (Markdown)

-- Profile-specific fields
- email, phone, home_phone, work_phone, text_number
- address, date_of_birth
- preferred_contact: 'email', 'call_cell', 'call_home', 'call_work', 'text'
- ok_to_leave_message: 'yes' or 'no'
- emergency_contact_name, emergency_contact_phone, emergency_contact_relationship
- referral_source, additional_info

-- Session-specific fields
- modality: 'in-person' or 'virtual'
- format: 'individual', 'couples', 'family', 'group'
- session_number, service, session_date, session_time
- duration, fee, is_consultation
- mood, affect, risk_assessment

-- Communication-specific fields
- comm_recipient: 'to_client', 'from_client', 'internal_note'
- comm_type: 'email', 'phone', 'text', 'administrative'
- comm_date: Unix timestamp
- comm_time: Free-form text (e.g., "2:00 PM")

-- Absence-specific fields
- absence_date: Unix timestamp
- absence_time: Free-form text

-- Item-specific fields
- item_date: Unix timestamp
- item_time: Free-form text
- base_price: Decimal (e.g., 100.00)
- tax_rate: Decimal percentage (e.g., 13.0 for 13%)
- fee: Calculated total (base_price + tax_rate)

-- Statement-specific fields (not yet implemented)
- statement_total, payment_status, payment_notes
- date_sent, date_paid, is_void

-- Edit tracking (Phase 2)
- edit_history: JSON array of edits
- locked: 0 or 1 (immutable after locking)
- locked_at: Unix timestamp
```

**Design Philosophy:** Class-specific fields are NULL for entries that don't use them. This is simpler than 6 separate tables and allows easy querying across all entry types.

#### 4. `client_links` (Couples/family therapy - Phase 1, Week 4)
```sql
- id: Primary key
- client_id_1, client_id_2: Foreign keys to clients
- created_at: Unix timestamp
- UNIQUE constraint on (client_id_1, client_id_2)
```

#### 5. `entry_links` (Linked entries across files - Phase 1, Week 4)
```sql
- id: Primary key
- entry_id_1, entry_id_2: Foreign keys to entries
- is_active: Toggle link on/off
- UNIQUE constraint on (entry_id_1, entry_id_2)
```

#### 6. `attachments` (File uploads - Future)
```sql
- id: Primary key
- entry_id: Foreign key to entries
- filename, description
- filepath: Relative path to file
- filesize: Bytes
- uploaded_at: Unix timestamp
```

#### 7. `settings` (Practice settings)
```sql
- key: Setting name (primary key)
- value: Setting value (stored as text, parse as needed)
- modified_at: Unix timestamp
```

---

## CORE MODULE: `core/database.py`

**Location:** `~/edgecase/core/database.py`  
**Lines:** 626 total  
**Purpose:** All database operations

### Key Classes

#### `Database` (Main class)
**Constructor:** `__init__(db_path: str)` (lines 18-27)
- Creates database file if doesn't exist
- Calls `_initialize_schema()` to create tables

**Key Methods:**

##### Schema Management
- `_initialize_schema()` (lines 33-205)
  - Creates all 7 tables if they don't exist
  - Calls `_run_migrations()` then `_create_default_types()`
  
- `_run_migrations()` (lines 207-240)
  - Automatically adds missing columns to entries table
  - Checks for: comm_date, comm_time, absence_date, absence_time, item_date, item_time, base_price, tax_rate
  - Uses ALTER TABLE to add columns without breaking existing data
  - Prints migration messages to console
  
- `_create_default_types()` (lines ~242-270)
  - Creates Active and Inactive types on first run
  - Only runs if no system types exist

##### Client Type Operations
- `add_client_type(type_data: Dict)` â†' int (lines ~274-295)
- `get_client_type(type_id: int)` â†' Dict (lines ~297-310)
- `get_all_client_types()` â†' List[Dict] (lines 399-409)

##### Client Operations
- `add_client(client_data: Dict)` â†' int (lines 413-438)
- `get_client(client_id: int)` â†' Dict (lines 440-450)
- `get_all_clients(type_id: Optional[int])` â†' List[Dict] (lines 452-469)
- `update_client(client_id: int, client_data: Dict)` â†' bool (lines 471-493)
- `search_clients(search_term: str)` â†' List[Dict] (lines 495-512)

##### Entry Operations
- `add_entry(entry_data: Dict)` â†' int (lines 516-564)
  - Dynamically builds INSERT based on provided fields
  - Handles all entry types (profile, session, communication, absence, item)
  - **optional_fields list (lines 528-541):** Includes all class-specific fields
    - Profile: email, phone, home_phone, work_phone, text_number, address, date_of_birth, preferred_contact, ok_to_leave_message, emergency_contact_*, referral_source, additional_info
    - Session: modality, format, session_number, service, session_date, session_time, duration, fee, is_consultation, mood, affect, risk_assessment
    - Communication: comm_recipient, comm_type, comm_date, comm_time
    - Absence: absence_date, absence_time
    - Item: item_date, item_time, base_price, tax_rate
    - Statement: statement_total, payment_status, payment_notes, date_sent, date_paid, is_void
    - Edit tracking: edit_history, locked, locked_at
  
- `get_entry(entry_id: int)` â†' Dict (lines 566-576)
- `get_client_entries(client_id: int, entry_class: Optional[str])` â†' List[Dict] (lines 578-598)
- `update_entry(entry_id: int, entry_data: Dict)` â†' bool (lines 600-627)
  - Dynamically builds UPDATE statement
  - Updates modified_at timestamp

##### Helper Methods
- `get_last_session_date(client_id: int)` â†' int
  - Returns Unix timestamp of most recent session
  
- `get_profile_entry(client_id: int)` â†' Dict
  - Returns profile entry for client (used to populate contact info)
  
- `get_payment_status(client_id: int)` â†' str
  - Returns 'paid', 'pending', or 'overdue'
  - Checks most recent statement

---

## WEB MODULE: `web/app.py`

**Location:** `~/edgecase/web/app.py`  
**Lines:** 987 total  
**Purpose:** Flask application, all routes and web logic

### Flask Setup (lines 1-28)

```python
from flask import Flask, render_template, request, redirect, url_for, jsonify
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.database import Database

app = Flask(__name__)
app.config['SECRET_KEY'] = 'edgecase-dev-key-change-in-production'

# Initialize database
project_root = Path(__file__).parent.parent
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

db_path = data_dir / "edgecase.db"
db = Database(str(db_path))
```

### Custom Jinja Filters (lines 29-37)

```python
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to YYYY-MM-DD."""
    if not timestamp:
        return '-'
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
```

**Usage in templates:** `{{ client.created_at|timestamp_to_date }}`

### Routes Overview

**Total Routes:** 15

1. `/` - Main view (client list)
2. `/client/<id>` - Client file view
3. `/client/<id>/change_type` - Change client type (POST)
4. `/add_client` - Add new client
5. `/client/<id>/profile` - Create/edit profile
6. `/client/<id>/session` - Create session
7. `/client/<id>/session/<entry_id>` - Edit session
8. `/client/<id>/communication` - Create communication
9. `/client/<id>/communication/<entry_id>` - Edit communication
10. `/client/<id>/absence` - Create absence
11. `/client/<id>/absence/<entry_id>` - Edit absence
12. `/client/<id>/item` - Create item
13. `/client/<id>/item/<entry_id>` - Edit item
14. `/types` - Manage client types
15. `/settings` - Settings page
16. `/api/backgrounds` - List background images (API)
17. `/add_type` - Add client type (POST)

### Route Details

#### 1. Main View: `@app.route('/')` (lines 41-214)
**Purpose:** Display client list with filtering, sorting, search

**Query Parameters:**
- `type` (list): Client type IDs to filter (multi-select)
- `sort`: Field to sort by ('file_number', 'last_name', 'first_name', 'created', 'last_session')
- `order`: 'asc' or 'desc'
- `search`: Search term
- `view`: 'detailed' or 'compact'

**Stats Calculated:**
- Active client count
- Sessions this week
- Pending invoices count
- Billable amount this month (sessions + items)

**Logic Flow:**
1. Get filter parameters from query string
2. Default to Active type if no types selected
3. Get all client types for filter UI
4. Get clients (filtered or searched)
5. Calculate stats for all clients
6. For each client:
   - Get client type info
   - Get profile entry for contact info
   - Determine which phone to display based on preferred_contact
   - Set contact icon (ðŸ"ž for call, ðŸ'¬ for text)
   - Get last session date
   - Get payment status
7. Sort clients by selected field
8. Render template with all data

**Template:** `main_view.html`

---

#### 2. Client File: `@app.route('/client/<int:client_id>')` (lines 215-347)
**Purpose:** Display single client's entry timeline grouped by year/month

**Query Parameters:**
- `class` (list): Entry classes to show (session, consultation, communication, absence, item)

**Logic:**
1. Get client by ID
2. Get client type
3. Get all types for type change dropdown
4. Get class filter from query params (default: all 5 classes)
5. Get profile entry separately (pinned at top)
6. Get ALL entries for client
7. **Calculate counts (always show all, regardless of filter):**
   - Session count (non-consultation sessions)
   - Consultation count
   - **Absence count for THIS CALENDAR YEAR ONLY** (lines 250-253)
     ```python
     year_start = int(datetime(now.year, 1, 1).timestamp())
     absence_entries = [e for e in all_entries if e['class'] == 'absence' 
                        and (e.get('absence_date') or 0) >= year_start]
     absence_count = len(absence_entries)
     ```
8. Filter entries by selected classes
9. Group filtered entries by year â†' month
10. Sort entries within each month by date (most recent first)
11. Mark current year/month for auto-expand

**Template:** `client_file.html`

---

#### 3. Change Client Type: `@app.route('/client/<int:client_id>/change_type', methods=['POST'])` (lines 349-380)
**Purpose:** Change client's type from client file view

**Logic:**
1. Get new_type_id from form
2. Update client's type_id
3. Smart redirect: Return to same page (client file or profile)

---

#### 4. Add Client: `@app.route('/add_client', methods=['GET', 'POST'])` (lines 382-403)
**Purpose:** Create new client

**GET:** Show form with all client types  
**POST:** Save client, redirect to client file

**Template:** `add_client.html`

---

#### 5. Edit Profile: `@app.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])` (lines 405-468)
**Purpose:** Create or edit client profile entry

**Logic:**
1. Get client and existing profile (if exists)
2. **POST:** Prepare profile_data dict with all form fields
   - Date of birth combines 3 dropdowns into YYYY-MM-DD
   - Phone numbers auto-formatted by JavaScript
   - All contact fields saved (email, phone, home_phone, work_phone, text_number)
   - preferred_contact, ok_to_leave_message
   - Emergency contact fields
   - referral_source, additional_info
3. If profile exists: update, else: create new
4. Redirect to client file

**Template:** `entry_forms/profile.html`

---

#### 6. Create Session: `@app.route('/client/<int:client_id>/session', methods=['GET', 'POST'])` (lines 470-545)
**Purpose:** Create new session entry

**Logic:**
1. Get client and client type (for defaults)
2. **POST:** 
   - Auto-generate session number (count non-consultations + 1)
   - If consultation: session_number=NULL, fee=0, description="Consultation"
   - Otherwise: increment session number
   - Save all session fields (modality, format, date, time, duration, fee, clinical observations, notes)
3. **GET:** Calculate next session number, show form with defaults

**Template:** `entry_forms/session.html`

---

#### 7. Edit Session: `@app.route('/client/<int:client_id>/session/<int:entry_id>', methods=['GET', 'POST'])` (lines 547-612)
**Purpose:** Edit existing session entry

**Logic:**
1. Get client, client type, and existing session
2. **POST:** Update session with form data, maintain session number
3. **GET:** Load existing session data into form

**Template:** `entry_forms/session.html` (reused with `is_edit=True`)

---

#### 8. Create Communication: `@app.route('/client/<int:client_id>/communication', methods=['GET', 'POST'])` (lines 614-664)
**Purpose:** Create new communication entry

**Logic:**
1. **POST:**
   - Convert date string to Unix timestamp
   - Save comm_date, comm_time, comm_recipient, comm_type, description, content
2. **GET:** Show form with today's date pre-filled

**Template:** `entry_forms/communication.html`

---

#### 9. Edit Communication: `@app.route('/client/<int:client_id>/communication/<int:entry_id>', methods=['GET', 'POST'])` (lines 666-720)
**Purpose:** Edit existing communication entry

**Logic:**
1. Get existing communication
2. **POST:** Update with new data
3. **GET:** Convert timestamp back to date string for form

**Template:** `entry_forms/communication.html` (reused with `is_edit=True`)

---

#### 10. Create Absence: `@app.route('/client/<int:client_id>/absence', methods=['GET', 'POST'])` (lines 722-771)
**Purpose:** Create new absence entry

**Logic:**
1. **POST:**
   - Convert date string to Unix timestamp
   - Save absence_date, absence_time, description, fee, content
2. **GET:** Show form with today's date, fee from client type

**Template:** `entry_forms/absence.html`

---

#### 11. Edit Absence: `@app.route('/client/<int:client_id>/absence/<int:entry_id>', methods=['GET', 'POST'])` (lines 773-826)
**Purpose:** Edit existing absence entry

**Logic:**
1. Get existing absence
2. **POST:** Update with new data
3. **GET:** Convert timestamp back to date string for form

**Template:** `entry_forms/absence.html` (reused with `is_edit=True`)

---

#### 12. Create Item: `@app.route('/client/<int:client_id>/item', methods=['GET', 'POST'])` (lines 828-879)
**Purpose:** Create new item entry with smart tax calculation

**Logic:**
1. **POST:**
   - Convert date string to Unix timestamp
   - Save item_date, item_time, description, base_price, tax_rate, content
   - **Note:** Fee is calculated in JavaScript but can also be calculated server-side
2. **GET:** Show form with today's date

**Template:** `entry_forms/item.html`

---

#### 13. Edit Item: `@app.route('/client/<int:client_id>/item/<int:entry_id>', methods=['GET', 'POST'])` (lines 881-936)
**Purpose:** Edit existing item entry

**Logic:**
1. Get existing item
2. **POST:** Update with new data
3. **GET:** Convert timestamp back to date string, load base_price and tax_rate

**Template:** `entry_forms/item.html` (reused with `is_edit=True`)

---

#### 14. Manage Types: `@app.route('/types')` (lines 938-942)
**Purpose:** View and manage client types

**Template:** `manage_types.html`

---

#### 15. Settings Page: `@app.route('/settings')` (lines 944-947)
**Purpose:** Display settings page

**Template:** `settings.html`

---

#### 16. API - List Backgrounds: `@app.route('/api/backgrounds')` (lines 949-966)
**Purpose:** Return list of available background images

**Returns:** JSON array of filenames from `web/static/img/`

---

#### 17. Add Type: `@app.route('/add_type', methods=['POST'])` (lines 968-987)
**Purpose:** Create new client type (called from manage_types)

---

## TEMPLATES

**Location:** `~/edgecase/web/templates/`

### Design System (Muted Palette)

**Applied across all templates:**
- Page background: `#EDF2F5` (soft gray-blue)
- Card background: `#FBFCFD` (soft gray)
- Primary color: `#1F8F74` (muted teal)
- Secondary: `#55607D` (muted navy)
- Border colors: `#DEE2E6`, `#E3E9EE`

**Entry Type Color Codes:**
- Session: Green `#CFE7DA` bg, `#0E5346` text
- Consultation: Amber `#FAF0DF` bg, `#5A4823` text
- Communication: Lavender `#DCD3E8` bg, `#3F3358` text
- Absence: Rose `#F5D8DB` bg, `#6B2832` text
- Item: Amber `#F5E6D3` bg, `#5A4823` text

### `base.html` (Base Layout)
**Lines:** ~150  
**Purpose:** Shared layout for all pages

**Structure:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}EdgeCase Equalizer{% endblock %}</title>
    <style>
        /* All CSS inline */
        /* Muted palette colors */
        /* Header with gradient */
        /* Navigation */
        /* Cards, buttons, forms */
        /* Utility classes */
    </style>
    {% block extra_css %}{% endblock %}
</head>
<body>
    <header>
        <h1>EdgeCase Equalizer</h1>
        <p>Practice Management for Independent Therapists</p>
    </header>
    
    <nav>
        <a href="/">Clients</a>
        <a href="/types">Client Types</a>
    </nav>
    
    <main>
        {% block content %}{% endblock %}
    </main>
    
    {% block extra_js %}{% endblock %}
</body>
</html>
```

---

### `main_view.html` (Client List)
**Lines:** ~786  
**Purpose:** Display filterable, sortable, searchable client list

**Key Sections:**

1. **Stats Cards** (2 rows of 3 cards)
   - Active Clients count
   - Sessions This Week count
   - Pending Invoices count
   - Billable This Month (dollars from sessions + items)
   - Current Time (live clock)
   - Current Date (live)
   - Navigation card with Settings and Edit Client Types buttons

2. **Controls Section**
   - Type filter checkboxes (multi-select)
   - Search box
   - Sort dropdown
   - View mode toggle
   - Add Client button

3. **Client Table**
   - Headers with sort links
   - Payment indicator dots (ðŸŸ¢ðŸŸ¡ðŸ"´)
   - Type badges with color coding
   - Contact info with smart display:
     - Email: mailto: link
     - Phone: tel: or sms: link
     - Preferred contact underlined
     - âš ï¸ if no message allowed

4. **Legend Card**
   - Payment status indicators
   - Preferred contact explanation
   - No-message warning
   - Sticky at bottom of viewport

**JavaScript Features:**
- `toggleDropdown()` - Filter/sort dropdown management
- `updateClock()` - Live clock update every second
- `syncClock()` - Synchronize with system clock
- Auto-submit filter form on checkbox change
- Clickable rows navigate to client file

---

### `client_file.html` (Entry Timeline)
**Lines:** 595  
**Purpose:** Display all entries for a client grouped by year/month

**Key Features:**

1. **Header Section**
   - Client name, file number
   - Clickable type badge (opens type change form)
   - Payment status indicator
   - Contact info preview (email, phone from profile)
   - Edit Profile / Create Profile button

2. **Session History Heading**
   - Shows: "X Sessions, Y Consultations, Z Absences this year"
   - Absence count is **calendar year only** (not all-time)

3. **Action Buttons**
   - Create Session
   - Create Communication
   - Create Absence
   - Create Item

4. **Entry Class Filter** (lines ~330-385)
   - Checkboxes for: Session, Consultation, Communication, Absence, Item
   - Default: All checked
   - Auto-submit on checkbox change
   - Shows count of selected types

5. **Profile Entry** (if exists)
   - Highlighted in green
   - Shows key contact info
   - Click to edit

6. **Entries Grouped by Year/Month**
   - Year headers (collapsible)
   - Month headers (collapsible)
   - Current year/month expanded by default
   - Entry count shown in headers

7. **Entry Table**
   - Fixed column widths for consistency
   - Columns: Date | Class | Description | Time | Details | Info
   - **Smart column display:**
     - **Sessions:** Details = Duration, Info = Fee
     - **Communications:** Details = Recipient, Info = Type
     - **Absences:** Details = "-", Info = Fee
     - **Items:** Details = "Base: $X (Y% tax)", Info = Fee
   - Description truncated at 50 characters (with "...")
   - Clickable rows navigate to edit form

**JavaScript Features:**
- `toggleYear()` - Expand/collapse year sections
- `toggleMonth()` - Expand/collapse month sections
- `toggleDropdown()` - Filter dropdown management
- Entry type badges color-coded

---

### Entry Forms

All entry forms follow consistent patterns:

**Common Structure:**
1. **Header** - Type badge, client name, file number (vertical layout)
2. **Date/Time fields** - Always at top
3. **Required fields** - Marked with asterisks
4. **Null dropdown options** - Force user selection
5. **Auto-expanding textareas** - 300px start, 600px max, then scrollbar
6. **Save/Cancel buttons** - Bottom of form
7. **Edit button** - Replaces Save after first save

#### `entry_forms/profile.html`
**Lines:** ~350  
**Purpose:** Create or edit client profile entry

**Key Features:**
- Date of Birth: 3 dropdowns (year, month, day) â†' hidden YYYY-MM-DD field
- Phone fields with auto-formatting: (123) 456-7890
- Text Number selector: None, Cell, Home, Work
- Preferred Contact: Email, Call Cell, Call Home, Call Work, Text
- OK to Leave Message: Yes, No, Select...
- Emergency contact fields
- JavaScript handles phone formatting and date conversion

---

#### `entry_forms/session.html`
**Lines:** ~400  
**Purpose:** Create or edit session entry

**Key Features:**
- Consultation checkbox (sets fee=0, no session number)
- Session number (auto-generated, read-only in edit)
- Date picker (defaults to today)
- Time input
- Duration, Fee (auto-populated from client type)
- Modality dropdown: Select..., In-Person, Virtual
- Format dropdown: Select..., Individual, Couples, Family, Group
- Clinical observations (all optional):
  - Mood: Normal, Angry, Anxious, Depressed, Euphoric
  - Affect: Normal, Blunted, Inappropriate, Intense, Labile
  - Risk: None, Ideation, Threat, Attempt
- Session Notes textarea (required)

---

#### `entry_forms/communication.html`
**Lines:** ~300  
**Purpose:** Create or edit communication entry

**Key Features:**
- Date/Time on same line
- Description (required)
- Recipient dropdown: Select..., To Client, From Client, Internal Note
- Type dropdown: Select..., Email, Phone, Text, Administrative
- Content textarea (required)

---

#### `entry_forms/absence.html`
**Lines:** ~250  
**Purpose:** Create or edit absence entry

**Key Features:**
- Date/Time on same line
- Description (required)
- Fee (auto-populated from client type)
- Notes textarea (optional)

---

#### `entry_forms/item.html`
**Lines:** ~350  
**Purpose:** Create or edit item entry with smart tax calculation

**Key Features:**
- Date/Time on same line
- Description (required)
- **Smart Tax Calculation** (lines ~180-280):
  - Three fields: Base Price, Tax Rate (%), Total Price
  - Fill any 2 fields, 3rd auto-calculates
  - JavaScript tracks last-edited field
  - Prevents circular calculation loops
  - Examples:
    - Enter Base=100, Tax=13% â†' Total=113.00
    - Enter Total=113, Tax=13% â†' Base=100.00
    - Enter Total=113, Base=100 â†' Tax=13.0%
- Notes textarea (optional)

**JavaScript Logic:**
```javascript
let lastEditedField = null;

function calculateTax() {
    const base = parseFloat(basePrice.value) || 0;
    const rate = parseFloat(taxRate.value) || 0;
    const total = parseFloat(totalPrice.value) || 0;
    
    if (lastEditedField === 'total' && base > 0) {
        // Calculate tax rate from total and base
        taxRate.value = (((total - base) / base) * 100).toFixed(2);
    } else if (lastEditedField === 'total' && rate > 0) {
        // Calculate base from total and rate
        basePrice.value = (total / (1 + rate / 100)).toFixed(2);
    } else if (lastEditedField === 'tax' && total > 0) {
        // Calculate base from total and rate
        basePrice.value = (total / (1 + rate / 100)).toFixed(2);
    } else if (lastEditedField === 'tax' && base > 0) {
        // Calculate total from base and rate
        totalPrice.value = (base * (1 + rate / 100)).toFixed(2);
    } else if (lastEditedField === 'base' && rate > 0) {
        // Calculate total from base and rate
        totalPrice.value = (base * (1 + rate / 100)).toFixed(2);
    } else if (lastEditedField === 'base' && total > 0) {
        // Calculate tax rate from base and total
        taxRate.value = (((total - base) / base) * 100).toFixed(2);
    }
}
```

---

### `manage_types.html` (Client Types)
**Lines:** ~80  
**Purpose:** View and manage client types

**Current Features:**
- Table of all types
- Shows: name, code, color, session fee, duration
- System types marked

**Coming Soon:**
- Add Type modal/form
- Edit Type functionality
- Delete Type (with validation)

---

### `settings.html` (Settings Page)
**Purpose:** Application settings and preferences

**Replaces:** Modal-based settings in main_view.html (removed Week 2, Day 1)

---

## DATA FLOW

### Creating a Session Entry (Full Workflow)

1. **User clicks "Create Session"** in client file
2. **GET /client/<client_id>/session** â†' Shows form
   - Next session number calculated (count non-consultations + 1)
   - Today's date default
   - Fee/duration from client type
3. **User fills form:**
   - Optional: Check "Consultation" (disables session number, sets fee=0)
   - Date (required)
   - Time (optional)
   - Modality (required): In-Person or Virtual
   - Format (required): Individual, Couples, Family, Group
   - Duration (required, pre-filled)
   - Fee (required, pre-filled)
   - Clinical observations (optional): Mood, Affect, Risk
   - Session Notes (required)
4. **User clicks Save**
5. **POST /client/<client_id>/session**:
   - Convert date string to Unix timestamp
   - If consultation: session_number=NULL, fee=0, description="Consultation"
   - Otherwise: use calculated session_number, description="Session Number X"
   - `db.add_entry(session_data)` with class='session'
6. **Redirect to /client/<client_id>**
7. **Client file shows:**
   - Updated session count: "X Sessions, Y Consultations"
   - New session in timeline (current month auto-expanded)

---

### Creating an Item Entry with Tax Calculation

1. **User clicks "Create Item"** in client file
2. **GET /client/<client_id>/item** â†' Shows form with today's date
3. **User fills form:**
   - Date (required)
   - Time (optional)
   - Description (required): e.g., "Book: The Body Keeps the Score"
   - **Option A:** Enter Base=30.00, Tax=13% â†' Total auto-calculates to 33.90
   - **Option B:** Enter Total=33.90, Base=30.00 â†' Tax auto-calculates to 13.0%
   - **Option C:** Enter Total=33.90, Tax=13% â†' Base auto-calculates to 30.00
   - Notes (optional)
4. **User clicks Save**
5. **POST /client/<client_id>/item**:
   - Convert date string to Unix timestamp
   - Save item_date, item_time, description, base_price, tax_rate, fee (total), content
   - `db.add_entry(item_data)` with class='item'
6. **Redirect to /client/<client_id>**
7. **Client file shows:**
   - New item in timeline with amber badge
   - Details column: "Base: $30.00 (13.0% tax)"
   - Info column: "$33.90"

---

### Filtering Entries in Client File

1. **User navigates to /client/<client_id>**
2. **Default filter:** All entry classes checked (session, consultation, communication, absence, item)
3. **User unchecks "Communication"**
4. **Form auto-submits:** `?class=session&class=consultation&class=absence&class=item`
5. **Server-side filtering** (lines 255-267 in app.py):
   ```python
   filtered_entries = []
   for entry in all_entries:
       if entry['class'] == 'session':
           if entry.get('is_consultation'):
               if 'consultation' in class_filter:
                   filtered_entries.append(entry)
           else:
               if 'session' in class_filter:
                   filtered_entries.append(entry)
       elif entry['class'] in class_filter:
           filtered_entries.append(entry)
   ```
6. **Template displays:** Only sessions, consultations, absences, items (no communications)
7. **Counts unchanged:** Session/consultation/absence counts always show ALL entries (lines 245-253)

---

### Calculating Absence Count for Current Year

**Location:** `app.py` client_file() route, lines 250-253

```python
# Get current year
from datetime import datetime
now = datetime.now()

# Calculate year start timestamp (January 1, YYYY at 00:00:00)
year_start = int(datetime(now.year, 1, 1).timestamp())

# Filter absences for this calendar year only
absence_entries = [e for e in all_entries 
                   if e['class'] == 'absence' 
                   and (e.get('absence_date') or 0) >= year_start]

# Count them
absence_count = len(absence_entries)
```

**Result:** Displayed as "X Absences this year" in Session History heading

**Why calendar year?** 
- Helps track cancellation patterns per year
- Resets automatically on January 1
- Different from all-time session count (which never resets)

---

## COMMON DEBUGGING WORKFLOWS

### Issue: Entry not saving date/time

**Check:**
1. Is the field in the entries table schema? (database.py lines 74-148)
2. Is the field in the migration system? (database.py lines 217-227)
3. Is the field in optional_fields list? (database.py lines 528-541)
4. Is the route converting date string to timestamp? (app.py, check specific route)

**Test:**
```python
# In Flask route, add debug print
print(f"Entry data: {entry_data}")
# Check if field present and has expected value
```

### Issue: Entry not appearing in timeline

**Check:**
1. Does the entry have a date field? (session_date, comm_date, absence_date, item_date)
2. Is the date field being extracted in client_file route? (app.py lines 281-289)
3. Is the entry class in the filter checkboxes? (client_file.html)
4. Is the entry's date field being sorted correctly? (app.py lines 305-315)

**Test:**
```python
# In Python
entries = db.get_client_entries(client_id)
for e in entries:
    print(f"Entry {e['id']}: class={e['class']}, date_field={e.get(f\"{e['class']}_date\")}")
```

### Issue: Tax calculation not working

**Problem:** JavaScript not recalculating when field changes

**Check:**
1. Are all three fields listening for 'input' event? (item.html lines ~220-260)
2. Is lastEditedField being set correctly?
3. Is calculateTax() being called after setting lastEditedField?
4. Are parseFloat() conversions handling empty strings?

**Test:** Open browser console, enter values, check for errors

### Issue: Absence count wrong

**Problem:** Count includes absences from previous years

**Check:**
1. Is year_start calculation correct? (app.py line 251)
2. Is absence_date comparison using >= year_start? (app.py line 252)
3. Are we filtering by absence_date not created_at?

**Test:**
```python
# Check what year_start is
from datetime import datetime
now = datetime.now()
year_start = int(datetime(now.year, 1, 1).timestamp())
print(f"Year start: {year_start} = {datetime.fromtimestamp(year_start)}")

# Check absence dates
absences = [e for e in db.get_client_entries(client_id) if e['class'] == 'absence']
for a in absences:
    print(f"Absence {a['id']}: date={a.get('absence_date')} = {datetime.fromtimestamp(a['absence_date']) if a.get('absence_date') else 'None'}")
```

### Issue: Entry filter not working

**Check:**
1. Is the checkbox value matching the entry class? (client_file.html)
2. Is the form submitting correctly?
3. Is the class_filter being parsed from query params? (app.py line 229)
4. Is the filtering logic handling consultations specially? (app.py lines 259-267)

**Test:** Check URL after clicking filter checkbox, should see `?class=session&class=...`

---

## KEY DESIGN DECISIONS

### Why Entry-Based Architecture?

**Problem:** Separate tables for notes, invoices, communications, etc. meant:
- Duplicate schemas (created_at, modified_at, locked, etc. in every table)
- Complex queries to get "all activity" for a client
- More code to maintain

**Solution:** One `entries` table with a `class` field. All entry types share common fields, class-specific fields are NULL when not used.

**Benefits:**
- Single query gets all entries: `SELECT * FROM entries WHERE client_id = ?`
- Easy to add new entry types (just add optional fields)
- Consistent interface for all entries
- Simpler codebase

**Trade-off:** Some NULL fields (but SQLite handles this efficiently)

---

### Why Separate Date Fields for Each Entry Type?

**Alternative considered:** Use single `entry_date` field for all entries

**Chosen approach:** `session_date`, `comm_date`, `absence_date`, `item_date`

**Reasons:**
1. **Explicit semantics:** Code clearly shows what the date represents
2. **Entry class specificity:** Different entries might use dates differently in future
3. **Migration safety:** Adding fields doesn't break existing entries
4. **Debugging clarity:** Can see exactly which date field is being used

**Trade-off:** Slightly more columns, but minimal storage impact and clearer code

---

### Why Calendar Year for Absence Count?

**Alternative considered:** All-time absence count (like session count)

**Chosen approach:** Current calendar year only

**Reasons:**
1. **Resets automatically:** January 1 starts fresh count
2. **Annual patterns:** Useful for identifying cancellation trends per year
3. **Clinical relevance:** Therapists often think in calendar years
4. **Distinct from sessions:** Sessions are cumulative (Session #47), absences are annual

**Implementation:** Filter by `absence_date >= year_start` where year_start is January 1 of current year

---

### Why Smart Tax Calculation in JavaScript?

**Alternative considered:** Calculate only on server-side

**Chosen approach:** JavaScript calculates as user types, server receives final values

**Reasons:**
1. **Immediate feedback:** User sees calculation instantly
2. **Flexibility:** User can enter any 2 of 3 values
3. **No form errors:** User always submits valid calculated values
4. **Server simplicity:** Server just stores the values, no calculation needed

**Implementation:** Track last-edited field to prevent circular calculations

---

### Why Vertical Header Layout in Entry Forms?

**Old approach:** Type badge, name, file number on one line

**New approach (Week 3):** Three separate lines

**Reasons:**
1. **Visual hierarchy:** Each element gets full attention
2. **Breathing room:** Less cramped, easier to scan
3. **Mobile friendly:** No wrapping issues on small screens
4. **Consistency:** Matches profile view layout

**Changed in:** session.html, communication.html, absence.html (commit 8d1b6c4)

---

## CURRENT STATE OF ENTRY TYPES

### Implemented (5 of 6)
- âœ… **Profile** - Client demographics and contact info
- âœ… **Session** - Therapy session notes with clinical observations
- âœ… **Communication** - Emails, calls, texts, administrative notes
- âœ… **Absence** - Cancellations, no-shows with fees (calendar year tracking)
- âœ… **Item** - Billable items with smart tax calculation

### Not Yet Implemented (1 of 6)
- âŒ **Statement** - Invoices (auto-generated from billable entries) - Week 4

### Features Working
- âœ… Entry creation and editing for all 5 types
- âœ… Entry filtering in client file (by class)
- âœ… Year/month grouping in timeline
- âœ… Smart column display (Details/Info adapt to entry type)
- âœ… Description truncation (50 characters)
- âœ… Absence count for current calendar year
- âœ… Tax calculation for items (JavaScript)
- âœ… Clickable type badges (change client type)
- âœ… Muted color palette throughout

### Features Not Yet Implemented
- âŒ Entry sorting in client file (currently chronological only)
- âŒ Entry search within content
- âŒ Client linking (couples/family therapy)
- âŒ Statement generation and invoicing
- âŒ PDF export
- âŒ Edit history tracking (columns exist but unused)
- âŒ Entry locking (immutable records - Phase 2)
- âŒ File attachments (table exists but no upload UI)

---

## FILES MODIFIED IN WEEK 3

**Database:**
- `core/database.py` - Added absence_date, absence_time, item_date, item_time, base_price, tax_rate to schema and migrations

**Web Application:**
- `web/app.py` - Added 4 routes (create/edit absence, create/edit item)

**Templates:**
- `web/templates/client_file.html` - Added absence/item filtering, smart column display, year/month grouping
- `web/templates/entry_forms/absence.html` - NEW FILE (complete)
- `web/templates/entry_forms/item.html` - NEW FILE (complete with smart tax calculation)
- `web/templates/entry_forms/session.html` - Improved header layout, required field validation
- `web/templates/entry_forms/communication.html` - Improved header layout
- `web/templates/entry_forms/profile.html` - Minor tweaks

---

## GIT COMMITS (WEEK 3)

1. "Add Item entry type with automatic tax calculation" (Nov 10, 19:54)
2. "Improve entry form headers with vertical layout" (Nov 10, 19:36)
3. "Add Absence entry type with calendar year tracking" (Nov 10, 19:24)
4. "Add client type management and entry filtering" (Nov 10, 18:45)
5. "Tweaked profile.html; added null option for messages and aligned text field properties with other Entry types" (Nov 10, 18:02)

---

## PRODUCTION READINESS STATUS

### Phase 1 Progress (Week 3 of 4)
- âœ… Week 1: Foundation (database, Flask, main view, client types)
- âœ… Week 2: Main view polish, client file view, profile entry, session entry
- âœ… **Week 3:** Communication entry, Absence entry, Item entry, Entry filtering
- â³ Week 4: Statement generation, Client linking, PDF export, Final polish

### System Stability
- âœ… Database schema complete with migrations
- âœ… 5 of 6 entry types fully functional
- âœ… Entry filtering and year/month grouping working
- âœ… Smart tax calculation tested and working
- âœ… Muted color palette applied consistently
- âœ… No known bugs
- âœ… Git history clean with meaningful commits

**Status:** On track for Phase 1 completion. Statement generation and client linking remain for Week 4.

---

## NEXT PRIORITIES (WEEK 4)

### Immediate Tasks
1. **Statement Entry** - Auto-generation from billable entries
   - Aggregate Sessions (non-consultation), Absences, Items
   - Calculate total with taxes
   - Payment tracking (paid/pending/overdue)
   - PDF generation with logo/signature

2. **Client Linking** - Couples/family therapy
   - Link/unlink clients in main view
   - Shared vs. individual entries
   - Smart invoicing (one pays, split, joint)

3. **UI/UX Polish**
   - Test responsive design (iPad, phone)
   - Add missing features (entry sorting, search)
   - Verify all pages use consistent styling

### Week 4 Deliverable
**USABLE FOR YOUR PRACTICE** - Complete Phase 1 feature set

---

## QUICK REFERENCE

### Start Server
```bash
cd ~/edgecase
source venv/bin/activate
python main.py
```

### Access Application
- Mac: http://localhost:8080
- iPad (same WiFi): http://richards-macbook.local:8080

### Database Location
```
~/edgecase/data/edgecase.db
```

### Reset Database (Fresh Start)
```bash
rm ~/edgecase/data/edgecase.db
python main.py  # Will recreate with default types
```

### Check Database Schema
```bash
sqlite3 ~/edgecase/data/edgecase.db
.schema entries  # See all columns
PRAGMA table_info(entries);  # Detailed column info
.quit
```

### Git Commands
```bash
git status                      # Check what changed
git add .                       # Stage all changes
git commit -m "Description"     # Commit with message
git push                        # Push to GitHub
git log --oneline -5            # Last 5 commits
```

---

*This navigation map is updated as the project evolves.*  
*For project plan and timeline, see: EdgeCase_Project_Plan_v2_0.md*  
*For session logs and decisions, see: Session summaries*  
*Last updated: November 10, 2025 (Week 3, Day 2)*
