# EdgeCase Equalizer - Navigation Map v2.1

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025 (Week 1, Day 2)  
**Last Updated:** November 28, 2025 (Statement System Complete)

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** with Flask + SQLite, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite (SQLCipher encryption planned for Phase 2)
- PDF Generation: ReportLab 4.4.5
- Development: MacBook Air M4, macOS Sequoia

**Access:**
- Mac: http://localhost:8080
- iPad (same WiFi): http://richards-macbook.local:8080

---

## CURRENT STATE (Nov 28, 2025 - Statement System Complete)

### Project Statistics
- **Total Routes:** 40+ across 7 blueprints
- **Entry Types:** 8 (6 client entry types + 2 ledger types)
- **Database Tables:** 12 tables (including statement_portions)
- **Templates:** 14 HTML files with external CSS/JS
- **Code Reduction:** ~4,300 lines eliminated through blueprint extraction + optimization

### Implementation Status

**✅ COMPLETE - Client Entry Types (6 of 6):**
- Profile (demographics, fees, guardian billing)
- Session (therapy notes, fee breakdown, pro bono)
- Communication (emails, calls, notes, file attachments)
- Absence (cancellations with fees)
- Item (billable items with tax)
- Upload (file attachments)

**✅ COMPLETE - Ledger Entry Types (2 of 2):**
- Income (payment tracking with receipts, auto-generated from statements)
- Expense (business expenses with categories)

**✅ COMPLETE - Core Systems:**
- Entry-based database with 12 tables
- Flask blueprints architecture (7 blueprints)
- Shared utility functions (Phase 10)
- Comprehensive billing (profile fees, guardian splits, link groups)
- Edit history system (smart word-level diff)
- File attachment system (upload/download/delete)
- Client type management (9 curated colors)
- File number generation (3 modes)
- Link groups (couples/family/group therapy)
- Year/month timeline grouping
- Real-time entry filtering
- Payment status tracking (green/yellow/red indicators)
- Ledger with income/expense tracking
- Calendar integration (.ics + AppleScript)
- **Statement generation and tracking**
- **PDF invoice generation (ReportLab)**
- **Email workflow (mailto + AppleScript)**
- **Auto-income creation on payment**

**⏳ REMAINING FOR PHASE 1:**
- Write-off unpaid invoices
- Ledger financial reports (tax time PDFs)
- Export entries to PDF and Markdown (with attachments)

---

## DIRECTORY STRUCTURE

```
~/edgecase/
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies (includes reportlab)
├── core/                        # Core business logic
│   ├── __init__.py
│   └── database.py              # Database class (~2,000 lines)
├── pdf/                         # PDF generation (NEW)
│   ├── __init__.py
│   └── generator.py             # Statement PDF generator (~600 lines)
├── web/                         # Flask web application
│   ├── __init__.py
│   ├── app.py                   # Main Flask app (77 lines)
│   ├── utils.py                 # Shared utilities
│   └── blueprints/              # Modular route handlers
│       ├── __init__.py
│       ├── clients.py           # Client management routes
│       ├── entries.py           # Entry CRUD routes
│       ├── ledger.py            # Income/Expense routes
│       ├── scheduler.py         # Calendar integration
│       ├── settings.py          # Settings and configuration
│       ├── statements.py        # Statement generation (NEW)
│       └── types.py             # Client type management
├── templates/                   # Jinja2 HTML templates (14 files)
│   ├── base.html
│   ├── main_view.html
│   ├── client_file.html
│   ├── ledger.html
│   ├── schedule_form.html
│   ├── outstanding_statements.html  # (NEW)
│   ├── entry_forms/
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
├── static/
│   ├── css/                    # External stylesheets (14+ files)
│   └── js/                     # External JavaScript (14+ files)
├── data/
│   └── edgecase.db            # SQLite database
├── attachments/                # File uploads (NOT in git)
│   ├── {client_id}/{entry_id}/
│   └── ledger/{entry_id}/
└── assets/                     # User uploads (logo, signature)
```

---

## KEY FILES

### Core Application

**main.py** - Application entry point

**web/app.py** (77 lines)
- Flask app initialization
- Blueprint registration (7 blueprints)
- Jinja2 filters

**web/utils.py**
- `parse_date_from_form(form_data)` - Convert dropdowns to timestamp
- `get_today_date_parts()` - Return dict with today's date components
- `save_uploaded_files(files, descriptions, entry_id, db, client_id=None)` - Handle uploads
- `generate_content_diff(old, new)` - Smart word-level diff for edit history

### Blueprints

**web/blueprints/clients.py** (~400 lines)
- Client list view (main view) with payment status indicators
- Client file view (entry timeline)
- Add client, change client type
- Linked client groups display

**web/blueprints/entries.py** (~500 lines)
- Profile, Session, Communication, Absence, Item, Upload CRUD
- Attachment download/view/delete
- Session renumbering logic
- Edit history tracking with content normalization

**web/blueprints/ledger.py** (~350 lines)
- Ledger main view
- Income/Expense create/edit/delete
- Payee and category management

**web/blueprints/statements.py** (~500 lines) - NEW
- Outstanding statements page
- Find unbilled entries by date range
- Generate statements (handles guardian billing splits)
- Mark sent (generates PDF, creates Communication, triggers email)
- Record payments (full/partial, auto-creates Income)
- PDF generation and download routes
- AppleScript email integration

**web/blueprints/scheduler.py** (~200 lines)
- Schedule form for client appointments
- Natural language date/time parsing
- .ics file generation
- AppleScript integration for Mac Calendar

**web/blueprints/types.py** (~100 lines)
- Manage client types
- Add/edit/delete types

**web/blueprints/settings.py** (~150 lines)
- Settings page
- Practice info API
- Logo/signature upload
- Calendar settings
- Statement settings (currency, email body, attestation, etc.)

### PDF Generation

**pdf/generator.py** (~600 lines) - NEW
- `generate_statement_pdf(db, portion_id, output_path, assets_path)`
- Professional invoice layout with logo/signature
- Practice info header, bill-to section
- Line items table (sessions, absences, items)
- Attestation and payment instructions
- Auto-scaling images, email detection in payment text

### Database

**core/database.py** (~2,000 lines)
- Database class with all CRUD operations
- Schema initialization and migrations
- 12 tables including statement_portions
- Payment status calculation (get_payment_status)
- Pending invoice counting (count_pending_invoices)
- Edit history tracking
- Entry locking system

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
  ...

entries_bp (14+ routes):
  Profile, Session, Communication, Absence, Item, Upload CRUD
  Attachment download/view/delete

ledger_bp (7 routes):
  GET  /ledger                     - Ledger main view
  Income and Expense CRUD

statements_bp (8 routes) - NEW:
  GET  /statements                 - Outstanding statements page
  GET  /statements/find-unbilled   - Find unbilled entries
  POST /statements/generate        - Generate statements
  POST /statements/mark-sent/<id>  - Mark sent (PDF + email)
  POST /statements/mark-paid       - Record payment
  GET  /statements/pdf/<id>        - Download PDF
  GET  /statements/view-pdf/<id>   - View PDF in browser
  POST /statements/send-applescript-email - AppleScript email

scheduler_bp (2 routes):
  GET  /client/<id>/schedule       - Schedule form
  POST /client/<id>/schedule       - Create calendar event

types_bp (5 routes):
  Type management

settings_bp (13 routes):
  Settings, practice info, logo/signature, calendar, statements
```

---

## STATEMENT SYSTEM

**Architecture:** Statements are generated from billable entries (Sessions, Absences, Items) and tracked via `statement_portions` table.

**Workflow:**
1. User selects date range, clicks "Find Unbilled"
2. System shows clients with unbilled entries
3. User selects clients, clicks "Generate Statements"
4. System creates Statement entry + statement_portions (handles guardian splits)
5. Statement appears in Outstanding Statements list (status: 'ready')
6. User clicks "Mark Sent":
   - Generates PDF invoice
   - Creates Communication entry in client file with PDF attached
   - Triggers email (mailto or AppleScript)
   - Updates status to 'sent', records date_sent
7. User clicks payment icon to record payment:
   - Records full or partial payment
   - Auto-creates Income entry in ledger
   - Updates status to 'partial' or 'paid'

**Payment Status Indicators (Main View):**
- 🟢 Green: No outstanding balance (paid or no statements)
- 🟡 Yellow: Statement sent, awaiting payment
- 🔴 Red: Overdue (sent 30+ days ago, still unpaid)

**PDF Layout:**
- Logo + practice info header
- Bill-to section (client or guardian)
- Line items table (date, service, duration, fee)
- Total
- Attestation text
- Signature with date
- Payment instructions

---

## SETTINGS - STATEMENTS SECTION

**Fields:**
- `currency` - Currency code (CAD, USD, EUR, etc.)
- `registration_info` - Professional registration number
- `payment_instructions` - Payment details for invoices
- `include_attestation` - Boolean
- `attestation_text` - Customizable attestation
- `email_method` - 'mailto' or 'applescript'
- `email_from_address` - For AppleScript (must match Mail.app account)
- `statement_email_body` - Email body template (follows auto-generated salutation)

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

### Key URLs
- Main View: http://localhost:8080/
- Outstanding Statements: http://localhost:8080/statements
- Ledger: http://localhost:8080/ledger
- Settings: http://localhost:8080/settings

---

## SYSTEM CAPABILITIES

**EdgeCase Equalizer can now:**
- ✅ Manage clients with customizable types (9 curated colors)
- ✅ Track 6 client entry types with comprehensive edit history
- ✅ Track 2 ledger entry types (income/expense)
- ✅ Generate file numbers (3 modes)
- ✅ Profile Fee Override (individual client fees)
- ✅ Guardian Billing (split payments to 2 guardians by percentage)
- ✅ Link Groups (couples/family/group therapy)
- ✅ Upload and manage file attachments
- ✅ Track income and expenses with categories
- ✅ Filter, sort, search in all views
- ✅ Payment status indicators (green/yellow/red)
- ✅ Calendar integration (natural language, .ics, AppleScript)
- ✅ **Generate statements from unbilled entries**
- ✅ **Create PDF invoices with professional layout**
- ✅ **Email statements (mailto or AppleScript with attachment)**
- ✅ **Track payments (full/partial)**
- ✅ **Auto-create Income entries on payment**
- ✅ **Communication entry with PDF attachment on send**

**Remaining for Phase 1:**
- ⏳ Write-off unpaid invoices
- ⏳ Ledger financial reports (tax time PDFs)
- ⏳ Export entries to PDF/Markdown with attachments

---

## VERSION HISTORY

- v1.0: Initial creation (Week 1, Day 2)
- v1.6: Comprehensive billing system complete (Week 3, Day 1)
- v1.7: Edit history system complete (Week 3, Day 4)
- v1.8: Upload entry type complete (Week 3, Day 5)
- v1.9: Phase 10 optimization, split into modular docs (Nov 23, 2025)
- v2.0: Calendar integration complete (Nov 25, 2025)
- v2.1: Statement system complete - PDF generation, email workflow, payment tracking (Nov 28, 2025)

---

## DETAILED DOCUMENTATION

For more detailed information, see:
1. **Database_Schema.md** - Complete table definitions
2. **Route_Reference.md** - All routes by blueprint
3. **Architecture_Decisions.md** - Design philosophy
4. **Debugging_Guide.md** - Common issues and solutions

---

*Last updated: November 28, 2025 (Statement System Complete)*
