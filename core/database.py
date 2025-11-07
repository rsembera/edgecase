"""
EdgeCase Database Module
Handles SQLite database operations with SQLCipher encryption.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any

class Database:
    """
    Database interface for EdgeCase.
    Manages all SQLite operations for clients, notes, invoices, etc.
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
        
        # Clients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT,
                date_of_birth TEXT,
                client_type TEXT NOT NULL DEFAULT 'active',
                notes TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        
        # Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                date INTEGER NOT NULL,
                content TEXT NOT NULL,
                locked INTEGER DEFAULT 0,
                locked_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Invoices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                invoice_number TEXT UNIQUE NOT NULL,
                date INTEGER NOT NULL,
                amount REAL NOT NULL,
                pdf_path TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Payments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                date_issued INTEGER NOT NULL,
                date_due INTEGER,
                date_paid INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Communications table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS communications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                type TEXT NOT NULL,
                direction TEXT NOT NULL,
                subject TEXT,
                content TEXT NOT NULL,
                pdf_path TEXT,
                locked INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        # Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                folder TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    # Client operations
    def add_client(self, client_data: Dict[str, Any]) -> int:
        """
        Add new client to database.
        
        Args:
            client_data: Dictionary with client information
            
        Returns:
            ID of newly created client
        """
        import time
        
        conn = self.connect()
        cursor = conn.cursor()
        
        now = int(time.time())
        cursor.execute("""
            INSERT INTO clients 
            (file_number, name, phone, email, address, date_of_birth, 
             client_type, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_data['file_number'],
            client_data['name'],
            client_data.get('phone', ''),
            client_data.get('email', ''),
            client_data.get('address', ''),
            client_data.get('date_of_birth', ''),
            client_data.get('client_type', 'active'),
            client_data.get('notes', ''),
            now,
            now
        ))
        
        client_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return client_id
    
    def get_client(self, client_id: int) -> Optional[Dict[str, Any]]:
        """
        Get client by ID.
        
        Args:
            client_id: Client ID
            
        Returns:
            Dictionary with client data or None if not found
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_clients(self, client_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all clients, optionally filtered by type.
        
        Args:
            client_type: Optional filter by client type
            
        Returns:
            List of client dictionaries
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if client_type:
            cursor.execute(
                "SELECT * FROM clients WHERE client_type = ? ORDER BY name",
                (client_type,)
            )
        else:
            cursor.execute("SELECT * FROM clients ORDER BY name")
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_client(self, client_id: int, client_data: Dict[str, Any]) -> bool:
        """
        Update client information.
        
        Args:
            client_id: Client ID
            client_data: Dictionary with updated client information
            
        Returns:
            True if successful
        """
        import time
        
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE clients 
            SET name = ?, phone = ?, email = ?, address = ?, 
                date_of_birth = ?, client_type = ?, notes = ?, updated_at = ?
            WHERE id = ?
        """, (
            client_data['name'],
            client_data.get('phone', ''),
            client_data.get('email', ''),
            client_data.get('address', ''),
            client_data.get('date_of_birth', ''),
            client_data.get('client_type', 'active'),
            client_data.get('notes', ''),
            int(time.time()),
            client_id
        ))
        
        conn.commit()
        conn.close()
        
        return True
    
    def delete_client(self, client_id: int) -> bool:
        """
        Delete client from database.
        
        Args:
            client_id: Client ID
            
        Returns:
            True if successful
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        
        conn.commit()
        conn.close()
        
        return True
    
    def search_clients(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Search clients by name, file number, phone, or email.
        
        Args:
            search_term: Search string
            
        Returns:
            List of matching client dictionaries
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        pattern = f"%{search_term}%"
        cursor.execute("""
            SELECT * FROM clients 
            WHERE name LIKE ? OR file_number LIKE ? 
               OR phone LIKE ? OR email LIKE ?
            ORDER BY name
        """, (pattern, pattern, pattern, pattern))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]