# EdgeCase Equalizer - Development & Upgrade Workflow

**Purpose:** Managing code updates without losing data  
**Created:** December 11, 2025

---

## CORE PRINCIPLE

**Code and data are completely separate.**

- Code: Python files, templates, CSS, JS (replaceable)
- Data: Database, attachments, assets, backups (precious)

Updating code never touches data. Migrations bridge schema changes automatically.

---

## PART 1: DEVELOPER WORKFLOW (Richard + Claude)

### Two Environments

```
~/edgecase/          # PRODUCTION - Real clients, real data
~/edgecase-dev/      # DEVELOPMENT - Fictional test clients
```

### Initial Setup

**Production** (already exists):
```bash
~/edgecase/
├── data/edgecase.db        # Your real encrypted database
├── attachments/            # Real client documents
├── assets/                 # Your logo, signature
├── backups/                # Your backups
└── [all code files]
```

**Development** (create once):
```bash
cd ~
git clone https://github.com/rsembera/edgecase.git edgecase-dev
cd edgecase-dev
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then run the app, create a password, and populate with fictional test clients from the Testing Guide.

### Daily Development Workflow

**1. Work in dev environment:**
```bash
cd ~/edgecase-dev
source venv/bin/activate
python main.py
# Access at http://localhost:8080
```

**2. Make changes, test thoroughly**

**3. Commit when working:**
```bash
git add .
git commit -m "Feature: description"
git push
```

**4. Deploy to production:**
```bash
cd ~/edgecase
git pull                    # Get new code
# Restart server if running
python main.py
```

That's it. Your production data is untouched, new code is in place.

### Port Conflict

If you need both running simultaneously:

```bash
# In edgecase-dev, edit main.py temporarily:
app.run(host='0.0.0.0', port=8081)  # Use different port
```

Or just stop production while developing.

---

## PART 2: DATABASE MIGRATIONS

### How It Works

The `_run_migrations()` method in `core/database.py` runs every time the app starts:

```python
def _run_migrations(self):
    """Run database migrations to update schema."""
    conn = self.connect()
    cursor = conn.cursor()
    
    # Example: Add a new column if it doesn't exist
    cursor.execute("PRAGMA table_info(entries)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'new_field' not in columns:
        cursor.execute("ALTER TABLE entries ADD COLUMN new_field TEXT")
        print("✓ Migration: Added new_field to entries")
    
    conn.commit()
```

### Migration Rules

1. **Always check before adding** - Use PRAGMA table_info to check if column exists
2. **Always additive** - Add columns, never remove or rename
3. **Always nullable** - New columns must allow NULL (existing rows won't have values)
4. **Always safe** - If migration already ran, it does nothing
5. **Log migrations** - Print confirmation so we know it worked

### Example: Adding a Feature That Needs New Fields

**Step 1:** Add migration code to `_run_migrations()`:
```python
# v1.1: Add appointment reminders
cursor.execute("PRAGMA table_info(entries)")
columns = [col[1] for col in cursor.fetchall()]

if 'reminder_sent' not in columns:
    cursor.execute("ALTER TABLE entries ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE entries ADD COLUMN reminder_date INTEGER")
    print("✓ Migration: Added reminder fields to entries")
```

**Step 2:** Add the feature code that uses these fields

**Step 3:** Test in dev environment

**Step 4:** Commit, push, pull to production

**Step 5:** On next production login, migration runs automatically

---

## PART 3: END-USER UPDATES (Future App Distribution)

### App Architecture

When EdgeCase is bundled as a standalone app:

```
/Applications/EdgeCase.app/     # The application (replaceable)
├── Contents/
│   ├── MacOS/EdgeCase          # Executable
│   ├── Resources/              # Code, templates, assets
│   └── Info.plist              # Version info

~/Library/Application Support/EdgeCase/    # User data (precious)
├── data/edgecase.db
├── attachments/
├── assets/
└── backups/

# Or simpler:
~/EdgeCase/                     # User data folder
├── data/edgecase.db
├── attachments/
├── assets/
└── backups/
```

**Key:** App bundle contains code. User folder contains data. They never mix.

### User Update Experience

**Option A: Manual Download**
1. User sees "Update available" notification (or checks website)
2. Downloads new EdgeCase.app
3. Drags to Applications (replaces old version)
4. Launches app
5. Migrations run automatically
6. Done - all data intact

**Option B: Auto-Update (Sparkle framework for Mac)**
1. App checks for updates on launch (or periodically)
2. Shows "Update available - Install now?"
3. User clicks Install
4. App downloads update, quits, installs, relaunches
5. Migrations run automatically
6. Done

### Version Tracking

Add to `database.py`:

```python
def _run_migrations(self):
    # Get current schema version
    current_version = int(self.get_setting('schema_version', '0'))
    
    if current_version < 1:
        # v1.0 -> v1.1 migrations
        self._migrate_to_v1()
        self.set_setting('schema_version', '1')
    
    if current_version < 2:
        # v1.1 -> v1.2 migrations
        self._migrate_to_v2()
        self.set_setting('schema_version', '2')
    
    # etc.
```

This is cleaner for production - each migration runs exactly once.

### What Users Need to Know

**In the User Manual:**

> **Updates**
> 
> EdgeCase automatically updates your database when you install a new version. 
> Your clients, sessions, and all data are preserved.
> 
> Before any major update, EdgeCase creates an automatic backup. You can also 
> manually back up anytime from the Backups page.
>
> **Your data is stored in:** ~/EdgeCase/
> **This folder is never modified by updates.**

---

## PART 4: BACKUP SAFETY NET

### What's Already Built

Before any restore operation, EdgeCase automatically creates a `pre_restore_*.zip` backup. This is a safety net.

### For Major Updates (Future)

Consider adding a pre-update backup:

```python
def _run_migrations(self):
    current_version = int(self.get_setting('schema_version', '0'))
    target_version = 5  # Current app version
    
    if current_version < target_version:
        # Major version jump - create safety backup
        from utils import backup
        backup.create_pre_update_backup()
        
        # Run migrations...
```

This way, if anything goes wrong, user can restore to pre-update state.

---

## SUMMARY

| Scenario | Code Update Method | Data Handling |
|----------|-------------------|---------------|
| **Richard developing** | `git pull` in production | Untouched |
| **End user (manual)** | Download new .app | Untouched |
| **End user (auto)** | Sparkle/auto-updater | Untouched |
| **Schema changes** | Migrations in `_run_migrations()` | Automatic |

**The golden rule:** Data lives in the user's folder. App updates replace app code only. Migrations handle schema changes. Backups provide safety net.

---

## CHECKLIST FOR NEW FEATURES

- [ ] Does it need new database fields?
  - [ ] Add migration code (check before add)
  - [ ] Test migration on fresh database
  - [ ] Test migration on existing database
- [ ] Test in dev environment with fictional clients
- [ ] Commit with clear message
- [ ] Pull to production
- [ ] Verify migration ran (check logs)
- [ ] Test feature with real data

---

*EdgeCase Equalizer - Development Workflow*  
*"Code updates, data persists"*
