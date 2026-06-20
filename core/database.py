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
from core.db.entries import EntryMixin
from core.db.ledger import LedgerMixin


class EntryLockedError(Exception):
    """Raised when update_entry is called on a locked entry without
    `allow_locked=True`. Locked clinical entries are immutable by design;
    edits to them must go through the route layer's lock-check + edit
    history flow, which then opts in via `allow_locked=True`.
    See CODE_REVIEW.md M11.
    """
    pass


class Database(SettingsMixin, ClientTypeMixin, EditHistoryMixin, LinkMixin, ClientMixin, EntryMixin, LedgerMixin):
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
        # v2 install: verify against the key-info verification token. A
        # correct password derives the file key that decrypts the token, which
        # (same Argon2id master) also yields the correct DB key. No DB open.
        if encryption_v2.keyinfo_exists():
            try:
                _salt, token = encryption_v2.read_keyinfo()
                _db_key_hex, file_key = encryption_v2.get_keys(password)
                return encryption_v2.check_verification_token(file_key, token)
            except Exception as e:
                print(f"verify_password: v2 verification error: {e}")
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

    # ============================================================
    # RETENTION SYSTEM FUNCTIONS
    # ============================================================

    @staticmethod
    def _calculate_retain_until(last_contact, retention_days, is_minor, dob_str):
        """
        Compute the epoch timestamp at which an Inactive client's file may be
        destroyed. Single source of truth for both the deletion sweep
        (get_clients_due_for_deletion) and the single-client preview, so the
        two can never drift apart.

        Anchored on last_contact (most recent entry's created_at). For minors,
        retention runs to the LATER of (last_contact + period) and
        (18th birthday + period). See Architecture_Decisions.md:
        RETENTION CLOCK ANCHORING.
        """
        from datetime import datetime

        retention_seconds = (retention_days or 0) * 24 * 60 * 60
        standard_retain_until = last_contact + retention_seconds

        if is_minor and dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d')
                try:
                    eighteenth_birthday = dob.replace(year=dob.year + 18)
                except ValueError:
                    # Feb 29 birthday: no Feb 29 in the target year. Clamp to
                    # Mar 1 (one day later than Feb 28) so a leap-day minor
                    # still gets the age-of-majority extension. Falling through
                    # to standard retention would be the unsafe, shorter direction.
                    eighteenth_birthday = dob.replace(year=dob.year + 18, month=3, day=1)
                after_majority = int(eighteenth_birthday.timestamp()) + retention_seconds
                return max(standard_retain_until, after_majority)
            except (ValueError, TypeError):
                return standard_retain_until

        return standard_retain_until

    def get_clients_due_for_deletion(self):
        """
        Get all Inactive clients whose retention period has expired.
        Returns list of dicts with client info and calculated retain_until.
        """
        from datetime import datetime
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get all Inactive clients with retention_days set.
        # Match on is_system_locked (the flag that uniquely identifies the
        # seeded Inactive workflow type — see _create_default_types) rather
        # than the literal name, so a rename can never silently disable the
        # retention sweep (CODE_REVIEW.md M10).
        # Entry date aggregates and profile fields are pulled in via scalar
        # subqueries so the whole sweep is one round trip instead of three
        # extra queries per client (CODE_REVIEW.md L5).
        cursor.execute("""
            SELECT c.*, ct.name as type_name,
                   (SELECT MAX(created_at) FROM entries
                    WHERE client_id = c.id) AS entry_last_contact,
                   (SELECT MIN(created_at) FROM entries
                    WHERE client_id = c.id) AS entry_first_contact,
                   (SELECT is_minor FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS profile_is_minor,
                   (SELECT date_of_birth FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS profile_dob,
                   (SELECT 1 FROM entries
                    WHERE client_id = c.id AND class = 'profile'
                    LIMIT 1) AS has_profile
            FROM clients c
            JOIN client_types ct ON c.type_id = ct.id
            WHERE ct.is_system_locked = 1
            AND c.retention_days IS NOT NULL
            AND c.is_deleted = 0
        """)

        columns = [description[0] for description in cursor.description]
        inactive_clients = [dict(zip(columns, row)) for row in cursor.fetchall()]

        clients_due = []
        today = int(time.time())

        for client in inactive_clients:
            client_id = client['id']
            retention_days = client['retention_days']

            # 0 retention_days means "keep forever" - skip these
            if retention_days == 0:
                continue

            # Last contact date (most recent entry, or fall back to modified_at)
            last_contact = client['entry_last_contact'] if client['entry_last_contact'] else client['modified_at']

            # Profile fields for minor status (0/None when no profile exists,
            # matching the previous per-client query's fallback)
            is_minor = client['profile_is_minor'] if client['has_profile'] else 0
            dob_str = client['profile_dob'] if client['has_profile'] else None

            # Calculate retain_until (see _calculate_retain_until)
            retain_until = self._calculate_retain_until(
                last_contact, retention_days, is_minor, dob_str
            )

            # Check if retention period has expired
            if today >= retain_until:
                # First contact (earliest entry, or fall back to created_at)
                first_contact = client['entry_first_contact'] if client['entry_first_contact'] else client['created_at']
                
                # Build full name
                full_name = client['first_name']
                if client.get('middle_name'):
                    full_name += f" {client['middle_name']}"
                full_name += f" {client['last_name']}"
                
                clients_due.append({
                    'id': client_id,
                    'file_number': client['file_number'],
                    'full_name': full_name,
                    'first_contact': first_contact,
                    'last_contact': last_contact,
                    'retain_until': retain_until,
                    'is_minor': is_minor
                })
        
        return clients_due

    def archive_and_delete_client(self, client_id):
        """
        Archive client info and delete all their data.
        Returns True on success, False on failure.

        All database deletes happen in one transaction; attachment files
        are removed from disk only AFTER the commit succeeds, so a failed
        DELETE can never roll back the DB while the files are already gone
        (CODE_REVIEW.md H6). File-deletion failures after the commit are
        logged but do not fail the operation.
        """
        import shutil

        conn = self.connect()
        cursor = conn.cursor()

        try:
            # Get client data
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            if not row:
                return False
            client = dict(zip(columns, row))
            
            # Get profile for minor check
            cursor.execute("""
                SELECT is_minor, date_of_birth
                FROM entries
                WHERE client_id = ? AND class = 'profile'
            """, (client_id,))
            profile = cursor.fetchone()
            is_minor = profile[0] if profile else 0
            dob_str = profile[1] if profile else None
            
            # Get first contact
            cursor.execute("""
                SELECT MIN(created_at) FROM entries WHERE client_id = ?
            """, (client_id,))
            result = cursor.fetchone()
            first_contact = result[0] if result and result[0] else client['created_at']
            
            # Get last contact
            cursor.execute("""
                SELECT MAX(created_at) FROM entries WHERE client_id = ?
            """, (client_id,))
            result = cursor.fetchone()
            # Fallback aligned with get_clients_due_for_deletion: use modified_at
            # (≈ when the file went cold) rather than created_at for entry-less clients
            last_contact = result[0] if result and result[0] else client['modified_at']
            
            # Calculate retain_until (see _calculate_retain_until)
            retention_days = client.get('retention_days') or 0
            retain_until = self._calculate_retain_until(
                last_contact, retention_days, is_minor, dob_str
            )
            
            # Build full name
            full_name = client['first_name']
            if client.get('middle_name'):
                full_name += f" {client['middle_name']}"
            full_name += f" {client['last_name']}"
            
            # Create archive record
            cursor.execute("""
                INSERT INTO archived_clients 
                (file_number, full_name, first_contact, last_contact, retain_until, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                client['file_number'],
                full_name,
                first_contact,
                last_contact,
                retain_until,
                int(time.time())
            ))
            
            # Get all entry IDs for this client (for attachment/link cleanup)
            cursor.execute("SELECT id FROM entries WHERE client_id = ?", (client_id,))
            entry_ids = [row[0] for row in cursor.fetchall()]

            if entry_ids:
                placeholders = ','.join('?' * len(entry_ids))

                # Delete attachments from database
                cursor.execute(f"DELETE FROM attachments WHERE entry_id IN ({placeholders})", entry_ids)

                # Delete entry links referencing this client's entries (either side)
                cursor.execute(
                    f"DELETE FROM entry_links WHERE entry_id_1 IN ({placeholders}) "
                    f"OR entry_id_2 IN ({placeholders})",
                    entry_ids + entry_ids
                )

            # Delete statement portions (orphans would permanently inflate
            # count_pending_invoices)
            cursor.execute("DELETE FROM statement_portions WHERE client_id = ?", (client_id,))

            # Delete client link rows (either side)
            cursor.execute(
                "DELETE FROM client_links WHERE client_id_1 = ? OR client_id_2 = ?",
                (client_id, client_id)
            )

            # Delete all entries
            cursor.execute("DELETE FROM entries WHERE client_id = ?", (client_id,))

            # Delete client record
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"Error archiving client {client_id}: {e}")
            return False

        # Delete attachment files from disk only AFTER the commit succeeded.
        # A failure here leaves the DB consistent; leftover files are logged
        # so they can be removed manually.
        try:
            from core.config import ATTACHMENTS_DIR
            client_attachments_dir = ATTACHMENTS_DIR / str(client_id)
            if os.path.exists(client_attachments_dir):
                shutil.rmtree(client_attachments_dir)
        except Exception as e:
            print(f"Warning: failed to delete attachment files for client {client_id}: {e}")

        return True

    def get_deleted_clients(self):
        """Get all archived client records."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM archived_clients
            ORDER BY deleted_at DESC
        """)
        
        columns = [description[0] for description in cursor.description]
        archived = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return archived

    def snapshot_retention_on_inactive(self, client_id, retention_days):
        """
        When changing to Inactive, store the retention_days from the original type.
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE clients 
            SET retention_days = ?, modified_at = ?
            WHERE id = ?
        """, (retention_days, int(time.time()), client_id))
        
        conn.commit()


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