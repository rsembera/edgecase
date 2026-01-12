# EdgeCase Equalizer - Project Status

**Owner:** Richard  
**Development Partner:** Claude  
**Last Updated:** January 7, 2026  
**Status:** ALL PHASES COMPLETE ✅ - In Production Use Since January 3, 2026

---

## PROJECT OVERVIEW

EdgeCase Equalizer is a web-based practice management system for independent therapists, built using AI-assisted development. The system uses an entry-based architecture where all client records are stored as unified entries in SQLite with SQLCipher encryption.

**Philosophy:** Every practice is an edge case - this software is built specifically for solo practitioners who need complete control, flexibility, and data ownership.

---

## PHASE STATUS

### Phase 1: Core Functionality ✅ COMPLETE (Nov 29, 2025)
- All 8 entry types (Profile, Session, Communication, Absence, Item, Upload, Income, Expense)
- Statement system with PDF generation and email
- Ledger system with financial reports
- Calendar integration (.ics + AppleScript)
- Export to PDF
- Billing features (profile fees, guardian splits, link groups)

### Phase 2: Professional Features ✅ COMPLETE (Dec 1, 2025)

| Feature | Status | Notes |
|---------|--------|-------|
| SQLCipher Encryption | ✅ Complete | Database fully encrypted |
| Attachment Encryption | ✅ Complete | Fernet encryption for all uploads |
| Master Password | ✅ Complete | Login system with session management |
| Password Change | ✅ Complete | Settings page |
| Session Timeout | ✅ Complete | 15/30/60/120 min or never |
| File Retention | ✅ Complete | Auto-prompts for expired inactive clients |
| Backup System | ✅ Complete | Full/incremental, auto-backup, restore, cloud folders |
| Performance | ✅ Complete | Persistent connections (4s → 100ms) |
| Code Quality | ✅ Complete | JSDoc comments, CSS deduplication |

### Phase 3: AI Integration ✅ COMPLETE (Dec 2, 2025)

| Feature | Status | Notes |
|---------|--------|-------|
| Local LLM Integration | ✅ Complete | llama-cpp-python with Hermes 3 8B |
| AI Scribe UI | ✅ Complete | Integrated into Session form |
| Write Up Action | ✅ Complete | Point-form to prose |
| Proofread Action | ✅ Complete | Grammar/spelling fixes |
| Expand Action | ✅ Complete | Add clinical detail |
| Condense Action | ✅ Complete | Make concise |
| Model Download | ✅ Complete | Progress tracking via SSE |
| Platform Detection | ✅ Complete | Auto-configures for Mac/Windows/Linux |
| Model Management | ✅ Complete | Download/unload in Settings |

---

## DEVELOPMENT STATISTICS

| Metric | Value |
|--------|-------|
| Development Period | Nov 7 - Dec 2, 2025 (26 days) |
| Total Lines of Code | ~30,000 |
| Python Lines | ~9,400 |
| HTML Lines | ~6,500 |
| JavaScript Lines | ~6,200 |
| CSS Lines | ~5,700 |
| Blueprints | 12 |
| Database Tables | 13 |
| Templates | 32 |
| Entry Types | 8 |
| Routes | 102 |
| Automated Tests | 41 |

---

## RECENT ACCOMPLISHMENTS

### January 6-7, 2026

**Backup System Improvements**
- Backup now runs on session timeout (not just explicit logout)
- Post-backup command (rsync) now runs on all shutdown paths: logout, Ctrl+C, atexit
- WAL checkpoint happens BEFORE backup (was after), ensuring recent changes are captured
- Renamed backup frequency `startup` → `session` to reflect logout-based backup behavior

**Desktop Mode Enhancements**
- Implemented Libram-style heartbeat monitoring for packaged apps
- Server auto-terminates after 30s without browser requests when `EDGECASE_DESKTOP=1`
- Repurposed existing `/api/session-status` polling (already runs every 30s)

**UI Consistency**
- Moved Back button to top-right in Settings and Backups pages
- Changed restore dropdown from chain hierarchy to flat reverse-chronological list

### December 27-30, 2025

**Security Hardening**
- Replaced fixed encryption salt with per-installation unique salts
- Added PRAGMA password escaping to prevent SQL injection
- Implemented persistent SECRET_KEY generation
- Created comprehensive input validators
- Added login rate limiting (5 attempts → 5-minute lockout)
- Replaced deprecated PyPDF2 with pypdf
- Created SECURITY.md for open-source release

**App Relocatability**
- Fixed hardcoded paths throughout codebase
- Added EDGECASE_DATA environment variable support
- Server port now configurable via --port flag or EDGECASE_PORT
- Added --help flag with usage information

**Theme System**
- Added Ink, Slate, Parchment themes (from Synesius)
- Removed underused themes (Ocean Breeze, Sunset Glow, Garden Path, Warm Stone)
- Final theme set: EdgeCase (default), Ink, Slate, Parchment, Tutti-Frutti

**Production Readiness**
- Server disconnect overlay when heartbeat fails
- Client names removed from page titles (browser history privacy)
- Canadian spelling preserved in AI Scribe prompts
- Database reset feature in Settings (requires password + typing "RESET")

### December 14-16, 2025

**Comprehensive Testing Complete**
- Completed comprehensive testing of all features
- Created fictional test dataset (8 clients covering all scenarios)
- Tested all entry types, billing workflows, statements, exports, backups
- Fixed 7 minor UX/logic issues discovered during testing
- All 41 automated tests passing
- System verified production-ready for January 2026 launch

**Final Polish**
- Updated info card logic (Active Clients count, Sessions This Month)
- Improved Main View column order (Created / Last Session)
- Fixed link group validation (switched from alerts to styled modals)
- Session timeout client-side protection (activity tracking, keepalive pings)
- Date dropdown arrow alignment fix (Choices.js CSS override)

### December 5, 2025

**Bug Investigation Complete**
- Systematic review of 41 potential issues from checklist
- 38 items confirmed resolved (fixed, handled, or by design)
- 3 minor theoretical edge cases that fail gracefully
- Created Bug_Investigation_Log.md for reference

**Double-Login Fix**
- Fixed Safari/Firefox requiring two logins
- Root cause: session cookie race condition on redirect

**Ledger Autocomplete Refactor**
- Unified architecture for all three autocomplete fields
- Added income_payors table to schema

### December 2, 2025

**AI Scribe Feature**
- Local LLM integration using llama-cpp-python
- Hermes 3 Llama 3.1 8B model (Q4_K_M quantization)
- Four text processing actions with SSE streaming

---

## ARCHITECTURE SUMMARY

### Blueprints (12)
1. **ai** - AI Scribe functionality
2. **auth** - Login/logout, session management
3. **backups** - Backup/restore system
4. **clients** - Client management, file viewing, session reports
5. **entries** - Entry CRUD (6 types)
6. **ledger** - Income/Expense, financial reports
7. **links** - Link group management
8. **statements** - Statement generation, PDF, email, payments
9. **scheduler** - Calendar integration
10. **types** - Client type management
11. **settings** - Practice configuration
12. **app.py routes** - Auto-backup, restore messages, filters

### Key Files
| File | Lines | Purpose |
|------|-------|---------|
| core/database.py | ~1,930 | Database operations |
| utils/backup.py | ~1,060 | Backup/restore system |
| web/blueprints/entries.py | ~1,780 | Entry CRUD |
| ai/assistant.py | ~335 | LLM model management |
| web/blueprints/ai.py | ~330 | AI Scribe routes |
| web/app.py | ~290 | Flask initialization |
| web/utils.py | ~270 | Shared utilities |
| web/static/css/shared.css | ~2,360 | Common CSS patterns |

---

## SUCCESS CRITERIA - ALL MET ✅

### Functional Requirements
- ✅ Manage clients via web interface
- ✅ Create and customize client types
- ✅ Create all entry types (6 client + 2 ledger)
- ✅ Link clients for couples/family therapy
- ✅ Generate invoices and track payments
- ✅ Track income and expenses
- ✅ Generate financial reports
- ✅ Export entries as PDF
- ✅ Calendar integration
- ✅ Encrypted database (SQLCipher)
- ✅ Encrypted attachments (Fernet)
- ✅ Backup/restore system
- ✅ Session timeout for security
- ✅ File retention compliance
- ✅ AI-assisted note writing

### Quality Requirements
- ✅ Clean, modular codebase (12 blueprints)
- ✅ External CSS/JS (no inline code)
- ✅ JSDoc documentation for IDE support
- ✅ Consistent naming conventions
- ✅ Professional UI with responsive design
- ✅ Automated tests for critical business logic (41 tests)

---

## KNOWN ISSUES

None critical. System is in active production use.

### Features Not Yet Tested with Real Data

The following features were extensively tested with test data during development but have not yet been used in production with real clients:

- **Guardian billing / split payments** - For billing minors' guardians separately
- **Link groups** - Couples, family, and group therapy billing
- **Tax calculations** - HST/GST on session fees (current practice doesn't charge tax)

These features passed all automated tests and manual testing in December 2025. First real-world use should be verified carefully.

---

## PRODUCTION MILESTONES

- **January 3, 2026:** First real client session using EdgeCase
- **AI Scribe:** Working well in production, generating quality session notes
- **Backups:** Running reliably on logout with rsync to Sentinel server

---

## GIT STATUS

**Branch:** main  
**Total Commits:** 503+ (as of Jan 7, 2026)

**Recent Commits:**
```
0e8a27b Run post-backup command on Ctrl+C and atexit shutdown
148ef0d Run backup on session timeout, not just explicit logout
01bafd9 Fix backup missing recent changes: checkpoint WAL before backup, not after
0bca8e8 Rename backup frequency 'startup' to 'session' to match logout-based backup behavior
024c7e6 Remove inline migration - databases updated manually
```

---

## ACCESS

- **Mac:** http://localhost:8080
- **iPad (same WiFi):** http://richards-macbook.local:8080

### Start Server
```bash
cd ~/apps/edgecase
source venv/bin/activate
python main.py
```

---

## DOCUMENTATION

| Document | Purpose |
|----------|---------|
| EdgeCase_Navigation_Map_v5_4.md | Quick reference, directory structure |
| EdgeCase_Project_Status.md | This file - current state |
| Database_Schema.md | Table definitions |
| Route_Reference.md | All routes by blueprint |
| Architecture_Decisions.md | Design rationale |
| CSS_Architecture.md | CSS organization |
| Bug_Investigation_Log.md | Production readiness audit |
| Flask_Double_Login_Fix.md | Technical reference |

---

*EdgeCase Equalizer - Practice Management for Solo Therapists*  
*"Every practice is an edge case"*  
*All Phases Complete: December 2, 2025*  
*In Production: January 3, 2026*
