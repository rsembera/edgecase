"""Entry operations — create/read/update/lock/redact the unified client entries
(sessions, communications, absences, items, uploads, profiles) and their
attachments and statement links.

Extracted from core/database.py (Step 3). Relies on self.connect() from the
base Database class.
"""
import time

import sqlcipher3 as sqlite3
from typing import Any, Dict, List, Optional

from core.db.errors import EntryLockedError


class EntryMixin:

    
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
            'reflections',  # two-note system; never exported (see database.py)
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
    
    def set_reflections(self, entry_id: int, text) -> bool:
        """Write entries.reflections alone, without touching modified_at.

        Reflections are not part of the exported record, so a change to them
        must not appear in the amendment trail — that would disclose the
        field's existence on a locked entry's edit history. And because there
        is no trail entry, modified_at must not move either: bumping it would
        assert an edit the trail doesn't show, which is exactly what the
        locked-entry no-op guard in the session route exists to prevent.
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE entries SET reflections = ? WHERE id = ?",
                       (text or None, entry_id))
        conn.commit()
        return cursor.rowcount > 0

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
