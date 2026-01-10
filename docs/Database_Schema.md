# EdgeCase Equalizer - Database Schema

**Purpose:** Complete database table definitions and design decisions  
**Last Updated:** January 10, 2026

---

## OVERVIEW

EdgeCase uses SQLite with SQLCipher encryption, containing 13 tables organized around an entry-based architecture. All client records (profiles, sessions, communications, etc.) are stored as entries in a unified table with class-specific fields.

**Database Location:** `~/edgecase/data/edgecase.db`

**Tables:**
1. clients - Client records
2. client_types - Status categories (Active, Inactive)
3. entries - Unified entry table (THE CORE)
4. link_groups - Couples/Family/Group therapy
5. client_links - Link group membership with fees
6. entry_links - Links between entries across clients
7. attachments - Encrypted file uploads
8. expense_categories - User-defined expense categories
9. payees - Expense payee names
10. income_payors - Income payor names
11. settings - Application settings
12. archived_clients - Retention system archives
13. statement_portions - Statement tracking

---

## FEE ARCHITECTURE

Fees are defined in three places:

1. **Profile** – Individual session fees (`session_base`, `session_tax_rate`, `session_total`)
2. **Link groups** – Per-member fees for couples/family/group sessions
3. **Settings** – Consultation fee (practice-wide, applied when session is marked as consultation)

**Client types have NO fee fields** – they're purely for organization and workflow.

**Guardian billing** is separate from fee definition. It determines who pays (split percentages), not how much.

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
    retention_days INTEGER,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    is_deleted INTEGER DEFAULT 0,
    FOREIGN KEY (type_id) REFERENCES client_types(id)
);
```

**Key Fields:**
- `file_number`: Unique identifier (format depends on settings)
- `session_offset`: Starting session number for migrated clients
- `retention_days`: Set when moving to Inactive status (snapshots the type's retention_period)
- `is_deleted`: Soft delete flag (0 = active, 1 = deleted)

---

### 2. client_types

Status categories for organization and workflow—NOT billing.

```sql
CREATE TABLE client_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT NOT NULL,
    color_name TEXT,
    bubble_color TEXT,
    retention_period INTEGER,
    is_system INTEGER DEFAULT 0,
    is_system_locked INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL
);
```

**Key Fields:**
- `name`: Type name (e.g., "Active", "Inactive")
- `color`: Hex color for client cards
- `bubble_color`: Light background for client cards
- `retention_period`: How long to keep records after becoming inactive (in days)
- `is_system_locked`: 1 for Inactive (can't delete or edit)

**Default Types:**
- Active (Seafoam #9FCFC0)
- Inactive (Warm Amber #D9C8A5, system-locked)

---

### 3. entries

**THE CORE TABLE** - Unified storage for all entry types.

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    class TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    
    -- Common fields
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
    
    -- Profile session fee fields (individual session pricing)
    session_base REAL,
    session_tax_rate REAL,
    session_total REAL,
    default_session_duration INTEGER,
    
    -- Profile guardian/billing fields
    is_minor INTEGER DEFAULT 0,
    guardian1_name TEXT,
    guardian1_email TEXT,
    guardian1_phone TEXT,
    guardian1_address TEXT,
    guardian1_pays_percent INTEGER DEFAULT 100,
    has_guardian2 INTEGER DEFAULT 0,
    guardian2_name TEXT,
    guardian2_email TEXT,
    guardian2_phone TEXT,
    guardian2_address TEXT,
    guardian2_pays_percent INTEGER DEFAULT 0,
    
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
    guardian1_amount REAL,
    guardian2_amount REAL,
    
    -- Upload-specific fields
    upload_date INTEGER,
    upload_time TEXT,
    
    -- Ledger-specific fields (Income/Expense entries)
    ledger_date INTEGER,
    ledger_type TEXT,
    source TEXT,
    payee_id INTEGER,
    category_id INTEGER,
    base_amount REAL,
    tax_amount REAL,
    total_amount REAL,
    statement_id INTEGER,
    
    -- Statement-specific fields
    statement_total REAL,
    statement_tax_total REAL,
    payment_status TEXT,
    payment_notes TEXT,
    date_sent INTEGER,
    date_paid INTEGER,
    is_void INTEGER DEFAULT 0,
    
    -- Edit tracking
    edit_history TEXT,
    locked INTEGER DEFAULT 0,
    locked_at INTEGER,
    
    -- Redaction (privacy protection)
    is_redacted INTEGER DEFAULT 0,
    redacted_at INTEGER,
    redaction_reason TEXT,
    
    FOREIGN KEY (client_id) REFERENCES clients(id)
);
```

**Entry Classes:**

**Client Entry Types (client_id NOT NULL):**
- `profile` - Client demographics, contact info, and session fees
- `session` - Therapy session notes
- `communication` - Emails, calls, administrative notes
- `absence` - Cancellations and no-shows with fees
- `item` - Billable items (books, letters, reports)
- `upload` - File attachments and documents
- `statement` - Generated invoice record

**Ledger Entry Types (client_id NULL, ledger_type set):**
- `income` - Payment received (ledger_type='income')
- `expense` - Business expenses (ledger_type='expense')

---

### 4. link_groups

Groups for couples/family/group therapy.

```sql
CREATE TABLE link_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    format TEXT,
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
    group_id INTEGER,
    member_base_fee REAL,
    member_tax_rate REAL,
    member_total_fee REAL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (client_id_1) REFERENCES clients(id),
    FOREIGN KEY (client_id_2) REFERENCES clients(id),
    FOREIGN KEY (group_id) REFERENCES link_groups(id)
);
```

In the self-referential pattern, `client_id_1` and `client_id_2` are the same value. All members of a group share the same `group_id`.

---

### 6. entry_links

Links entries across client files (e.g., linked sessions for couples therapy).

```sql
CREATE TABLE entry_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id_1 INTEGER NOT NULL,
    entry_id_2 INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (entry_id_1) REFERENCES entries(id),
    FOREIGN KEY (entry_id_2) REFERENCES entries(id),
    UNIQUE(entry_id_1, entry_id_2)
);
```

---

### 7. attachments

Encrypted file uploads for entries.

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

### 8. expense_categories

User-defined expense categories for tax reporting.

```sql
CREATE TABLE expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 9. payees

Expense payee names (for autocomplete).

```sql
CREATE TABLE payees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 10. income_payors

Income payor names (for autocomplete).

```sql
CREATE TABLE income_payors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 11. settings

Application configuration (key-value store).

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
- `calendar_method`, `calendar_name`
- `email_method`: 'mailto' or 'applescript'
- `statement_email_body`: Email body template
- `registration_info`, `payment_instructions`

---

### 12. archived_clients

Minimal info kept after retention deletion (audit trail).

```sql
CREATE TABLE archived_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_number TEXT NOT NULL,
    full_name TEXT NOT NULL,
    first_contact INTEGER,
    last_contact INTEGER,
    retain_until INTEGER,
    deleted_at INTEGER NOT NULL
);
```

---

### 13. statement_portions

Tracks individual payment portions for statements.

```sql
CREATE TABLE statement_portions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_entry_id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    guardian_number INTEGER,
    amount_due REAL NOT NULL,
    amount_paid REAL DEFAULT 0,
    status TEXT DEFAULT 'ready',
    date_sent INTEGER,
    created_at INTEGER NOT NULL,
    write_off_reason TEXT,
    write_off_date INTEGER,
    write_off_note TEXT,
    FOREIGN KEY (statement_entry_id) REFERENCES entries(id),
    FOREIGN KEY (client_id) REFERENCES clients(id)
);
```

**Key Fields:**
- `guardian_number`: NULL for client paying directly, 1 or 2 for guardian splits
- `amount_due`: Total amount for this portion
- `amount_paid`: Running total of payments received
- `status`: 'ready', 'sent', 'partial', 'paid', 'written_off'

---

## KEY DESIGN DECISIONS

### Statement System Architecture

**Why statement_portions table?**
- Separates billing tracking from entry data
- Handles guardian splits (2 portions per statement)
- Tracks payment status independently
- Easy to query outstanding statements

**Auto-Income Generation:**
When payment recorded:
1. Update statement_portions (amount_paid, status)
2. Create Income entry in ledger
3. Link Income to statement via statement_id field
4. Use file_number as source (privacy - not client name)

---

## MIGRATIONS

**Location:** `core/database.py` in `_run_migrations()` method

**Philosophy:** Always additive, never destructive. Old data stays intact.

---

*For route information, see Route_Reference.md*  
*For design philosophy, see Architecture_Decisions.md*

*Last updated: December 28, 2025*
