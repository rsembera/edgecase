"""
EdgeCase Database Module
Handles SQLite database operations.
(SQLCipher encryption will be added in Phase 2)
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import time

class Database:
    """
    Database interface for EdgeCase.
    Manages all SQLite operations using Entry-based architecture.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()
    
    def connect(self):
        """Create and return database connection."""
        return sqlite3.connect(str(self.db_path))
    
    def _initialize_schema(self):
        """Create tables if they don't exist."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Client Types table (customizable)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT NOT NULL,
                file_number_style TEXT NOT NULL,
                file_number_prefix TEXT,
                file_number_suffix TEXT,
                file_number_counter INTEGER DEFAULT 0,
                session_fee REAL,
                session_duration INTEGER,
                retention_period INTEGER,
                is_system INTEGER DEFAULT 0,
                service_description TEXT,
                is_system_locked INTEGER DEFAULT 0,
                base_price REAL,
                tax_rate REAL,
                created_at INTEGER NOT NULL,
                modified_at INTEGER NOT NULL
            )
        """)
        
        # Clients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
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
            )
        """)
        
        # Entries table (unified for all entry types)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
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
                
                -- Session-specific fields
                modality TEXT,
                format TEXT,
                session_number INTEGER,
                service TEXT,
                session_date INTEGER,
                session_time TEXT,
                duration INTEGER,
                fee REAL,
                is_consultation INTEGER DEFAULT 0,
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
                tax_rate REAL,
                
                -- Statement-specific fields
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
                
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Link Groups (for couples/family therapy billing arrangement)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS link_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                billing_type TEXT NOT NULL,
                principal_payer_id INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (principal_payer_id) REFERENCES clients(id)
            )
        """)
        
        # Client Linking (for couples/family therapy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id_1 INTEGER NOT NULL,
                client_id_2 INTEGER NOT NULL,
                group_id INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (client_id_1) REFERENCES clients(id),
                FOREIGN KEY (client_id_2) REFERENCES clients(id),
                FOREIGN KEY (group_id) REFERENCES link_groups(id),
                UNIQUE(client_id_1, client_id_2)
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
        
        conn.commit()
        
        # Run migrations to add any missing columns
        self._run_migrations()
        
        # Create default client types if they don't exist
        self._create_default_types()
    
    def _run_migrations(self):
        """Run database migrations to add missing columns"""
        conn = self.connect()
        cursor = conn.cursor()
        
        # ============================================
        # EXISTING MIGRATIONS (from Week 2)
        # ============================================
        
        # Migration: Add color_name and bubble_color to client_types
        cursor.execute("PRAGMA table_info(client_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'color_name' not in columns:
            print("Running migration: Add color_name to client_types")
            cursor.execute("ALTER TABLE client_types ADD COLUMN color_name TEXT")
            
            # Set default color names based on existing colors
            cursor.execute("UPDATE client_types SET color_name = 'Soft Teal' WHERE color = '#9FCFC0'")
            cursor.execute("UPDATE client_types SET color_name = 'Mint Green' WHERE color = '#A7D4A4'")
            cursor.execute("UPDATE client_types SET color_name = 'Sage' WHERE color = '#B8C5A8'")
            cursor.execute("UPDATE client_types SET color_name = 'Lavender' WHERE color = '#C8B8D9'")
            cursor.execute("UPDATE client_types SET color_name = 'Dusty Rose' WHERE color = '#D4A5A5'")
            cursor.execute("UPDATE client_types SET color_name = 'Peach' WHERE color = '#E8C4A8'")
            cursor.execute("UPDATE client_types SET color_name = 'Powder Blue' WHERE color = '#A8C8D9'")
            cursor.execute("UPDATE client_types SET color_name = 'Soft Gray' WHERE color = '#B8B8C5'")
            cursor.execute("UPDATE client_types SET color_name = 'Warm Amber' WHERE color = '#D9C8A5'")
            
            # Default to Soft Teal for any other colors
            cursor.execute("UPDATE client_types SET color_name = 'Soft Teal' WHERE color_name IS NULL")
            conn.commit()
        
        if 'bubble_color' not in columns:
            print("Running migration: Add bubble_color to client_types")
            cursor.execute("ALTER TABLE client_types ADD COLUMN bubble_color TEXT")
            
            # Set bubble colors based on existing colors
            cursor.execute("UPDATE client_types SET bubble_color = '#E6F5F1' WHERE color = '#9FCFC0'")
            cursor.execute("UPDATE client_types SET bubble_color = '#E8F5E7' WHERE color = '#A7D4A4'")
            cursor.execute("UPDATE client_types SET bubble_color = '#EEF2E9' WHERE color = '#B8C5A8'")
            cursor.execute("UPDATE client_types SET bubble_color = '#F1EDF5' WHERE color = '#C8B8D9'")
            cursor.execute("UPDATE client_types SET bubble_color = '#F5E9E9' WHERE color = '#D4A5A5'")
            cursor.execute("UPDATE client_types SET bubble_color = '#F9F0E8' WHERE color = '#E8C4A8'")
            cursor.execute("UPDATE client_types SET bubble_color = '#E8F0F5' WHERE color = '#A8C8D9'")
            cursor.execute("UPDATE client_types SET bubble_color = '#EEEEEF' WHERE color = '#B8B8C5'")
            cursor.execute("UPDATE client_types SET bubble_color = '#F5F0E9' WHERE color = '#D9C8A5'")
            
            # Default to Soft Teal bubble for any other colors
            cursor.execute("UPDATE client_types SET bubble_color = '#E6F5F1' WHERE bubble_color IS NULL")
            conn.commit()
        
        # ============================================
        # FEE OVERRIDE MIGRATIONS (Week 3, Session 1)
        # ============================================
        
        # Re-fetch columns after existing migrations
        cursor.execute("PRAGMA table_info(client_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Migration: Add fee breakdown to client_types
        if 'session_base_price' not in columns:
            print("Running migration: Add session_base_price to client_types")
            cursor.execute("ALTER TABLE client_types ADD COLUMN session_base_price REAL")
            
            # Migrate existing session_fee to base (assume 0% tax initially)
            cursor.execute("UPDATE client_types SET session_base_price = session_fee WHERE session_fee IS NOT NULL")
            conn.commit()
        
        if 'session_tax_rate' not in columns:
            print("Running migration: Add session_tax_rate to client_types")
            cursor.execute("ALTER TABLE client_types ADD COLUMN session_tax_rate REAL DEFAULT 0.0")
            conn.commit()
        
        # Migration: Add fee override to entries (for Profile class)
        cursor.execute("PRAGMA table_info(entries)")
        entries_columns = [col[1] for col in cursor.fetchall()]
        
        if 'fee_override_base' not in entries_columns:
            print("Running migration: Add fee_override_base to entries")
            cursor.execute("ALTER TABLE entries ADD COLUMN fee_override_base REAL")
            conn.commit()
        
        if 'fee_override_tax_rate' not in entries_columns:
            print("Running migration: Add fee_override_tax_rate to entries")
            cursor.execute("ALTER TABLE entries ADD COLUMN fee_override_tax_rate REAL")
            conn.commit()
        
        if 'fee_override_total' not in entries_columns:
            print("Running migration: Add fee_override_total to entries")
            cursor.execute("ALTER TABLE entries ADD COLUMN fee_override_total REAL")
            conn.commit()
        
        # ============================================
        # GUARDIAN/BILLING MIGRATIONS (Week 3, Session 1)
        # ============================================
        
        # Add guardian/billing fields to entries table
        guardian_columns = {
            'is_minor': 'INTEGER DEFAULT 0',
            'guardian1_name': 'TEXT',
            'guardian1_email': 'TEXT',
            'guardian1_phone': 'TEXT',
            'guardian1_address': 'TEXT',
            'guardian1_pays_percent': 'INTEGER DEFAULT 100',
            'has_guardian2': 'INTEGER DEFAULT 0',
            'guardian2_name': 'TEXT',
            'guardian2_email': 'TEXT',
            'guardian2_phone': 'TEXT',
            'guardian2_address': 'TEXT',
            'guardian2_pays_percent': 'INTEGER DEFAULT 0'
        }
        
        for column, data_type in guardian_columns.items():
            if column not in entries_columns:
                print(f"Running migration: Add {column} to entries")
                cursor.execute(f"ALTER TABLE entries ADD COLUMN {column} {data_type}")
                conn.commit()
                
        # ============================================
        # SESSION FEE BREAKDOWN MIGRATION (Week 3, Session 1 Part 2)
        # ============================================

        # Add base_fee and tax_rate to entries for Sessions
        # (Same pattern as Items, but for Sessions)

        if 'base_fee' not in entries_columns:
            print("Running migration: Add base_fee to entries")
            cursor.execute("ALTER TABLE entries ADD COLUMN base_fee REAL")
            conn.commit()

        if 'tax_rate' not in entries_columns:
            print("Running migration: Add tax_rate to entries")
            cursor.execute("ALTER TABLE entries ADD COLUMN tax_rate REAL")
            conn.commit()
        
        # ============================================
        # CLEAN UP CLIENT_TYPES TABLE (Week 3, Session 1)
        # ============================================
        
        # Remove file number columns from client_types (they're global settings now)
        # SQLite doesn't support DROP COLUMN, so we recreate the table
        
        cursor.execute("PRAGMA table_info(client_types)")
        client_types_columns = [col[1] for col in cursor.fetchall()]
        
        if 'file_number_style' in client_types_columns:
            print("Running migration: Remove file number columns from client_types")
            
            # Create new table without file number columns
            cursor.execute("""
                CREATE TABLE client_types_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT NOT NULL,
                    color_name TEXT,
                    bubble_color TEXT,
                    session_fee REAL,
                    session_base_price REAL,
                    session_tax_rate REAL DEFAULT 0.0,
                    session_duration INTEGER,
                    retention_period INTEGER,
                    is_system INTEGER DEFAULT 0,
                    service_description TEXT,
                    is_system_locked INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    modified_at INTEGER NOT NULL
                )
            """)
            
            # Copy data from old table (excluding file number columns)
            cursor.execute("""
                INSERT INTO client_types_new 
                (id, name, color, color_name, bubble_color, session_fee, session_base_price, 
                 session_tax_rate, session_duration, retention_period, is_system, 
                 service_description, is_system_locked, created_at, modified_at)
                SELECT id, name, color, 
                       COALESCE(color_name, 'Soft Teal'), 
                       COALESCE(bubble_color, '#E6F5F1'), 
                       session_fee, session_base_price, 
                       COALESCE(session_tax_rate, 0.0), 
                       session_duration, retention_period, is_system,
                       service_description, is_system_locked, created_at, modified_at
                FROM client_types
            """)
            
            # Drop old table and rename new one
            cursor.execute("DROP TABLE client_types")
            cursor.execute("ALTER TABLE client_types_new RENAME TO client_types")
            
            conn.commit()
            print("Migration complete: File number columns removed from client_types")
        
        # ============================================
        # LINK GROUP SIMPLIFICATION NOTE
        # ============================================
        
        # Check if link_groups has old billing columns
        cursor.execute("PRAGMA table_info(link_groups)")
        link_columns = [col[1] for col in cursor.fetchall()]
        
        # Note: SQLite doesn't support DROP COLUMN easily
        # We'll just leave these columns in place (they won't be used after Session 6)
        # Future: Could create new table and migrate data if needed
        
        if 'billing_type' in link_columns or 'principal_payer_id' in link_columns:
            print("Note: link_groups still has old billing columns (will be unused after Session 6, safe to ignore)")
        
        print("All migrations complete")
        conn.close()

    def _create_default_types(self):
        """Create default client types on first run.
        
        Creates 5 types:
        - Inactive (locked, workflow state)
        - Deleted (locked, workflow state)  
        - Active (editable, default therapy type)
        - Assess (editable, example type)
        - Low Fee (editable, example type)
        """
        # Check if any types exist
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM client_types")
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            return
        
        now = int(time.time())
        
        # Default types with muted color palette
        default_types = [
            {
                'name': 'Inactive',
                'color': '#D9C8A5',  # Warm Amber
                'color_name': 'Warm Amber',
                'bubble_color': '#F5F0E9',
                'file_number_style': 'manual',
                'session_fee': 0.0,
                'session_base_price': 0.0,
                'session_tax_rate': 0.0,
                'session_duration': 50,
                'retention_period': 2555,  # 7 years in days
                'is_system': 1,
                'is_system_locked': 1,
                'service_description': 'Inactive client (no longer in treatment)'
            },
            {
                'name': 'Deleted',
                'color': '#B8B8C5',  # Soft Gray
                'color_name': 'Soft Gray',
                'bubble_color': '#EEEEEF',
                'file_number_style': 'manual',
                'session_fee': 0.0,
                'session_base_price': 0.0,
                'session_tax_rate': 0.0,
                'session_duration': 50,
                'retention_period': 0,
                'is_system': 1,
                'is_system_locked': 1,
                'service_description': 'Deleted client (purged from system)'
            },
            {
                'name': 'Active',
                'color': '#9FCFC0',  # Soft Teal
                'color_name': 'Soft Teal',
                'bubble_color': '#E6F5F1',
                'file_number_style': 'date-initials',
                'session_fee': 200.0,
                'session_base_price': 200.0,
                'session_tax_rate': 0.0,
                'session_duration': 50,
                'retention_period': 2555,  # 7 years
                'is_system': 0,
                'is_system_locked': 0,
                'service_description': 'Psychotherapy'
            },
            {
                'name': 'Assess',
                'color': '#A8C8D9',  # Powder Blue
                'color_name': 'Powder Blue',
                'bubble_color': '#E8F0F5',
                'file_number_style': 'date-initials',
                'session_fee': 225.0,
                'session_base_price': 225.0,
                'session_tax_rate': 0.0,
                'session_duration': 90,
                'retention_period': 2555,
                'is_system': 0,
                'is_system_locked': 0,
                'service_description': 'Psychological Assessment'
            },
            {
                'name': 'Low Fee',
                'color': '#A7D4A4',  # Mint Green
                'color_name': 'Mint Green',
                'bubble_color': '#E8F5E7',
                'file_number_style': 'date-initials',
                'session_fee': 100.0,
                'session_base_price': 100.0,
                'session_tax_rate': 0.0,
                'session_duration': 50,
                'retention_period': 2555,
                'is_system': 0,
                'is_system_locked': 0,
                'service_description': 'Sliding Scale Psychotherapy'
            }
        ]
        
        for type_data in default_types:
            cursor.execute("""
                INSERT INTO client_types (
                    name, color, color_name, bubble_color, file_number_style,
                    session_fee, session_base_price, session_tax_rate, session_duration,
                    retention_period, is_system, is_system_locked, service_description,
                    created_at, modified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                type_data['name'],
                type_data['color'],
                type_data['color_name'],
                type_data['bubble_color'],
                type_data['file_number_style'],
                type_data['session_fee'],
                type_data['session_base_price'],
                type_data['session_tax_rate'],
                type_data['session_duration'],
                type_data['retention_period'],
                type_data['is_system'],
                type_data['is_system_locked'],
                type_data['service_description'],
                now,
                now
            ))
        
        conn.commit()
        conn.close()
        print("Created 5 default client types")
    
    # ===== CLIENT TYPE OPERATIONS =====
    
    def add_client_type(self, type_data: Dict[str, Any]) -> int:
        """Add new client type."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
        cursor.execute("""
            INSERT INTO client_types (
                name, color, color_name, bubble_color,
                session_fee, session_base_price, session_tax_rate, session_duration,
                retention_period, service_description, is_system, is_system_locked,
                created_at, modified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            type_data['name'],
            type_data['color'],
            type_data.get('color_name', ''),
            type_data.get('bubble_color', ''),
            type_data.get('session_fee', 0.0),
            type_data.get('session_base_price', 0.0),
            type_data.get('session_tax_rate', 0.0),
            type_data.get('session_duration', 50),
            type_data.get('retention_period', 2555),
            type_data.get('service_description', ''),
            type_data.get('is_system', 0),
            type_data.get('is_system_locked', 0),
            now,
            now
        ))
        
        type_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return type_id

    
    def get_client_type(self, type_id: int) -> Optional[Dict[str, Any]]:
        """Get client type by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM client_types WHERE id = ?", (type_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_client_types(self) -> List[Dict[str, Any]]:
        """Get all client types."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM client_types ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_client_type(self, type_id: int, type_data: Dict[str, Any]) -> bool:
        """Update client type."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
        cursor.execute("""
            UPDATE client_types
            SET name = ?, color = ?, color_name = ?, bubble_color = ?,
                session_fee = ?, session_base_price = ?, session_tax_rate = ?,
                session_duration = ?, retention_period = ?,
                service_description = ?, modified_at = ?
            WHERE id = ?
        """, (
            type_data['name'],
            type_data['color'],
            type_data.get('color_name', ''),
            type_data.get('bubble_color', ''),
            type_data.get('session_fee', 0.0),
            type_data.get('session_base_price', 0.0),
            type_data.get('session_tax_rate', 0.0),
            type_data.get('session_duration', 50),
            type_data.get('retention_period', 2555),
            type_data.get('service_description', ''),
            now,
            type_id
        ))
        
        conn.commit()
        conn.close()
        
        return True

    
    def delete_client_type(self, type_id: int) -> bool:
        """Delete client type (only if not in use and not system type)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if it's a system type
        cursor.execute("SELECT is_system FROM client_types WHERE id = ?", (type_id,))
        row = cursor.fetchone()
        if row and row[0] == 1:
            conn.close()
            return False
        
        # Check if any clients use this type
        cursor.execute("SELECT COUNT(*) FROM clients WHERE type_id = ?", (type_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            return False
        
        # Safe to delete
        cursor.execute("DELETE FROM client_types WHERE id = ?", (type_id,))
        conn.commit()
        conn.close()
        
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
        conn.close()
        
        return client_id
    
    def get_client(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get client by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        
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
        conn.close()
        
        return [dict(row) for row in rows]
    
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
        conn.close()
        
        return True
    
    def search_clients(self, search_term: str) -> List[Dict[str, Any]]:
        """Search clients by name, file number, email, or phone."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Search in client table and profile entries
        cursor.execute("""
            SELECT DISTINCT c.* FROM clients c
            LEFT JOIN entries e ON c.id = e.client_id AND e.class = 'profile'
            WHERE c.is_deleted = 0 AND (
                c.file_number LIKE ? OR
                c.first_name LIKE ? OR
                c.last_name LIKE ? OR
                e.email LIKE ? OR
                e.phone LIKE ?
            )
            ORDER BY c.file_number
        """, (f'%{search_term}%',) * 5)
        
        rows = cursor.fetchall()
        conn.close()
        
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
        conn.close()
        
        return row[0] if row else 0
    
    def get_payment_status(self, client_id: int) -> str:
        """Get client's payment status (paid/pending/overdue)."""
        # Placeholder - will implement when Statement generation is done
        return 'paid'
    
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
        conn.close()
        
        return dict(row) if row else None
    
    # ===== CLIENT LINKING OPERATIONS =====
    
    def create_link_group(self, client_ids: List[int], billing_type: str = 'principal', principal_payer_id: Optional[int] = None) -> int:
        """Create a new link group using star pattern.
        
        Args:
            client_ids: List of client IDs to link (first becomes hub)
            billing_type: Billing arrangement (unused after Session 6)
            principal_payer_id: Principal payer ID (unused after Session 6)
        
        Returns:
            Link group ID
        """
        conn = self.connect()
        cursor = conn.cursor()
        now = int(time.time())
        
        # Create link group
        cursor.execute("""
            INSERT INTO link_groups (billing_type, principal_payer_id, created_at)
            VALUES (?, ?, ?)
        """, (billing_type, principal_payer_id, now))
        
        group_id = cursor.lastrowid
        
        # Create links using star pattern (first client is hub)
        hub_client_id = client_ids[0]
        
        for i in range(1, len(client_ids)):
            client_id = client_ids[i]
            
            # Always store smaller ID first (for uniqueness constraint)
            id1, id2 = (hub_client_id, client_id) if hub_client_id < client_id else (client_id, hub_client_id)
            
            cursor.execute("""
                INSERT INTO client_links (client_id_1, client_id_2, group_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (id1, id2, group_id, now))
        
        conn.commit()
        conn.close()
        
        return group_id
    
    def get_link_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get link group with all member details.
        
        Args:
            group_id: Link group ID
        
        Returns:
            Dict with group info and members list
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get link group
        cursor.execute("SELECT * FROM link_groups WHERE id = ?", (group_id,))
        group_row = cursor.fetchone()
        
        if not group_row:
            conn.close()
            return None
        
        group = dict(group_row)
        
        # Get all client IDs in this group
        cursor.execute("""
            SELECT DISTINCT client_id_1, client_id_2 FROM client_links
            WHERE group_id = ?
        """, (group_id,))
        
        # Build set of all unique client IDs
        client_ids = set()
        for row in cursor.fetchall():
            client_ids.add(row[0])
            client_ids.add(row[1])
        
        # Get client details for each member
        members = []
        for client_id in client_ids:
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            client_row = cursor.fetchone()
            if client_row:
                members.append(dict(client_row))
        
        group['members'] = members
        
        conn.close()
        return group
    
    def get_all_link_groups(self) -> List[Dict[str, Any]]:
        """Get all link groups with member details.
        
        Returns:
            List of link groups with members
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM link_groups ORDER BY created_at DESC")
        group_rows = cursor.fetchall()
        
        groups = []
        for group_row in group_rows:
            group = dict(group_row)
            group_id = group['id']
            
            # Get all client IDs in this group
            cursor.execute("""
                SELECT DISTINCT client_id_1, client_id_2 FROM client_links
                WHERE group_id = ?
            """, (group_id,))
            
            # Build set of all unique client IDs
            client_ids = set()
            for row in cursor.fetchall():
                client_ids.add(row[0])
                client_ids.add(row[1])
            
            # Get client details for each member
            members = []
            for client_id in client_ids:
                cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
                client_row = cursor.fetchone()
                if client_row:
                    members.append(dict(client_row))
            
            group['members'] = members
            groups.append(group)
        
        conn.close()
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
        
        # Find all links involving this client
        cursor.execute("""
            SELECT client_id_1, client_id_2 FROM client_links
            WHERE client_id_1 = ? OR client_id_2 = ?
        """, (client_id, client_id))
        
        # Collect all linked client IDs
        linked_ids = set()
        for row in cursor.fetchall():
            if row[0] != client_id:
                linked_ids.add(row[0])
            if row[1] != client_id:
                linked_ids.add(row[1])
        
        # Get client details for each linked client
        linked_clients = []
        for linked_id in linked_ids:
            cursor.execute("SELECT * FROM clients WHERE id = ?", (linked_id,))
            client_row = cursor.fetchone()
            if client_row:
                linked_clients.append(dict(client_row))
        
        conn.close()
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
        conn.close()
        
        return count > 0
    
    def update_link_group(self, group_id: int, client_ids: List[int], billing_type: str, principal_payer_id: Optional[int] = None) -> bool:
        """Update an existing link group.
        
        Args:
            group_id: Link group ID
            client_ids: Updated list of client IDs
            billing_type: Updated billing type
            principal_payer_id: Updated principal payer (if applicable)
        
        Returns:
            True if successful
        """
        conn = self.connect()
        cursor = conn.cursor()
        now = int(time.time())
        
        # Update link group
        cursor.execute("""
            UPDATE link_groups
            SET billing_type = ?, principal_payer_id = ?
            WHERE id = ?
        """, (billing_type, principal_payer_id, group_id))
        
        # Delete existing links for this group
        cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))
        
        # Recreate links with new client list (same star pattern as create_link_group)
        hub_client_id = client_ids[0]
        
        for i in range(1, len(client_ids)):
            client_id = client_ids[i]
            id1, id2 = (hub_client_id, client_id) if hub_client_id < client_id else (client_id, hub_client_id)
            
            cursor.execute("""
                INSERT INTO client_links (client_id_1, client_id_2, group_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (id1, id2, group_id, now))
        
        conn.commit()
        conn.close()
        
        return True
    
    def delete_link_group(self, group_id: int) -> bool:
        """Delete a link group and all its links.
        
        Args:
            group_id: Link group ID to delete
        
        Returns:
            True if successful
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Delete all client_links for this group
            cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))
            
            # Delete the link group
            cursor.execute("DELETE FROM link_groups WHERE id = ?", (group_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting link group: {e}")
            conn.close()
            return False
    
    # ===== ENTRY OPERATIONS =====
    
    def add_entry(self, entry_data: Dict[str, Any]) -> int:
        """Add new entry."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        
        # Build SQL dynamically based on which fields are provided
        fields = ['client_id', 'class', 'created_at', 'modified_at']
        values = [entry_data['client_id'], entry_data['class'], now, now]
        
        # Add optional fields if present in entry_data
        optional_fields = [
            'description', 'content', 'email', 'phone', 'home_phone', 'work_phone',
            'text_number', 'address', 'date_of_birth', 'preferred_contact',
            'ok_to_leave_message', 'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relationship', 'referral_source', 'additional_info',
            'modality', 'format', 'session_number', 'service', 'session_date', 'session_time',
            'duration', 'fee', 'is_consultation', 'mood', 'affect', 'risk_assessment',
            'comm_recipient', 'comm_type', 'comm_date', 'comm_time',
            'absence_date', 'absence_time',
            'item_date', 'item_time', 'base_price', 'tax_rate',
            'statement_total', 'payment_status',
            'payment_notes', 'date_sent', 'date_paid', 'is_void', 'edit_history',
            'locked', 'locked_at',
            # Fee Override fields (NEW)
            'fee_override_base', 'fee_override_tax_rate', 'fee_override_total',
            # Guardian fields (NEW)
            'is_minor', 'guardian1_name', 'guardian1_email', 'guardian1_phone',
            'guardian1_address', 'guardian1_pays_percent', 'has_guardian2',
            'guardian2_name', 'guardian2_email', 'guardian2_phone',
            'guardian2_address', 'guardian2_pays_percent'
        ]
        
        for field in optional_fields:
            if field in entry_data:
                fields.append(field)
                # Convert empty strings to empty strings (not None)
                value = entry_data[field]
                if value is None:
                    value = ''
                values.append(value)
        
        placeholders = ', '.join(['?' for _ in values])
        field_names = ', '.join(fields)
        
        cursor.execute(f"""
            INSERT INTO entries ({field_names})
            VALUES ({placeholders})
        """, values)
        
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return entry_id
    
    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Get entry by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_client_entries(self, client_id: int, entry_class: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all entries for a client, optionally filtered by class."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if entry_class:
            cursor.execute(
                "SELECT * FROM entries WHERE client_id = ? AND class = ? ORDER BY created_at DESC",
                (client_id, entry_class)
            )
        else:
            cursor.execute(
                "SELECT * FROM entries WHERE client_id = ? ORDER BY created_at DESC",
                (client_id,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_entry(self, entry_id: int, entry_data: Dict[str, Any]) -> bool:
        """Update entry (adds to edit history if locked)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Build UPDATE statement dynamically
        set_clauses = []
        values = []
        
        for key, value in entry_data.items():
            if key != 'id':
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
        conn.close()
        
        return True
    
    # ===== SETTINGS OPERATIONS =====
    
    def set_setting(self, key: str, value: str):
        """Set a setting value."""
        import time
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        cursor.execute("""
            INSERT INTO settings (key, value, modified_at) 
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=?, modified_at=?
        """, (key, value, now, value, now))
        
        conn.commit()
        conn.close()


    def get_setting(self, key: str, default: str = '') -> str:
        """Get a setting value."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else default