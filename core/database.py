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


class EntryLockedError(Exception):
    """Raised when update_entry is called on a locked entry without
    `allow_locked=True`. Locked clinical entries are immutable by design;
    edits to them must go through the route layer's lock-check + edit
    history flow, which then opts in via `allow_locked=True`.
    See CODE_REVIEW.md M11.
    """
    pass


class Database(SettingsMixin):
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

    def add_client_type(self, type_data: Dict[str, Any]) -> int:
        """Add new client type."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
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
            type_data.get('color_name', ''),
            type_data.get('bubble_color', ''),
            type_data.get('retention_period', 2555),
            type_data.get('is_system', 0),
            type_data.get('is_system_locked', 0),
            now,
            now
        ))
        
        type_id = cursor.lastrowid
        conn.commit()
        
        return type_id


    def get_client_type(self, type_id: int) -> Optional[Dict[str, Any]]:
        """Get client type by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM client_types WHERE id = ?", (type_id,))
        row = cursor.fetchone()
        
        return dict(row) if row else None

    def get_all_client_types(self) -> List[Dict[str, Any]]:
        """Get all client types."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM client_types ORDER BY name")
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]

    def update_client_type(self, type_id: int, type_data: Dict[str, Any]) -> bool:
        """Update client type.

        Refuses to rename a system type (is_system or is_system_locked set):
        the retention sweep identifies the Inactive workflow type by these
        flags, and renaming it must not be possible at the DB layer. Returns
        False in that case, matching how delete_client_type guards deletion.
        See CODE_REVIEW.md M10.
        """
        conn = self.connect()
        cursor = conn.cursor()

        # Guard: never rename a system type
        cursor.execute(
            "SELECT name, is_system, is_system_locked FROM client_types WHERE id = ?",
            (type_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False
        current_name, is_system, is_system_locked = row
        if (is_system or is_system_locked) and type_data['name'] != current_name:
            return False

        now = int(time.time())

        cursor.execute("""
            UPDATE client_types
            SET name = ?, color = ?, color_name = ?, bubble_color = ?,
                retention_period = ?, modified_at = ?
            WHERE id = ?
        """, (
            type_data['name'],
            type_data['color'],
            type_data.get('color_name', ''),
            type_data.get('bubble_color', ''),
            type_data.get('retention_period', 2555),
            now,
            type_id
        ))
        
        conn.commit()
        
        return True


    def delete_client_type(self, type_id: int) -> bool:
        """Delete client type (only if not in use and not system type)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if it's a system type
        cursor.execute("SELECT is_system FROM client_types WHERE id = ?", (type_id,))
        row = cursor.fetchone()
        if row and row[0] == 1:
            return False
        
        # Check if any clients use this type
        cursor.execute("SELECT COUNT(*) FROM clients WHERE type_id = ?", (type_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            return False
        
        # Safe to delete
        cursor.execute("DELETE FROM client_types WHERE id = ?", (type_id,))
        conn.commit()
        
        return True

    # ===== CLIENT OPERATIONS =====
    
    def add_client(self, client_data: Dict[str, Any]) -> int:
        """Add new client."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
        cursor.execute("""
            INSERT INTO clients (
                file_number, first_name, middle_name, last_name, type_id,
                session_offset, created_at, modified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_data['file_number'],
            client_data['first_name'],
            client_data.get('middle_name', ''),
            client_data['last_name'],
            client_data['type_id'],
            client_data.get('session_offset', 0),
            now,
            now
        ))
        
        client_id = cursor.lastrowid
        conn.commit()
        
        return client_id
    
    def file_number_exists(self, file_number: str) -> bool:
        """Check if a file number already exists."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM clients WHERE file_number = ?", (file_number,))
        return cursor.fetchone() is not None

    def get_client(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get client by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        
        return dict(row) if row else None
    
    def get_all_clients(self, type_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all clients, optionally filtered by type."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if type_id:
            cursor.execute(
                "SELECT * FROM clients WHERE type_id = ? AND is_deleted = 0 ORDER BY file_number",
                (type_id,)
            )
        else:
            cursor.execute("SELECT * FROM clients WHERE is_deleted = 0 ORDER BY file_number")
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]

    # Allowed column names for dynamic UPDATE queries (security: prevents SQL injection via column names)
    ALLOWED_CLIENT_COLUMNS = frozenset({
        'file_number', 'first_name', 'middle_name', 'last_name', 'type_id',
        'session_offset', 'retention_days', 'is_deleted', 'modified_at'
    })

    ALLOWED_ENTRY_COLUMNS = frozenset({
        # Common fields
        'client_id', 'class', 'description', 'content',
        # Profile fields
        'email', 'phone', 'home_phone', 'work_phone', 'text_number', 'address',
        'date_of_birth', 'preferred_contact', 'ok_to_leave_message',
        'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
        'referral_source', 'additional_info', 'meeting_link',
        'session_base', 'session_tax_rate', 'session_total', 'default_session_duration',
        'is_minor', 'guardian1_name', 'guardian1_email', 'guardian1_phone', 'guardian1_address',
        'guardian1_pays_percent', 'has_guardian2', 'guardian2_name', 'guardian2_email',
        'guardian2_phone', 'guardian2_address', 'guardian2_pays_percent',
        # Session fields
        'modality', 'format', 'session_number', 'service', 'session_date', 'session_time',
        'duration', 'base_fee', 'tax_rate', 'fee', 'is_consultation', 'is_pro_bono',
        'mood', 'affect', 'risk_assessment',
        # Communication fields
        'comm_recipient', 'comm_type', 'comm_date', 'comm_time',
        # Absence fields
        'absence_date', 'absence_time',
        # Item fields
        'item_date', 'item_time', 'base_price', 'guardian1_amount', 'guardian2_amount',
        # Upload fields
        'upload_date', 'upload_time',
        # Ledger fields
        'ledger_date', 'ledger_type', 'source', 'payee_id', 'category_id',
        'base_amount', 'tax_amount', 'total_amount', 'statement_id',
        # Statement fields
        'statement_total', 'statement_tax_total', 'payment_status', 'payment_notes',
        'date_sent', 'date_paid', 'is_void',
        # Edit tracking
        'edit_history', 'locked', 'locked_at',
        # Redaction
        'is_redacted', 'redacted_at', 'redaction_reason',
        # Metadata
        'modified_at'
    })

    # Columns where '' is semantically wrong — they're INTEGER or REAL in the
    # schema, so SQLite stores '' as TEXT, which sorts above all numbers,
    # breaks BETWEEN/range filters and ORDER BY, and causes IS NULL checks to
    # silently fail (e.g. `if statement_id is not None` returns True for ''
    # entries). add_entry coerces '' → None for these so SQLite stores NULL.
    # See CODE_REVIEW.md H5.
    TYPED_ENTRY_COLUMNS = frozenset({
        # Integer date/time columns
        'session_date', 'comm_date', 'absence_date', 'item_date',
        'upload_date', 'ledger_date', 'date_sent', 'date_paid',
        'locked_at', 'redacted_at', 'date_of_birth',
        # Other integer columns
        'session_number', 'duration', 'default_session_duration',
        'payee_id', 'category_id', 'statement_id',
        'guardian1_pays_percent', 'guardian2_pays_percent',
        # Boolean (stored as INTEGER) columns
        'is_minor', 'has_guardian2', 'is_consultation', 'is_pro_bono',
        'is_void', 'locked', 'is_redacted',
        # Real (money/percentage) columns
        'base_fee', 'tax_rate', 'fee', 'base_price',
        'base_amount', 'tax_amount', 'total_amount',
        'statement_total', 'statement_tax_total',
        'session_base', 'session_tax_rate', 'session_total',
        'guardian1_amount', 'guardian2_amount',
    })

    def update_client(self, client_id: int, client_data: Dict[str, Any]) -> bool:
        """Update client."""
        conn = self.connect()
        cursor = conn.cursor()

        now = int(time.time())

        # Build UPDATE statement dynamically based on provided fields
        set_clauses = []
        values = []

        for key, value in client_data.items():
            if key != 'id':
                # Validate column name against whitelist
                if key not in self.ALLOWED_CLIENT_COLUMNS:
                    raise ValueError(f"Invalid column name: {key}")
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        set_clauses.append("modified_at = ?")
        values.append(now)
        values.append(client_id)
        
        cursor.execute(f"""
            UPDATE clients 
            SET {', '.join(set_clauses)}
            WHERE id = ?
        """, values)
        
        conn.commit()
        
        return True
    
    def search_clients(self, search_term: str) -> List[Dict[str, Any]]:
        """Search clients by name, file number, email, or phone."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Escape LIKE wildcards (% and _) and the escape character itself so
        # a search for e.g. '100%' matches literally instead of acting as a
        # wildcard (CODE_REVIEW.md L14).
        escaped_term = (search_term
                        .replace('\\', '\\\\')
                        .replace('%', '\\%')
                        .replace('_', '\\_'))

        # Search in client table and profile entries
        cursor.execute("""
            SELECT DISTINCT c.* FROM clients c
            LEFT JOIN entries e ON c.id = e.client_id AND e.class = 'profile'
            WHERE c.is_deleted = 0 AND (
                c.file_number LIKE ? ESCAPE '\\' OR
                c.first_name LIKE ? ESCAPE '\\' OR
                c.last_name LIKE ? ESCAPE '\\' OR
                e.email LIKE ? ESCAPE '\\' OR
                e.phone LIKE ? ESCAPE '\\'
            )
            ORDER BY c.file_number
        """, (f'%{escaped_term}%',) * 5)
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_last_session_date(self, client_id: int) -> int:
        """Get timestamp of client's most recent session."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_date FROM entries
            WHERE client_id = ? AND class = 'session'
            ORDER BY session_date DESC
            LIMIT 1
        """, (client_id,))
        
        row = cursor.fetchone()
        
        return row[0] if row else 0
    
    def get_payment_status(self, client_id: int) -> str:
        """Get client's payment status based on statement_portions.
        
        Returns:
            'paid' (green) - No outstanding portions, or all paid/written_off
            'pending' (yellow) - Has sent/partial portions, none overdue
            'overdue' (red) - Has sent portions 30+ days old
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all non-paid, non-written-off portions for this client
        cursor.execute("""
            SELECT status, date_sent 
            FROM statement_portions 
            WHERE client_id = ? AND status NOT IN ('paid', 'written_off')
        """, (client_id,))
        
        portions = cursor.fetchall()
        
        # No outstanding portions = paid/current
        if not portions:
            return 'paid'
        
        # Check for overdue (sent more than 30 days ago)
        thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())
        
        for portion in portions:
            status = portion['status']
            date_sent = portion['date_sent']
            
            # If sent and date_sent is 30+ days ago, it's overdue
            if status in ('sent', 'partial') and date_sent and date_sent < thirty_days_ago:
                return 'overdue'
        
        # Has outstanding portions but none overdue = pending
        return 'pending'


    def count_pending_invoices(self) -> int:
        """Count statement portions that aren't fully paid or written off.
        
        Returns count of portions with status not in ('paid', 'written_off')
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM statement_portions 
            WHERE status NOT IN ('paid', 'written_off')
        """)
        
        return cursor.fetchone()[0]
    
    def get_profile_entry(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get client's profile entry."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM entries
            WHERE client_id = ? AND class = 'profile'
            LIMIT 1
        """, (client_id,))
        
        row = cursor.fetchone()
        
        return dict(row) if row else None
    
    # ===== EDIT HISTORY SYSTEM ======
    
    def lock_entry(self, entry_id):
        """Lock an entry after first save, making it immutable."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE entries 
            SET locked = 1, locked_at = ?
            WHERE id = ?
        """, (int(time.time()), entry_id))
        
        conn.commit()

    def is_entry_locked(self, entry_id):
        """Check if an entry is locked."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT locked FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        
        return result[0] == 1 if result else False

    def add_to_edit_history(self, entry_id, change_description):
        """Add an edit to the entry's history."""
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get current history
        cursor.execute("SELECT edit_history FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        
        history = json.loads(result[0]) if result and result[0] else []
        
        # Add new edit
        history.append({
            'timestamp': int(time.time()),
            'description': change_description
        })
        
        # Save back
        cursor.execute("""
            UPDATE entries 
            SET edit_history = ?, modified_at = ?
            WHERE id = ?
        """, (json.dumps(history), int(time.time()), entry_id))
        
        conn.commit()

    def get_edit_history(self, entry_id):
        """Get the edit history for an entry."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT edit_history FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            return json.loads(result[0])
        return []
    
    def redact_entry(self, entry_id: int, reason: str) -> bool:
        """Redact an entry, clearing all content fields.
        
        This is for privacy incidents where confidential information was entered
        in the wrong client file. The redaction clears all free-text content
        but preserves structural metadata (dates, fees, session numbers) and
        does NOT add to edit_history (to avoid capturing confidential content).
        
        Args:
            entry_id: The entry to redact
            reason: Required explanation for the redaction
            
        Returns:
            True if successful, False if entry not found or not locked
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        # Verify entry exists, is locked, and is not billed
        cursor.execute("SELECT class, locked, statement_id FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        
        if not result:
            return False
        
        entry_class, is_locked, statement_id = result
        
        # Only allow redaction of locked entries (Session, Communication, Absence, Item)
        if not is_locked or entry_class not in ('session', 'communication', 'absence', 'item'):
            return False
        
        # Cannot redact billed entries
        if statement_id is not None:
            return False
        
        # Clear all free-text content fields, time fields, and fee fields
        # These are the fields that could contain confidential information
        # Fee fields cleared so redacted entries can't be invoiced
        redaction_fields = {
            'description': '[REDACTED]',
            'content': None,
            'mood': None,
            'affect': None,
            'risk_assessment': None,
            'comm_recipient': None,
            'additional_info': None,
            'session_number': None,  # Clear session number so it doesn't affect numbering
            'duration': None,  # Clear duration
            'format': None,  # Clear format (Individual, Couples, etc.)
            # Clear time fields - session time could be identifying
            'session_time': None,
            'absence_time': None,
            'comm_time': None,
            'item_time': None,
            'upload_time': None,
            # Clear fee fields so entry can't be invoiced
            'base_fee': None,
            'tax_rate': None,
            'fee': None,
            'base_price': None,  # For Item entries
            # Mark as redacted
            'is_redacted': 1,
            'redacted_at': int(time.time()),
            'redaction_reason': reason,
            'modified_at': int(time.time())
        }
        
        # Build UPDATE statement
        set_clauses = []
        values = []
        
        for key, value in redaction_fields.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        
        values.append(entry_id)
        
        cursor.execute(f"""
            UPDATE entries 
            SET {', '.join(set_clauses)}
            WHERE id = ?
        """, values)
        
        conn.commit()
        return True
    
    # ===== CLIENT LINKING OPERATIONS =====
    
    def create_link_group(self, client_ids: List[int], format: str, session_duration: int, member_fees: Dict[int, Dict[str, float]]) -> int:
        """Create a new link group.
        
        Args:
            client_ids: List of client IDs to link
            format: Session format ('couples', 'family', 'group')
            session_duration: Session duration in minutes for this group
            member_fees: Dict mapping client_id to {base_fee, tax_rate, total_fee}
        
        Returns:
            Link group ID
        """
        conn = self.connect()
        cursor = conn.cursor()
        now = int(time.time())
        
        # Check for duplicate group - simpler approach
        # Get all groups and their members in one query
        cursor.execute("""
            SELECT group_id, GROUP_CONCAT(client_id_1) as members
            FROM client_links
            GROUP BY group_id
        """)
        
        sorted_new_ids = ','.join(map(str, sorted(client_ids)))
        
        for row in cursor.fetchall():
            existing_members = ','.join(map(str, sorted(map(int, row[1].split(',')))))
            if sorted_new_ids == existing_members:
                raise ValueError("Link duplicates an existing arrangement. Please edit or delete the existing link.")
        
        # Check for format conflicts - client can only be in one group of each format
        cursor.execute("""
            SELECT cl.client_id_1, lg.format, c.first_name, c.last_name
            FROM client_links cl
            JOIN link_groups lg ON cl.group_id = lg.id
            JOIN clients c ON cl.client_id_1 = c.id
            WHERE cl.client_id_1 IN ({}) AND lg.format = ?
        """.format(','.join('?' * len(client_ids))), (*client_ids, format))
        
        conflict = cursor.fetchone()
        if conflict:
            raise ValueError(f"{conflict[2]} {conflict[3]} is already in a {format} link group. A client can only belong to one link group of each type.")
        
        # Multi-statement write: roll back on any failure so a partial group
        # can't be committed later by unrelated code on this thread-local
        # connection (CODE_REVIEW.md H8).
        try:
            # Create link group with format and duration
            cursor.execute("""
                INSERT INTO link_groups (format, session_duration, created_at)
                VALUES (?, ?, ?)
            """, (format, session_duration, now))

            group_id = cursor.lastrowid

            # Create a row for each member (self-referential)
            for client_id in client_ids:
                # Get fees for this member
                fees = member_fees.get(str(client_id), {})  # JSON keys are strings
                base_fee = fees.get('base_fee', 0)
                tax_rate = fees.get('tax_rate', 0)
                total_fee = fees.get('total_fee', 0)

                cursor.execute("""
                    INSERT INTO client_links
                    (client_id_1, client_id_2, group_id, member_base_fee, member_tax_rate, member_total_fee, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (client_id, client_id, group_id, base_fee, tax_rate, total_fee, now))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return group_id

    def get_link_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get link group with all member details and fees.
        
        Args:
            group_id: Link group ID
        
        Returns:
            Dict with group info and members list (including fees)
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get link group
        cursor.execute("SELECT * FROM link_groups WHERE id = ?", (group_id,))
        group_row = cursor.fetchone()
        
        if not group_row:
            return None
        
        group = dict(group_row)

        # Get all members (client details + fees) in one JOIN query
        # (CODE_REVIEW.md L5: was one query per member)
        cursor.execute("""
            SELECT c.*, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee
            FROM client_links cl
            JOIN clients c ON c.id = cl.client_id_1
            WHERE cl.group_id = ?
            ORDER BY cl.id
        """, (group_id,))

        group['members'] = [dict(row) for row in cursor.fetchall()]

        return group
    
    def get_all_link_groups(self) -> List[Dict[str, Any]]:
        """Get all link groups with member details and fees.
        
        Returns:
            List of link groups with members (including fees)
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM link_groups ORDER BY created_at DESC")
        groups = [dict(row) for row in cursor.fetchall()]

        # Fetch all members (client details + fees) for all groups in one
        # JOIN query and bucket by group (CODE_REVIEW.md L5: was 1 + N×M
        # queries — one per group plus one per member)
        cursor.execute("""
            SELECT c.*, cl.member_base_fee, cl.member_tax_rate, cl.member_total_fee,
                   cl.group_id AS link_group_id
            FROM client_links cl
            JOIN clients c ON c.id = cl.client_id_1
            ORDER BY cl.id
        """)

        members_by_group = {}
        for row in cursor.fetchall():
            member = dict(row)
            link_group_id = member.pop('link_group_id')
            members_by_group.setdefault(link_group_id, []).append(member)

        for group in groups:
            group['members'] = members_by_group.get(group['id'], [])

        return groups
    
    def get_linked_clients(self, client_id: int) -> List[Dict[str, Any]]:
        """Get all clients linked to this client.
        
        Args:
            client_id: Client ID to find links for
        
        Returns:
            List of linked client dicts
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find which group(s) this client belongs to
        cursor.execute("""
            SELECT DISTINCT group_id FROM client_links
            WHERE client_id_1 = ?
        """, (client_id,))
        
        group_ids = [row['group_id'] for row in cursor.fetchall()]
        
        if not group_ids:
            return []
        
        # Get all other clients in those groups
        linked_clients = []
        for group_id in group_ids:
            cursor.execute("""
                SELECT client_id_1 as client_id FROM client_links
                WHERE group_id = ? AND client_id_1 != ?
            """, (group_id, client_id))
            
            for row in cursor.fetchall():
                other_client_id = row['client_id']
                cursor.execute("SELECT * FROM clients WHERE id = ?", (other_client_id,))
                client_row = cursor.fetchone()
                if client_row:
                    linked_clients.append(dict(client_row))
        
        return linked_clients
    
    def is_client_linked(self, client_id: int) -> bool:
        """Check if a client is linked to any other clients.
        
        Args:
            client_id: Client ID to check
        
        Returns:
            True if client is linked to others
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM client_links
            WHERE client_id_1 = ? OR client_id_2 = ?
        """, (client_id, client_id))
        
        count = cursor.fetchone()[0]
        
        return count > 0
    
    def update_link_group(self, group_id: int, client_ids: List[int], format: str, session_duration: int, member_fees: Dict[int, Dict[str, float]]) -> bool:
        """Update an existing link group.
        
        Args:
            group_id: Link group ID
            client_ids: Updated list of client IDs
            format: Updated session format
            session_duration: Updated session duration in minutes
            member_fees: Dict mapping client_id to {base_fee, tax_rate, total_fee}
        
        Returns:
            True if successful
        """
        conn = self.connect()
        cursor = conn.cursor()
        now = int(time.time())
        
        # Check for format conflicts - client can only be in one group of each format
        # Exclude current group from check
        cursor.execute("""
            SELECT cl.client_id_1, lg.format, c.first_name, c.last_name
            FROM client_links cl
            JOIN link_groups lg ON cl.group_id = lg.id
            JOIN clients c ON cl.client_id_1 = c.id
            WHERE cl.client_id_1 IN ({}) AND lg.format = ? AND cl.group_id != ?
        """.format(','.join('?' * len(client_ids))), (*client_ids, format, group_id))
        
        conflict = cursor.fetchone()
        if conflict:
            raise ValueError(f"{conflict[2]} {conflict[3]} is already in a {format} link group. A client can only belong to one link group of each type.")
        
        # Multi-statement write: roll back on any failure so half-applied
        # changes (e.g. links deleted but not recreated) can't be committed
        # later by unrelated code (CODE_REVIEW.md H8).
        try:
            # Update link group format and duration
            cursor.execute("""
                UPDATE link_groups
                SET format = ?, session_duration = ?
                WHERE id = ?
            """, (format, session_duration, group_id))

            # Delete existing links for this group
            cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))

            # Recreate links with new client list and fees
            for client_id in client_ids:
                fees = member_fees.get(str(client_id), {})
                base_fee = fees.get('base_fee', 0)
                tax_rate = fees.get('tax_rate', 0)
                total_fee = fees.get('total_fee', 0)

                cursor.execute("""
                    INSERT INTO client_links
                    (client_id_1, client_id_2, group_id, member_base_fee, member_tax_rate, member_total_fee, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (client_id, client_id, group_id, base_fee, tax_rate, total_fee, now))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return True
    
    def delete_link_group(self, group_id: int) -> bool:
        """Delete a link group and all its member links.
        
        Args:
            group_id: Link group ID
        
        Returns:
            True if successful
        """
        conn = self.connect()
        cursor = conn.cursor()

        # Multi-statement write: roll back on any failure (CODE_REVIEW.md H8)
        try:
            # Delete all member links
            cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))

            # Delete the group itself
            cursor.execute("DELETE FROM link_groups WHERE id = ?", (group_id,))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return True
    
    # ===== ENTRY OPERATIONS =====
    
    def add_entry(self, entry_data: Dict[str, Any]) -> int:
        """Add new entry."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
        # Build SQL dynamically based on which fields are provided
        fields = ['client_id', 'class', 'created_at', 'modified_at']
        values = [entry_data['client_id'], entry_data['class'], now, now]
        
        optional_fields = [
            'description', 'content', 'email', 'phone', 'home_phone', 'work_phone',
            'text_number', 'address', 'date_of_birth', 'preferred_contact',
            'ok_to_leave_message', 'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship', 'referral_source', 'additional_info',
            'modality', 'format', 'session_number', 'service', 'session_date', 'session_time',
            'duration', 'base_fee', 'tax_rate', 'fee', 'is_consultation', 'is_pro_bono',  # ← ADDED base_fee, tax_rate, is_pro_bono here
            'mood', 'affect', 'risk_assessment',
            'comm_recipient', 'comm_type', 'comm_date', 'comm_time',
            'absence_date', 'absence_time',
            'item_date', 'item_time', 'base_price',  # ← removed tax_rate from here (it's now above)
            'upload_date', 'upload_time',
            'statement_total', 'statement_tax_total', 'payment_status',
            'payment_notes', 'date_sent', 'date_paid', 'is_void', 'edit_history',
            'locked', 'locked_at',
            # Session fee fields
            'session_base', 'session_tax_rate', 'session_total', 'default_session_duration',
            # Guardian fields
            'is_minor', 'guardian1_name', 'guardian1_email', 'guardian1_phone',
            'guardian1_address', 'guardian1_pays_percent', 'has_guardian2',
            'guardian2_name', 'guardian2_email', 'guardian2_phone',
            'guardian2_address', 'guardian2_pays_percent',
            # Item guardian split fields
            'guardian1_amount', 'guardian2_amount',
            # Ledger fields
            'ledger_date', 'ledger_type', 'source', 'payee_id', 'category_id',
            'payee_name', 'category_name',  # Text fields for ledger entries
            'base_amount', 'tax_amount', 'total_amount', 'statement_id'
        ]
        
        for field in optional_fields:
            if field in entry_data:
                fields.append(field)
                value = entry_data[field]
                # Preserve None so SQLite stores NULL (was: coerced None → '',
                # which produced TEXT '' in INTEGER/REAL columns and broke range
                # filters, ORDER BY, and `IS NULL` checks downstream).
                # For TYPED_ENTRY_COLUMNS, also coerce '' → None so a stray
                # empty string from a form post can't pollute a typed column.
                if value == '' and field in self.TYPED_ENTRY_COLUMNS:
                    value = None
                values.append(value)
        
        placeholders = ', '.join(['?' for _ in values])
        field_names = ', '.join(fields)
        
        cursor.execute(f"""
            INSERT INTO entries ({field_names})
            VALUES ({placeholders})
        """, values)
        
        entry_id = cursor.lastrowid
        conn.commit()
        
        return entry_id
    
    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Get entry by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        
        return dict(row) if row else None
    
    def get_client_entries(self, client_id: int, entry_class: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all entries for a client, optionally filtered by class.
        
        Includes attachment_count via JOIN for performance.
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if entry_class:
            cursor.execute("""
                SELECT entries.*, COUNT(attachments.id) as attachment_count
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                WHERE entries.client_id = ? AND entries.class = ?
                GROUP BY entries.id
                ORDER BY entries.created_at DESC
            """, (client_id, entry_class))
        else:
            cursor.execute("""
                SELECT entries.*, COUNT(attachments.id) as attachment_count
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                WHERE entries.client_id = ?
                GROUP BY entries.id
                ORDER BY entries.created_at DESC
            """, (client_id,))
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def update_entry(self, entry_id: int, entry_data: Dict[str, Any],
                     allow_locked: bool = False) -> bool:
        """Update entry. Callers are responsible for edit-history logging.

        Raises EntryLockedError if the target entry is locked unless
        `allow_locked=True`. Pass `allow_locked=True` after you've checked
        the lock state at the route layer and recorded the change to
        edit_history (or in legitimate system-invariant operations such
        as renumber_sessions). See CODE_REVIEW.md M11.
        """
        conn = self.connect()
        cursor = conn.cursor()

        if not allow_locked:
            cursor.execute("SELECT locked FROM entries WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            if row and row[0]:
                raise EntryLockedError(
                    f"Entry {entry_id} is locked; pass allow_locked=True "
                    f"after handling edit-history logging at the route layer."
                )

        # Build UPDATE statement dynamically
        set_clauses = []
        values = []

        for key, value in entry_data.items():
            if key != 'id':
                # Validate column name against whitelist
                if key not in self.ALLOWED_ENTRY_COLUMNS:
                    raise ValueError(f"Invalid column name: {key}")
                # Coerce '' → None for typed columns (see TYPED_ENTRY_COLUMNS comment).
                if value == '' and key in self.TYPED_ENTRY_COLUMNS:
                    value = None
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        set_clauses.append("modified_at = ?")
        values.append(int(time.time()))
        values.append(entry_id)
        
        cursor.execute(f"""
            UPDATE entries 
            SET {', '.join(set_clauses)}
            WHERE id = ?
        """, values)
        
        conn.commit()
        
        return True
    
    def get_attachments(self, entry_id):
        """Get all attachments for an entry."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM attachments 
            WHERE entry_id = ? 
            ORDER BY uploaded_at DESC
        """, (entry_id,))
        
        attachments = [dict(row) for row in cursor.fetchall()]
        
        return attachments
        
    # ===== SETTINGS OPERATIONS =====
    # Extracted to core/db/settings.py (SettingsMixin).

    # EdgeCase Ledger - Database Methods

    # ============================================================================
    # PAYEE OPERATIONS
    # ============================================================================

    def add_payee(self, name: str) -> int:
        """Add a new payee to the payees table."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO payees (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        payee_id = cursor.lastrowid
        conn.commit()
        return payee_id

    def get_payee(self, payee_id: int) -> dict:
        """Get a single payee by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees WHERE id = ?", (payee_id,))
        payee = cursor.fetchone()
        
        return dict(payee) if payee else None

    def get_all_payees(self) -> list:
        """Get all payees ordered by name."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees ORDER BY name ASC")
        payees = [dict(row) for row in cursor.fetchall()]
        
        return payees

    def update_payee(self, payee_id: int, name: str) -> bool:
        """Update a payee's name."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE payees
            SET name = ?
            WHERE id = ?
        """, (name, payee_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        return success

    def delete_payee(self, payee_id: int) -> bool:
        """Delete a payee (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this payee
        cursor.execute("SELECT COUNT(*) FROM entries WHERE payee_id = ?", (payee_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM payees WHERE id = ?", (payee_id,))
        success = cursor.rowcount > 0
        conn.commit()
        return success


    # ============================================================================
    # EXPENSE CATEGORY OPERATIONS
    # ============================================================================

    def add_expense_category(self, name: str) -> int:
        """Add a new expense category."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO expense_categories (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        category_id = cursor.lastrowid
        conn.commit()
        return category_id

    def get_expense_category(self, category_id: int) -> dict:
        """Get a single expense category by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories WHERE id = ?", (category_id,))
        category = cursor.fetchone()
        
        return dict(category) if category else None

    def get_all_expense_categories(self) -> list:
        """Get all expense categories ordered by name."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories ORDER BY name ASC")
        categories = [dict(row) for row in cursor.fetchall()]
        
        return categories

    def get_expense_category_by_name(self, name: str) -> dict:
        """Get an expense category by name (case-insensitive)."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories WHERE LOWER(name) = LOWER(?)", (name,))
        category = cursor.fetchone()
        
        return dict(category) if category else None

    def get_distinct_payee_names(self) -> list:
        """Get payee names from payees table for autocomplete."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM payees
            ORDER BY name ASC
        """)
        
        return [row[0] for row in cursor.fetchall()]

    def add_payee_if_new(self, name: str) -> int:
        """Add payee to table if it doesn't exist. Returns payee ID."""
        if not name:
            return None
        conn = self.connect()
        cursor = conn.cursor()
        # Check if exists first
        cursor.execute("SELECT id FROM payees WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return row[0]
        # Insert new
        cursor.execute("INSERT INTO payees (name, created_at) VALUES (?, ?)",
                       (name, int(time.time())))
        conn.commit()
        return cursor.lastrowid

    def get_distinct_payor_sources(self) -> list:
        """Get payor names from income_payors table for autocomplete."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM income_payors
            ORDER BY name ASC
        """)
        
        return [row[0] for row in cursor.fetchall()]

    def add_income_payor_if_new(self, name: str) -> None:
        """Add payor to income_payors table if it doesn't exist."""
        if not name:
            return
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO income_payors (name, created_at) VALUES (?, ?)",
                       (name, int(time.time())))
        conn.commit()

    def delete_income_payor(self, name: str) -> bool:
        """Delete a payor from income_payors table."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM income_payors WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

    def update_expense_category(self, category_id: int, name: str) -> bool:
        """Update an expense category's name."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE expense_categories
            SET name = ?
            WHERE id = ?
        """, (name, category_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        return success

    def delete_expense_category(self, category_id: int) -> bool:
        """Delete an expense category (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this category
        cursor.execute("SELECT COUNT(*) FROM entries WHERE category_id = ?", (category_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM expense_categories WHERE id = ?", (category_id,))
        success = cursor.rowcount > 0
        conn.commit()
        return success


    # ============================================================================
    # LEDGER ENTRY OPERATIONS
    # ============================================================================

    def get_all_ledger_entries(self, ledger_type: str = None) -> list:
        """
        Get all ledger entries (income and/or expense).
        
        Includes attachment_count via JOIN for performance.
        Joins payee and category names for display.
        
        Args:
            ledger_type: Optional filter - 'income' or 'expense' or None for both
        
        Returns:
            List of ledger entries sorted by date (newest first), then created_at
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT entries.*, 
                       COUNT(attachments.id) as attachment_count,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type = ?
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """, (ledger_type,))
        else:
            cursor.execute("""
                SELECT entries.*, 
                       COUNT(attachments.id) as attachment_count,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type IN ('income', 'expense')
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """)
        
        entries = [dict(row) for row in cursor.fetchall()]
        
        return entries

    def get_ledger_entry(self, entry_id: int) -> dict:
        """Get a single ledger entry (same as get_entry, just for clarity)."""
        return self.get_entry(entry_id)

    def get_ledger_entries_by_date_range(self, start_date: int, end_date: int, 
                                        ledger_type: str = None) -> list:
        """
        Get ledger entries within a date range.
        
        Args:
            start_date: Unix timestamp for start of range
            end_date: Unix timestamp for end of range
            ledger_type: Optional filter - 'income' or 'expense' or None for both
        
        Returns:
            List of ledger entries in date range
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT entries.*,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type = ?
                AND entries.ledger_date BETWEEN ? AND ?
                ORDER BY entries.ledger_date ASC, entries.created_at ASC
            """, (ledger_type, start_date, end_date))
        else:
            cursor.execute("""
                SELECT entries.*,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type IN ('income', 'expense')
                AND entries.ledger_date BETWEEN ? AND ?
                ORDER BY entries.ledger_date ASC, entries.created_at ASC
            """, (start_date, end_date))
        
        entries = [dict(row) for row in cursor.fetchall()]
        
        return entries

    def get_ledger_totals(self, start_date: int = None, end_date: int = None) -> dict:
        """
        Calculate total income, expenses, and net for a date range.
        
        Args:
            start_date: Optional Unix timestamp for start (None = all time)
            end_date: Optional Unix timestamp for end (None = all time)
        
        Returns:
            Dict with: total_income, total_expenses, total_tax_collected, 
                    total_tax_paid, net_income, net_tax_owing
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        # Build WHERE clause for date range
        date_filter = ""
        params = []
        if start_date and end_date:
            date_filter = "AND ledger_date BETWEEN ? AND ?"
            params = [start_date, end_date]
        elif start_date:
            date_filter = "AND ledger_date >= ?"
            params = [start_date]
        elif end_date:
            date_filter = "AND ledger_date <= ?"
            params = [end_date]
        
        # Total income and tax collected
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(total_amount), 0) as total_income,
                COALESCE(SUM(tax_amount), 0) as total_tax_collected
            FROM entries 
            WHERE ledger_type = 'income' {date_filter}
        """, params)
        income_row = cursor.fetchone()
        
        # Total expenses and tax paid
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(total_amount), 0) as total_expenses,
                COALESCE(SUM(tax_amount), 0) as total_tax_paid
            FROM entries 
            WHERE ledger_type = 'expense' {date_filter}
        """, params)
        expense_row = cursor.fetchone()
        
        
        total_income = income_row[0]
        total_tax_collected = income_row[1]
        total_expenses = expense_row[0]
        total_tax_paid = expense_row[1]
        
        return {
            'total_income': total_income,
            'total_expenses': total_expenses,
            'total_tax_collected': total_tax_collected,
            'total_tax_paid': total_tax_paid,
            'net_income': total_income - total_expenses,
            'net_tax_owing': total_tax_collected - total_tax_paid
        }
        
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