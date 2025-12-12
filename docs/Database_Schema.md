# EdgeCase Equalizer - Database Schema

**Purpose:** Complete database table definitions and design decisions  
**Last Updated:** December 5, 2025

---

## OVERVIEW

EdgeCase uses SQLite with 12 tables organized around an entry-based architecture. All client records (profiles, sessions, communications, etc.) are stored as entries in a unified table with class-specific fields.

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
9. income_payors - Income payor names (NEW)
10. settings - Application settings
11. archived_clients - Retention system archives
12. statement_portions - Statement tracking

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
    
    -- Profile Session Fee (individual session pricing)
    session_base REAL,
    session_tax_rate REAL,
    session_total REAL,
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
    
    -- Statement-specific fields
    statement_total REAL,
    statement_tax_total REAL,        -- Total tax from billable entries (for pro-rata calculation)
    statement_id INTEGER,           -- Links billable entries to their statement
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
    FOREIGN KEY (category_id) REFERENCES expense_categories(id),
    FOREIGN KEY (statement_id) REFERENCES entries(id)
);
```

**Entry Classes:**

**Client Entry Types (client_id NOT NULL):**
- `profile` - Client demographics and contact info
- `session` - Therapy session notes
- `communication` - Emails, calls, administrative notes (with file attachments)
- `absence` - Cancellations and no-shows with fees
- `item` - Billable items (books, letters, reports)
- `upload` - File attachments and documents
- `statement` - Generated invoice record

**Ledger Entry Types (client_id NULL, ledger_type NOT NULL):**
- `income` - Payment received (ledger_type='income')
- `expense` - Business expenses (ledger_type='expense')

**Key Fields for Statements:**
- `statement_id`: On billable entries (session, absence, item), links to the statement entry
- `statement_total`: On statement entries, the total amount due

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

### 9. income_payors

Income payor names (reusable, for autocomplete).

```sql
CREATE TABLE income_payors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 10. settings

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
- `calendar_method`, `calendar_name`
- `email_method`: 'mailto' or 'applescript'
- `email_from_address`: For AppleScript email
- `statement_email_body`: Email body template
- `registration_info`, `payment_instructions`
- `include_attestation`, `attestation_text`

---

### 11. archived_clients

Retention system archives (minimal info kept after deletion).

```sql
CREATE TABLE archived_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_number TEXT NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    first_contact INTEGER,
    last_contact INTEGER,
    retain_until INTEGER,
    deletion_date INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
```

---

### 12. statement_portions (NEW)

Tracks individual payment portions for statements.

```sql
CREATE TABLE statement_portions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_entry_id INTEGER NOT NULL,
    client_id INTEGER NOT NULL,
    guardian_number INTEGER,          -- NULL for client, 1 or 2 for guardians
    amount_due REAL NOT NULL,
    amount_paid REAL DEFAULT 0,
    status TEXT DEFAULT 'ready',      -- 'ready', 'sent', 'partial', 'paid'
    created_at INTEGER NOT NULL,
    date_sent INTEGER,                -- When statement was emailed
    FOREIGN KEY (statement_entry_id) REFERENCES entries(id),
    FOREIGN KEY (client_id) REFERENCES clients(id)
);
```

**Key Fields:**
- `statement_entry_id`: Links to the statement entry in entries table
- `client_id`: The client this portion is for
- `guardian_number`: NULL for client paying directly, 1 or 2 for guardian splits
- `amount_due`: Total amount for this portion
- `amount_paid`: Running total of payments received
- `status`: Payment status for this portion
- `date_sent`: Unix timestamp when "Mark Sent" was clicked

**Status Values:**
- `ready`: Statement generated, not yet sent
- `sent`: Email sent to client/guardian
- `partial`: Some payment received, balance remaining
- `paid`: Fully paid

**Guardian Billing:**
When a client is a minor with guardian billing:
- Two portions created (one per guardian)
- Each portion has `guardian_number` = 1 or 2
- `amount_due` calculated from guardian's `pays_percent`

**Payment Status Calculation (in database.py):**
```python
def get_payment_status(self, client_id):
    # Returns: 'paid', 'pending', or 'overdue'
    # - 'paid': No outstanding portions
    # - 'pending': Has sent/partial portions, none 30+ days old
    # - 'overdue': Has sent/partial portions 30+ days old
```

---

## KEY DESIGN DECISIONS

### Statement System Architecture

**Why statement_portions table?**
- Separates billing tracking from entry data
- Handles guardian splits (2 portions per statement)
- Tracks payment status independently
- Easy to query outstanding statements
- Payment status calculation doesn't require complex entry queries

**Why Communication entry on send?**
- Creates audit trail in client file
- PDF attachment preserved
- Email content recorded
- No separate "sent statements" view needed
- Natural fit with existing entry timeline

**Auto-Income Generation:**
When payment recorded:
1. Update statement_portions (amount_paid, status)
2. Create Income entry in ledger
3. Link Income to statement via statement_id field
4. Use file_number as source (privacy - not client name)

---

## MIGRATIONS

**Location:** `core/database.py` in `_run_migrations()` method

**Recent Migrations (Nov 28):**
- Added statement_portions table
- Added statement_id field to entries (links billable entries to statements)

**Philosophy:** Always additive, never destructive. Old data stays intact.

---

*For route information, see Route_Reference.md*  
*For design philosophy, see Architecture_Decisions.md*  
*For debugging help, see Debugging_Guide.md*

*Last updated: November 28, 2025*
