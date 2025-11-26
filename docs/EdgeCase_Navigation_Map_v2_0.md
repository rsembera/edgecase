# EdgeCase Equalizer - Navigation Map v2.0

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025 (Week 1, Day 2)  
**Last Updated:** November 25, 2025 (Calendar Integration Complete)

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** with Flask + SQLite, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite (SQLCipher encryption planned for Phase 2)
- Development: MacBook Air M4, macOS Sequoia

**Access:**
- Mac: http://localhost:8080
- iPad (same WiFi): http://richards-macbook.local:8080

---

## CURRENT STATE (Nov 25, 2025 - Calendar Integration Complete)

### Project Statistics
- **Total Routes:** 35+ across 6 blueprints
- **Entry Types:** 8 (6 client entry types + 2 ledger types)
- **Database Tables:** 11 tables (appointments table deprecated)
- **Templates:** 12 HTML files with external CSS/JS
- **Code Reduction:** ~4,300 lines eliminated through blueprint extraction + optimization

### Implementation Status

**✅ COMPLETE - Client Entry Types (6 of 6):**
- Profile (demographics, fees, guardian billing)
- Session (therapy notes, fee breakdown, pro bono)
- Communication (emails, calls, notes)
- Absence (cancellations with fees)
- Item (billable items with tax)
- Upload (file attachments)

**✅ COMPLETE - Ledger Entry Types (2 of 2):**
- Income (payment tracking with receipts)
- Expense (business expenses with categories)

**✅ COMPLETE - Core Systems:**
- Entry-based database with 11 tables
- Flask blueprints architecture (6 blueprints)
- Shared utility functions (Phase 10)
- Comprehensive billing (profile fees, guardian splits, link groups)
- Edit history system (smart word-level diff)
- File attachment system (upload/download/delete)
- Client type management (9 curated colors)
- File number generation (3 modes)
- Link groups (couples/family/group therapy)
- Year/month timeline grouping
- Real-time entry filtering
- Payment status tracking
- Ledger with income/expense tracking
- **Calendar integration (.ics + AppleScript)**

**⏳ NOT YET IMPLEMENTED:**
- Statement generation (auto-invoices)
- PDF generation for statements
- Income/Expense reports
- Data encryption (SQLCipher - Phase 2)
- Backup system (Phase 2 - placeholder button added)
- AI features (Phase 2)

---

## DIRECTORY STRUCTURE

```
~/edgecase/
├── main.py                      # Application entry point (77 lines)
├── requirements.txt             # Python dependencies
├── core/                        # Core business logic
│   ├── __init__.py
│   └── database.py              # Database class, all CRUD operations
├── web/                         # Flask web application
│   ├── __init__.py
│   ├── app.py                   # Main Flask app (77 lines - OPTIMIZED)
│   ├── utils.py                 # Shared utilities (Phase 10)
│   └── blueprints/              # Modular route handlers
│       ├── __init__.py
│       ├── clients.py           # Client management routes
│       ├── entries.py           # Entry CRUD routes
│       ├── ledger.py            # Income/Expense routes
│       ├── scheduler.py         # Calendar integration (NEW)
│       ├── settings.py          # Settings and configuration
│       └── types.py             # Client type management
├── templates/                   # Jinja2 HTML templates (12 files)
│   ├── base.html               # Base layout
│   ├── main_view.html          # Client list
│   ├── client_file.html        # Entry timeline
│   ├── ledger.html             # Income/Expense view
│   ├── schedule_form.html      # Calendar appointment form (NEW)
│   ├── entry_forms/            # Entry creation/edit forms
│   │   ├── profile.html
│   │   ├── session.html
│   │   ├── communication.html
│   │   ├── absence.html
│   │   ├── item.html
│   │   ├── upload.html
│   │   ├── income.html
│   │   └── expense.html
│   ├── settings.html
│   ├── manage_types.html
│   ├── manage_links.html
│   └── add_edit_link_group.html
├── static/                     # Static assets
│   ├── css/                    # External stylesheets (12 files)
│   └── js/                     # External JavaScript (12 files)
├── data/                       # Application data
│   └── edgecase.db            # SQLite database
├── attachments/                # File uploads (NOT in git)
│   ├── {client_id}/{entry_id}/ # Client entry attachments
│   └── ledger/{entry_id}/      # Ledger entry attachments
└── assets/                     # User uploads (logo, signature)
```

---

## KEY FILES

### Core Application (77 lines total)

**main.py** (1 line)
- Imports and runs Flask app

**web/app.py** (77 lines)
- Flask app initialization
- Blueprint registration (6 blueprints)
- Jinja2 filters
- Placeholder route (/billing)

**web/utils.py** (Phase 10)
- `parse_date_from_form(form_data)` - Convert dropdowns to timestamp
- `get_today_date_parts()` - Return dict with today's date components
- `save_uploaded_files(files, descriptions, entry_id, db, client_id=None)` - Handle uploads

### Blueprints (~1,600 lines total)

**web/blueprints/clients.py** (~400 lines)
- Client list view (main view)
- Client file view (entry timeline)
- Add client
- Change client type
- Linked client groups display

**web/blueprints/entries.py** (~450 lines)
- Profile create/edit
- Session create/edit
- Communication create/edit
- Absence create/edit
- Item create/edit
- Upload create/edit
- Attachment download/delete
- Session renumbering logic

**web/blueprints/ledger.py** (~350 lines)
- Ledger main view
- Income create/edit/delete
- Expense create/edit/delete
- Payee management
- Category management

**web/blueprints/scheduler.py** (~200 lines) - NEW
- Schedule form for client appointments
- Natural language date/time parsing
- .ics file generation (VEVENT, RRULE, VALARM)
- AppleScript integration for Mac Calendar
- Fallback page with auto-download on error

**web/blueprints/types.py** (~100 lines)
- Manage client types
- Add/edit/delete types
- Color palette management

**web/blueprints/settings.py** (~120 lines)
- Settings page
- Practice info API
- Logo/signature upload
- File number format settings
- Background image management
- Calendar settings API (NEW)

### Database

**core/database.py** (~1,500 lines)
- Database class with all CRUD operations
- Schema initialization and migrations
- 11 tables: clients, client_types, entries, link_groups, client_links, attachments, expense_categories, payees, settings
- Edit history tracking
- Entry locking system
- Note: appointments table exists but is deprecated/empty

---

## BLUEPRINT ARCHITECTURE

**Route Distribution:**

```
clients_bp (11 routes):
  GET  /                           - Main view (client list)
  GET  /client/<id>                - Client file (entry timeline)
  POST /client/<id>/change_type    - Change client type
  GET  /add_client                 - Add client form
  POST /add_client                 - Create client
  GET  /links                      - Manage link groups
  GET  /links/add                  - Add link group
  POST /links/add                  - Create link group
  GET  /links/<id>/edit            - Edit link group
  POST /links/<id>/edit            - Update link group
  POST /links/<id>/delete          - Delete link group

entries_bp (14 routes):
  GET  /client/<id>/profile        - Profile form
  POST /client/<id>/profile        - Create/edit profile
  GET  /client/<id>/session        - Session form
  POST /client/<id>/session        - Create session
  GET  /client/<id>/session/<eid>  - Edit session form
  POST /client/<id>/session/<eid>  - Update session
  GET  /client/<id>/communication  - Communication form
  POST /client/<id>/communication  - Create communication
  GET  /client/<id>/communication/<eid> - Edit communication form
  POST /client/<id>/communication/<eid> - Update communication
  (+ absence, item, upload - same pattern)
  GET  /attachment/<id>/download   - Download file
  GET  /attachment/<id>/view       - View file in browser
  POST /attachment/<id>/delete     - Delete file

ledger_bp (7 routes):
  GET  /ledger                     - Ledger main view
  GET  /ledger/income              - Income form
  POST /ledger/income              - Create income
  GET  /ledger/income/<id>         - Edit income form
  POST /ledger/income/<id>         - Update income
  POST /ledger/income/<id>/delete  - Delete income
  (+ expense - same pattern)

scheduler_bp (1 route) - NEW:
  GET  /client/<id>/schedule       - Schedule form
  POST /client/<id>/schedule       - Create calendar event (.ics or AppleScript)

types_bp (4 routes):
  GET  /types                      - Manage types
  GET  /add_type                   - Add type form
  POST /add_type                   - Create type
  GET  /edit_type/<id>             - Edit type form
  POST /edit_type/<id>             - Update type
  POST /types/<id>/delete          - Delete type

settings_bp (11 routes):
  GET  /settings                   - Settings page
  GET  /api/practice_info          - Get practice info
  POST /api/practice_info          - Save practice info
  POST /upload_logo                - Upload logo
  POST /upload_signature           - Upload signature
  POST /delete_logo                - Delete logo
  POST /delete_signature           - Delete signature
  GET  /api/backgrounds            - List backgrounds
  POST /upload_background          - Upload background
  POST /delete_background          - Delete background
  GET  /settings/file-number       - File number settings
  POST /settings/file-number       - Save file number settings
  GET  /api/calendar_settings      - Get calendar settings (NEW)
  POST /api/calendar_settings      - Save calendar settings (NEW)
```

---

## CALENDAR INTEGRATION (NEW)

**Architecture Decision:** Calendar apps are the source of truth for scheduling. EdgeCase generates events, doesn't store them.

**Features:**
- Natural language date/time parsing ("Friday 2pm", "Nov 28", "tomorrow")
- Quick entry field with real-time preview
- Repeat options: None, Weekly, Biweekly, Monthly
- Two configurable alerts (e.g., 15 min before, 1 day before)
- Meet link field (auto-recognized by Apple Calendar for video calls)

**Two Output Methods:**
1. **.ics file download** - Works everywhere (default)
2. **AppleScript direct add** - Mac only, adds directly to Calendar app

**Settings (in Settings page):**
- `calendar_method`: 'ics' or 'applescript'
- `calendar_name`: Target calendar name for AppleScript (e.g., "Work", "Clients")

**Fallback Behavior:**
If AppleScript fails (wrong calendar name), shows friendly message and auto-downloads .ics file.

**Event Content:**
- Title: Client file number (privacy - no names)
- Notes: Contact info (preferred method first) + user notes
- URL/Location: Meet link (if provided)
- Alerts: VALARM entries in .ics, display alarms in AppleScript

---

## QUICK REFERENCE

### Start Server
```bash
cd ~/edgecase
source venv/bin/activate
python main.py
```

### Database Location
```
~/edgecase/data/edgecase.db
```

### Common Tasks

**Add new route:**
1. Add to appropriate blueprint in ~/edgecase/web/blueprints/
2. Use shared utilities from web/utils for date parsing, file uploads
3. Follow existing patterns (see Route Reference doc)

**Debug entry sorting:**
- Check parse_time_to_seconds() in clients.py
- Ensure all entry types have time_str extraction in get_entry_sort_key()

**Add new entry type:**
1. Add to database schema (migrations in database.py)
2. Create route in entries.py blueprint
3. Create template in templates/entry_forms/
4. Add CSS/JS files to static/
5. Update client_file.html filter and dropdown

**Update navigation map:**
- Main overview: EdgeCase_Navigation_Map.md (this file)
- Database details: Database_Schema.md
- Route listings: Route_Reference.md
- Design decisions: Architecture_Decisions.md
- Debugging help: Debugging_Guide.md

---

## SYSTEM CAPABILITIES

**EdgeCase Equalizer can now:**
- ✅ Manage clients with customizable types (9 curated colors)
- ✅ Track 6 client entry types with comprehensive edit history
- ✅ Track 2 ledger entry types (income/expense)
- ✅ Generate file numbers (3 modes: Manual, Date-Initials, Prefix-Counter)
- ✅ Profile Fee Override (individual client fees)
- ✅ Guardian Billing (split payments to 2 guardians by percentage)
- ✅ Link Groups (couples/family/group therapy with per-member fees)
- ✅ Session fee calculation (dynamic based on format and profile)
- ✅ Upload and manage file attachments (with descriptions)
- ✅ Download/delete attachments
- ✅ Track income and expenses with categories
- ✅ Store receipts with expense entries
- ✅ Filter, sort, search clients and entries
- ✅ Year/month timeline grouping
- ✅ Real-time entry filtering (no reload)
- ✅ Payment status indicators (green/yellow/red)
- ✅ Responsive design (desktop + iPad)
- ✅ Professional UI with muted color palette
- ✅ Edit history with smart word-level diff
- ✅ Entry locking (immediate for billable, on first edit for Profile)
- ✅ Session numbering with offset support
- ✅ Pro bono session tracking (excluded from billing)
- ✅ **Calendar integration** (natural language parsing, .ics, AppleScript)
- ✅ **Video call link support** (auto-recognized by calendar apps)

**Cannot yet:**
- ⏳ Generate statements/invoices automatically
- ⏳ Create PDF invoices
- ⏳ Generate financial reports for tax time
- ⏳ Encrypt database (Phase 2)
- ⏳ Automated backups (Phase 2 - placeholder button added)
- ⏳ AI note expansion (Phase 2)

---

## DETAILED DOCUMENTATION

For more detailed information, see:

1. **Database_Schema.md** - Complete table definitions, field descriptions, design decisions
2. **Route_Reference.md** - All routes organized by blueprint with parameters and return values
3. **Architecture_Decisions.md** - Why we built things certain ways (billing, edit history, blueprints, calendar)
4. **Debugging_Guide.md** - Common issues, solutions, debugging workflows

---

## VERSION HISTORY

- v1.0: Initial creation (Week 1, Day 2)
- v1.6: Comprehensive billing system complete (Week 3, Day 1)
- v1.7: Edit history system complete (Week 3, Day 4)
- v1.8: Upload entry type complete (Week 3, Day 5)
- v1.9: Phase 10 optimization complete, split into modular docs (Nov 23, 2025)
- v2.0: Calendar integration complete (.ics, AppleScript, natural language) (Nov 25, 2025)

---

*This is the main navigation map. For detailed information on specific topics, refer to the specialized documentation files listed above.*

*Last updated: November 25, 2025 (Calendar Integration Complete)*
