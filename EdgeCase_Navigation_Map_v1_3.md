# EdgeCase Equalizer - Navigation Map v1.3

**Purpose:** Quick reference for finding code, understanding architecture, and debugging  
**Created:** November 8, 2025 (Week 1, Day 2)  
**Last Updated:** November 13, 2025 (Week 2, Day 5)

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. It uses an **Entry-based architecture** where all client records (profiles, sessions, communications, etc.) are stored as entries in a unified database table.

**Tech Stack:**
- Backend: Python 3.13, Flask
- Frontend: HTML, CSS (inline), Vanilla JavaScript
- Database: SQLite (will add SQLCipher encryption in Phase 2)
- No external frameworks: Pure Python/Flask/SQLite

**Current State (Week 2, Day 5):**
- Entry-based database with 8 tables
- Flask web interface with 17 routes
- 5 of 6 entry types implemented:
  - ✅ Profile (client demographics with flexible address)
  - ✅ Session (therapy notes with clinical fields)
  - ✅ Communication (emails, calls, administrative notes)
  - ✅ Absence (cancellations, no-shows with fees)
  - ✅ Item (billable items with smart tax calculation)
  - ⬜ Statement (auto-generated invoices - Week 3)
- Client list view with filtering, sorting (search coming Week 3)
- Client file view with year/month grouping and entry filtering
- Client type management (9-character names, no codes)
- File number format settings (3 modes: Manual, Date-Initials, Prefix-Counter)
- Flexible address fields (international support)
- Muted color palette UI throughout
- Responsive design (tested on desktop + iPad)

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
│   │   ├── add_client.html     # New client form (with dynamic file numbers)
│   │   ├── manage_types.html   # Client types management
│   │   ├── add_edit_type.html  # Add/Edit type form
│   │   ├── settings.html       # Settings page (file number format, practice info)
│   │   └── entry_forms/
│   │       ├── profile.html    # Profile entry form (5-row address)
│   │       ├── session.html    # Session entry form
│   │       ├── communication.html # Communication entry form
│   │       ├── absence.html    # Absence entry form
│   │       └── item.html       # Item entry form
│   └── static/                 # Static assets
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

**Location:** `~/edgecase/core/database.py` (lines 38-198 in `_initialize_schema()`)

### Tables

#### 1. `client_types` (Customizable client categories)
```sql
- id: Primary key
- name: Type name (max 9 chars: "Active", "Inactive", "Low Fee", etc.)
- color: Hex color for UI (#00AA88)
- file_number_style: How to generate file numbers
- file_number_prefix/suffix: Optional text
- file_number_counter: Auto-increment counter
- session_fee: Default session fee
- session_duration: Default duration (minutes)
- retention_period: Days to retain after inactive
- is_system: 1 for Active/Inactive (can't delete)
- created_at, modified_at: Unix timestamps
```

**Note:** The `code` field was removed in Week 2. Type names are now limited to 9 characters and displayed in full on badges.

**Default Types:** Active (green), Inactive (yellow) - created automatically on first run

#### 2. `clients` (Client records)
```sql
- id: Primary key
- file_number: Unique identifier (format depends on settings)
- first_name, middle_name, last_name: Name fields
- type_id: Foreign key to client_types
- session_offset: Starting session number (for migrated clients)
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
- address: Multi-line address (stores with \n line breaks)
- date_of_birth
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

#### 4-8. Other Tables
(Same as v1.2: client_links, entry_links, attachments, settings)

#### NEW: `settings` table usage (Week 2, Day 5)
The settings table now stores:
- Practice information (name, therapist, credentials, email, phone, **address** [single field], website)
- File number format settings (format, prefix, suffix, counter)
- Logo and signature filenames
- Currency, consultation fee/duration

---

## CORE MODULE: `core/database.py`

**Location:** `~/edgecase/core/database.py`  
**Lines:** ~650 total  
**Purpose:** All database operations

### Key Classes

#### `Database` (Main class)
**Constructor:** `__init__(db_path: str)` (lines 18-27)
- Creates database file if doesn't exist
- Calls `_initialize_schema()` to create tables

**Key Methods:**

##### Settings Management (NEW in Week 2, Day 5)
- `set_setting(key: str, value: str)` → None
  - Saves a setting to the settings table
  - Uses INSERT ... ON CONFLICT to update existing settings
  - Updates modified_at timestamp

- `get_setting(key: str, default: str)` → str
  - Retrieves a setting value
  - Returns default if key doesn't exist

##### Schema Management
- `_initialize_schema()` (lines 33-205)
  - Creates all 8 tables if they don't exist
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
- `add_client_type(type_data: Dict)` → int
- `get_client_type(type_id: int)` → Dict
- `get_all_client_types()` → List[Dict]
- `update_client_type(type_id: int, type_data: Dict)` → bool

**Note:** The `code` field is no longer used. Type names are limited to 9 characters.

##### Client Operations
- `add_client(client_data: Dict)` → int
- `get_client(client_id: int)` → Dict
- `get_all_clients(type_id: Optional[int])` → List[Dict]
- `update_client(client_id: int, client_data: Dict)` → bool
- `search_clients(search_term: str)` → List[Dict] (coming Week 3)

##### Entry Operations
(Same as v1.2 - comprehensive entry CRUD)

---

## WEB MODULE: `web/app.py`

**Location:** `~/edgecase/web/app.py`  
**Lines:** ~1100 total  
**Purpose:** Flask application, all routes and web logic

### Flask Setup (lines 1-28)
(Same as v1.2)

### Routes Overview

**Total Routes:** 17 (was 15 in v1.2)

1. `/` - Main view (client list)
2. `/client/<id>` - Client file view
3. `/client/<id>/change_type` - Change client type (POST)
4. `/add_client` - Add new client (with dynamic file number generation)
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
15. `/add_type` - Add client type (POST)
16. `/edit_type/<id>` - Edit client type (GET/POST)
17. `/settings` - Settings page
18. **NEW:** `/settings/file-number` - File number format settings (GET/POST)
19. **NEW:** `/api/practice_info` - Practice information (GET/POST)
20. `/api/backgrounds` - List background images (API)

### New Routes (Week 2, Day 5)

#### File Number Settings: `@app.route('/settings/file-number', methods=['GET', 'POST'])`
**Purpose:** Get or save file number format settings

**GET:** Returns current settings as JSON
```python
{
    'format': 'manual' | 'date-initials' | 'prefix-counter',
    'prefix': 'CLI',
    'suffix': 'XYZ',
    'counter': 1
}
```

**POST:** Saves settings to database
```python
{
    'format': 'prefix-counter',
    'prefix': 'CLI',
    'suffix': '',
    'counter': 1
}
```

**Implementation:**
- Uses `db.set_setting()` to save each setting
- Uses `db.get_setting()` to retrieve settings
- Settings keys: `file_number_format`, `file_number_prefix`, `file_number_suffix`, `file_number_counter`

#### Practice Info: `@app.route('/api/practice_info', methods=['GET', 'POST'])`
**Purpose:** Get or save practice information

**GET:** Returns all practice info from settings table
```python
{
    'success': True,
    'info': {
        'practice_name': 'Mindful Pathways',
        'therapist_name': 'Dr. Jane Smith',
        'credentials': 'MSW, RSW',
        'email': 'jane@practice.com',
        'phone': '(613) 123-4567',
        'address': '123 Main St\nSuite 200\nOttawa, ON K1A 0B1',  # Single field with \n
        'website': 'https://practice.com',
        'currency': 'CAD',
        'consultation_fee': '0.00',
        'consultation_duration': '20',
        'logo_filename': 'logo.png',
        'signature_filename': 'signature.png'
    }
}
```

**POST:** Saves practice information
- Stores each field as a separate setting in the database
- **Important:** Address is now a single field (was 3 separate lines in v1.2)

#### Updated Route: Add Client
**Changes in Week 2, Day 5:**
- Now handles file number auto-generation based on settings
- Three modes:
  1. **Manual:** User types file number freely
  2. **Date-Initials:** Auto-generates YYYYMMDD-ABC (updates as user types names)
  3. **Prefix-Counter:** Auto-generates PREFIX-0001-SUFFIX

**Logic:**
```python
# Get file number settings
format_setting = db.get_setting('file_number_format', 'manual')

if format_setting == 'manual':
    # Show empty field, user types
    file_number_readonly = False
    file_number_preview = ''
    
elif format_setting == 'date-initials':
    # Show YYYYMMDD-ABC, JavaScript updates as user types
    file_number_readonly = True
    today = date.today()
    file_number_preview = f"{today.strftime('%Y%m%d')}-ABC"
    
elif format_setting == 'prefix-counter':
    # Show next number PREFIX-0001-SUFFIX
    file_number_readonly = True
    counter = int(db.get_setting('file_number_counter', '1'))
    prefix = db.get_setting('file_number_prefix', '')
    suffix = db.get_setting('file_number_suffix', '')
    
    number_part = str(counter).zfill(4)
    file_number_preview = ''
    if prefix:
        file_number_preview += prefix + '-'
    file_number_preview += number_part
    if suffix:
        file_number_preview += '-' + suffix
```

---

## TEMPLATES

**Location:** `~/edgecase/web/templates/`

### New/Updated Templates (Week 2, Day 5)

#### `add_client.html` - Dynamic File Number Generation
**New JavaScript Feature:** Updates file number as user types names

```javascript
function updateFileNumber() {
    const fileNumberInput = document.getElementById('file_number');
    
    // Only update if field is readonly (auto-generated)
    if (!fileNumberInput.hasAttribute('readonly')) {
        return;
    }
    
    const isDateInitials = '{{ "date-initials" if file_number_readonly and "ABC" in file_number_preview else "" }}';
    
    if (isDateInitials === 'date-initials') {
        const first = document.getElementById('first_name').value.trim();
        const middle = document.getElementById('middle_name').value.trim();
        const last = document.getElementById('last_name').value.trim();
        
        const today = new Date();
        const dateStr = today.getFullYear() + 
                      String(today.getMonth() + 1).padStart(2, '0') + 
                      String(today.getDate()).padStart(2, '0');
        
        // Progressive initials - works with just first name!
        let initials = '';
        if (first) initials += first[0].toUpperCase();
        if (middle) initials += middle[0].toUpperCase();
        if (last) initials += last[0].toUpperCase();
        
        if (!initials) {
            initials = 'ABC';
        }
        
        fileNumberInput.value = dateStr + '-' + initials;
    }
}

// Add event listeners
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('first_name').addEventListener('input', updateFileNumber);
    document.getElementById('middle_name').addEventListener('input', updateFileNumber);
    document.getElementById('last_name').addEventListener('input', updateFileNumber);
    
    updateFileNumber();  // Run once on page load
});
```

**Behavior:**
- Manual mode: Empty field, user types
- Date-Initials mode: 
  - Shows "20251113-ABC" initially
  - Updates to "20251113-R" when first name typed
  - Updates to "20251113-RS" when last name typed
  - Updates to "20251113-RLS" when middle name typed
- Prefix-Counter mode: Shows "PREFIX-0001-SUFFIX", readonly

#### `settings.html` - File Number Format Section
**New Section:** File Number Format (lines ~800-950)

**HTML Structure:**
```html
<div class="settings-section">
    <h3>File Number Format</h3>
    <p>Choose how client file numbers are generated</p>
    
    <div class="form-group">
        <label for="file-number-format">Format</label>
        <select id="file-number-format" onchange="toggleFileNumberFields()">
            <option value="manual">Manual Entry</option>
            <option value="date-initials">Auto: Date + Initials (YYYYMMDD-ABC)</option>
            <option value="prefix-counter">Auto: Prefix + Counter</option>
        </select>
    </div>
    
    <!-- Prefix-Counter fields (hidden unless selected) -->
    <div id="prefix-counter-fields" style="display: none;">
        <div class="form-group">
            <label for="file-number-prefix">Prefix (optional)</label>
            <input type="text" id="file-number-prefix" maxlength="3">
        </div>
        
        <div class="form-group">
            <label for="file-number-suffix">Suffix (optional)</label>
            <input type="text" id="file-number-suffix" maxlength="3">
        </div>
        
        <div class="form-group">
            <label for="file-number-start">Starting Number</label>
            <input type="number" id="file-number-start" value="1" min="1">
        </div>
        
        <div class="form-group">
            <label>Preview</label>
            <div id="file-number-preview" class="preview-box">0001</div>
        </div>
    </div>
</div>
```

**JavaScript Functions:**
```javascript
// Toggle visibility of prefix-counter fields
function toggleFileNumberFields() {
    const format = document.getElementById('file-number-format').value;
    const fields = document.getElementById('prefix-counter-fields');
    
    if (format === 'prefix-counter') {
        fields.style.display = 'block';
        updateFileNumberPreview();
    } else {
        fields.style.display = 'none';
    }
}

// Update preview as user types
function updateFileNumberPreview() {
    const prefix = document.getElementById('file-number-prefix').value || '';
    const suffix = document.getElementById('file-number-suffix').value || '';
    const start = document.getElementById('file-number-start').value || '1';
    
    const paddedNumber = start.toString().padStart(4, '0');
    
    let preview = '';
    if (prefix) preview += prefix + '-';
    preview += paddedNumber;
    if (suffix) preview += '-' + suffix;  // Note the hyphen!
    
    document.getElementById('file-number-preview').textContent = preview;
    
    // Warn if too long (>12 chars)
    if (preview.length > 12) {
        document.getElementById('file-number-preview').style.borderColor = '#B91C1C';
        document.getElementById('file-number-preview').style.color = '#B91C1C';
    } else {
        document.getElementById('file-number-preview').style.borderColor = '#DEE2E6';
        document.getElementById('file-number-preview').style.color = '#111827';
    }
}

// Load current settings on page load
function loadFileNumberSettings() {
    fetch('/settings/file-number')
        .then(response => response.json())
        .then(data => {
            if (data.format) {
                document.getElementById('file-number-format').value = data.format;
                toggleFileNumberFields();
                
                if (data.format === 'prefix-counter') {
                    document.getElementById('file-number-prefix').value = data.prefix || '';
                    document.getElementById('file-number-suffix').value = data.suffix || '';
                    document.getElementById('file-number-start').value = data.counter || 1;
                    updateFileNumberPreview();
                }
            }
        })
        .catch(error => console.error('Error loading file number settings:', error));
}

// Save settings
function saveFileNumberSettings() {
    const format = document.getElementById('file-number-format').value;
    const settings = {
        format: format,
        prefix: format === 'prefix-counter' ? document.getElementById('file-number-prefix').value : '',
        suffix: format === 'prefix-counter' ? document.getElementById('file-number-suffix').value : '',
        counter: format === 'prefix-counter' ? parseInt(document.getElementById('file-number-start').value) : 1
    };
    
    fetch('/settings/file-number', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const status = document.getElementById('file-number-status');
            status.textContent = '✓ File number format saved';
            status.style.display = 'block';
            setTimeout(() => status.style.display = 'none', 3000);
        }
    })
    .catch(error => console.error('Error saving file number settings:', error));
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadBackgroundOptions();
    loadPracticeInfo();
    loadFileNumberSettings();  // NEW: Load file number settings
});
```

#### `settings.html` - Practice Address (Updated)
**Changed:** Address from 3 separate input fields to single 5-row textarea

**Old (v1.2):**
```html
<div class="form-group">
    <label for="address-line-1">Address Line 1</label>
    <input type="text" id="address-line-1" placeholder="e.g., 123 Main Street">
</div>

<div class="form-group">
    <label for="address-line-2">Address Line 2</label>
    <input type="text" id="address-line-2" placeholder="e.g., Suite 200">
</div>

<div class="form-group">
    <label for="address-line-3">Address Line 3</label>
    <input type="text" id="address-line-3" placeholder="e.g., Ottawa, ON K1A 0B1">
</div>
```

**New (v1.3):**
```html
<div class="form-group">
    <label for="practice-address">Practice Address</label>
    <textarea id="practice-address" rows="5" 
              placeholder="123 Main Street&#10;Suite 200&#10;Ottawa, ON K1A 0B1&#10;Canada"></textarea>
</div>
```

**CSS Update:**
```css
input[type="text"],
input[type="email"],
input[type="url"],
input[type="tel"],
input[type="number"],
textarea {
    width: 100%;
    max-width: 400px;
    padding: 0.75rem;
    border: 2px solid #DEE2E6;
    border-radius: 0.5rem;
    font-size: 1rem;
    color: #111827;
    transition: all 0.2s;
    background: #FBFCFD;
    font-family: 'Lexend', sans-serif;
}

textarea {
    resize: vertical;
    min-height: 120px;
}
```

**JavaScript Update:**
```javascript
// Save practice info
async function savePracticeInfo() {
    const practiceData = {
        practice_name: document.getElementById('practice-name').value,
        therapist_name: document.getElementById('therapist-name').value,
        credentials: document.getElementById('credentials').value,
        email: document.getElementById('practice-email').value,
        phone: document.getElementById('practice-phone').value,
        address: document.getElementById('practice-address').value,  // Single field!
        website: document.getElementById('website').value,
        currency: document.getElementById('currency').value,
        consultation_fee: document.getElementById('consultation-fee').value,
        consultation_duration: document.getElementById('consultation-duration').value
    };
    // ... rest of function
}

// Load practice info
async function loadPracticeInfo() {
    // ... fetch data ...
    document.getElementById('practice-address').value = data.info.address || '';  // Single field!
    // ... rest of function
}
```

#### `entry_forms/profile.html` - Client Address (Updated)
**Changed:** Address from 1-line input to 5-row textarea

**Old (v1.2):**
```html
<div class="form-row-full">
    <div class="form-group">
        <label for="address">Address</label>
        <input type="text" id="address" name="address" 
               value="{{ profile.address if profile else '' }}"
               placeholder="Street address">
    </div>
</div>
```

**New (v1.3):**
```html
<div class="form-row-full">
    <div class="form-group">
        <label for="address">Address</label>
        <textarea id="address" name="address" rows="5" 
                  placeholder="123 Main Street&#10;Apt 4B&#10;Toronto, ON M5V 1A1&#10;Canada">{{ profile.address if profile else '' }}</textarea>
    </div>
</div>
```

**CSS Update:**
```css
textarea {
    width: 100%;
    padding: 0.75rem;
    border: 2px solid #e2e8f0;
    border-radius: 0.5rem;
    font-size: 1rem;
    font-family: inherit;
    resize: vertical;
    transition: border-color 0.2s;
}

textarea:focus {
    outline: none;
    border-color: #00aa88;
}

/* Specific heights for different textareas */
textarea[name="address"] {
    min-height: 120px;
}

textarea[name="content"],
textarea[name="additional_info"] {
    min-height: 300px;
}
```

#### `manage_types.html` and `add_edit_type.html` - Type Management (Updated Earlier in Week 2)
**Changes:**
- Removed "Code" column from types table
- Type name field limited to 9 characters (`maxlength="9"`)
- Type badges now show full names instead of codes
- Two categories: Lifecycle States (Inactive, Deleted) and Client Types (Active, custom types)

**Testing notes from earlier session:**
- ✅ "Code" column gone from both tables
- ✅ Type names display full text on badges
- ✅ 9-character limit enforced in UI
- ✅ Can't type 10th character

---

## KEY DESIGN DECISIONS

### File Number Format System (NEW in Week 2, Day 5)

**Problem:** Different practices need different file numbering schemes

**Solution:** Three configurable modes stored in settings table

**Modes:**
1. **Manual:** User types file number freely (legacy support)
2. **Date-Initials:** YYYYMMDD-ABC (auto-generates, updates as user types names)
3. **Prefix-Counter:** PREFIX-0001-SUFFIX (auto-increments)

**Benefits:**
- Flexible for different practice workflows
- Date-Initials mode provides immediate visual feedback
- Prefix-Counter mode ensures sequential numbering
- Settings persist across sessions
- Easy to switch modes at any time

**Implementation:**
- Settings stored in database (file_number_format, prefix, suffix, counter)
- JavaScript in add_client.html updates preview in real-time
- Flask route handles both GET (load settings) and POST (save settings)
- Progressive initials: works with just first name (no longer requires last name)

### Address Field Flexibility (NEW in Week 2, Day 5)

**Problem:** Different countries have vastly different address formats

**Alternative considered:** Fixed 3-5 input fields

**Solution:** Single textarea with natural line breaks

**Benefits:**
- Works for any international address format
- Natural typing experience (just press Enter)
- Database stores with \n line breaks
- Display converts \n to <br> tags
- PDF generation can strip empty lines

**Trade-off:** Less structured data, but much more flexible

### Type Code Removal (Earlier in Week 2)

**Problem:** 3-letter codes were constraining and not user-friendly

**Solution:** Removed code field entirely, use full 9-character names

**Benefits:**
- Type badges more readable (show full names)
- Simpler data model (one less field)
- No need to invent codes for new types
- 9 characters is enough for clarity ("Low Fee", "High Rate", etc.)

---

## CURRENT STATE OF FEATURES

### Implemented ✅
- Complete database with automatic migrations
- Full CRUD for 5 entry types (Profile, Session, Communication, Absence, Item)
- Client Type management (9-char names, no codes)
- **File number format settings (3 modes: Manual, Date-Initials, Prefix-Counter)**
- **Dynamic file number generation in Add Client form**
- Client filtering by type
- Client sorting (file number, name, created, last session)
- Smart tax calculation (Item entries + Client Types)
- Calendar year absence tracking
- Drag-to-rearrange dashboard
- **Complete settings page (practice info + file number format)**
- Entry navigation (Session, Communication)
- **Flexible address fields (5-row textareas)**
- Muted color palette throughout
- **Responsive design (tested desktop + iPad)**

### Not Yet Implemented ⬜
- Search function in Main View (Week 3 Day 1 - 30 min)
- Statement generation (invoices) - Week 3
- Client linking (couples/family therapy) - Week 3
- Income/Expense tracking - Week 4
- PDF export - Week 4
- Entry sorting in client file
- Entry search within content
- Edit history tracking (columns exist but unused)
- Entry locking (Phase 2)
- File attachments (table exists but no upload UI)

---

## FILES MODIFIED IN WEEK 2 DAY 5

**Database:**
- `core/database.py` - Added `set_setting()` and `get_setting()` methods

**Backend:**
- `web/app.py` - Added `/settings/file-number` route
- `web/app.py` - Updated `/api/practice_info` route (single address field)
- `web/app.py` - Updated `/add_client` route (file number auto-generation)

**Templates:**
- `web/templates/add_client.html` - Added dynamic file number JavaScript
- `web/templates/settings.html` - Added file number format section
- `web/templates/settings.html` - Changed practice address to textarea
- `web/templates/settings.html` - Updated JavaScript functions
- `web/templates/entry_forms/profile.html` - Changed client address to textarea

---

## GIT COMMITS (WEEK 2 DAY 5)

**Last Commit:** "Complete file number format feature + address field improvements"

**Changes included:**
- File number format system (Manual, Date-Initials, Prefix-Counter)
- Dynamic initials calculation (progressive, works with first name only)
- Settings page loads current format on page load
- Preview shows correct hyphen formatting
- Practice address changed to 5-row textarea
- Client address changed to 5-row textarea
- Backend updated for single address field
- All features tested on desktop and iPad

---

## PRODUCTION READINESS STATUS

### Phase 1 Progress (Week 2 of 4)
- ✅ Week 1: Foundation (database, Flask, main view, client types)
- ✅ **Week 2: COMPLETE** (All entry types, settings, file numbers, addresses)
- ⏳ Week 3: Statement generation, Client linking, Search function
- ⏳ Week 4: Income/Expense tracking, PDF export, Final polish

### System Stability
- ✅ Database schema complete with migrations
- ✅ 5 of 6 entry types fully functional
- ✅ Entry filtering and year/month grouping working
- ✅ Smart tax calculation tested and working
- ✅ File number system tested (all 3 modes)
- ✅ Address fields support international formats
- ✅ Responsive design tested on iPad
- ✅ Muted color palette applied consistently
- ✅ No known bugs
- ✅ Git history clean with meaningful commits

**Status:** Week 2 complete. Ready for Week 3 (Statement generation, Client linking, Search).

---

## NEXT PRIORITIES (WEEK 3)

### Immediate Tasks
1. **Search Function** (Day 1 - 30 min)
   - Search across: First Name, Last Name, File Number, Email, Phone
   - Case-insensitive
   - Works alongside existing filters
   - Wire up existing search input in main_view.html

2. **Statement Entry** (Day 2-3)
   - Auto-generation from billable entries (Sessions, Absences, Items)
   - Calculate total with taxes
   - Payment tracking (paid/pending/overdue)
   - PDF generation with logo/signature

3. **Client Linking** (Day 4-5)
   - Link/unlink clients in main view
   - Visual grouping (indented display)
   - Entry creation across linked files
   - Smart invoicing (one pays, split, joint)

### Week 3 Deliverable
**All 6 entry types complete** + **Basic invoicing** + **Client linking**

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

### Test Responsive Design (Safari)
- ⌥⌘R (Option-Command-R) to enter Responsive Design Mode
- Select "iPad" from device dropdown
- Choose portrait or landscape orientation

### Settings Locations
```
Settings Table Keys:
- file_number_format: 'manual' | 'date-initials' | 'prefix-counter'
- file_number_prefix: Optional prefix text (e.g., 'CLI')
- file_number_suffix: Optional suffix text
- file_number_counter: Next number to use (e.g., 1, 2, 3...)
- practice_name, therapist_name, credentials, email, phone
- address: Multi-line practice address (with \n line breaks)
- website, currency, consultation_fee, consultation_duration
- logo_filename, signature_filename
```

---

*This navigation map is updated as the project evolves.*  
*For project plan and timeline, see: EdgeCase_Project_Plan_v2_1.md*  
*For session logs and decisions, see: Migration summaries in ~/edgecase/docs/*  
*Last updated: November 13, 2025 (Week 2, Day 5)*
