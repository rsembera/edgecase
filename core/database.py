"""
EdgeCase Database Module
Handles SQLite database operations with SQLCipher encryption.
"""

import sqlcipher3 as sqlite3  # Drop-in replacement with encryption
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import os
import time
import threading
from datetime import datetime, timedelta

from core import encryption_v2
from core.db.settings import SettingsMixin
from core.db.client_types import ClientTypeMixin
from core.db.edit_history import EditHistoryMixin
from core.db.links import LinkMixin
from core.db.clients import ClientMixin
from core.db.allocations import AllocationMixin
from core.db.entries import EntryMixin
from core.db.ledger import LedgerMixin
from core.db.retention import RetentionMixin
from core.db.providers import ProviderMixin
from core.db.errors import EntryLockedError  # re-exported; defined in a leaf module to avoid an import cycle with EntryMixin

# 2.0.3: the two-note system (2.0.2) was withdrawn. Text written into
# entries.reflections is folded into content under this divider on open.
REFLECTIONS_DIVIDER = "\n\n--- Reflections (moved from the withdrawn Reflections field) ---\n"


class Database(SettingsMixin, ClientTypeMixin, EditHistoryMixin, LinkMixin, ClientMixin, AllocationMixin, EntryMixin, LedgerMixin, RetentionMixin, ProviderMixin):
    """
    Database interface for EdgeCase.
    Manages all SQLite operations using Entry-based architecture.
    Uses SQLCipher for AES-256 encryption at rest.
    """
    
    def __init__(self, db_path: str, password: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
            password: Encryption password (required for encrypted databases)
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.password = password
        self._local = threading.local()  # Thread-local storage for connections
        # FK enforcement is decided after startup checks (False until then
        # so connections opened during init don't enforce prematurely)
        self._enforce_foreign_keys = False
        self._initialize_schema()
        self._migrate_typed_empty_strings()
        # Give pre-existing payments their allocation rows. Idempotent and
        # guarded by NOT EXISTS, so this is a no-op from the second launch
        # onward; kept a standalone method (not inlined in schema init) so
        # it can be re-run and tested independently.
        self.backfill_payment_allocations(verbose=True)
        self._enforce_foreign_keys = self._check_foreign_key_integrity()
        if self._enforce_foreign_keys:
            # Apply to the connection this thread already opened during init
            self.connect().execute('PRAGMA foreign_keys = ON')
        # Restrict database file permissions to owner only
        if self.db_path.exists():
            os.chmod(self.db_path, 0o600)
        
    def connect(self):
        """Return thread-local database connection with encryption."""
        # Each thread gets its own connection
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            
            # Set encryption key FIRST, before any other operations.
            # A migrated (v2) install has a .keyinfo file: key SQLCipher with
            # the raw Argon2id-derived key. Otherwise (v1 install) key with the
            # passphrase exactly as before, so un-migrated installs are wholly
            # unaffected. See Architecture_Decisions.md (Attachment Encryption v2).
            if self.password:
                if encryption_v2.keyinfo_exists():
                    db_key_hex, _ = encryption_v2.get_keys(self.password)
                    self._local.conn.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
                else:
                    # Escape single quotes to prevent SQL injection/breakage
                    escaped_password = self.password.replace("'", "''")
                    self._local.conn.execute(f"PRAGMA key = '{escaped_password}'")
            
            # Enable WAL mode for better concurrent access
            self._local.conn.execute('PRAGMA journal_mode=WAL')

            # Enforce the schema's FOREIGN KEY constraints (off by default
            # in SQLite, must be set per connection; CODE_REVIEW.md M2).
            # Conditional because EdgeCase is distributed: enforcement is
            # only enabled when this database passed the startup
            # foreign_key_check (see _check_foreign_key_integrity) — a
            # legacy database with pre-existing orphans keeps working,
            # with a warning pointing at tools/audit_orphans.py. All
            # delete paths were audited to remove child rows first.
            if self._enforce_foreign_keys:
                self._local.conn.execute('PRAGMA foreign_keys = ON')
        return self._local.conn

    def _check_foreign_key_integrity(self) -> bool:
        """Decide whether FOREIGN KEY enforcement can be enabled.

        Runs PRAGMA foreign_key_check once at startup. A clean database
        gets enforcement; a database with pre-existing orphans (possible
        on installs that predate the 2026-06 integrity work) runs without
        enforcement and logs a warning so the user can clean up with
        tools/audit_orphans.py — after which enforcement turns on
        automatically at the next launch.
        """
        try:
            cursor = self.connect().cursor()
            cursor.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
        except Exception as e:
            print(f"Warning: foreign_key_check failed ({e}); "
                  "FK enforcement disabled for this run")
            return False
        if violations:
            print(f"WARNING: {len(violations)} foreign-key violation(s) found "
                  "in this database. Foreign-key enforcement is disabled for "
                  "this run. Run 'python tools/audit_orphans.py' to inspect "
                  "and clean up; enforcement enables automatically once clean.")
            return False
        return True

    def _migrate_typed_empty_strings(self):
        """Idempotent startup migration: rewrite legacy '' values in typed
        entry columns to NULL.

        Versions before the H5 fix coerced None to '' on insert, leaving
        TEXT empty strings in REAL/INTEGER columns — breaking range
        filters, ORDER BY, and IS NULL checks (e.g. the redaction lock's
        statement_id test). New writes are clean; this sweeps up what
        older versions left behind, on every install rather than only
        where tools/audit_typed_columns.py --fix was run by hand.
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        existing = {row[1] for row in cursor.fetchall()}
        fixed = 0
        try:
            # Column names come from the frozenset constant, not user input
            for col in sorted(self.TYPED_ENTRY_COLUMNS & existing):
                cursor.execute(f"UPDATE entries SET {col} = NULL WHERE {col} = ''")
                fixed += cursor.rowcount
            # Always commit: even no-op UPDATEs open an implicit
            # transaction, and PRAGMA foreign_keys (set right after this
            # in __init__) is silently ignored inside one.
            conn.commit()
            if fixed:
                print(f"Migration: rewrote {fixed} legacy empty-string "
                      f"value(s) to NULL in typed entry columns")
        except Exception:
            conn.rollback()
            raise
    
    def close(self):
        """Close database connection for current thread."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
    
    def checkpoint(self):
        """Force WAL checkpoint to flush all changes to main database file."""
        conn = self.connect()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    
    def verify_password(self, password):
        """Verify if the given password can decrypt the database.

        Opens a fresh connection to test the password rather than
        comparing against the in-memory password string.

        Returns bool. The test connection is always closed (try/finally),
        and failure causes are distinguished in the log: an
        OperationalError (file missing/unreadable/locked) is not the same
        as a DatabaseError (wrong key / not decryptable / corrupt).
        See CODE_REVIEW.md L18.
        """
        # Migrated install (v2 or v3): verify without opening the database.
        #
        # v2 — derive the file key and decrypt the key-info verification token.
        # v3 — there is no separate token: the password wrapper is AES-GCM, so a
        #      wrong password fails the auth tag and unwrapping raises. The
        #      wrapper IS the verification, which is why ECC3 has no token field.
        # Either way the same master (and so the same DB key) is what a
        # successful check proves access to.
        if encryption_v2.keyinfo_exists():
            try:
                from core import encryption_v3
                if encryption_v3.keyinfo_version() == 3:
                    encryption_v3.unwrap_with_password(
                        encryption_v3.read_keyinfo(), password)
                    return True
                _salt, token = encryption_v2.read_keyinfo()
                _db_key_hex, file_key = encryption_v2.get_keys(password)
                return encryption_v2.check_verification_token(file_key, token)
            except ValueError:
                # Wrong password on a v3 install — expected, not an error.
                return False
            except Exception as e:
                print(f"verify_password: key-info verification error: {e}")
                return False

        test_conn = None
        try:
            test_conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            escaped = password.replace("'", "''")
            test_conn.execute(f"PRAGMA key = '{escaped}'")
            test_conn.execute("SELECT count(*) FROM client_types")
            return True
        except sqlite3.OperationalError as e:
            # File missing, unreadable, or locked — not proof of a bad password
            print(f"verify_password: database not accessible: {e}")
            return False
        except sqlite3.DatabaseError as e:
            # Wrong key (file won't decrypt) or corrupt database
            print(f"verify_password: wrong password or corrupt database: {e}")
            return False
        except Exception as e:
            print(f"verify_password: unexpected error: {e}")
            return False
        finally:
            if test_conn is not None:
                try:
                    test_conn.close()
                except Exception:
                    pass
    
    def _initialize_schema(self):
        """Create tables if they don't exist."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Client Types table (status/organization only, no fees)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_types (
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
            )
        """)
        
        # Clients table (unchanged)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
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
            )
        """)
        
        # Entries table (WITH Profile fee fields and default_session_duration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
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
                meeting_link TEXT,
                
                -- Profile session fee fields (primary individual session fees)
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
                
                -- Redaction fields
                is_redacted INTEGER DEFAULT 0,
                redacted_at INTEGER,
                redaction_reason TEXT,
                
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Link Groups (for couples/family/group therapy - WITH session_duration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS link_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                format TEXT,
                session_duration INTEGER,
                created_at INTEGER NOT NULL
            )
        """)
        
        # Client Linking (self-referential with per-member fees)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_links (
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
            )
        """)
        
        # Entry Links (linked entries across client files)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entry_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id_1 INTEGER NOT NULL,
                entry_id_2 INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (entry_id_1) REFERENCES entries(id),
                FOREIGN KEY (entry_id_2) REFERENCES entries(id),
                UNIQUE(entry_id_1, entry_id_2)
            )
        """)
        
        # Attachments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                description TEXT,
                filepath TEXT NOT NULL,
                filesize INTEGER,
                uploaded_at INTEGER NOT NULL,
                FOREIGN KEY (entry_id) REFERENCES entries(id)
            )
        """)
        
        # Practice Settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                modified_at INTEGER NOT NULL
            )
        """)
        
        # Payees table (for expense entries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        
        # Expense Categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expense_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        
        # Income Payors table (for income entries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS income_payors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        
        # Archived Clients (retention system audit trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS archived_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_number TEXT NOT NULL,
                full_name TEXT NOT NULL,
                first_contact INTEGER,
                last_contact INTEGER,
                retain_until INTEGER,
                deleted_at INTEGER NOT NULL
            )
        """)
        
        # Statement Portions (payment tracking for Outstanding Statements)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statement_portions (
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
        )
        """)

        # Payment Allocations (one payment settling one or more portions).
        #
        # A row is a claim on a ledger entry: portion_id NOT NULL applies the
        # amount to that statement portion; portion_id NULL holds it as an
        # unallocated CREDIT on the client's account. client_id and
        # guardian_number carry the payer scope so a credit can be found and
        # spent without inferring the payer from a description string.
        #
        # Additive only — no migration runner and no backup gate, unlike the
        # crypto versions: the table appears on next launch, and installs
        # that never overpay simply never write a NULL-portion row. See
        # core/db/allocations.py and docs/Payment_Allocation_Plan.md.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                portion_id INTEGER,
                client_id INTEGER NOT NULL,
                guardian_number INTEGER,
                amount REAL NOT NULL,
                tax_amount REAL,
                created_at INTEGER NOT NULL,
                is_credit INTEGER DEFAULT 0,
                FOREIGN KEY (entry_id) REFERENCES entries(id),
                FOREIGN KEY (portion_id) REFERENCES statement_portions(id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)

        # is_credit marks a row written by consuming a credit balance rather
        # than by a payment arriving, so the statement PDF can show "Credit
        # applied" as its own line. Added a day after the table itself, so
        # existing copies need the column filled in — guarded by table_info
        # rather than ALTER-and-catch, which is the same idempotent shape as
        # _migrate_typed_empty_strings.
        cursor.execute("PRAGMA table_info(payment_allocations)")
        alloc_columns = {row[1] for row in cursor.fetchall()}
        if 'is_credit' not in alloc_columns:
            cursor.execute("ALTER TABLE payment_allocations "
                           "ADD COLUMN is_credit INTEGER DEFAULT 0")

        # entries.reflections was added by 2.0.2 (two-note system) and the
        # feature withdrawn in 2.0.3 before it had been lived with. The
        # column is left in place on databases that have it — dropping a
        # column on an encrypted database is not worth the risk — but any
        # text in it is folded into content so nothing is stranded in a
        # field the UI no longer shows. A migration is not an amendment:
        # modified_at is left alone and no edit-history row is written.
        # Fresh databases never gain the column.
        cursor.execute("PRAGMA table_info(entries)")
        entry_columns = {row[1] for row in cursor.fetchall()}
        if 'reflections' in entry_columns:
            cursor.execute("SELECT id, content, reflections FROM entries "
                           "WHERE reflections IS NOT NULL AND reflections != ''")
            for eid, content, reflections in cursor.fetchall():
                folded = (content + REFLECTIONS_DIVIDER + reflections if content
                          else REFLECTIONS_DIVIDER.lstrip() + reflections)
                cursor.execute("UPDATE entries SET content = ?, reflections = NULL "
                               "WHERE id = ?", (folded, eid))

        # Insurance providers (networks the practitioner has joined). The
        # number is the practitioner's, but WHICH number prints on a document
        # is a property of the client, because the insurer is: see
        # clients.provider_id. `number_format` is the line as the insurer
        # wants it, with {number} substituted — insurers differ and the app
        # should not impose a house style.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insurance_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_number TEXT NOT NULL,
                number_format TEXT NOT NULL DEFAULT '{name} — Provider No. {number}',
                created_at INTEGER NOT NULL,
                modified_at INTEGER NOT NULL
            )
        """)

        # clients.provider_id: nullable, so "no insurer" is the default and
        # changing or dropping an insurer is just reselecting.
        cursor.execute("PRAGMA table_info(clients)")
        client_columns = {row[1] for row in cursor.fetchall()}
        if 'provider_id' not in client_columns:
            cursor.execute("ALTER TABLE clients "
                           "ADD COLUMN provider_id INTEGER REFERENCES "
                           "insurance_providers(id)")

        # Indexes for the most common query patterns (CODE_REVIEW.md M3).
        # IF NOT EXISTS makes this idempotent, so running at every startup
        # also migrates existing databases.
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_client_class
            ON entries(client_id, class)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_ledger
            ON entries(ledger_type, ledger_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_entry
            ON attachments(entry_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_statement_portions_client_status
            ON statement_portions(client_id, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alloc_entry
            ON payment_allocations(entry_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alloc_portion
            ON payment_allocations(portion_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alloc_credit
            ON payment_allocations(client_id, guardian_number)
        """)

        conn.commit()

        # Create default client types if they don't exist
        self._create_default_types()

    def _create_default_types(self):
        """Create default client types on first run.
        
        Creates 2 system types:
        - Active (editable, default)
        - Inactive (locked, workflow state)
        """
        # Check if any types exist
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM client_types")
        count = cursor.fetchone()[0]
        
        if count > 0:
            return
        
        now = int(time.time())
        
        # Default types with muted color palette (NO FEE FIELDS)
        default_types = [
            {
                'name': 'Active',
                'color': '#9FCFC0',  # Seafoam
                'color_name': 'Seafoam',
                'bubble_color': '#E6F5F1',
                'retention_period': 2555,  # 7 years
                'is_system': 0,
                'is_system_locked': 0
            },
            {
                'name': 'Inactive',
                'color': '#D9C8A5',  # Warm Amber
                'color_name': 'Warm Amber',
                'bubble_color': '#F5F0E9',
                'retention_period': 2555,  # 7 years in days
                'is_system': 1,
                'is_system_locked': 1
            }
        ]
        
        # Multi-statement write: roll back on any failure (CODE_REVIEW.md H8)
        try:
            for type_data in default_types:
                cursor.execute("""
                    INSERT INTO client_types (
                        name, color, color_name, bubble_color,
                        retention_period, is_system, is_system_locked,
                        created_at, modified_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    type_data['name'],
                    type_data['color'],
                    type_data['color_name'],
                    type_data['bubble_color'],
                    type_data['retention_period'],
                    type_data['is_system'],
                    type_data['is_system_locked'],
                    now,
                    now
                ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print("Created 2 default client types (Active, Inactive)")
    
    # ===== CLIENT TYPE OPERATIONS =====
    # Extracted to core/db/client_types.py (ClientTypeMixin).

    # ===== CLIENT OPERATIONS =====
    # Extracted to core/db/clients.py (ClientMixin).

    # ===== EDIT HISTORY SYSTEM ======
    # Extracted to core/db/edit_history.py (EditHistoryMixin).

    # ===== CLIENT LINKING OPERATIONS =====
    # Extracted to core/db/links.py (LinkMixin).

    # ===== ENTRY OPERATIONS =====
    # Extracted to core/db/entries.py (EntryMixin).

    # ===== SETTINGS OPERATIONS =====
    # Extracted to core/db/settings.py (SettingsMixin).

    # EdgeCase Ledger operations extracted to core/db/ledger.py (LedgerMixin).

    # Retention system extracted to core/db/retention.py (RetentionMixin).

    # ============================================================================
    # NOTES
    # ============================================================================

    # These methods integrate with existing Database class methods:
    # - add_entry() - works for ledger entries (class='income' or 'expense')
    # - update_entry() - works for editing ledger entries
    # - get_entry() - works for getting single ledger entry
    # - add_to_edit_history() - tracks changes to ledger entries
    # - get_edit_history() - retrieves edit history
    # - get_attachments() - gets attachments for ledger entries

    # Ledger entries use client_id = NULL since they're practice-wide
    # Attachments are stored in attachments/ledger/{entry_id}/