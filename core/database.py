"""
EdgeCase Database Module
Handles SQLite database operations with SQLCipher encryption.
"""

import sqlcipher3 as sqlite3  # Drop-in replacement with encryption
from pathlib import Path
from typing import Dict, List, Optional, Any
import time
from datetime import datetime, timedelta

class Database:
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
        self._conn = None  # Persistent connection
        self._initialize_schema()
        
    def connect(self):
        """Get database connection (reuses existing connection for performance)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            
            # Set encryption key FIRST, before any other operations
            if self.password:
                self._conn.execute(f"PRAGMA key = '{self.password}'")
            
            # Enable WAL mode for better concurrent access
            self._conn.execute('PRAGMA journal_mode=WAL')
        
        return self._conn
    
    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
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
                
                -- Profile fee fields (primary individual session fees)
                fee_override_base REAL,
                fee_override_tax_rate REAL,
                fee_override_total REAL,
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
        
        conn.commit()
        
        # Create default client types if they don't exist
        self._create_default_types()
    
    def _run_migrations(self):
        """Run database migrations to update schema."""
        # No migrations needed - clean schema in _initialize_schema()
        pass

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
            conn.close()
            return
        
        now = int(time.time())
        
        # Default types with muted color palette (NO FEE FIELDS)
        default_types = [
            {
                'name': 'Active',
                'color': '#9FCFC0',  # Soft Teal
                'color_name': 'Soft Teal',
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
        conn.close()
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
        conn.close()
        
        return dict(row) if row else None
    
    # ===== EDIT HISTORY SYSTEM ======
    
    def lock_entry(self, entry_id):
        """Lock an entry after first save, making it immutable."""
        import time
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE entries 
            SET locked = 1, locked_at = ?
            WHERE id = ?
        """, (int(time.time()), entry_id))
        
        conn.commit()
        conn.close()

    def is_entry_locked(self, entry_id):
        """Check if an entry is locked."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT locked FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result[0] == 1 if result else False

    def add_to_edit_history(self, entry_id, change_description):
        """Add an edit to the entry's history."""
        import time
        import json
        
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
        conn.close()

    def get_edit_history(self, entry_id):
        """Get the edit history for an entry."""
        import json
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT edit_history FROM entries WHERE id = ?", (entry_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            return json.loads(result[0])
        return []
    
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
                conn.close()
                raise ValueError("Link duplicates an existing arrangement. Please edit or delete the existing link.")
        
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
        conn.close()
        
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
            conn.close()
            return None
        
        group = dict(group_row)
        
        # Get all members with their fees
        cursor.execute("""
            SELECT client_id_1 as client_id, member_base_fee, member_tax_rate, member_total_fee
            FROM client_links
            WHERE group_id = ?
        """, (group_id,))
        
        members = []
        for row in cursor.fetchall():
            client_id = row['client_id']
            
            # Get client details
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            client_row = cursor.fetchone()
            
            if client_row:
                member = dict(client_row)
                # Add fee info
                member['member_base_fee'] = row['member_base_fee']
                member['member_tax_rate'] = row['member_tax_rate']
                member['member_total_fee'] = row['member_total_fee']
                members.append(member)
        
        group['members'] = members
        
        conn.close()
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
        group_rows = cursor.fetchall()
        
        groups = []
        for group_row in group_rows:
            group = dict(group_row)
            group_id = group['id']
            
            # Get all members with their fees
            cursor.execute("""
                SELECT client_id_1 as client_id, member_base_fee, member_tax_rate, member_total_fee
                FROM client_links
                WHERE group_id = ?
            """, (group_id,))
            
            members = []
            for row in cursor.fetchall():
                client_id = row['client_id']
                
                # Get client details
                cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
                client_row = cursor.fetchone()
                
                if client_row:
                    member = dict(client_row)
                    # Add fee info
                    member['member_base_fee'] = row['member_base_fee']
                    member['member_tax_rate'] = row['member_tax_rate']
                    member['member_total_fee'] = row['member_total_fee']
                    members.append(member)
            
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
        
        # Find which group(s) this client belongs to
        cursor.execute("""
            SELECT DISTINCT group_id FROM client_links
            WHERE client_id_1 = ?
        """, (client_id,))
        
        group_ids = [row['group_id'] for row in cursor.fetchall()]
        
        if not group_ids:
            conn.close()
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
        conn.close()
        
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
        
        # Delete all member links
        cursor.execute("DELETE FROM client_links WHERE group_id = ?", (group_id,))
        
        # Delete the group itself
        cursor.execute("DELETE FROM link_groups WHERE id = ?", (group_id,))
        
        conn.commit()
        conn.close()
        
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
            'statement_total', 'payment_status',
            'payment_notes', 'date_sent', 'date_paid', 'is_void', 'edit_history',
            'locked', 'locked_at',
            # Fee Override fields
            'fee_override_base', 'fee_override_tax_rate', 'fee_override_total',
            # Guardian fields
            'is_minor', 'guardian1_name', 'guardian1_email', 'guardian1_phone',
            'guardian1_address', 'guardian1_pays_percent', 'has_guardian2',
            'guardian2_name', 'guardian2_email', 'guardian2_phone',
            'guardian2_address', 'guardian2_pays_percent',
            # Ledger fields  ← ADD THIS SECTION
            'ledger_date', 'ledger_type', 'source', 'payee_id', 'category_id',
            'base_amount', 'tax_amount', 'total_amount', 'statement_id'
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
        conn.close()
        
        return attachments
        
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
    
    # EdgeCase Ledger - Database Methods
    # Add these methods to the Database class in ~/edgecase/core/database.py

    # ============================================================================
    # PAYEE OPERATIONS
    # ============================================================================

    def add_payee(self, name: str) -> int:
        """Add a new payee to the payees table."""
        import time
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO payees (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        payee_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return payee_id

    def get_payee(self, payee_id: int) -> dict:
        """Get a single payee by ID."""
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees WHERE id = ?", (payee_id,))
        payee = cursor.fetchone()
        conn.close()
        
        return dict(payee) if payee else None

    def get_all_payees(self) -> list:
        """Get all payees ordered by name."""
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees ORDER BY name ASC")
        payees = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
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
        conn.close()
        return success

    def delete_payee(self, payee_id: int) -> bool:
        """Delete a payee (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this payee
        cursor.execute("SELECT COUNT(*) FROM entries WHERE payee_id = ?", (payee_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM payees WHERE id = ?", (payee_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success


    # ============================================================================
    # EXPENSE CATEGORY OPERATIONS
    # ============================================================================

    def add_expense_category(self, name: str) -> int:
        """Add a new expense category."""
        import time
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO expense_categories (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        category_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return category_id

    def get_expense_category(self, category_id: int) -> dict:
        """Get a single expense category by ID."""
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories WHERE id = ?", (category_id,))
        category = cursor.fetchone()
        conn.close()
        
        return dict(category) if category else None

    def get_all_expense_categories(self) -> list:
        """Get all expense categories ordered by name."""
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories ORDER BY name ASC")
        categories = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return categories

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
        conn.close()
        return success

    def delete_expense_category(self, category_id: int) -> bool:
        """Delete an expense category (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this category
        cursor.execute("SELECT COUNT(*) FROM entries WHERE category_id = ?", (category_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            conn.close()
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM expense_categories WHERE id = ?", (category_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success


    # ============================================================================
    # LEDGER ENTRY OPERATIONS
    # ============================================================================

    def get_all_ledger_entries(self, ledger_type: str = None) -> list:
        """
        Get all ledger entries (income and/or expense).
        
        Includes attachment_count via JOIN for performance.
        
        Args:
            ledger_type: Optional filter - 'income' or 'expense' or None for both
        
        Returns:
            List of ledger entries sorted by date (newest first), then created_at
        """
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT entries.*, COUNT(attachments.id) as attachment_count
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                WHERE entries.ledger_type = ?
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """, (ledger_type,))
        else:
            cursor.execute("""
                SELECT entries.*, COUNT(attachments.id) as attachment_count
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                WHERE entries.ledger_type IN ('income', 'expense')
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """)
        
        entries = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
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
        import sqlcipher3 as sqlite3
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT * FROM entries 
                WHERE ledger_type = ?
                AND ledger_date BETWEEN ? AND ?
                ORDER BY ledger_date ASC, created_at ASC
            """, (ledger_type, start_date, end_date))
        else:
            cursor.execute("""
                SELECT * FROM entries 
                WHERE ledger_type IN ('income', 'expense')
                AND ledger_date BETWEEN ? AND ?
                ORDER BY ledger_date ASC, created_at ASC
            """, (start_date, end_date))
        
        entries = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
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
        
        conn.close()
        
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
    # Add these methods to the Database class in database.py
    # ============================================================

    def get_clients_due_for_deletion(self):
        """
        Get all Inactive clients whose retention period has expired.
        Returns list of dicts with client info and calculated retain_until.
        """
        import time
        from datetime import datetime, timedelta
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Get all Inactive clients with retention_days set
        cursor.execute("""
            SELECT c.*, ct.name as type_name
            FROM clients c
            JOIN client_types ct ON c.type_id = ct.id
            WHERE ct.name = 'Inactive' 
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
            
            # Get last contact date (most recent entry)
            cursor.execute("""
                SELECT MAX(created_at) as last_contact
                FROM entries
                WHERE client_id = ?
            """, (client_id,))
            result = cursor.fetchone()
            last_contact = result[0] if result and result[0] else client['created_at']
            
            # Get profile to check for minor status
            cursor.execute("""
                SELECT is_minor, date_of_birth
                FROM entries
                WHERE client_id = ? AND class = 'profile'
            """, (client_id,))
            profile = cursor.fetchone()
            
            is_minor = profile[0] if profile else 0
            dob_str = profile[1] if profile else None
            
            # Calculate retain_until
            retention_seconds = retention_days * 24 * 60 * 60
            standard_retain_until = last_contact + retention_seconds
            
            # For minors, also calculate based on 18th birthday
            if is_minor and dob_str:
                try:
                    dob = datetime.strptime(dob_str, '%Y-%m-%d')
                    eighteenth_birthday = dob.replace(year=dob.year + 18)
                    after_majority = int(eighteenth_birthday.timestamp()) + retention_seconds
                    retain_until = max(standard_retain_until, after_majority)
                except (ValueError, TypeError):
                    retain_until = standard_retain_until
            else:
                retain_until = standard_retain_until
            
            # Check if retention period has expired
            if today >= retain_until:
                # Get first contact (profile created_at or earliest entry)
                cursor.execute("""
                    SELECT MIN(created_at) as first_contact
                    FROM entries
                    WHERE client_id = ?
                """, (client_id,))
                result = cursor.fetchone()
                first_contact = result[0] if result and result[0] else client['created_at']
                
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
        
        conn.close()
        return clients_due

    def archive_and_delete_client(self, client_id):
        """
        Archive client info and delete all their data.
        Returns True on success, False on failure.
        """
        import time
        import os
        import shutil
        from datetime import datetime
        
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
            last_contact = result[0] if result and result[0] else client['created_at']
            
            # Calculate retain_until (same logic as get_clients_due_for_deletion)
            retention_days = client.get('retention_days') or 0
            retention_seconds = retention_days * 24 * 60 * 60
            standard_retain_until = last_contact + retention_seconds
            
            if is_minor and dob_str:
                try:
                    dob = datetime.strptime(dob_str, '%Y-%m-%d')
                    eighteenth_birthday = dob.replace(year=dob.year + 18)
                    after_majority = int(eighteenth_birthday.timestamp()) + retention_seconds
                    retain_until = max(standard_retain_until, after_majority)
                except (ValueError, TypeError):
                    retain_until = standard_retain_until
            else:
                retain_until = standard_retain_until
            
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
            
            # Get all entry IDs for this client (for attachment cleanup)
            cursor.execute("SELECT id FROM entries WHERE client_id = ?", (client_id,))
            entry_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete attachment files from disk
            attachments_base = os.path.expanduser('~/edgecase/attachments')
            client_attachments_dir = os.path.join(attachments_base, str(client_id))
            if os.path.exists(client_attachments_dir):
                shutil.rmtree(client_attachments_dir)
            
            # Delete attachments from database
            if entry_ids:
                placeholders = ','.join('?' * len(entry_ids))
                cursor.execute(f"DELETE FROM attachments WHERE entry_id IN ({placeholders})", entry_ids)
            
            # Delete all entries
            cursor.execute("DELETE FROM entries WHERE client_id = ?", (client_id,))
            
            # Delete client record
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            conn.rollback()
            conn.close()
            print(f"Error archiving client {client_id}: {e}")
            return False

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
        conn.close()
        return archived

    def snapshot_retention_on_inactive(self, client_id, retention_days):
        """
        When changing to Inactive, store the retention_days from the original type.
        """
        import time
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE clients 
            SET retention_days = ?, modified_at = ?
            WHERE id = ?
        """, (retention_days, int(time.time()), client_id))
        
        conn.commit()
        conn.close()


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
    # Attachments are stored in ~/edgecase/attachments/ledger/{entry_id}/