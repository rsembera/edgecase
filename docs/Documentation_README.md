# EdgeCase Documentation - README

**Created:** November 23, 2025  
**Purpose:** Guide to the new modular documentation structure

---

## DOCUMENTATION FILES

EdgeCase Equalizer now has **5 modular documentation files** instead of one monolithic navigation map:

### 1. EdgeCase_Navigation_Map_v1_9.md (~300 lines)
**Purpose:** Main overview and quick reference  
**Use when:** Starting a session, need project overview, want quick commands

**Contents:**
- Project overview and current status (Phase 10 complete)
- Directory structure
- Tech stack summary
- Blueprint architecture overview
- Phase 10 optimization summary
- Quick reference commands
- System capabilities checklist
- Links to other documentation

**Start here** every session to get oriented.

---

### 2. Database_Schema.md (~400 lines)
**Purpose:** Complete database table definitions and design decisions  
**Use when:** Working with database, adding fields, understanding data structure

**Contents:**
- All 11 table definitions with CREATE TABLE statements
- Field descriptions and purposes
- Entry-based architecture explanation
- Migration history
- Design pattern rationale (why unified entries table, etc.)
- Color palette reference
- Storage locations

**Read this** when:
- Adding new fields to tables
- Understanding data relationships
- Debugging database queries
- Planning new features that need data storage

---

### 3. Route_Reference.md (~350 lines)
**Purpose:** Complete route listings organized by blueprint  
**Use when:** Creating routes, debugging routing, understanding request/response flow

**Contents:**
- All 30+ routes across 5 blueprints
- Route signatures (parameters, query params, form data)
- Return values and redirects
- Special behaviors and validation
- Shared utility function documentation

**Organized by blueprint:**
- clients_bp: Main view, client file, links
- entries_bp: Entry CRUD operations
- ledger_bp: Income/Expense operations
- types_bp: Type management
- settings_bp: Settings and uploads

**Read this** when:
- Adding new routes
- Debugging 404 errors
- Understanding form submissions
- Looking up route parameters

---

### 4. Architecture_Decisions.md (~500 lines)
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
- Common issues with solutions:
  - Server won't start
  - 404 errors
  - Database locked
  - Entries not appearing
  - Fee calculations wrong
  - Edit history not saving
  - File uploads failing
  - Entry sorting wrong
  - Modals not appearing
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
- Need to debug step-by-step

---

## HOW TO USE THIS DOCUMENTATION

### Starting a New Session

1. **Read:** EdgeCase_Navigation_Map_v1_9.md
   - Get current project state
   - See what's complete, what's remaining
   - Check system capabilities

2. **Quick Reference:** Use command reference at bottom
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

### Understanding the System

1. **Overview:** EdgeCase_Navigation_Map_v1_9.md
2. **Deep Dive:** Architecture_Decisions.md
3. **Details:** Database_Schema.md + Route_Reference.md
4. **Troubleshooting:** Debugging_Guide.md

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

**EdgeCase_Navigation_Map_v1_9.md:**
- Phase completion
- Major feature additions
- Directory structure changes
- Blueprint additions

**Database_Schema.md:**
- New tables
- New fields
- Schema migrations
- Design pattern changes

**Route_Reference.md:**
- New routes
- Route signature changes
- New blueprints
- Shared utility updates

**Architecture_Decisions.md:**
- Major architectural decisions
- Design pattern explanations
- "Why we did it this way" insights

**Debugging_Guide.md:**
- New common issues discovered
- Solutions to recurring problems
- New debugging workflows
- Tool tips and tricks

### How to Update

1. **Identify which file** needs updating
2. **Update only that section** - don't need to touch others
3. **Keep other files in sync** if changes affect multiple areas
4. **Update "Last Updated" date** at top of file

---

## FILE LOCATIONS

**Current location:** `/home/claude/` (Claude's workspace)

**To deploy to project:**
```bash
# Copy all documentation files to project docs folder
cp EdgeCase_Navigation_Map_v1_9.md ~/edgecase/docs/
cp Database_Schema.md ~/edgecase/docs/
cp Route_Reference.md ~/edgecase/docs/
cp Architecture_Decisions.md ~/edgecase/docs/
cp Debugging_Guide.md ~/edgecase/docs/
```

**Add to Project Knowledge in Claude Projects:**
- EdgeCase_Navigation_Map_v1_9.md (main reference)
- Architecture_Decisions.md (design philosophy)
- Database_Schema.md (data reference)

**Keep local for quick reference:**
- Route_Reference.md (look up as needed)
- Debugging_Guide.md (reference when stuck)

---

## MIGRATION FROM OLD NAVIGATION MAP

**Old system:** EdgeCase_Equalizer_Navigation_Map_v1_8.md (1000+ lines)

**What happened:**
- Split into 5 focused files
- Navigation map reduced to ~300 lines
- Each topic now has dedicated file
- Better organization by purpose

**What to do with old file:**
- Keep as backup for now
- Can archive once comfortable with new structure
- All information preserved, just reorganized

---

## NEXT STEPS

1. ✅ All 5 documentation files created
2. Copy files to ~/edgecase/docs/
3. Update Project Knowledge with new files
4. Archive old navigation map v1.8
5. Test documentation in next session

---

## QUICK ACCESS

**Main entry point:** EdgeCase_Navigation_Map_v1_9.md  
**Design philosophy:** Architecture_Decisions.md  
**Data reference:** Database_Schema.md  
**Route lookup:** Route_Reference.md  
**Troubleshooting:** Debugging_Guide.md

**Start every session with the Navigation Map, branch out as needed.**

---

*EdgeCase Equalizer - Modular Documentation System*  
*Created: November 23, 2025*
