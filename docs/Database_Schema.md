# EdgeCase Equalizer - Database Schema

**Purpose:** Complete database table definitions and design decisions  
**Last Updated:** November 23, 2025

---

## OVERVIEW

EdgeCase uses SQLite with 11 tables organized around an entry-based architecture. All client records (profiles, sessions, communications, etc.) are stored as entries in a unified table with class-specific fields.

**Database Location:** `~/edgecase/data/edgecase.db`

**Tables:**
1. clients - Client records
2. client_types - Customizable client categories
3. entries - Unified entry table (THE CORE)
4. link_groups - Couples/Family/Group therapy
5. client_links - Link group membership
6. attachments - File uploads
7. expense_categories - User-defined expense categories
8. payees - Expense payee names
9. settings - Application settings

---

## TABLE DEFINITIONS

### 1. clients

Client records with basic identification.

```sql
CREATE TABLE clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_number TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    type_id INTEGER NOT NULL,
    session_offset INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    is_deleted INTEGER DEFAULT 0,
    FOREIGN KEY (type_id) REFERENCES client_types(id)
);
```

**Key Fields:**
- `file_number`: Unique identifier (format depends on settings)
- `session_offset`: Starting session number for migrated clients
- `is_deleted`: Soft delete flag (0 = active, 1 = deleted)

---

### 2. client_types

Customizable client categories with billing defaults.

```sql
CREATE TABLE client_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT NOT NULL,
    color_name TEXT NOT NULL,
    bubble_color TEXT NOT NULL,
    file_number_style TEXT,
    file_number_prefix TEXT,
    file_number_suffix TEXT,
    file_number_counter INTEGER,
    session_base_price REAL,
    session_tax_rate REAL,
    session_fee REAL,
    session_duration INTEGER,
    retention_period INTEGER,
    is_system INTEGER DEFAULT 0,
    is_system_locked INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL
);
```

**Key Fields:**
- `name`: Max 9 characters ("Active", "Low Fee", etc.)
- `color`: Hex color (#9FCFC0)
- `bubble_color`: Light background for client cards
- `session_base_price`/`session_tax_rate`/`session_fee`: Three-way fee calculation
- `is_system_locked`: 1 for Inactive/Deleted (can't delete or edit)

**Color Palette (9 curated colors):**
1. Soft Teal (#9FCFC0, bubble: #E6F5F1)
2. Mint Green (#A7D4A4, bubble: #E8F5E7)
3. Sage (#B8C5A8, bubble: #EEF2E9)
4. Lavender (#C8B8D9, bubble: #F1EDF5)
5. Dusty Rose (#D4A5A5, bubble: #F5E9E9)
6. Peach (#E8C4A8, bubble: #F9F0E8)
7. Powder Blue (#A8C8D9, bubble: #E8F0F5)
8. Soft Gray (#B8B8C5, bubble: #EEEEEF)
9. Warm Amber (#D9C8A5, bubble: #F5F0E9)

---

### 3. entries

**THE CORE TABLE** - Unified storage for all entry types.

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    class TEXT NOT NULL,
    ledger_type TEXT,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    
    -- Common fields (all entries)
    description TEXT,
    content TEXT,
    
    -- Profile-specific fields
    email TEXT,
    phone TEXT,
    home_phone TEXT,
    work_phone TEXT,
    text_number TEXT,
    address TEXT,
    date_of_birth TEXT,
    preferred_contact TEXT,
    ok_to_leave_message TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    emergency_contact_relationship TEXT,
    referral_source TEXT,
    additional_info TEXT,
    
    -- Profile Fee Override
    fee_override_base REAL,
    fee_override_tax_rate REAL,
    fee_override_total REAL,
    default_session_duration INTEGER,
    
    -- Profile Guardian/Billing
    is_minor INTEGER DEFAULT 0,
    guardian1_name TEXT,
    guardian1_email TEXT,
    guardian1_phone TEXT,
    guardian1_address TEXT,
    guardian1_pays_percent REAL,
    has_guardian2 INTEGER DEFAULT 0,
    guardian2_name TEXT,
    guardian2_email TEXT,
    guardian2_phone TEXT,
    guardian2_address TEXT,
    guardian2_pays_percent REAL,
    
    -- Session-specific fields
    modality TEXT,
    format TEXT,
    session_number INTEGER,
    service TEXT,
    session_date INTEGER,
    session_time TEXT,
    duration INTEGER,
    base_fee REAL,
    tax_rate REAL,
    fee REAL,
    is_consultation INTEGER DEFAULT 0,
    is_pro_bono INTEGER DEFAULT 0,
    mood TEXT,
    affect TEXT,
    risk_assessment TEXT,
    
    -- Communication-specific fields
    comm_recipient TEXT,
    comm_type TEXT,
    comm_date INTEGER,
    comm_time TEXT,
    
    -- Absence-specific fields
    absence_date INTEGER,
    absence_time TEXT,
    
    -- Item-specific fields
    item_date INTEGER,
    item_time TEXT,
    base_price REAL,
    
    -- Upload-specific fields
    upload_date INTEGER,
    upload_time TEXT,
    
    -- Ledger-specific fields
    ledger_date INTEGER,
    source TEXT,
    payee_id INTEGER,
    category_id INTEGER,
    total_amount REAL,
    tax_amount REAL,
    
    -- Statement-specific fields (not yet implemented)
    statement_total REAL,
    payment_status TEXT,
    payment_notes TEXT,
    date_sent INTEGER,
    date_paid INTEGER,
    is_void INTEGER DEFAULT 0,
    
    -- Edit tracking
    edit_history TEXT,
    locked INTEGER DEFAULT 0,
    locked_at INTEGER,
    
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (payee_id) REFERENCES payees(id),
    FOREIGN KEY (category_id) REFERENCES expense_categories(id)
);
```

**Entry Classes:**

**Client Entry Types (client_id NOT NULL):**
- `profile` - Client demographics and contact info
- `session` - Therapy session notes
- `communication` - Emails, calls, administrative notes
- `absence` - Cancellations and no-shows with fees
- `item` - Billable items (books, letters, reports)
- `upload` - File attachments and documents

**Ledger Entry Types (client_id NULL, ledger_type NOT NULL):**
- `income` - Payment received (ledger_type='income')
- `expense` - Business expenses (ledger_type='expense')

**Design Philosophy:**
- Class-specific fields are NULL for entries that don't use them
- Simpler than 6+ separate tables
- Easy querying across all entry types
- Easy to add new entry types

**Locking Behavior:**
- Session, Communication, Absence, Item: Lock on creation
- Profile: Lock on first edit (designed to be updated frequently)
- Upload, Income, Expense: Never locked (editable administrative records)

---

### 4. link_groups

Groups for couples/family/group therapy.

```sql
CREATE TABLE link_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    format TEXT NOT NULL,
    session_duration INTEGER,
    created_at INTEGER NOT NULL
);
```

**Key Fields:**
- `format`: 'couples', 'family', or 'group'
- `session_duration`: Default duration for sessions with this group

---

### 5. client_links

**Self-referential link pattern** - Each member gets own row with fees.

```sql
CREATE TABLE client_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id_1 INTEGER NOT NULL,
    client_id_2 INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    member_base_fee REAL,
    member_tax_rate REAL,
    member_total_fee REAL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (client_id_1) REFERENCES clients(id),
    FOREIGN KEY (client_id_2) REFERENCES clients(id),
    FOREIGN KEY (group_id) REFERENCES link_groups(id)
);
```

**Self-Referential Pattern:**
Each client gets their own row where `client_id_1 = client_id_2`.

**Example:** For group [A, B, C]:
```
client_id_1 | client_id_2 | group_id | member_base_fee | member_tax_rate | member_total_fee
------------|-------------|----------|-----------------|-----------------|------------------
     A      |      A      |    1     |     60.00       |      13.00      |      67.80
     B      |      B      |    1     |     75.00       |      13.00      |      84.75
     C      |      C      |    1     |     50.00       |      13.00      |      56.50
```

**Benefits:**
- Each member has own fee allocation
- Easy query: `SELECT * FROM client_links WHERE group_id = 1`
- Semantically accurate: group therapy = individuals attending together

---

### 6. attachments

File uploads for entries.

```sql
CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    description TEXT,
    filepath TEXT NOT NULL,
    filesize INTEGER,
    uploaded_at INTEGER NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id)
);
```

**Storage Locations:**
- Client entries: `~/edgecase/attachments/{client_id}/{entry_id}/`
- Ledger entries: `~/edgecase/attachments/ledger/{entry_id}/`

---

### 7. expense_categories

User-defined expense categories for tax reporting.

```sql
CREATE TABLE expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

**Design:** No pre-populated categories - user defines based on their jurisdiction.

---

### 8. payees

Expense payee names (reusable).

```sql
CREATE TABLE payees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 9. settings

Application configuration.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    modified_at INTEGER NOT NULL
);
```

**Key Settings:**
- `file_number_format`: 'manual', 'date-initials', 'prefix-counter'
- `file_number_prefix`, `file_number_suffix`, `file_number_counter`
- `practice_name`, `therapist_name`, `credentials`
- `email`, `phone`, `address`, `website`
- `currency`: 'CAD', 'USD', 'EUR', 'GBP', etc.
- `consultation_base_price`, `consultation_tax_rate`, `consultation_fee`, `consultation_duration`
- `logo_filename`, `signature_filename`

---

## KEY DESIGN DECISIONS

### Entry-Based Architecture

**Why unified entries table?**
- Single interface for all record types
- Unified timeline view per client
- Built-in edit history and audit trail
- Easy to add new entry types
- Simpler codebase (one system vs. many)

**Alternative considered:** Separate tables for each entry type
- More "normalized" but much more complex
- Would need 6+ tables with similar fields
- Harder to query across entry types
- More code duplication

### Self-Referential Link Pattern

**Why not "star pattern" or "full mesh"?**
- Star pattern: One "hub" client, others link to hub → complex queries, special hub logic
- Full mesh: Every pair linked → N*(N-1)/2 records, redundant
- Self-referential: Each member links to themselves → N records, simple queries, semantically accurate

**Benefits:**
- Each member has own row with own fees
- Query all members: `SELECT * FROM client_links WHERE group_id = X`
- No special "hub" logic needed
- Semantically accurate: group therapy = individuals attending together
- Easy to add/remove members (just insert/delete rows)

### Three-Way Fee Calculation

**Pattern used in:**
- Client Types (session fees)
- Profile Fee Override
- Item entries
- Link Group member fees

**How it works:** User can edit any 2 of 3 fields, system calculates the 3rd:
- Change base + tax → calculates total
- Change total + tax → calculates base
- Change total + base → (less common, but supported)

**Why store base/tax/total separately?**
- Tax rates change over time
- Need historical accuracy for invoicing
- Can regenerate invoices years later with correct breakdown
- Matches real-world accounting

### Session Fee Breakdown Storage

**Why store base_fee and tax_rate, not just fee?**
- Tax rates change (e.g., from 13% to 15%)
- Need historical accuracy for audits
- Can regenerate invoices with correct tax breakdown
- Matches pattern everywhere else (consistency)

**When consultation checkbox is checked:**
- Sets `base_fee = 0`, `tax_rate = 0`, `fee = 0`
- Excludes from session numbering
- Still stored for audit trail

### Guardian/Billing for Minors

**Problem:** When therapy is for a child, parents pay

**Solution:** Store guardian info in Profile, split bill by percentage

**Fields:**
- `is_minor`: 1 or 0
- Guardian 1: name, email, phone, address, pays_percent
- `has_guardian2`: 1 or 0
- Guardian 2: name, email, phone, address, pays_percent

**Percentages must add to 100** (validation in Statement generation)

**Data preservation:** Unchecking "Client is minor" sets `is_minor = 0` but keeps guardian data

---

## MIGRATIONS

**Location:** `core/database.py` in `_run_migrations()` method

**How migrations work:**
1. Check if column exists
2. If not, use ALTER TABLE to add column
3. Print migration message to console
4. Never breaks existing data

**Major migrations completed:**
- Week 3: Session fee breakdown (base_fee, tax_rate)
- Week 3: Profile fee override and guardian fields
- Week 3: Link group format and member fees
- Week 3: Upload entry date/time fields
- Week 4: Ledger entry fields (income/expense)

**Philosophy:** Always additive, never destructive. Old data stays intact.

---

*For route information, see Route_Reference.md*  
*For design philosophy, see Architecture_Decisions.md*  
*For debugging help, see Debugging_Guide.md*

*Last updated: November 23, 2025*
