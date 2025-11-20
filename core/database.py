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
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()
        
    def connect(self):
        """Create and return database connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        # Enable WAL mode for better concurrent access
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    
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
        
        conn.commit()
        
        # Create default client types if they don't exist
        self._create_default_types()
    
    def _run_migrations(self):
        """Run database migrations to update schema."""
        # No migrations needed - clean schema in _initialize_schema()
        pass

    def _create_default_types(self):
        """Create default client types on first run.
        
        Creates 3 system types:
        - Active (editable, default)
        - Inactive (locked, workflow state)
        - Deleted (locked, workflow state)
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
            },
            {
                'name': 'Deleted',
                'color': '#B8B8C5',  # Soft Gray
                'color_name': 'Soft Gray',
                'bubble_color': '#EEEEEF',
                'retention_period': 0,
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
        print("Created 3 default client types (Active, Inactive, Deleted)")
    
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