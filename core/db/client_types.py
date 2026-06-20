"""Client type operations — the workflow categories (e.g. Active/Inactive).

Extracted from core/database.py (Step 3). System types (is_system /
is_system_locked) are guarded against rename and delete at the DB layer here;
the retention sweep depends on those flags. Relies on self.connect() from the
base Database class.
"""
import time

import sqlcipher3 as sqlite3
from typing import Any, Dict, List, Optional


class ClientTypeMixin:


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
