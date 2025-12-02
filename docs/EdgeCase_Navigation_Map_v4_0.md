# EdgeCase Equalizer - Navigation Map v4.0

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025  
**Last Updated:** December 1, 2025 - Phase 2 Complete

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** (Nov 7 - Dec 1, 2025) with Flask + SQLite/SQLCipher, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with 11 Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite with SQLCipher encryption (12 tables)
- PDF Generation: ReportLab 4.4.5
- Encryption: cryptography (Fernet for attachments)
- Development: MacBook Air M4, macOS Sequoia

**Access:**
- Mac: http://localhost:8080
- iPad (same WiFi): http://richards-macbook.local:8080

---

## PHASE STATUS

### Phase 1: Core Functionality ✅ COMPLETE (Nov 29, 2025)
- All 8 entry types
- Statement system with PDF generation
- Ledger system with financial reports
- Calendar integration
- Export to PDF/Markdown
- Comprehensive billing

### Phase 2: Professional Features ✅ COMPLETE (Dec 1, 2025)
- SQLCipher database encryption
- Fernet attachment encryption
- Master password authentication
- Session timeout (configurable)
- Backup/restore system (full + incremental)
- Auto-backup on login
- Performance optimizations

### Phase 3: AI Integration ⏸️ DEFERRED
- Local LLM for note assistance (planned, not critical for launch)

---

## PROJECT STATISTICS

| Metric | Count |
|--------|-------|
| Python Lines | ~12,000 |
| Blueprints | 11 |
| Database Tables | 12 |
| Templates | 33 (23 main + 2 components + 8 entry forms) |
| CSS Files | 25 |
| JS Files | 24 |
| Entry Types | 8 (6 client + 2 ledger) |
| Routes | 60+ |

---

## DIRECTORY STRUCTURE

```
~/edgecase/
├── main.py                      # Application entry point (21 lines)
├── requirements.txt             # Python dependencies (13 packages)
├── core/
│   ├── database.py              # Database class (1,788 lines)
│   └── encryption.py            # Fernet file encryption (48 lines)
├── pdf/
│   ├── generator.py             # Statement + Session report PDFs
│   ├── ledger_report.py         # Financial report PDFs
│   ├── client_export.py         # Client file export
│   ├── formatting.py            # PDF helpers
│   └── templates.py             # PDF templates
├── utils/
│   ├── backup.py                # Backup/restore system (915 lines)
│   ├── formatters.py            # Date/string formatting
│   └── validators.py            # Input validation
├── ai/                          # Placeholder for future AI features
│   ├── assistant.py             # (empty)
│   ├── model_manager.py         # (empty)
│   └── prompts.py               # (empty)
├── web/
│   ├── app.py                   # Flask app initialization (219 lines)
│   ├── utils.py                 # Shared web utilities
│   └── blueprints/
│       ├── auth.py              # Login/logout, session management
│       ├── backups.py           # Backup/restore UI
│       ├── clients.py           # Client management, session reports
│       ├── entries.py           # Entry CRUD (6 types)
│       ├── ledger.py            # Income/Expense, financial reports
│       ├── links.py             # Link group management
│       ├── scheduler.py         # Calendar integration
│       ├── settings.py          # Practice configuration
│       ├── statements.py        # Statement generation, payments
│       └── types.py             # Client type management
├── templates/                   # 33 HTML templates
│   ├── base.html
│   ├── login.html
│   ├── change_password.html
│   ├── main_view.html
│   ├── client_file.html
│   ├── add_client.html
│   ├── deleted_clients.html
│   ├── ledger.html
│   ├── ledger_report.html
│   ├── outstanding_statements.html
│   ├── session_report.html
│   ├── export.html
│   ├── schedule_form.html
│   ├── backups.html
│   ├── settings.html
│   ├── manage_types.html
│   ├── add_edit_type.html
│   ├── manage_links.html
│   ├── add_edit_link_group.html
│   ├── components/
│   │   ├── attachment_upload.html
│   │   └── edit_history.html
│   └── entry_forms/
│       ├── profile.html
│       ├── session.html
│       ├── communication.html
│       ├── absence.html
│       ├── item.html
│       ├── upload.html
│       ├── income.html
│       └── expense.html
├── static/
│   ├── css/                     # 25 CSS files
│   │   ├── shared.css           # Common patterns (1,181 lines)
│   │   └── [page-specific].css
│   ├── js/                      # 24 JS files (all with JSDoc)
│   │   ├── lucide.min.js        # Icon library
│   │   ├── color_palette.js     # Type color picker
│   │   └── [page-specific].js
│   ├── fonts/                   # Lexend font family
│   ├── favicons/
│   └── img/                     # Background images
├── assets/                      # Practice logo, signature
├── attachments/                 # Encrypted file uploads
│   ├── {client_id}/{entry_id}/  # Client attachments
│   └── ledger/{entry_id}/       # Ledger attachments
├── backups/                     # Backup files + manifest.json
└── data/
    └── edgecase.db              # SQLCipher encrypted database
```

---

## BLUEPRINTS OVERVIEW (11)

### 1. auth_bp (auth.py) - NEW in Phase 2
- Login/logout
- Password change
- Session management
- Session timeout enforcement

### 2. backups_bp (backups.py) - NEW in Phase 2
- Backup settings page
- Create backup (auto full/incremental)
- Restore from backup
- Delete old backups
- Cloud folder configuration

### 3. clients_bp (clients.py)
- Main view with client list
- Client file with entry timeline
- Session summary reports
- Export entries to PDF/Markdown
- Deleted clients view

### 4. entries_bp (entries.py)
- Profile, Session, Communication
- Absence, Item, Upload
- Edit history tracking
- Attachment handling (encrypted)

### 5. ledger_bp (ledger.py)
- Income and expense entries
- Category and payee management
- Financial reports with PDF

### 6. links_bp (links.py) - Extracted from clients
- Link group CRUD
- Member management
- Fee allocation

### 7. statements_bp (statements.py)
- Statement generation
- PDF invoice creation
- Email workflow (mailto + AppleScript)
- Payment tracking
- Write-off functionality

### 8. scheduler_bp (scheduler.py)
- Calendar event creation
- Natural language parsing
- .ics file generation
- AppleScript Calendar integration

### 9. types_bp (types.py)
- Client type CRUD
- Color palette management
- Retention settings

### 10. settings_bp (settings.py)
- Practice info
- Logo/signature upload
- File number settings
- Statement settings
- Email settings
- Session timeout settings

### 11. Main App Routes (app.py)
- Auto-backup check
- Restore message API
- Placeholder routes (scheduler, billing)

---

## DATABASE TABLES (12)

1. **clients** - Client records
2. **client_types** - Customizable categories
3. **entries** - Unified entry storage (THE CORE)
4. **link_groups** - Couples/family/group therapy
5. **client_links** - Link group membership with fees
6. **attachments** - Encrypted file uploads
7. **expense_categories** - User-defined categories
8. **payees** - Expense payee names
9. **settings** - Application configuration
10. **archived_clients** - Retention archives
11. **statement_portions** - Payment tracking

---

## KEY FEATURES

### Security (Phase 2)
- SQLCipher encrypted database
- Fernet encrypted attachments
- Master password authentication
- Configurable session timeout (15/30/60/120 min or never)
- Thread-local database connections

### Backup System (Phase 2)
- Full backups (weekly or first backup)
- Incremental backups (daily changes only)
- Auto-backup on login (configurable frequency)
- Cloud folder support (iCloud, Dropbox, Google Drive)
- One-click restore with safety backup
- Backup deletion with orphan handling

### Performance (Phase 2)
- Persistent database connections (4s → 100ms per page)
- Thread-local storage for Flask workers

---

## QUICK REFERENCE

### Start Server
```bash
cd ~/edgecase
source venv/bin/activate
python main.py
```

### Key URLs
- Login: http://localhost:8080/login
- Main View: http://localhost:8080/
- Ledger: http://localhost:8080/ledger
- Statements: http://localhost:8080/statements
- Backups: http://localhost:8080/backups
- Settings: http://localhost:8080/settings

### Git Commands
```bash
git status
git add .
git commit -m "message"
git push
```

---

## RECENT CHANGES (Dec 1, 2025)

- Auto-backup on login with configurable frequency
- Thread-local storage for database connections
- Performance optimization (persistent connections)
- JSDoc comments added to all JS files
- Form field width fixes
- Session cookie reliability improvements

---

## VERSION HISTORY

- v1.0: Initial creation (Nov 8, 2025)
- v2.0: Calendar integration (Nov 25, 2025)
- v2.1: Statement system (Nov 28, 2025)
- v2.2: Ledger reports (Nov 29, 2025)
- v3.0: Phase 1 Complete (Nov 29, 2025)
- **v4.0: Phase 2 Complete (Dec 1, 2025)**

---

*EdgeCase Equalizer - Phase 2 Complete*  
*"Every practice is an edge case"*
