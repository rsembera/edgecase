# EdgeCase Equalizer - Navigation Map v5.5

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025  
**Last Updated:** January 12, 2026 - Folder picker for backup location

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** (Nov 7 - Dec 2, 2025) with Flask + SQLite/SQLCipher, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with 12 Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite with SQLCipher encryption (13 tables)
- PDF Generation: ReportLab 4.4.5
- Encryption: cryptography (Fernet for attachments)
- AI: llama-cpp-python with Hermes 3 8B model
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
- Export to PDF
- Comprehensive billing

### Phase 2: Professional Features ✅ COMPLETE (Dec 1, 2025)
- SQLCipher database encryption
- Fernet attachment encryption
- Master password authentication
- Session timeout (configurable)
- Backup/restore system (full + incremental)
- Auto-backup on logout/shutdown
- Performance optimizations

### Phase 3: AI Integration ✅ COMPLETE (Dec 2, 2025)
- Local LLM integration (Hermes 3 8B)
- AI Scribe for session notes
- Four actions: Write Up, Proofread, Expand, Condense
- Auto-platform detection (Mac/Windows/Linux)
- Model download with progress tracking
- Settings page model management

---

## PROJECT STATISTICS

| Metric | Count |
|--------|-------|
| Python Lines | ~14,300 |
| HTML Lines | ~7,200 |
| JavaScript Lines | ~8,900 |
| CSS Lines | ~7,600 |
| **Total Lines** | **~38,000** |
| Blueprints | 12 |
| Database Tables | 13 |
| Templates | 30 |
| CSS Files | 27 |
| JS Files | 27 |
| Python Files | 37 |
| Entry Types | 8 (6 client + 2 ledger) |
| Routes | 99 |
| Automated Tests | 41 |

---

## DIRECTORY STRUCTURE

```
~/apps/edgecase/
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── pyproject.toml               # Package configuration
├── README.md                    # Installation instructions
├── core/
│   ├── config.py                # Path configuration (~35 lines)
│   ├── database.py              # Database class (~1,930 lines)
│   └── encryption.py            # Fernet file encryption
├── pdf/
│   ├── generator.py             # Statement + Session report PDFs
│   ├── ledger_report.py         # Financial report PDFs
│   ├── client_export.py         # Client file export
│   ├── formatting.py            # PDF helpers
│   └── templates.py             # PDF templates
├── utils/
│   ├── backup.py                # Backup/restore system (~1,060 lines)
│   ├── formatters.py            # Date/string formatting
│   └── validators.py            # Input validation
├── ai/
│   ├── assistant.py             # Model loading and generation (~340 lines)
│   ├── model_manager.py         # Model download management
│   └── prompts.py               # Prompt templates for AI actions
├── web/
│   ├── app.py                   # Flask app initialization (~285 lines)
│   ├── utils.py                 # Shared web utilities (~265 lines)
│   ├── cli.py                   # Command-line interface
│   └── blueprints/
│       ├── ai.py                # AI Scribe routes (~330 lines)
│       ├── auth.py              # Login/logout, session management
│       ├── backups.py           # Backup/restore UI
│       ├── clients.py           # Client management, session reports
│       ├── entries.py           # Entry CRUD (~1,780 lines)
│       ├── ledger.py            # Income/Expense, financial reports
│       ├── links.py             # Link group management
│       ├── scheduler.py         # Calendar integration
│       ├── settings.py          # Practice configuration
│       ├── statements.py        # Statement generation, payments
│       └── types.py             # Client type management
├── web/templates/               # 30 HTML templates
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
│   ├── ai_scribe.html
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
├── web/static/
│   ├── css/                     # 27 CSS files
│   │   ├── shared.css           # Common patterns (~2,360 lines)
│   │   └── [page-specific].css
│   ├── js/                      # 27 JS files
│   │   ├── lucide.min.js        # Icon library
│   │   ├── choices.min.js       # Dropdown library
│   │   └── [page-specific].js
│   ├── fonts/                   # Lexend font family
│   ├── favicons/
│   └── img/                     # Background images
├── models/                      # AI models (git-ignored)
│   └── Hermes-3-Llama-3.1-8B.Q4_K_M.gguf
├── tests/
│   ├── test_edgecase.py         # 41 tests
│   └── pytest.ini               # Test configuration
├── assets/                      # Practice logo, signature
├── attachments/                 # Encrypted file uploads
├── backups/                     # Backup files + manifest.json
└── data/
    └── edgecase.db              # SQLCipher encrypted database
```

---

## BLUEPRINTS OVERVIEW (12)

### 1. ai_bp (ai.py)
- AI Scribe page
- Model status/download/unload endpoints
- Text processing with SSE streaming
- Platform auto-detection

### 2. auth_bp (auth.py)
- Login/logout
- Password change
- Session management
- Session timeout enforcement

### 3. backups_bp (backups.py)
- Backup settings page
- Create backup (auto full/incremental)
- Restore from backup
- Cloud folder configuration

### 4. clients_bp (clients.py)
- Main view with client list
- Client file with entry timeline
- Session summary reports
- Export entries to PDF
- Deleted clients view

### 5. entries_bp (entries.py)
- Profile, Session, Communication
- Absence, Item, Upload
- Edit history tracking
- Attachment handling (encrypted)

### 6. ledger_bp (ledger.py)
- Income and expense entries
- Category and payee management
- Financial reports with PDF

### 7. links_bp (links.py)
- Link group CRUD
- Member management
- Fee allocation

### 8. statements_bp (statements.py)
- Statement generation
- PDF invoice creation
- Email workflow (mailto + AppleScript)
- Payment tracking
- Write-off functionality

### 9. scheduler_bp (scheduler.py)
- Calendar event creation
- Natural language parsing
- .ics file generation
- AppleScript Calendar integration

### 10. types_bp (types.py)
- Client type CRUD
- Color palette management
- Retention settings

### 11. settings_bp (settings.py)
- Practice info
- Logo/signature upload
- File number settings
- Statement settings
- Email settings
- Session timeout settings
- 12h/24h time format

### 12. Main App Routes (app.py)
- Auto-backup check
- Restore message API
- Template filters (timestamp_to_date, close_tags)

---

## DATABASE TABLES (13)

1. **clients** - Client records
2. **client_types** - Status categories (Active, Inactive)
3. **entries** - Unified entry storage (THE CORE)
4. **link_groups** - Couples/family/group therapy
5. **client_links** - Link group membership with fees
6. **entry_links** - Links between entries across clients
7. **attachments** - Encrypted file uploads
8. **expense_categories** - User-defined categories
9. **payees** - Expense payee names
10. **income_payors** - Income payor names
11. **settings** - Application configuration
12. **archived_clients** - Retention archives
13. **statement_portions** - Payment tracking

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
- Auto-backup on logout/shutdown (configurable frequency)
- Cloud folder support (iCloud, Dropbox, Google Drive)
- One-click restore with safety backup
- Post-backup command support (e.g., rsync to remote server)

### AI Scribe (Phase 3)
- Local LLM (Hermes 3 Llama 3.1 8B)
- Four actions: Write Up, Proofread, Expand, Condense
- SSE streaming for real-time output
- Auto-platform detection (Metal on Mac, CPU elsewhere)
- Model download with progress tracking
- Integrated into Session entry form

### Performance
- Persistent database connections (4s → 100ms per page)
- Thread-local storage for Flask workers

---

## QUICK REFERENCE

### Start Server
```bash
cd ~/apps/edgecase
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

### Run Tests
```bash
cd ~/apps/edgecase
source venv/bin/activate
pytest tests/ -v
```

---

## RECENT CHANGES

### January 2026
- **In production** since January 3, 2026
- Folder picker modal for backup location settings (Jan 12)
- Backup now runs on logout/shutdown (not login)
- Backup on session timeout added
- Post-backup command runs on all shutdown paths
- WAL checkpoint before backup (captures recent changes)
- Desktop mode with heartbeat auto-shutdown
- Server disconnect overlay when heartbeat fails

### December 2025
- Security hardening (unique salts, rate limiting, input validation)
- App relocatability (EDGECASE_DATA, configurable port)
- Theme system update (Ink, Slate, Parchment themes added)
- Comprehensive testing complete
- System verified production-ready

---

## VERSION HISTORY

- v1.0: Initial creation (Nov 8, 2025)
- v2.0: Calendar integration (Nov 25, 2025)
- v2.1: Statement system (Nov 28, 2025)
- v2.2: Ledger reports (Nov 29, 2025)
- v3.0: Phase 1 Complete (Nov 29, 2025)
- v4.0: Phase 2 Complete (Dec 1, 2025)
- v5.0: AI Scribe Complete (Dec 2, 2025)
- v5.1: Backup protection, UI polish (Dec 4, 2025)
- v5.2: Bug investigation complete, autocomplete refactor (Dec 5, 2025)
- v5.3: Comprehensive testing complete, production ready (Dec 16, 2025)
- v5.4: Documentation accuracy audit (Dec 28, 2025)
- **v5.5: Production updates, backup improvements (Jan 7, 2026)**

---

*EdgeCase Equalizer - All Phases Complete*  
*In Production Since January 3, 2026*  
*"Every practice is an edge case"*
