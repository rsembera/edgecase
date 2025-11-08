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
                code TEXT,
                file_number_style TEXT NOT NULL,
                file_number_prefix TEXT,
                file_number_suffix TEXT,
                file_number_counter INTEGER DEFAULT 0,
                session_fee REAL,
                session_duration INTEGER,
                retention_period INTEGER,
                is_system INTEGER DEFAULT 0,
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
        
        # Create default client types if they don't exist
        self._create_default_types()
        
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
    
    def _create_default_types(self):
        """Create default Active and Inactive client types."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if default types exist
        cursor.execute("SELECT COUNT(*) FROM client_types WHERE is_system = 1")
        if cursor.fetchone()[0] == 0:
            now = int(time.time())
            
            # Active type
            cursor.execute("""
                INSERT INTO client_types 
                (name, color, code, file_number_style, session_fee, session_duration, 
                 retention_period, is_system, created_at, modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'Active', '#00AA88', 'ACT', 'YYYYMMDD-III', 
                150.0, 50, 2555, 1, now, now
            ))
            
            # Inactive type
            cursor.execute("""
                INSERT INTO client_types 
                (name, color, code, file_number_style, session_fee, session_duration, 
                 retention_period, is_system, created_at, modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'Inactive', '#FFAA00', 'INA', 'YYYYMMDD-III', 
                150.0, 50, 2555, 1, now, now
            ))
            
            conn.commit()
        
        conn.close()
    
    # ===== CLIENT TYPE OPERATIONS =====
    
    def add_client_type(self, type_data: Dict[str, Any]) -> int:
        """Add new client type."""
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        cursor.execute("""
            INSERT INTO client_types 
            (name, color, code, file_number_style, file_number_prefix, 
             file_number_suffix, session_fee, session_duration, retention_period, 
             created_at, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            type_data['name'],
            type_data['color'],
            type_data.get('code', ''),
            type_data['file_number_style'],
            type_data.get('file_number_prefix', ''),
            type_data.get('file_number_suffix', ''),
            type_data.get('session_fee', 0.0),
            type_data.get('session_duration', 50),
            type_data.get('retention_period', 2555),
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
             created_at, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            client_data['file_number'],
            client_data['first_name'],
            client_data.get('middle_name', ''),
            client_data['last_name'],
            client_data['type_id'],
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
        
        # Add optional fields if present
        optional_fields = [
            'description', 'content', 'modality', 'session_number', 'service',
            'session_date', 'session_time', 'duration', 'fee', 'is_consultation',
            'mood', 'affect', 'risk_assessment', 'comm_recipient', 'comm_type',
            'statement_total', 'payment_status', 'payment_notes', 'date_sent',
            'date_paid', 'edit_history', 'locked', 'locked_at'
        ]
        
        for field in optional_fields:
            if field in entry_data:
                fields.append(field)
                values.append(entry_data[field])
        
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
    
    