# EdgeCase Documentation - README

**Created:** November 23, 2025  
**Updated:** December 16, 2025  
**Purpose:** Guide to the modular documentation structure

---

## DOCUMENTATION FILES

EdgeCase Equalizer has **8 modular documentation files**:

### 1. EdgeCase_Navigation_Map_v5_3.md (~363 lines)
**Purpose:** Main overview and quick reference  
**Use when:** Starting a session, need project overview, want quick commands

**Contents:**
- Project overview and current status (All Phases Complete)
- Directory structure (all 11 blueprints)
- Tech stack summary
- Blueprint architecture overview
- Database tables list
- Quick reference commands
- System capabilities checklist

**Start here** every session to get oriented.

---

### 2. EdgeCase_Project_Status.md (~215 lines)
**Purpose:** Current project state and accomplishments  
**Use when:** Planning sessions, tracking progress, understanding what's done

**Contents:**
- Phase 1 & 2 completion status
- Development statistics
- Recent accomplishments
- Architecture summary
- Success criteria tracking
- Git status

**Read this** when:
- Starting a new session
- Planning what to work on
- Checking what's been tested
- Reviewing project progress

---

### 3. Database_Schema.md (~450 lines)
**Purpose:** Complete database table definitions and design decisions  
**Use when:** Working with database, adding fields, understanding data structure

**Contents:**
- All 12 table definitions with CREATE TABLE statements
- Field descriptions and purposes
- Entry-based architecture explanation
- statement_portions table
- Migration history
- Design pattern rationale
- Color palette reference
- Storage locations

---

### 4. Route_Reference.md (~790 lines)
**Purpose:** Complete route listings organized by blueprint  
**Use when:** Creating routes, debugging routing, understanding request/response flow

**Contents:**
- All 60+ routes across 11 blueprints
- Route signatures (parameters, query params, form data)
- Return values and redirects
- Special behaviors and validation
- Shared utility function documentation

**Organized by blueprint:**
- auth_bp: Login, logout, password change (NEW)
- backups_bp: Backup/restore operations (NEW)
- clients_bp: Main view, client file, export
- entries_bp: Entry CRUD operations
- ledger_bp: Income/Expense operations
- links_bp: Link group management (EXTRACTED)
- statements_bp: Statement generation, PDF, email
- scheduler_bp: Calendar integration
- types_bp: Type management
- settings_bp: Settings and uploads

---

### 5. Architecture_Decisions.md (~550 lines)
**Purpose:** Explain *why* we built things certain ways  
**Use when:** Understanding design philosophy, making architectural decisions

**Contents:**
- Entry-based architecture rationale
- Blueprint organization reasoning
- Shared utilities philosophy
- Comprehensive billing system design
- Edit history implementation
- Self-referential link pattern explanation
- File number generation modes
- Calendar integration philosophy
- Statement system architecture
- Migration strategy
- Testing approach

---

### 6. CSS_Architecture.md (~160 lines)
**Purpose:** CSS organization and patterns  
**Use when:** Adding styles, understanding CSS structure

**Contents:**
- shared.css sections breakdown
- Page-specific CSS file sizes
- Naming conventions
- Common patterns
- Where to put new styles

---

### 7. AI_Integration_Plan.md (~350 lines)
**Purpose:** Future AI feature roadmap  
**Use when:** Planning AI integration work

**Contents:**
- Local LLM integration plan
- Tested prompts
- Architecture design
- Implementation phases

### 7. Bug_Investigation_Log.md (~349 lines)
**Purpose:** Complete bug investigation audit  
**Use when:** Understanding production readiness verification

**Contents:**
- Systematic review of 41 potential issues
- Resolution status for each item
- Evidence of fixes
- Theoretical edge cases documentation

---

### 8. Flask_Double_Login_Fix.md (~179 lines)
**Purpose:** Technical reference for Flask session cookie issue  
**Use when:** Debugging similar session/cookie problems

**Contents:**
- Safari/Firefox double-login bug analysis
- Root cause explanation
- Complete fix implementation
- Pattern for future Flask projects

---

## HOW TO USE THIS DOCUMENTATION

### Starting a New Session

1. **Read:** EdgeCase_Navigation_Map_v5_3.md
   - Get current project state
   - See directory structure
   - Check system capabilities

2. **Check:** EdgeCase_Project_Status.md
   - See what's remaining
   - Review recent work
   - Plan session focus

3. **Quick Reference:** Use command reference at bottom of Navigation Map
   - Start server
   - Access URLs
   - Common git commands

### Adding a New Feature

1. **Plan:** Read Architecture_Decisions.md
   - Understand existing patterns
   - See how similar features were built
   - Learn from past decisions

2. **Check Database:** Read Database_Schema.md
   - See what tables exist
   - Check if fields needed exist
   - Plan any necessary migrations

3. **Add Routes:** Reference Route_Reference.md
   - See existing route patterns
   - Check which blueprint to use
   - Follow naming conventions

4. **Add Styles:** Reference CSS_Architecture.md
   - Check shared.css for existing patterns
   - Follow naming conventions

### Debugging Issues

1. **Start:** Quick checklist
   - Server running?
   - Hard refresh?
   - Check console?

2. **Check other docs:**
   - Route_Reference.md for route details
   - Database_Schema.md for data structure
   - Architecture_Decisions.md for design context

---

## FILE LOCATIONS

**Project docs folder:** `~/edgecase/docs/`

**Files:**
- EdgeCase_Navigation_Map_v5_3.md (main reference)
- EdgeCase_Project_Status.md (current state)
- Architecture_Decisions.md (design philosophy)
- Database_Schema.md (data reference)
- Route_Reference.md (route lookup)
- CSS_Architecture.md (styling guide)
- Bug_Investigation_Log.md (production readiness audit)
- Flask_Double_Login_Fix.md (technical reference)

---

## QUICK ACCESS

**Main entry point:** EdgeCase_Navigation_Map_v5_3.md  
**Current status:** EdgeCase_Project_Status.md  
**Design philosophy:** Architecture_Decisions.md  
**Data reference:** Database_Schema.md  
**Route lookup:** Route_Reference.md  
**Styling guide:** CSS_Architecture.md

**Start every session with the Navigation Map, branch out as needed.**

---

## VERSION HISTORY

- Nov 23, 2025: Initial modular documentation (5 files)
- Nov 28, 2025: Updated for Statement System completion (Navigation Map v2.1)
- Dec 1, 2025: Phase 2 complete - Navigation Map v4.0, updated all docs
- **Dec 16, 2025: All phases complete - Navigation Map v5.3, testing complete**

---

*EdgeCase Equalizer - Modular Documentation System*  
*Last Updated: December 16, 2025*
