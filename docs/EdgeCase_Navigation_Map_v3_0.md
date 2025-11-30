# EdgeCase Equalizer - Navigation Map v3.0

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025  
**Last Updated:** November 29, 2025 - Phase 1 Complete

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** (23 days, Nov 7-29, 2025) with Flask + SQLite, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with 7 Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite (12 tables)
- PDF Generation: ReportLab 4.4.5
- Development: MacBook Air M4, macOS Sequoia

**Access:**
- Mac: http://localhost:8080
- iPad (same WiFi): http://richards-macbook.local:8080

---

## PHASE 1 STATUS: COMPLETE ✅

### Project Statistics
- **Development:** 23 days (Nov 7-29, 2025)
- **Total Routes:** 50+ across 7 blueprints
- **Entry Types:** 8 (6 client + 2 ledger)
- **Database Tables:** 12
- **Templates:** 17 HTML files with external CSS/JS

### All Systems Complete
- ✅ All 8 entry types
- ✅ Statement system (PDF, email, payments, write-offs)
- ✅ Ledger system (income/expense, financial reports)
- ✅ Calendar integration (.ics + AppleScript)
- ✅ Export to PDF/Markdown with attachments
- ✅ Session summary reports
- ✅ Comprehensive billing (profile fees, guardian splits, link groups)

---

## DIRECTORY STRUCTURE

```
~/edgecase/
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── core/
│   └── database.py              # Database class (~2,000 lines)
├── pdf/
│   ├── generator.py             # Statement + Session report PDFs
│   └── ledger_report.py         # Financial report PDFs
├── web/
│   ├── app.py                   # Main Flask app (77 lines)
│   ├── utils.py                 # Shared utilities
│   └── blueprints/
│       ├── clients.py           # Client management + session reports
│       ├── entries.py           # Entry CRUD (6 types)
│       ├── ledger.py            # Income/Expense + financial reports
│       ├── scheduler.py         # Calendar integration
│       ├── statements.py        # Statement generation + payments
│       ├── settings.py          # Configuration
│       └── types.py             # Client type management
├── templates/                   # 17 HTML templates
│   ├── base.html
│   ├── main_view.html
│   ├── client_file.html
│   ├── ledger.html
│   ├── ledger_report.html
│   ├── outstanding_statements.html
│   ├── session_report.html
│   ├── export.html
│   ├── scheduler.html
│   └── ... (entry forms, settings, etc.)
├── static/
│   ├── css/                     # 15+ CSS files
│   └── js/                      # 15+ JS files
├── assets/                      # Logo, signature
├── attachments/                 # Uploaded files
│   ├── {client_id}/{entry_id}/  # Client attachments
│   └── ledger/{entry_id}/       # Ledger attachments
└── data/
    └── edgecase.db              # SQLite database
```

---

## BLUEPRINTS OVERVIEW

### 1. clients_bp (clients.py)
- Main view with client list
- Client file with entry timeline
- Link group management
- **Session summary reports** (NEW)
- Export entries to PDF/Markdown

### 2. entries_bp (entries.py)
- Profile, Session, Communication
- Absence, Item, Upload
- Edit history tracking
- Attachment handling

### 3. ledger_bp (ledger.py)
- Income and expense entries
- Category and payee management
- **Financial reports with PDF**

### 4. statements_bp (statements.py)
- Statement generation
- PDF invoice creation
- Email workflow (mailto + AppleScript)
- Payment tracking
- **Write-off functionality**
- **View PDF without sending**

### 5. scheduler_bp (scheduler.py)
- Calendar event creation
- Natural language parsing
- .ics file generation
- AppleScript Calendar integration

### 6. types_bp (types.py)
- Client type CRUD
- Color palette management
- Retention settings

### 7. settings_bp (settings.py)
- Practice info
- Logo/signature upload
- File number settings
- Statement settings
- Email settings

---

## KEY ROUTES

### Client Routes
```
GET  /                           # Main view
GET  /client/<id>                # Client file
GET  /client/<id>/session-report # Session summary report
GET  /client/<id>/export         # Export entries
POST /client/<id>/export/pdf     # Generate export PDF
POST /client/<id>/export/markdown # Generate export Markdown
```

### Statement Routes
```
GET  /statements                 # Outstanding statements
POST /statements/generate        # Generate statements
POST /statements/mark-sent/<id>  # Send statement (PDF + email)
POST /statements/mark-paid       # Record payment
POST /statements/write-off       # Write off unpaid
GET  /statements/view-pdf/<id>   # View PDF without sending
```

### Ledger Routes
```
GET  /ledger                     # Income/expense list
GET  /ledger/report              # Financial report form
GET  /ledger/report/calculate    # Preview totals (JSON)
GET  /ledger/report/pdf          # Generate report PDF
```

### Scheduler Routes
```
GET  /client/<id>/schedule       # Schedule form
POST /client/<id>/schedule       # Generate event
```

---

## DATABASE TABLES (12)

1. **clients** - Client records
2. **client_types** - Customizable categories
3. **entries** - Unified entry storage (THE CORE)
4. **link_groups** - Couples/family/group therapy
5. **client_links** - Link group membership with fees
6. **attachments** - File uploads
7. **expense_categories** - User-defined categories
8. **payees** - Expense payee names
9. **settings** - Application configuration
10. **archived_clients** - Retention archives
11. **statement_portions** - Payment tracking

---

## PDF GENERATORS

### pdf/generator.py
- `StatementPDFGenerator` class
- `generate_statement_pdf()` - Professional invoices
- `generate_session_report_pdf()` - Session summaries

### pdf/ledger_report.py
- `generate_ledger_report_pdf()` - Financial reports

---

## QUICK REFERENCE

### Start Server
```bash
cd ~/edgecase
source venv/bin/activate
python main.py
```

### Key URLs
- Main View: http://localhost:8080/
- Ledger: http://localhost:8080/ledger
- Statements: http://localhost:8080/statements
- Settings: http://localhost:8080/settings

### Git Commands
```bash
git status
git add .
git commit -m "message"
git push
```

---

## PHASE 2 PREVIEW

1. **Security + Encryption** - SQLCipher, master password
2. **File Retention + Backup** - Automated retention, incremental backups
3. **AI Integration** - Local LLM for note expansion
4. **Final Polish** - Themes, bug fixes, documentation

---

## VERSION HISTORY

- v1.0: Initial creation (Nov 8, 2025)
- v2.0: Calendar integration (Nov 25, 2025)
- v2.1: Statement system (Nov 28, 2025)
- v2.2: Ledger reports (Nov 29, 2025)
- **v3.0: Phase 1 Complete (Nov 29, 2025)**

---

*EdgeCase Equalizer - Phase 1 Complete*  
*"Every practice is an edge case"*
