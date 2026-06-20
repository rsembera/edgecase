"""Edit history — the append-only amendment trail for locked entries.

Extracted from core/database.py (Step 3). Relies on self.connect() from the
base Database class.
"""
import json
import time



class EditHistoryMixin:

    
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
