# EdgeCase Documentation - README

**Created:** November 23, 2025  
**Updated:** November 28, 2025  
**Purpose:** Guide to the modular documentation structure

---

## DOCUMENTATION FILES

EdgeCase Equalizer has **6 modular documentation files**:

### 1. EdgeCase_Navigation_Map_v2_1.md (~350 lines)
**Purpose:** Main overview and quick reference  
**Use when:** Starting a session, need project overview, want quick commands

**Contents:**
- Project overview and current status (Statement System complete)
- Directory structure (including pdf/ folder)
- Tech stack summary (including ReportLab)
- Blueprint architecture overview (7 blueprints)
- Statement system workflow
- Quick reference commands
- System capabilities checklist

**Start here** every session to get oriented.

---

### 2. Database_Schema.md (~450 lines)
**Purpose:** Complete database table definitions and design decisions  
**Use when:** Working with database, adding fields, understanding data structure

**Contents:**
- All 12 table definitions with CREATE TABLE statements
- Field descriptions and purposes
- Entry-based architecture explanation
- **statement_portions table** (NEW)
- Migration history
- Design pattern rationale
- Color palette reference
- Storage locations

**Read this** when:
- Adding new fields to tables
- Understanding data relationships
- Debugging database queries
- Planning new features that need data storage

---

### 3. Route_Reference.md (~400 lines)
**Purpose:** Complete route listings organized by blueprint  
**Use when:** Creating routes, debugging routing, understanding request/response flow

**Contents:**
- All 40+ routes across 7 blueprints
- Route signatures (parameters, query params, form data)
- Return values and redirects
- Special behaviors and validation
- Shared utility function documentation

**Organized by blueprint:**
- clients_bp: Main view, client file, links
- entries_bp: Entry CRUD operations
- ledger_bp: Income/Expense operations
- **statements_bp: Statement generation, PDF, email** (NEW)
- scheduler_bp: Calendar integration
- types_bp: Type management
- settings_bp: Settings and uploads

**Read this** when:
- Adding new routes
- Debugging 404 errors
- Understanding form submissions
- Looking up route parameters

---

### 4. Architecture_Decisions.md (~550 lines)
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
- External CSS/JS rationale
- Year/month timeline grouping
- **Calendar integration philosophy** (calendar as source of truth)
- **Statement system architecture** (NEW)
- Migration strategy
- Testing approach

**Read this** when:
- Planning new features (understand patterns)
- Questioning existing decisions (see rationale)
- Teaching others about the system
- Making similar architectural choices

---

### 5. Debugging_Guide.md (~600 lines)
**Purpose:** Common issues, solutions, and troubleshooting workflows  
**Use when:** Something's broken, debugging, encountering errors

**Contents:**
- Quick debugging checklist
- Common issues with solutions
- Step-by-step debugging workflows
- Common error messages explained
- Git debugging commands
- Browser DevTools tips
- Performance debugging
- When to ask for help

**Read this** when:
- Getting error messages
- Feature not working as expected
- Testing reveals bugs
- Performance issues

---

### 6. EdgeCase_Project_Status_2025-11-28.md (~400 lines)
**Purpose:** Current project state and remaining work  
**Use when:** Planning sessions, tracking progress, understanding what's done

**Contents:**
- Phase 1 completion status (95%)
- Completed features list
- Remaining tasks with time estimates
- Testing status
- Known issues
- Git status
- Success criteria tracking

**Read this** when:
- Starting a new session
- Planning what to work on
- Checking what's been tested
- Reviewing project progress

---

## HOW TO USE THIS DOCUMENTATION

### Starting a New Session

1. **Read:** EdgeCase_Navigation_Map_v2_1.md
   - Get current project state
   - See directory structure
   - Check system capabilities

2. **Check:** EdgeCase_Project_Status_2025-11-28.md
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

4. **Test:** Use Debugging_Guide.md if issues arise

### Debugging Issues

1. **Start:** Quick checklist in Debugging_Guide.md
   - Server running?
   - Hard refresh?
   - Check console?

2. **Find Issue:** Look up specific problem
   - Common issues section
   - Debugging workflows
   - Error message reference

3. **If Stuck:** Check other docs
   - Route_Reference.md for route details
   - Database_Schema.md for data structure
   - Architecture_Decisions.md for design context

---

## BENEFITS OF MODULAR DOCUMENTATION

✅ **Focused reading** - Read only what you need  
✅ **Easier updates** - Update one section without affecting others  
✅ **Better organization** - Find information faster  
✅ **Scales better** - Can add more specialized docs as needed  
✅ **Less overwhelming** - ~300-600 lines per file vs 1000+ in one file

---

## UPDATING DOCUMENTATION

### When to Update

**EdgeCase_Navigation_Map:**
- Phase completion
- Major feature additions
- Directory structure changes
- Blueprint additions

**Database_Schema.md:**
- New tables
- New fields
- Schema migrations

**Route_Reference.md:**
- New routes
- Route signature changes
- New blueprints

**Architecture_Decisions.md:**
- Major architectural decisions
- Design pattern explanations

**Debugging_Guide.md:**
- New common issues discovered
- Solutions to recurring problems

**Project_Status:**
- After each session
- When features complete
- When issues found/fixed

### How to Update

1. **Identify which file** needs updating
2. **Update only that section** - don't need to touch others
3. **Keep other files in sync** if changes affect multiple areas
4. **Update "Last Updated" date** at top of file

---

## FILE LOCATIONS

**Project docs folder:** `~/edgecase/docs/`

**Add to Project Knowledge in Claude Projects:**
- EdgeCase_Navigation_Map_v2_1.md (main reference)
- EdgeCase_Project_Status_2025-11-28.md (current state)
- Architecture_Decisions.md (design philosophy)
- Database_Schema.md (data reference)

**Keep local for quick reference:**
- Route_Reference.md (look up as needed)
- Debugging_Guide.md (reference when stuck)

---

## QUICK ACCESS

**Main entry point:** EdgeCase_Navigation_Map_v2_1.md  
**Current status:** EdgeCase_Project_Status_2025-11-28.md  
**Design philosophy:** Architecture_Decisions.md  
**Data reference:** Database_Schema.md  
**Route lookup:** Route_Reference.md  
**Troubleshooting:** Debugging_Guide.md

**Start every session with the Navigation Map, branch out as needed.**

---

## VERSION HISTORY

- Nov 23, 2025: Initial modular documentation (5 files)
- Nov 28, 2025: Updated for Statement System completion (Navigation Map v2.1, new Project Status)

---

*EdgeCase Equalizer - Modular Documentation System*  
*Last Updated: November 28, 2025*
