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
        
        # Client Linking (for couples/family therapy)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id_1 INTEGER NOT NULL,
                client_id_2 INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (client_id_1) REFERENCES clients(id),
                FOREIGN KEY (client_id_2) REFERENCES clients(id),
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
            return  # Types already exist, don't create defaults
        
        import time
        now = int(time.time())
        
        # Create 5 default types (names limited to 9 characters for badge display)
        default_types = [
            # Workflow state types (locked, cannot edit/delete)
            {
                'name': 'Inactive',
                'color': '#F5DDA9',
                'color_name': 'Soft Amber',
                'bubble_color': '#FEF8E8',
                'service_description': None,
                'session_fee': None,
                'session_duration': None,
                'retention_period': None,
                'is_system': 1,
                'is_system_locked': 1
            },
            {
                'name': 'Deleted',
                'color': '#F5C2C4',
                'color_name': 'Soft Rose',
                'bubble_color': '#FDEEF0',
                'service_description': None,
                'session_fee': None,
                'session_duration': None,
                'retention_period': None,
                'is_system': 1,
                'is_system_locked': 1
            },
            # Editable therapy types
            {
                'name': 'Active',
                'color': '#9FCFC0',
                'color_name': 'Soft Teal',
                'bubble_color': '#E0F2EE', 
                'service_description': 'Psychotherapy',
                'session_fee': 150.00,
                'session_duration': 50,
                'retention_period': 365,  # 1 year in days
                'is_system': 1,
                'is_system_locked': 0
            },
            {
                'name': 'Assess',
                'color': '#B8D4E8',
                'color_name': 'Soft Blue',
                'bubble_color': '#EBF3FA',
                'service_description': 'Assessment',
                'session_fee': 200.00,
                'session_duration': 90,
                'retention_period': 365,
                'is_system': 0,
                'is_system_locked': 0
            },
            {
                'name': 'Low Fee',
                'color': '#D4C5E0',
                'color_name': 'Soft Lavender',
                'bubble_color': '#F3EDF7',
                'service_description': 'Psychotherapy',
                'session_fee': 75.00,
                'session_duration': 45,
                'retention_period': 365,
                'is_system': 0,
                'is_system_locked': 0
            }
        ]
        
        for type_data in default_types:
            cursor.execute('''
                INSERT INTO client_types 
                (name, color, color_name, bubble_color, file_number_style, service_description, session_fee, session_duration, 
                retention_period, is_system, is_system_locked, created_at, modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                type_data['name'],
                type_data['color'],
                type_data['color_name'],
                type_data.get('bubble_color'),
                'manual',
                type_data['service_description'],
                type_data['session_fee'],
                type_data['session_duration'],
                type_data['retention_period'],
                type_data['is_system'],
                type_data['is_system_locked'],
                now,
                now
            ))
        
        conn.commit()
        conn.close()
        print(f"Created 5 default client types: Inactive, Deleted, Active, Assess, Low Fee")
    
    def _run_migrations(self):
        """Check for missing columns and add them if needed."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get current columns in entries table
        cursor.execute("PRAGMA table_info(entries)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # Define required columns with their types
        required_columns = {
            'comm_date': 'INTEGER',
            'comm_time': 'TEXT',
            'absence_date': 'INTEGER',
            'absence_time': 'TEXT',
            'item_date': 'INTEGER',
            'item_time': 'TEXT',
            'base_price': 'REAL',
            'tax_rate': 'REAL'
        }  # <-- CLOSE THE DICTIONARY HERE
        
        # Add missing columns to entries table
        for column, col_type in required_columns.items():
            if column not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE entries ADD COLUMN {column} {col_type}")
                    print(f"Migration: Added column '{column}' to entries table")
                except sqlite3.OperationalError as e:
                    print(f"Migration warning: Could not add column '{column}': {e}")
        
        # Add session_offset column to clients table
        cursor.execute("PRAGMA table_info(clients)")
        client_columns = [col[1] for col in cursor.fetchall()]
        if 'session_offset' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN session_offset INTEGER DEFAULT 0")
            print("Migration: Added session_offset column to clients table")
            
        # NEW: Add columns to client_types table
        cursor.execute("PRAGMA table_info(client_types)")
        type_columns = [col[1] for col in cursor.fetchall()]
        
        if 'service_description' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN service_description TEXT")
            print("Migration: Added service_description to client_types")
        
        if 'is_system_locked' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN is_system_locked INTEGER DEFAULT 0")
            print("Migration: Added is_system_locked to client_types")
            
            # Lock existing Inactive and Deleted types
            cursor.execute("UPDATE client_types SET is_system_locked = 1 WHERE name IN ('Inactive', 'Deleted')")
            print("Migration: Locked Inactive and Deleted types")
        
        if 'base_price' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN base_price REAL")
            print("Migration: Added base_price to client_types")
        
        if 'tax_rate' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN tax_rate REAL")
            print("Migration: Added tax_rate to client_types")
            
            # Calculate base_price and tax_rate from existing session_fee (assuming 13% tax)
            cursor.execute("""
                UPDATE client_types 
                SET base_price = session_fee / 1.13,
                    tax_rate = 13.0
                WHERE session_fee IS NOT NULL AND session_fee > 0
            """)
            print("Migration: Calculated base_price and tax_rate from session_fee")
            
        # Add color_name column to client_types table
        cursor.execute("PRAGMA table_info(client_types)")
        type_columns = [col[1] for col in cursor.fetchall()]

        if 'color_name' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN color_name TEXT")
            print("Migration: Added color_name to client_types")
            
            # Update existing types with color names based on their hex values
            color_map = {
                '#9FCFC0': 'Soft Teal',
                '#F5DDA9': 'Soft Amber',
                '#F5C2C4': 'Soft Rose',
                '#B8D4E8': 'Soft Blue',
                '#D4C5E0': 'Soft Lavender'
            }
            
            for hex_code, color_name in color_map.items():
                cursor.execute(
                    "UPDATE client_types SET color_name = ? WHERE color = ?",
                    (color_name, hex_code)
                )
            print("Migration: Added color names to existing types")
            
        # Add bubble_color column to client_types table
        cursor.execute("PRAGMA table_info(client_types)")
        type_columns = [col[1] for col in cursor.fetchall()]

        if 'bubble_color' not in type_columns:
            cursor.execute("ALTER TABLE client_types ADD COLUMN bubble_color TEXT")
            print("Migration: Added bubble_color to client_types")
            
            # Update existing types with bubble colors
            bubble_map = {
                '#9FCFC0': '#E0F2EE',  # Soft Teal
                '#F5DDA9': '#FEF8E8',  # Soft Amber (Inactive)
                '#F5C2C4': '#FDEEF0',  # Soft Rose (Deleted)
                '#B8D4E8': '#EBF3FA',  # Soft Blue
                '#D4C5E0': '#F3EDF7',  # Soft Lavender
            }
            
            for badge_color, bubble_color in bubble_map.items():
                cursor.execute(
                    "UPDATE client_types SET bubble_color = ? WHERE color = ?",
                    (bubble_color, badge_color)
                )
            print("Migration: Added bubble colors to existing types")
        
        conn.commit()
        conn.close()
        
    # ===== HELPER METHODS =====
    
    def get_last_session_date(self, client_id: int) -> Optional[int]:
        """Get the date of the most recent session for a client."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_date FROM entries 
            WHERE client_id = ? AND class = 'session' AND session_date IS NOT NULL
            ORDER BY session_date DESC
            LIMIT 1
        """, (client_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def get_profile_entry(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get the profile entry for a client."""
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
    
    def get_payment_status(self, client_id: int) -> str:
        """
        Get payment status for a client.
        Returns: 'paid', 'pending', or 'overdue'
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get most recent statement
        cursor.execute("""
            SELECT payment_status, date_sent FROM entries
            WHERE client_id = ? AND class = 'statement' AND is_void = 0
            ORDER BY created_at DESC
            LIMIT 1
        """, (client_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return 'paid'  # No statements = up to date
        
        payment_status = row[0]
        date_sent = row[1]
        
        if payment_status == 'paid':
            return 'paid'
        elif payment_status == 'pending':
            # Check if overdue (more than 30 days)
            if date_sent:
                import time
                days_since_sent = (int(time.time()) - date_sent) / 86400
                if days_since_sent > 30:
                    return 'overdue'
            return 'pending'
        
        return 'paid'
        
        conn.close()
    
    # ===== CLIENT TYPE OPERATIONS =====
    
    def add_client_type(self, type_data: Dict) -> int:
        """Add a new client type.
        
        Args:
            type_data: Dictionary with type fields (name, color, color_name, session_fee, etc.)
        
        Returns:
            ID of newly created type
        """
        import time
        now = int(time.time())
        
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO client_types 
            (name, color, color_name, bubble_color, file_number_style, service_description, session_fee, session_duration, 
            retention_period, is_system, is_system_locked, created_at, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            type_data['name'],
            type_data['color'],
            type_data.get('color_name'),
            type_data.get('bubble_color'),
            'manual',
            type_data.get('service_description'),
            type_data.get('session_fee'),
            type_data.get('session_duration'),
            type_data.get('retention_period'),
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
    
    # ===== CLIENT OPERATIONS =====
    
    def add_client(self, client_data: Dict[str, Any]) -> int:
        """Add new client."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        cursor.execute("""
            INSERT INTO clients 
            (file_number, first_name, middle_name, last_name, type_id, 
            session_offset, created_at, modified_at)
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
                "SELECT * FROM clients WHERE type_id = ? AND is_deleted = 0 ORDER BY last_name, first_name",
                (type_id,)
            )
        else:
            cursor.execute("SELECT * FROM clients WHERE is_deleted = 0 ORDER BY last_name, first_name")
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_client(self, client_id: int, client_data: Dict[str, Any]) -> bool:
        """Update client information."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE clients 
            SET first_name = ?, middle_name = ?, last_name = ?, 
                type_id = ?, modified_at = ?
            WHERE id = ?
        """, (
            client_data['first_name'],
            client_data.get('middle_name', ''),
            client_data['last_name'],
            client_data['type_id'],
            int(time.time()),
            client_id
        ))
        
        conn.commit()
        conn.close()
        
        return True
    
    def search_clients(self, search_term: str) -> List[Dict[str, Any]]:
        """Search clients by name or file number."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        pattern = f"%{search_term}%"
        cursor.execute("""
            SELECT * FROM clients 
            WHERE (first_name LIKE ? OR last_name LIKE ? OR file_number LIKE ?)
              AND is_deleted = 0
            ORDER BY last_name, first_name
        """, (pattern, pattern, pattern))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
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
            'locked', 'locked_at'
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
    
    def update_client_type(self, type_id: int, type_data: Dict) -> bool:
        """Update an existing client type.
        
        Args:
            type_id: ID of type to update
            type_data: Dictionary with fields to update
        
        Returns:
            True if successful
        """
        import time
        now = int(time.time())
        
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE client_types 
            SET name = ?, color = ?, color_name = ?, bubble_color = ?, service_description = ?, 
                session_fee = ?, session_duration = ?, retention_period = ?, modified_at = ?
            WHERE id = ?
        ''', (
            type_data['name'],
            type_data['color'],
            type_data.get('color_name'), 
            type_data.get('bubble_color'),
            type_data.get('service_description'),
            type_data.get('session_fee'),
            type_data.get('session_duration'),
            type_data.get('retention_period'),
            now,
            type_id
        ))
        
        conn.commit()
        conn.close()
        
        return True

    def delete_client_type(self, type_id: int) -> bool:
        """Delete a client type.
        
        Only succeeds if:
        - Type is not locked (is_system_locked = 0)
        - No clients are assigned to this type
        
        Args:
            type_id: ID of type to delete
        
        Returns:
            True if successful, False otherwise
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            # Check if type is locked (do it in this connection, don't call get_client_type)
            cursor.execute(
                "SELECT is_system_locked FROM client_types WHERE id = ?",
                (type_id,)
            )
            result = cursor.fetchone()
            
            if not result or result[0] == 1:
                conn.close()
                return False
            
            # Check if any clients use this type
            cursor.execute(
                "SELECT COUNT(*) FROM clients WHERE type_id = ?",
                (type_id,)
            )
            count = cursor.fetchone()[0]
            
            if count > 0:
                conn.close()
                return False
            
            # Safe to delete
            cursor.execute("DELETE FROM client_types WHERE id = ?", (type_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting client type: {e}")
            conn.close()
            return False
    
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