# EdgeCase Equalizer - Navigation Map

**Purpose:** Quick reference for finding code, understanding architecture, and debugging  
**Created:** November 8, 2025 (Week 1, Day 2)  
**Last Updated:** November 8, 2025

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. It uses an **Entry-based architecture** where all client records (profiles, sessions, communications, etc.) are stored as entries in a unified database table.

**Tech Stack:**
- Backend: Python 3.13, Flask
- Frontend: HTML, CSS (inline), Vanilla JavaScript
- Database: SQLite (will add SQLCipher encryption in Phase 2)
- No external frameworks: Pure Python/Flask/SQLite

**Current State (Week 1, Day 2):**
- Entry-based database with 8 tables
- Flask web interface with 5 routes
- Client list view with filtering, sorting, search
- Profile entry creation and editing
- Contact management with smart phone display

---

## DIRECTORY STRUCTURE

```
~/edgecase/
├── main.py                      # Application entry point (launches Flask)
├── requirements.txt             # Python dependencies
├── core/                        # Core business logic
│   ├── __init__.py
│   ├── database.py              # Database class, all CRUD operations
│   ├── client.py                # (Placeholder for future)
│   ├── entry.py                 # (Placeholder for future)
│   ├── encryption.py            # (Phase 2 - SQLCipher)
│   └── ...
├── web/                         # Flask web application
│   ├── __init__.py
│   ├── app.py                   # Flask routes and application logic
│   ├── auth.py                  # (Phase 3 - Authentication)
│   ├── templates/               # Jinja2 HTML templates
│   │   ├── base.html           # Base layout (header, nav, styling)
│   │   ├── main_view.html      # Client list with filters
│   │   ├── client_file.html    # Client entry timeline
│   │   ├── add_client.html     # New client form
│   │   ├── manage_types.html   # Client types management
│   │   └── entry_forms/
│   │       └── profile.html    # Profile entry form
│   └── static/                 # Static assets (future)
│       ├── css/
│       ├── js/
│       └── img/
├── pdf/                         # PDF generation (Phase 1, Week 4)
├── ai/                          # AI features (Phase 2, Week 7)
├── utils/                       # Utility functions
└── assets/                      # User uploads (logo, signature)
```

---

## DATABASE SCHEMA

**Location:** `~/edgecase/core/database.py` (lines ~42-230 in `_initialize_schema()`)

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
- class: Entry type ('profile', 'session', 'communication', 'statement', 'absence', 'item')
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
- session_number, service, session_date, session_time
- duration, fee, is_consultation
- mood, affect, risk_assessment

-- Communication-specific fields
- comm_recipient: 'to_client', 'from_client', 'internal_note'
- comm_type: 'email', 'phone', 'text', 'administrative'

-- Statement-specific fields
- statement_total, payment_status, payment_notes
- date_sent, date_paid, is_void

-- Edit tracking
- edit_history: JSON array of edits
- locked: 0 or 1 (immutable after locking)
- locked_at: Unix timestamp
```

**Design Philosophy:** Class-specific fields are NULL for entries that don't use them. This is simpler than 6 separate tables and allows easy querying across all entry types.

#### 4. `client_links` (Couples/family therapy)
```sql
- id: Primary key
- client_id_1, client_id_2: Foreign keys to clients
- created_at: Unix timestamp
- UNIQUE constraint on (client_id_1, client_id_2)
```

#### 5. `entry_links` (Linked entries across files)
```sql
- id: Primary key
- entry_id_1, entry_id_2: Foreign keys to entries
- is_active: Toggle link on/off
- UNIQUE constraint on (entry_id_1, entry_id_2)
```

#### 6. `attachments` (File uploads)
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
**Lines:** ~350 total  
**Purpose:** All database operations

### Key Classes

#### `Database` (Main class)
**Constructor:** `__init__(db_path: str)` (lines ~20-30)
- Creates database file if doesn't exist
- Calls `_initialize_schema()` to create tables

**Key Methods:**

##### Schema Management
- `_initialize_schema()` (lines ~42-230)
  - Creates all 7 tables if they don't exist
  - Calls `_create_default_types()`
  
- `_create_default_types()` (lines ~232-260)
  - Creates Active and Inactive types on first run
  - Only runs if no system types exist

##### Client Type Operations
- `add_client_type(type_data: Dict)` → int (lines ~264-285)
- `get_client_type(type_id: int)` → Dict (lines ~287-295)
- `get_all_client_types()` → List[Dict] (lines ~297-305)

##### Client Operations
- `add_client(client_data: Dict)` → int (lines ~309-330)
- `get_client(client_id: int)` → Dict (lines ~332-345)
- `get_all_clients(type_id: Optional[int])` → List[Dict] (lines ~347-365)
- `update_client(client_id: int, client_data: Dict)` → bool (lines ~367-385)
- `search_clients(search_term: str)` → List[Dict] (lines ~387-405)

##### Entry Operations
- `add_entry(entry_data: Dict)` → int (lines ~409-450)
  - Dynamically builds INSERT based on provided fields
  - Handles all entry types (profile, session, etc.)
  
- `get_entry(entry_id: int)` → Dict (lines ~452-462)
- `get_client_entries(client_id: int, entry_class: Optional[str])` → List[Dict] (lines ~464-480)
- `update_entry(entry_id: int, entry_data: Dict)` → bool (lines ~482-505)

##### Helper Methods
- `get_last_session_date(client_id: int)` → int (lines ~509-522)
  - Returns Unix timestamp of most recent session
  
- `get_profile_entry(client_id: int)` → Dict (lines ~524-536)
  - Returns profile entry for client (used to populate contact info)
  
- `get_payment_status(client_id: int)` → str (lines ~538-565)
  - Returns 'paid', 'pending', or 'overdue'
  - Checks most recent statement

---

## WEB MODULE: `web/app.py`

**Location:** `~/edgecase/web/app.py`  
**Lines:** ~250 total  
**Purpose:** Flask application, all routes and web logic

### Flask Setup (lines ~1-20)

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
db_path = Path.home() / "edgecase_data" / "edgecase.db"
db = Database(str(db_path))
```

### Custom Jinja Filters (lines ~22-28)

```python
@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to YYYY-MM-DD."""
    if not timestamp:
        return '-'
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
```

**Usage in templates:** `{{ client.created_at|timestamp_to_date }}`

### Routes

#### 1. Main View: `@app.route('/')` (lines ~32-110)
**Purpose:** Display client list with filtering, sorting, search

**Query Parameters:**
- `type` (list): Client type IDs to filter (multi-select)
- `sort`: Field to sort by ('file_number', 'last_name', 'first_name', 'created', 'last_session')
- `order`: 'asc' or 'desc'
- `search`: Search term

**Logic Flow:**
1. Get filter parameters from query string
2. Default to Active type if no types selected
3. Get all client types for filter UI
4. Get clients (filtered or searched)
5. For each client:
   - Get client type info
   - Get profile entry for contact info
   - Determine which phone to display based on preferred_contact
   - Set contact icon (📞 for call, 💬 for text)
   - Get last session date
   - Get payment status
6. Sort clients by selected field
7. Render template with all data

**Smart Phone Display Logic (lines ~68-95):**
```python
if client['preferred_contact'] == 'call_cell':
    client['display_phone'] = client['phone']
    client['contact_icon'] = '📞'
elif client['preferred_contact'] == 'text':
    # Use text_number preference, default to cell
    if client['text_number'] == 'none':
        # No texting, show phone for calling
    else:
        client['display_phone'] = client['phone'] or home or work
        client['contact_icon'] = '💬'
# ... etc
```

**Template:** `main_view.html`

#### 2. Client File: `@app.route('/client/<int:client_id>')` (lines ~112-130)
**Purpose:** Display single client's entry timeline

**Logic:**
1. Get client by ID
2. Get client type
3. Get all entries for client
4. Render template

**Template:** `client_file.html`

#### 3. Add Client: `@app.route('/add_client', methods=['GET', 'POST'])` (lines ~132-155)
**Purpose:** Create new client

**GET:** Show form with all client types  
**POST:** Save client, redirect to client file

**Template:** `add_client.html`

#### 4. Edit Profile: `@app.route('/client/<int:client_id>/profile', methods=['GET', 'POST'])` (lines ~157-205)
**Purpose:** Create or edit client profile entry

**Logic:**
1. Get client and existing profile (if exists)
2. **POST:** Prepare profile_data dict with all form fields
   - Date of birth combines 3 dropdowns into YYYY-MM-DD
   - Phone numbers auto-formatted by JavaScript
   - All contact fields saved
3. If profile exists: update, else: create new
4. Redirect to client file

**Important Fields:**
- `text_number`: 'none', 'cell', 'home', or 'work'
- `preferred_contact`: 'email', 'call_cell', 'call_home', 'call_work', 'text'
- `ok_to_leave_message`: 'yes' or 'no'

**Template:** `entry_forms/profile.html`

#### 5. Manage Types: `@app.route('/types')` (lines ~207-212)
**Purpose:** View all client types (management coming in Week 2)

**Template:** `manage_types.html`

#### 6. Add Type: `@app.route('/add_type', methods=['POST'])` (lines ~214-227)
**Purpose:** Create new client type (called from manage_types)

---

## TEMPLATES

**Location:** `~/edgecase/web/templates/`

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
        /* All CSS inline (lines ~10-140) */
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

**Design System:**
- Primary color: `#00aa88` (teal)
- Secondary: `#1a365d` (navy)
- Accent: (will add in Week 4)
- Font: System fonts (-apple-system, BlinkMacSystemFont, etc.)

### `main_view.html` (Client List)
**Lines:** ~250  
**Purpose:** Display filterable, sortable, searchable client list

**Key Sections:**

1. **Controls Section** (lines ~60-95)
   - Type filter checkboxes (multi-select)
   - Search box
   - Add Client button

2. **Client Table** (lines ~97-180)
   - Headers with sort links
   - Payment indicator dots (🟢🟡🔴)
   - Type badges with color coding
   - Contact info with smart display:
     - Email: mailto: link
     - Phone: tel: or sms: link
     - Preferred contact underlined
     - ⚠️ if no message allowed

3. **Legend** (lines ~182-200)
   - Payment status indicators
   - Preferred contact explanation
   - No-message warning

**JavaScript Features:**
- Auto-submit filter form on checkbox change
- Clickable rows navigate to client file
- Click on email/phone doesn't trigger row click

### `client_file.html` (Entry Timeline)
**Lines:** ~100  
**Purpose:** Display all entries for a client

**Key Features:**
- Profile entry highlighted (green background, left border)
- Edit/Create Profile button (context-aware)
- Entry list with class, description, date
- Contact info preview (email, phone from profile)

### `add_client.html` (New Client Form)
**Lines:** ~70  
**Purpose:** Create new client

**Fields:**
- Client type (dropdown)
- File number (text input)
- First, middle, last name

**Note:** This just creates the client record. Profile entry created separately.

### `entry_forms/profile.html` (Profile Form)
**Lines:** ~350  
**Purpose:** Create or edit client profile entry

**Key Features:**

1. **Date of Birth** (lines ~80-110)
   - Three dropdowns (year, month, day)
   - Year range: 2024 → 1900
   - Combines into hidden field: YYYY-MM-DD

2. **Phone Fields** (lines ~130-165)
   - Cell, Home, Work, Emergency Contact
   - Auto-formatting via JavaScript
   - Accepts: 1234567890 → (123) 456-7890

3. **Text Number Selector** (lines ~167-177)
   - Options: None, Cell, Home, Work
   - Used when preferred_contact = 'text'

4. **Preferred Contact** (lines ~185-194)
   - Options: Email, Call Cell, Call Home, Call Work, Text
   - Determines display in main view

5. **JavaScript** (lines ~250-350)
   - Phone formatting (no duplicate digits bug!)
   - Date dropdown → hidden field
   - Event listeners on all phone inputs

**Form Submission:**
- POST to `/client/<id>/profile`
- All fields optional except those auto-populated
- Redirects to client file after save

### `manage_types.html` (Client Types)
**Lines:** ~80  
**Purpose:** View all client types (management UI coming Week 2)

**Current Features:**
- Table of all types
- Shows: name, code, color, session fee, duration
- System types marked

**Coming Soon:**
- Add Type modal
- Edit Type functionality
- Delete Type (with validation)

---

## DATA FLOW

### Creating a New Client (Full Workflow)

1. **User clicks "Add Client"** in main view
2. **GET /add_client** → Shows form
3. **User fills form and submits**
4. **POST /add_client**:
   - `db.add_client(client_data)`
   - Creates client record in database
   - Returns new client_id
5. **Redirect to /client/<client_id>** (client file view)
6. **User clicks "Create Profile"**
7. **GET /client/<client_id>/profile** → Shows profile form
8. **User fills profile and submits**
9. **POST /client/<client_id>/profile**:
   - `db.add_entry(profile_data)` with class='profile'
   - Creates profile entry in database
10. **Redirect to /client/<client_id>**
11. **Client file now shows profile entry**
12. **Main view now shows contact info from profile**

### Displaying Client List (Query Flow)

1. **User navigates to /** (main view)
2. **Flask route handler:**
   - Parse query params (type, sort, order, search)
   - `db.get_all_client_types()` → All types for filter
   - `db.get_all_clients(type_id)` → Clients by type
   - For each client:
     - `db.get_client_type(type_id)` → Type info
     - `db.get_profile_entry(client_id)` → Contact info
     - `db.get_last_session_date(client_id)` → Last session
     - `db.get_payment_status(client_id)` → Payment status
   - Sort clients by selected field
3. **Render main_view.html** with all data
4. **Template displays:**
   - Filtered clients
   - Color-coded type badges
   - Payment indicators
   - Smart contact display (preferred underlined)
   - Clickable mailto: and tel: links

---

## COMMON DEBUGGING WORKFLOWS

### Issue: Phone number not saving

**Check:**
1. `web/app.py` line ~175: Is `phone` field in `profile_data` dict?
2. `core/database.py` line ~420: Is `phone` in `optional_fields` list?
3. `core/database.py` line ~435: Is value being added correctly?
4. Browser console: Any JavaScript errors preventing form submit?

**Test:**
```python
# In Flask route, add debug print
print(f"Profile data: {profile_data}")
# Check if phone field present and has expected value
```

### Issue: Client not appearing in main view

**Check:**
1. `web/app.py` line ~45: Type filter - is client's type selected?
2. `core/database.py` line ~355: Is `is_deleted = 0`?
3. `web/app.py` line ~50: Is search filtering them out?

**Test:**
```python
# In database
all_clients = db.get_all_clients()
print(f"Total clients: {len(all_clients)}")
for c in all_clients:
    print(f"  {c['file_number']}: type_id={c['type_id']}, deleted={c['is_deleted']}")
```

### Issue: Profile entry showing as "None"

**Cause:** Empty strings being stored as NULL in database

**Fix:** Ensure `add_entry()` converts None → '' (line ~440)

**Test:**
```python
profile = db.get_profile_entry(client_id)
print(f"Profile: {profile}")
# Check if fields are None vs ''
```

### Issue: Preferred contact not underlining

**Check:**
1. `web/app.py` line ~68-95: Is `preferred_contact` being set correctly?
2. `main_view.html` line ~145: Is template checking correct value?
3. Browser inspector: Is `text-decoration: underline` style applied?

**Test:**
```python
# In Flask route
print(f"Client {client['file_number']}: preferred={client['preferred_contact']}")
```

### Issue: Server won't start

**Check:**
1. Virtual environment activated? `source venv/bin/activate`
2. Dependencies installed? `pip list | grep Flask`
3. Database path exists? Check `~/edgecase_data/`
4. Port 8080 available? `lsof -ti:8080 | xargs kill -9`

**Test:**
```bash
cd ~/edgecase
source venv/bin/activate
python main.py
# Should see: "Running on http://0.0.0.0:8080"
```

---

## KEY DESIGN DECISIONS

### Why Entry-Based Architecture?

**Problem:** v1.6 had separate tables for notes, invoices, communications, etc. This meant:
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

### Why Flask Over Django?

**Reasons:**
- **Simplicity:** Flask is lightweight, no magic
- **Control:** We define everything explicitly
- **Learning:** Richard understands every line
- **Solo dev:** Don't need Django's admin, auth, ORM complexity

### Why Inline CSS?

**Reasons:**
- **Simplicity:** Everything in one file
- **No build step:** No webpack, no compilation
- **Easy to modify:** Find style right next to HTML
- **Phase 1 only:** Will extract to external CSS in Week 4 polish

**Trade-off:** Larger HTML files, some repetition (acceptable for Phase 1)

### Why No ORM?

**Reasons:**
- **Direct SQL:** Richard can see exactly what's happening
- **Performance:** No abstraction overhead
- **Simplicity:** One less library to learn
- **Debugging:** Easy to copy SQL and run manually

**Trade-off:** More verbose code (but more explicit and debuggable)

---

## FUTURE ADDITIONS (Not Yet Implemented)

### Week 2: Session & Communication Entries
- Session entry form with clinical fields
- Communication entry form
- Entry filtering in client file
- Client type management UI

### Week 3: Statements & Linking
- Statement generation from billable entries
- Client linking for couples/family therapy
- Entry linking across files
- Payment tracking

### Week 4: Polish & Export
- PDF generation (invoices, exports)
- UI/UX polish (HedgeDoc-inspired design)
- Practice settings (logo, signature)
- Export functionality

### Phase 2: Security (Week 5-7)
- SQLCipher encryption
- Entry locking (immutable records)
- File retention automation
- Incremental backup system
- AI integration (Mac only)

### Phase 3: Deployment (Optional)
- Authentication (Flask-Login)
- Raspberry Pi deployment
- Remote access configuration

---

## TODOS / KNOWN ISSUES

**From Session Notes:**

1. **Phone Validation** (Week 2)
   - Check that phone numbers have exactly 10 digits when saving
   - Show error message if invalid format
   - Location: `web/app.py` edit_profile route, or JavaScript validation

2. **Server Disconnect Handling** (Week 2)
   - Detect when Flask server stops
   - Show friendly error message in browser
   - Provide "reconnect" or "return to main view" button
   - Location: `base.html` - add JavaScript error handler

**Other Known Issues:**
- None currently tracked

---

## VERSION HISTORY

**v1.0 (Week 1, Day 2 - November 8, 2025):**
- Entry-based architecture implemented
- Flask web interface working
- Main view with filtering, sorting, search
- Profile entry form complete
- Smart contact display with preferred method
- Phone auto-formatting
- Date of birth dropdowns
- mailto: and tel: links
- No-message indicator

**Previous versions:** See EdgeCase_Project_Plan_v2_0.md for v1.6 architecture (superseded)

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
~/edgecase_data/edgecase.db
```

### Reset Database (Fresh Start)
```bash
rm ~/edgecase_data/edgecase.db
python main.py  # Will recreate with default types
```

### Git Commands
```bash
git status                      # Check what changed
git add .                       # Stage all changes
git commit -m "Description"     # Commit with message
git push                        # Push to GitHub
```

### Common Flask Debugging
```python
# Add to any route for debugging
print(f"Debug: {variable}")
import pdb; pdb.set_trace()  # Python debugger
```

### SQLite Query (Manual)
```bash
sqlite3 ~/edgecase_data/edgecase.db
.tables                         # List all tables
.schema entries                 # Show table schema
SELECT * FROM clients;          # Query data
.quit                          # Exit
```

---

*This navigation map will be updated as the project evolves.*  
*For project plan and timeline, see: EdgeCase_Project_Plan_v2_0.md*  
*For session logs and decisions, see: EdgeCase_Collaboration_Journal.md (to be created)*
