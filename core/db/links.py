"""Client linking — couple/family link groups and their member fees.

Extracted from core/database.py (Step 3). Relies on self.connect() from the
base Database class.
"""
import time

import sqlcipher3 as sqlite3
from typing import Any, Dict, List, Optional


class LinkMixin:

    
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
