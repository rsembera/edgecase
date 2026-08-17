# EdgeCase Equalizer - Navigation Map v5.6

**Purpose:** Quick reference for code location, current status, and project overview  
**Created:** November 8, 2025  
**Last Updated:** June 21, 2026

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists. Built using **AI-assisted development** (Nov 7 - Dec 2, 2025) with Flask + SQLite/SQLCipher, it uses an **Entry-based architecture** where all client records are stored as unified entries.

**Tech Stack:**
- Backend: Python 3.13, Flask with 11 Blueprints
- Frontend: HTML, External CSS/JS files, Vanilla JavaScript
- Database: SQLite with SQLCipher encryption (13 tables)
- PDF Generation: ReportLab 4.4.5
- Encryption: cryptography (Fernet v1 + Argon2id/AES-256-GCM v2 for attachments)
- AI: llama-cpp-python with Gemma 4 12B QAT model
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
- Local LLM integration (Gemma 4 12B QAT)
- AI Scribe for session notes
- Four actions: Write Up, Proofread, Expand, Condense
- Auto-platform detection (Mac/Windows/Linux)
- Model download with progress tracking
- Settings page model management

---

## PROJECT STATISTICS

| Metric | Count |
|--------|-------|
| Python Lines (app) | ~17,000 |
| HTML Lines | ~7,900 |
| JavaScript Lines | ~9,900 |
| CSS Lines | ~7,500 |
| **Total Lines** | **~42,000** |
| Blueprints | 11 |
| Database Tables | 13 |
| Templates | 33 |
| CSS Files | 28 |
| JS Files | 29 |
| Python Files | 58 app (+ 19 test files) |
| Entry Types | 8 (6 client + 2 ledger) |
| Routes | 105 |
| Automated Tests | 201 |

---

## DIRECTORY STRUCTURE

```
~/Applications/edgecase/
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies (+ requirements-dev.txt for pytest/ruff)
├── pyproject.toml               # Package config + [tool.ruff] lint config
├── README.md                    # Installation instructions
├── core/
│   ├── config.py                # Path configuration (~165 lines)
│   ├── database.py              # Database FACADE — composes the db/ mixins (~623 lines; was ~2,350)
│   ├── billing.py               # Statement/payment math (totals, guardian splits, apply_payment)
│   ├── money.py                 # Decimal / cents money helpers
│   ├── encryption.py            # Fernet file encryption (v1)
│   ├── encryption_v2.py         # Argon2id / AES-256-GCM file encryption (v2)
│   ├── encryption_v3.py         # Envelope encryption + recovery keys (v3)
│   ├── migrate_crypto.py        # Crypto migration (v1/v2 -> v3), password change, recovery
│   └── db/                      # Database domain mixins (split from database.py)
│       ├── settings.py          #   SettingsMixin
│       ├── client_types.py      #   ClientTypeMixin
│       ├── clients.py           #   ClientMixin
│       ├── edit_history.py      #   EditHistoryMixin (+ is_entry_locked)
│       ├── entries.py           #   EntryMixin (add/update/lock/redact)
│       ├── errors.py            #   EntryLockedError (leaf module, no imports)
│       ├── ledger.py            #   LedgerMixin (payees, categories, ledger)
│       ├── links.py             #   LinkMixin (link groups)
│       └── retention.py         #   RetentionMixin (archiving)
├── pdf/
│   ├── generator.py             # Statement + session report PDFs (~1,050 lines)
│   ├── ledger_report.py         # Financial report PDFs (~570 lines)
│   └── client_export.py         # Client file export (~1,100 lines)
├── utils/
│   └── backup.py                # Backup/restore system (~1,280 lines)
├── ai/
│   ├── assistant.py             # Model loading and generation (~380 lines)
│   └── prompts.py               # Prompt templates for AI actions
├── web/
│   ├── app.py                   # Flask app initialization (~505 lines)
│   ├── utils.py                 # Shared web utilities incl. diff engine (~390 lines)
│   ├── cli.py                   # Command-line interface
│   └── blueprints/
│       ├── ai.py                # AI Scribe routes
│       ├── auth.py              # Login/logout, session management
│       ├── backups.py           # Backup/restore UI
│       ├── clients.py           # Client management, session reports (~1,080 lines)
│       ├── ledger.py            # Income/Expense, financial reports
│       ├── links.py             # Link group management
│       ├── scheduler.py         # Calendar integration
│       ├── settings.py          # Practice configuration
│       ├── types.py             # Client type management
│       ├── entries/             # entries_bp PACKAGE (split from entries.py ~1,920)
│       │   ├── common.py        #   blueprint + get_db + shared helpers
│       │   ├── profile.py       #   profile entries
│       │   ├── sessions.py      #   session entries
│       │   ├── communications.py
│       │   ├── absences.py
│       │   ├── items.py
│       │   ├── uploads.py
│       │   ├── attachments.py   #   encrypted attachment upload/serve/delete
│       │   └── redaction.py
│       └── statements/          # statements_bp PACKAGE (split from statements.py ~1,080)
│           ├── common.py        #   blueprint + get_db
│           ├── views.py         #   outstanding-statements index
│           ├── generation.py    #   find-unbilled, generate
│           ├── payments.py      #   mark-paid, write-off (+ ledger helpers)
│           └── delivery.py      #   mark-sent, PDF download/view, email
├── web/templates/               # 39 HTML templates (incl. entry_forms/, components/)
│   ├── (base, login, client_file, ledger, settings, outstanding_statements, ...)
│   ├── components/              # attachment_upload, edit_history
│   └── entry_forms/             # profile, session, communication, absence, item, upload, income, expense
├── web/static/
│   ├── css/                     # 28 CSS files (shared.css + page-specific)
│   ├── js/                      # 29 JS files (lucide, choices + page-specific)
│   ├── fonts/                   # Lexend font family
│   ├── favicons/
│   └── img/                     # Background images
├── models/                      # AI model (git-ignored): gemma-4-12B-it-QAT-Q4_0.gguf
├── tests/                       # 31 test files, 642 tests (pytest; cheap-KDF switch in conftest)
├── docs/                        # Navigation Map, Project Status, Architecture Decisions, etc.
├── assets/                      # Practice logo, signature
├── attachments/                 # Encrypted file uploads
├── backups/                     # Backup files + manifest.json
└── data/
    └── edgecase.db              # SQLCipher encrypted database
```

---

## BLUEPRINTS OVERVIEW (11 blueprints + app-level routes)

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

### 5. entries_bp (entries/ package)
- Profile, Session, Communication
- Absence, Item, Upload
- Edit history tracking
- Attachment handling (encrypted)

### 6. ledger_bp (ledger.py)
- Income and expense entries
- Category and payee management
- Financial reports with PDF (optional attachment appendix)

### 7. links_bp (links.py)
- Link group CRUD
- Member management
- Fee allocation

### 8. statements_bp (statements/ package)
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
- Local LLM (Gemma 4 12B QAT)
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
cd ~/Applications/edgecase
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
cd ~/Applications/edgecase
source venv/bin/activate
pytest tests/ -v
```

---

## RECENT CHANGES

### June 2026
- **God-file refactors (Jun 20):** `core/database.py` (~2,350 lines -> 623-line facade + `core/db/` domain mixins), `web/blueprints/entries.py` (~1,920 -> `entries/` package), and `web/blueprints/statements.py` (~1,080 -> `statements/` package) split behind unchanged public interfaces (endpoint sets + imports identical). No god-files remain.
- **ruff lint gate + bug hunt (Jun 20-21):** added ruff (`[tool.ruff]`, pyflakes `F` rules) as a "did I break a reference?" gate; it caught a latent `EntryLockedError` NameError, fixed via the leaf module `core/db/errors.py` + a regression test. Also closed an upload edit-history audit gap and removed dead scaffolding from descoped features. Tests grew to 201.
- **Attachment encryption v2 (Argon2id / AES-256-GCM):** `core/encryption_v2.py` + `core/migrate_crypto.py` (started Jun 14).
- **Envelope encryption v3 (recovery keys):** `core/encryption_v3.py` + `core/migrate_crypto.py` (Aug 9). Key-info magic `ECC3`; recovery screens are `recovery_key*.html` and `recover*.html`; entry points on the login page and Settings → Security.

### February 2026
- Financial Report attachment appendix option (Feb 1)
  - Receipts/invoices attached to ledger entries can be included in tax reports
  - Images rendered inline, PDFs merged at end

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
- v5.5: Production updates, backup improvements (Jan 7, 2026)
- **v5.6: God-file refactors, ruff lint gate, post-refactor bug hunt (Jun 21, 2026)**

---

*EdgeCase Equalizer - All Phases Complete*  
*In Production Since January 3, 2026*  
*"Every practice is an edge case"*
