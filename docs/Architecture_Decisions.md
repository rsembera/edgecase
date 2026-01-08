# EdgeCase Equalizer - Architecture Decisions

**Purpose:** Document key design decisions and the reasoning behind them  
**Last Updated:** December 28, 2025

---

## PROJECT PHILOSOPHY

**EdgeCase Equalizer: Every practice is an edge case.**

This philosophy drives every architectural decision. We're not building for the average practice or the common use case. We're building for therapists who need complete control, flexibility, and ownership of their data.

**Core Principles:**
1. **Therapist autonomy** - Full control over data and workflows
2. **Privacy first** - Local data, no cloud dependencies
3. **Flexibility over constraints** - Adapt to unique practices, not vice versa
4. **Simplicity where possible** - Complex where necessary
5. **Professional standards** - PHIPA compliance, audit trails, immutable records

---

## ENTRY-BASED ARCHITECTURE

### The Decision

All client records (profiles, sessions, communications, etc.) are stored as entries in a **unified entries table** with class-specific fields.

### Why?

**Alternative considered:** Separate tables for each type
- More "normalized" database design
- 6+ tables: profiles, sessions, communications, absences, items, uploads
- Each with similar fields: created_at, modified_at, client_id, description, content

**Problems with separate tables:**
- **Code duplication** - 6 sets of CRUD operations
- **Complex queries** - JOINs needed to get client timeline
- **Harder to extend** - Adding new entry type = new table + new routes + new templates
- **Fragmented audit trail** - Edit history scattered across tables

**Benefits of unified table:**
- ✅ **Single interface** - One set of CRUD operations
- ✅ **Unified timeline** - Easy query: `SELECT * FROM entries WHERE client_id = X`
- ✅ **Easy to extend** - New entry type = add columns (nullable), new template
- ✅ **Centralized audit** - All edit history in one place
- ✅ **Simpler codebase** - Less code, fewer bugs

**Trade-offs:**
- ❌ Many NULL fields (acceptable - storage is cheap)
- ❌ Less "pure" normalization (acceptable - simplicity wins)

### Result

~2,000 lines of code saved vs. separate-table approach. Easy to add new entry types (took 3 hours to add Upload entry type in Phase 1, Week 3, Day 5).

---

## BLUEPRINT ARCHITECTURE

### The Decision

Organize routes into 12 modular blueprints instead of one monolithic app.py.

### Why?

**Original state:** app.py was 3,700+ lines
- Hard to navigate
- Merge conflicts likely if team grows
- Related functionality scattered
- Testing difficult

**Blueprint organization:**
- `ai.py` - AI Scribe functionality (~330 lines)
- `auth.py` - Login/logout, session management (~340 lines)
- `backups.py` - Backup/restore operations (~210 lines)
- `clients.py` - Client management (~1,065 lines)
- `entries.py` - Entry CRUD (~1,780 lines)
- `ledger.py` - Income/Expense (~660 lines)
- `links.py` - Link group management (~200 lines)
- `scheduler.py` - Calendar integration (~440 lines)
- `statements.py` - Statement generation (~1,090 lines)
- `types.py` - Client types (~205 lines)
- `settings.py` - Configuration (~550 lines)
- `app.py` - Flask initialization (~290 lines)

**Benefits:**
- ✅ **Maintainability** - Find code faster
- ✅ **Separation of concerns** - Each blueprint has clear responsibility
- ✅ **Testability** - Can test blueprints independently
- ✅ **Scalability** - Easy to add new blueprints
- ✅ **Mental model** - Matches how we think about the app

**Implementation (Phase 7-9):**
- Week 4, Day 1: Extracted all blueprints
- Result: Modular codebase with clean separation
- No functionality lost, all tests passed

---

## SHARED UTILITIES

### The Decision (Phase 10)

Extract duplicate code into shared utility functions in `web/utils.py`.

### Why?

**Problem discovered:** After blueprint extraction, noticed identical code blocks:
- Date parsing from dropdowns (14 places, 8-9 lines each)
- Today date components for forms (7 places, 6 lines + 4 params each)
- File upload handling (6 places, ~25 lines each)

**Traditional approach:** "Don't repeat yourself" - create functions early

**Our approach:** 
1. Build features quickly (get to working system)
2. Notice patterns emerge naturally
3. Extract when duplication becomes burden
4. Result: Functions that actually match real usage patterns

**Benefits:**
- ✅ **~400 lines saved** - Real code reduction
- ✅ **Consistency** - Same behavior everywhere
- ✅ **Easier to fix bugs** - One place to update
- ✅ **Future-proof** - New entry types automatically benefit

**Functions created:**
- `parse_date_from_form()` - Replaced 14 occurrences
- `get_today_date_parts()` - Replaced 7 occurrences
- `save_uploaded_files()` - Replaced 6 occurrences

**Why this worked:** Waited until we had real usage patterns, not premature abstraction.

---

## FEE ARCHITECTURE

### The Problem

Different billing scenarios need different fee structures:
- Individual clients: Custom fee per client
- Minors: Parents pay, sometimes split between guardians
- Couples: Each partner may pay different portion
- Family/Group: Each member may pay different portion
- Consultations: Practice-wide fee for initial sessions

### The Solution

**Three fee sources:**

1. **Profile** - Individual session fees stored in Profile entry (`session_base`, `session_tax_rate`, `session_total`). Used when session format is "Individual".

2. **Link Groups** - Per-member fees for couples/family/group sessions. Each member has their own `member_base_fee`, `member_tax_rate`, `member_total_fee`. Used when session format involves multiple clients.

3. **Settings** - Consultation fee (`consultation_base_price`, `consultation_tax_rate`, `consultation_fee`). Applied practice-wide when a session is marked as consultation.

**Client types have NO fee fields** - they're purely for organization and workflow (Active/Inactive status, retention periods, color coding).

### Guardian Billing

Guardian billing is separate from fee definition—it determines **who pays**, not **how much**.

For minors, the Profile stores:
- Guardian 1 contact info and payment percentage
- Guardian 2 contact info and payment percentage (optional)

When generating statements, portions are created for each guardian based on their percentage of whatever fee was charged.

### Three-Way Fee Calculation

**Pattern:** Base Price + Tax Rate = Total Fee

**Used in:**
- Profile session fees
- Link Group member fees
- Item entries
- Absence fees
- Consultation settings

**Why store all three?**
- **Historical accuracy** - Tax rates change over time
- **Audit trail** - Show exact breakdown years later
- **Flexibility** - User can edit any 2 fields, system calculates 3rd
- **Professional** - Matches real accounting

### Why This Works

✅ **Simplicity** - No complex hierarchy or "override" logic  
✅ **Flexibility** - Handles every billing scenario  
✅ **Clarity** - Each fee source has a clear purpose  
✅ **Professional** - Meets accounting standards

---

## EDIT HISTORY SYSTEM

### The Decision

Track all changes to entries with smart word-level diff and immutable records.

### Why?

**PHIPA compliance requires:**
- Audit trail of all changes
- Who changed what and when
- Cannot delete records (only soft delete after retention period)

**Smart diff approach:**
- **Text fields** (description, content, address) - Word-level diff with `<del>` and `<strong>` tags
- **Structured data** (dates, fees, dropdowns) - Simple arrow format: "old → new"
- **Client-level changes** (name, file number) - Tracked in Profile history

**Example text field:**
```
Content: Discussed <del>anxiety</del> <strong>depression</strong> symptoms
```

**Example structured data:**
```
Fee: $100.00 → $120.00
Date: 2025-11-15 → 2025-11-16
```

### Locking Behavior

**Lock immediately:**
- Session, Communication, Absence, Item
- Reason: Billable records, financial implications
- Result: Immutable after creation, only edit history appends

**Lock on first edit:**
- Profile
- Reason: Living document, frequently updated
- Result: Editable until first change, then immutable with history

**Never lock:**
- Upload, Income, Expense
- Reason: Administrative records, need flexibility
- Result: Always editable, but history still tracked

### Why This Works

✅ **Compliance** - Meets professional standards  
✅ **Flexibility** - Different rules for different entry types  
✅ **Useful** - Readable history, not just timestamps  
✅ **Trustworthy** - Can prove what changed and when

**Alternative considered:** Full versioning (keep copies of entire entry)
- More storage
- Harder to show meaningful changes
- Overkill for our needs
- Decision: Smart diff is sufficient

---

## SELF-REFERENTIAL LINK PATTERN

### The Problem

Couples, families, and groups need to be linked for joint sessions.

### Alternative Patterns Considered

**1. Star Pattern:**
```
Hub Client (A) ← B
              ← C
```
- One "hub" client, others link to hub
- Problems: Complex queries, special hub logic, what if hub becomes inactive?

**2. Full Mesh:**
```
A ↔ B
A ↔ C
B ↔ C
```
- Every pair explicitly linked
- Problems: N*(N-1)/2 records, redundant, complex maintenance

**3. Self-Referential (chosen):**
```
A → A (in group 1)
B → B (in group 1)
C → C (in group 1)
```
- Each client links to themselves with same group_id
- All members have `group_id = 1`

### Why Self-Referential?

✅ **Semantic accuracy** - Group therapy = individuals attending together  
✅ **Simple queries** - `SELECT * FROM client_links WHERE group_id = X`  
✅ **Per-member fees** - Each row stores that member's fee allocation  
✅ **No special logic** - No "hub" concept, all members equal  
✅ **Easy maintenance** - Add member = INSERT row, Remove = DELETE row

**Example:**
```sql
client_id_1 | client_id_2 | group_id | member_base_fee | member_total_fee
------------|-------------|----------|-----------------|------------------
     A      |      A      |    1     |     60.00       |      67.80
     B      |      B      |    1     |     75.00       |      84.75
     C      |      C      |    1     |     50.00       |      56.50
```

Query all members: `SELECT * FROM client_links WHERE group_id = 1`

### Result

Clean, understandable, extensible. No regrets.

---

## FILE NUMBER GENERATION

### The Problem

Different practices have different file number conventions:
- Some use dates
- Some use sequential numbers
- Some have prefixes/suffixes
- Some need manual control

### The Solution

**Three modes:**

1. **Manual** - User enters file number
2. **Date-Initials** - YYYYMMDD-ABC (auto-generated from name)
3. **Prefix-Counter** - PREFIX-0001-SUFFIX (auto-incremented)

**Stored in settings:**
- `file_number_format`: Which mode
- `file_number_prefix`: Optional prefix text
- `file_number_suffix`: Optional suffix text
- `file_number_counter`: Next number to use

### Why Multiple Modes?

**Real-world requirement:** Different practices need different systems
- Some migrating from paper: need manual entry
- Some want date-based: easy to sort chronologically
- Some want sequential: traditional numbering

**Alternative considered:** Force one format
- Simpler to implement
- But violates "every practice is an edge case" philosophy
- Decision: Support flexibility, even if more complex

### Implementation Details

**Date-Initials:**
```python
date_str = datetime.now().strftime('%Y%m%d')  # 20251123
first = first_name[0].upper()  # R
middle = middle_name[0].upper() if middle_name else ''  # L
last = last_name[0].upper()  # S
file_number = f"{date_str}-{first}{middle}{last}"  # 20251123-RLS
```

**Prefix-Counter:**
```python
counter = int(db.get_setting('file_number_counter', '1'))
parts = []
if prefix: parts.append(prefix)
parts.append(str(counter).zfill(4))  # 0001, 0002, etc.
if suffix: parts.append(suffix)
file_number = '-'.join(parts)  # PREFIX-0001-SUFFIX
db.set_setting('file_number_counter', str(counter + 1))
```

**Result:** Works for everyone, doesn't constrain anyone.

---

## ATTACHMENT STORAGE ORGANIZATION

### The Decision

Store files in organized directory hierarchy:
```
~/edgecase/attachments/
  ├── {client_id}/{entry_id}/  # Client entry attachments
  └── ledger/{entry_id}/        # Ledger entry attachments
```

### Why?

**Benefits:**
- ✅ **Easy to find** - Logical hierarchy matches database structure
- ✅ **No filename conflicts** - Each entry has own folder
- ✅ **Easy cleanup** - Delete entry = delete folder
- ✅ **Easy backup** - Copy entire attachments folder
- ✅ **Atomic operations** - Entry + files stay together

**Alternative considered:** Flat directory with UUID filenames
- Simpler implementation
- But: Harder to debug, harder to backup selectively, harder to understand
- Decision: Structure matches mental model

### Security

- Files named with `secure_filename()` - Prevents directory traversal
- Only accessible through authenticated routes
- Encrypted with Fernet (Phase 2)
- Not in web/static/ - Not directly web-accessible

---

## EXTERNAL CSS/JS FILES

### The Decision (Phase 6)

Extract inline CSS and JavaScript into external files.

### Why?

**Original state:** All styling and JavaScript embedded in HTML templates
- 11 templates with inline `<style>` and `<script>` tags
- Hard to maintain consistency
- No browser caching
- Harder to find and fix bugs

**After extraction:**
- 12 CSS files in `web/static/css/`
- 12 JS files in `web/static/js/`
- Templates just link to files
- **Result: 48.1% file size reduction**

**Benefits:**
- ✅ **Browser caching** - CSS/JS cached, faster page loads
- ✅ **Maintainability** - Find styles quickly
- ✅ **Consistency** - Shared patterns across files
- ✅ **IDE support** - Syntax highlighting, linting work properly

**Trade-off:** One more file to edit when creating new entry type
- But worth it for maintainability

---

## NO FRAMEWORK FRONTEND

### The Decision

Use vanilla JavaScript, no React/Vue/Angular.

### Why?

**Requirements:**
- Forms with dropdowns, text inputs
- Some dynamic fee calculation
- File upload handling
- No complex state management
- No real-time updates (except via page refresh)

**Vanilla JS is sufficient:**
- Event listeners for form interactions
- Fetch API for AJAX
- DOM manipulation for modals
- Total JavaScript across all files: ~2,000 lines

**Benefits:**
- ✅ **No build step** - Edit and reload
- ✅ **No dependencies** - No npm, no webpack, no bundler
- ✅ **Fast** - No framework overhead
- ✅ **Simple** - Easy to understand and debug
- ✅ **Works everywhere** - No compatibility issues

**Alternative considered:** React
- Overkill for our needs
- Adds complexity: JSX, build process, component lifecycle
- Doesn't align with "simple where possible" principle
- Decision: Vanilla JS unless proven insufficient

**When we'd reconsider:** If we need real-time updates, complex state, or heavy interactivity. Current features don't require this.

---

## YEAR/MONTH TIMELINE GROUPING

### The Decision

Organize entries by year and month with expand/collapse functionality.

### Why?

**Problem:** Client files can have hundreds of entries over years
- All in one list = overwhelming, slow to load
- Need to find entries from specific time periods

**Solution:** Group by year → month → entries
```
▼ 2025 (147 entries)
  ▼ November (23 entries)
    - Session 45 (Nov 23)
    - Communication (Nov 22)
    - Session 44 (Nov 15)
  ▶ October (19 entries)
▶ 2024 (89 entries)
```

**Benefits:**
- ✅ **Scalability** - Handles hundreds of entries
- ✅ **Performance** - Render only expanded months
- ✅ **Usability** - Easy to find time period
- ✅ **Context** - Current month expanded by default

**Implementation:**
- Server groups entries: `entries_by_year[year][month]`
- Template renders with expand/collapse state
- JavaScript handles toggle (no page reload)
- Current year/month expanded by default

**Alternative considered:** Pagination
- More traditional (Page 1, 2, 3...)
- But: Doesn't match how therapists think ("What did we discuss in October?")
- Decision: Chronological grouping is more natural

---

## MIGRATION STRATEGY

### The Decision

v1.0 ships with a complete, clean schema. No migrations needed for initial release.

### Development vs. Production

**During development:** We used ALTER TABLE migrations to add columns incrementally as features evolved. This let us iterate without recreating test data.

**For v1.0 release:** 
- New users get fresh database with complete schema from `_initialize_schema()`
- No existing users to migrate from
- All development migrations folded into the clean schema
- `_run_migrations()` method exists but is a pass-through stub

### Future Versions (v1.1+)

When we release updates that change the schema, migrations will be needed:

**Philosophy:** Always additive, never destructive

**How migrations will work:**
1. Check if column/table exists
2. If not, ALTER TABLE ADD COLUMN (or CREATE TABLE)
3. Log migration to console
4. Existing data unchanged, new columns are NULL
5. Future entries populate new fields

**Example pattern for future use:**
```python
def _run_migrations(self):
    """Run database migrations to update schema."""
    conn = self.connect()
    cursor = conn.cursor()
    
    # v1.1: Add new_field to entries
    cursor.execute("PRAGMA table_info(entries)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'new_field' not in columns:
        cursor.execute("ALTER TABLE entries ADD COLUMN new_field TEXT")
        print("✓ Migration: Added new_field to entries")
    
    conn.commit()
```

### Why This Approach?

- ✅ **Clean slate for v1.0** - No legacy cruft
- ✅ **Ready for future** - Infrastructure in place when needed
- ✅ **Safe upgrades** - Additive changes preserve existing data
- ✅ **Simple testing** - Delete test database, restart, get clean schema

---

## TESTING STRATEGY

### The Decision

Hybrid approach: Automated tests for critical business logic, manual testing for UI/UX and integration.

### Why?

**Context:**
- Solo development with rapid iteration
- Some logic is critical and easy to break (fee calculations, billing splits)
- Some things are best tested manually (UI flows, iPad responsiveness)

**Our approach:**

**Automated tests (pytest):** Cover business logic that could cause real problems:
- Fee calculations (billing accuracy)
- Session numbering (record integrity)
- Payment status (visual indicators)
- Guardian billing splits (percentage validation)
- Edit history tracking (audit compliance)
- Date parsing (data integrity)
- Link groups (couples/family therapy)
- Ledger totals (financial accuracy)

**Manual testing:** Cover everything else:
- UI/UX workflows
- Cross-device testing (Mac + iPad)
- PDF generation appearance
- Email/calendar integration
- Edge cases as discovered

### Test Suite Details

**Location:** `tests/test_edgecase.py` (874 lines)

**Coverage:** 41 tests across 11 test classes:
| Test Class | What It Covers |
|------------|----------------|
| TestFeeCalculations | Three-way fee math |
| TestProfileFeeOverride | Client-specific fees |
| TestGuardianBilling | Split percentages |
| TestSessionNumbering | Numbering, offsets, consultations |
| TestPaymentStatus | paid/pending/overdue logic |
| TestEditHistory | Audit trail, locking |
| TestDateParsing | Form validation, leap years |
| TestContentDiff | Word-level diff |
| TestLinkGroups | Couples/family linking |
| TestLedger | Income/expense, totals |
| TestSettings | Settings storage |

**Run tests:**
```bash
cd ~/edgecase
source venv/bin/activate
pytest tests/ -v
```

**Benefits:**
- ✅ **Critical logic protected** - Fee calculations can't silently break
- ✅ **Fast feedback** - 41 tests run in 0.23 seconds
- ✅ **Safe refactoring** - Catch regressions before they ship
- ✅ **No over-testing** - UI flows tested manually where appropriate

**Trade-offs:**
- ❌ No UI test automation (acceptable for solo dev)
- ❌ No continuous integration (run manually before commits)

**Philosophy:** Test what matters most (money and compliance), trust manual testing for the rest.

---

## CALENDAR INTEGRATION

### The Decision

Calendar apps are the source of truth for scheduling. EdgeCase generates events via .ics files or AppleScript, but does not store appointments.

### Why?

**Problem:** Therapists need to schedule appointments with clients.

**Alternative considered:** Build a full scheduler in EdgeCase
- Create appointments table
- Day/week/month calendar views
- Drag-and-drop rescheduling
- Conflict detection
- Reminders system

**Problems with built-in scheduler:**
- **Dual maintenance** - Appointments in EdgeCase AND calendar app = sync issues
- **Reinventing the wheel** - Calendar apps already do this well
- **No calendar sync** - Can't easily share with receptionist or see on phone
- **More code** - Significant development time for solved problem
- **Feature creep** - Endless feature requests (recurring, reminders, etc.)

### The Solution

**EdgeCase as "event generator":**
1. User clicks "Schedule" from client file
2. Fills in date, time, duration, meet link, repeat, alerts
3. EdgeCase generates event and adds to calendar

**Two output methods:**
- **.ics file download** - Works with any calendar app (default)
- **AppleScript direct add** - Mac only, adds directly to Calendar app

### Implementation Details

**Event content:**
- Title: Client file number (not name - privacy)
- Notes: Contact info (preferred method first) + user notes
- URL/Location: Meet link (for video calls)
- RRULE: Repeat pattern (weekly, biweekly, monthly)
- VALARM: Alert triggers (5 min, 15 min, 1 hour, etc.)

**Natural language parsing:**
- "Friday 2pm" → auto-fills date and time fields
- "Nov 28" → sets date
- "tomorrow" → calculates next day
- Custom implementation (no external dependencies)

**AppleScript fallback:**
- If wrong calendar name → shows friendly error
- Auto-downloads .ics file as backup
- User can import manually

### Why This Works

✅ **No sync issues** - Calendar app is single source of truth  
✅ **Leverages existing tools** - Reminders, sharing, mobile sync already work  
✅ **Privacy** - Client names never appear in calendar titles  
✅ **Flexibility** - Works with any calendar app via .ics  
✅ **Mac integration** - Power users get direct Calendar.app add  
✅ **Simple code** - ~200 lines vs thousands for full scheduler

### Why NOT Auto-Notify Clients

**Decision:** No automatic email/notification to clients when scheduling

**Reasons:**
1. **Consent** - Client didn't opt into calendar invites
2. **Privacy** - Some clients don't want therapy in shared/work calendars
3. **Professional boundary** - Therapist should confirm verbally first
4. **Control** - Therapist handles rescheduling their way

**Contact info in notes:** For therapist reference, not automated sending

### Alternative Considered: Full Sync

Could have implemented two-way calendar sync (EdgeCase ↔ Google/Apple Calendar)
- Much more complex
- OAuth, API keys, token refresh
- Sync conflicts
- Privacy concerns (data leaving local machine)
- Decision: Generate-only is simpler and sufficient

---

## KEY TAKEAWAYS

1. **Entry-based architecture** - Simplicity and flexibility over "pure" normalization
2. **Blueprint organization** - Maintainability through modularity
3. **Shared utilities** - Extract when patterns emerge, not prematurely
4. **Comprehensive billing** - Handle complexity where needed (real-world requirements)
5. **Smart edit history** - Professional audit trail with readable diffs
6. **Self-referential links** - Semantic accuracy leads to simpler code
7. **Flexible file numbers** - Support diverse practices, don't constrain
8. **Organized storage** - Structure matches mental model
9. **External assets** - Maintainability and performance
10. **Vanilla JS** - Simple tools for simple needs
11. **Year/month grouping** - Scale with natural thinking patterns
12. **Safe migrations** - Never destructive, always additive
13. **Manual testing** - Sufficient for solo development with fast iteration
14. **Calendar as source of truth** - Generate events, don't store them (NEW)

**Overarching principle:** Build for the specific user (solo therapists) with their specific needs (flexibility, privacy, professional standards), not for hypothetical future users or corporate features.

---

## SAFARI POPUP BLOCKER PATTERN

### The Problem

Safari aggressively blocks `window.open()` calls, even when triggered by user clicks, if:

- Called after async operations (fetch, setTimeout)
- Called via inline `onclick` handlers in some cases
- Called from console (not trusted user action)

### The Solution

**Blank-Window-First Pattern:**

```javascript
document.getElementById('button').addEventListener('click', function() {
    // Open window IMMEDIATELY on user action (before any async)
    const pdfWindow = window.open('about:blank', '_blank');
    
    // Build URL (synchronous - fast enough)
    const params = new URLSearchParams();
    params.append('param1', value1);
    // ... more params
    
    const url = '/route?' + params.toString();
    
    // Navigate the already-open window
    pdfWindow.location.href = url;
});
```

**Why it works:**

- `window.open('about:blank', '_blank')` is synchronous and happens on trusted click
- Safari allows this because it's the direct result of user action
- Subsequent `location.href` navigation is allowed on already-open window

### Where We Use It

1. **Statement PDF viewing** (`outstanding_statements.js`)
   - Open blank → fetch mark-sent → navigate to PDF
2. **Session summary reports** (`session_report.html`)
   - Open blank → build params → navigate to PDF route

### Alternative Approaches (Rejected)

**Form with target="_blank":**

- Works for POST forms in some browsers
- Safari still blocks it

**Direct window.open without blank:**

- Works if truly synchronous
- Fails if any computation takes too long

**Download instead of new tab:**

- Works but worse UX for PDFs
- Users can't preview before saving

### Key Insight

The pattern separates "permission to open" (immediate on click) from "what to show" (can be async). Safari grants popup permission at click time; we use that permission later.

---

## SESSION SUMMARY REPORTS

### The Decision

Create a separate "session report" feature rather than reusing statements.

### Why Not Reuse Statements?

**Statements are:**

- For billing (include Items, Absences)
- Generated from unbilled entries only
- Tracked in statement_portions table
- Have payment workflow

**Session reports are:**

- For attendance records
- Any date range (billed or not)
- No payment tracking
- Can exclude fees entirely

### Use Cases

1. **Insurance verification** - Client needs proof of attendance
2. **Employer documentation** - EAP or workplace requirements
3. **Lost statements** - Client needs summary without re-billing
4. **Fee-free records** - Attendance without financial info

### Implementation

- Route on clients_bp (not statements_bp)
- Reuses StatementPDFGenerator for styling
- Optional fee inclusion checkbox
- Access via client file "Add" dropdown

---

## SETTINGS UPLOAD BUTTON VISIBILITY

### The Problem

After uploading logo/signature, the "Choose" button should hide. CSS `display: flex !important` overrode JavaScript `style.display = 'none'`.

### The Solution

**CSS Class Pattern:**

```css
#logo-choose-button.hidden,
#signature-choose-button.hidden {
    display: none !important;
}
// To hide:
button.classList.add('hidden');

// To show:
button.classList.remove('hidden');
```

### Why CSS Classes Beat Inline Styles

1. **Specificity** - Class with `!important` overrides other rules
2. **Consistency** - Same pattern as delete button visibility
3. **Debuggability** - Can see `.hidden` in DOM inspector
4. **Maintainability** - Logic in CSS, not scattered in JS

---

## PDF LINE WIDTH MATCHING

### The Problem

Statement signature and date lines were fixed width (3.0 inches), didn't match actual content.

### The Solution

Calculate widths from content:

```python
# Signature line width from image
sig_width = sig_img.drawWidth

# Date line width from text (approximate)
date_width = len(today_str) * 5.5

# Use HRFlowable for dynamic lines
HRFlowable(width=sig_width, thickness=0.5, color=colors.black)
```

### Why Dynamic Widths?

- **Professionalism** - Lines that match content look intentional
- **Flexibility** - Different signature sizes work automatically
- **Consistency** - Date line matches date text length

---

## BACKUP TIMING: LOGOUT VS LOGIN

### The Problem

When should automatic backups run - at login (start of session) or logout (end of session)?

### The Decision

**Backup on logout/shutdown**, not login.

### Why?

**Login backup** captures yesterday's state:
- You're backing up work that's already been sitting unprotected overnight
- If your disk died at 3am, that work is gone
- You have to wait until tomorrow's login to back up today's work

**Logout backup** captures today's work immediately:
- Much shorter window of vulnerability
- You finish your day's work, logout, and it's backed up
- Natural "checkpoint" at the end of each session

**Desktop apps have natural endpoints:**
- Unlike servers that run 24/7, desktop apps start and stop
- Logout/shutdown is the obvious moment to capture state
- Matches user mental model of "save my work when I'm done"

### Implementation

Backup runs on:
1. **Explicit logout** (clicking Logout button)
2. **Session timeout** (when `before_request` detects expired session)
3. **Ctrl+C** (via signal handler)
4. **atexit** (when Python process exits)
5. **Desktop heartbeat timeout** (when browser closes in packaged app)

WAL checkpoint runs before every backup to ensure recent changes are flushed to the main database file.

Post-backup command (e.g., rsync to remote server) runs after successful backup on all paths.

---

## BACKUP DELETION PROTECTION

### The Problem

EdgeCase uses incremental backups that depend on previous backups in a chain:
- Full backup → Incremental 1 → Incremental 2 → Incremental 3
- Each incremental only contains changes since the previous backup
- Deleting a backup in the middle breaks the chain for all later backups

### The Solution

**Protection Rule:** You can only delete a backup if nothing depends on it, OR if a newer full backup exists.

**Behavior by backup type:**

| Backup Type | Has Dependents | Newer Full Exists | Can Delete? |
|-------------|----------------|-------------------|-------------|
| Full | No | N/A | ✅ Yes |
| Full | Yes | No | ❌ No (protected) |
| Full | Yes | Yes | ✅ Yes (cascades) |
| Incremental | No (is newest) | N/A | ✅ Yes |
| Incremental | Yes (later incr exist) | N/A | ❌ No (protected) |

**Cascade deletion:** When deleting an old full backup that has a newer full backup available, all its dependent incrementals are automatically deleted too. The user sees a warning in the confirmation modal.

### Why This Design?

**Alternative considered:** Cascade delete always (delete full → delete all its incrementals)
- Problem: User could accidentally delete their only backup chain
- Too dangerous for a backup system

**Alternative considered:** Never allow deletion of backups with dependents
- Problem: Old backup chains accumulate forever
- Users can't clean up after a new full backup is created

**Chosen approach:** Protect the newest chain, allow cleanup of older chains
- ✅ Always have at least one complete restore chain
- ✅ Can clean up old backups when no longer needed
- ✅ UI clearly shows which backups are protected (grayed out button)
- ✅ Backend validates even if UI bypassed

### Implementation Details

**Frontend (backups.js):**
- Calculates `newerFullExists` for each full backup
- Calculates `laterCount` for each incremental
- Disables delete button with tooltip for protected backups
- Shows cascade warning in modal when dependents will be deleted

**Backend (backup.py):**
- `delete_backup()` validates protection rules
- Raises `ValueError` if deletion would break restore chain
- Cascades deletion to dependents when allowed

---

*For database details, see Database_Schema.md*  
*For route details, see Route_Reference.md*  
*Last Updated: January 7, 2026*
