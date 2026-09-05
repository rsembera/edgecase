"""Client records — core CRUD, search, and the per-client lookups (profile,
last session date, file-number existence).

Extracted from core/database.py (Step 3). Relies on self.connect() from the
base Database class.
"""
import time

import sqlcipher3 as sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from core.money import dec, quantize_cents


class ClientMixin:

    
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
        
        return client_id
    
    def file_number_exists(self, file_number: str) -> bool:
        """Check if a file number already exists."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM clients WHERE file_number = ?", (file_number,))
        return cursor.fetchone() is not None

    def get_client(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get client by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        
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
        
        return [dict(row) for row in rows]

    # Allowed column names for dynamic UPDATE queries (security: prevents SQL injection via column names)
    ALLOWED_CLIENT_COLUMNS = frozenset({
        'file_number', 'first_name', 'middle_name', 'last_name', 'type_id',
        'session_offset', 'retention_days', 'is_deleted', 'modified_at'
    })

    ALLOWED_ENTRY_COLUMNS = frozenset({
        # Common fields
        'client_id', 'class', 'description', 'content',
        # Profile fields
        'email', 'phone', 'home_phone', 'work_phone', 'text_number', 'address',
        'date_of_birth', 'preferred_contact', 'ok_to_leave_message',
        'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
        'referral_source', 'additional_info', 'meeting_link',
        'session_base', 'session_tax_rate', 'session_total', 'default_session_duration',
        'is_minor', 'guardian1_name', 'guardian1_email', 'guardian1_phone', 'guardian1_address',
        'guardian1_pays_percent', 'has_guardian2', 'guardian2_name', 'guardian2_email',
        'guardian2_phone', 'guardian2_address', 'guardian2_pays_percent',
        # Session fields
        'modality', 'format', 'session_number', 'service', 'session_date', 'session_time',
        'duration', 'base_fee', 'tax_rate', 'fee', 'is_consultation', 'is_pro_bono',
        'mood', 'affect', 'risk_assessment',
        # Communication fields
        'comm_recipient', 'comm_type', 'comm_date', 'comm_time',
        # Absence fields
        'absence_date', 'absence_time',
        # Item fields
        'item_date', 'item_time', 'base_price', 'guardian1_amount', 'guardian2_amount',
        # Upload fields
        'upload_date', 'upload_time',
        # Ledger fields
        'ledger_date', 'ledger_type', 'source', 'payee_id', 'category_id',
        'base_amount', 'tax_amount', 'total_amount', 'statement_id',
        # Statement fields
        'statement_total', 'statement_tax_total', 'payment_status', 'payment_notes',
        'date_sent', 'date_paid', 'is_void',
        # Edit tracking
        'edit_history', 'locked', 'locked_at',
        # Redaction
        'is_redacted', 'redacted_at', 'redaction_reason',
        # Metadata
        'modified_at'
    })

    # Columns where '' is semantically wrong — they're INTEGER or REAL in the
    # schema, so SQLite stores '' as TEXT, which sorts above all numbers,
    # breaks BETWEEN/range filters and ORDER BY, and causes IS NULL checks to
    # silently fail (e.g. `if statement_id is not None` returns True for ''
    # entries). add_entry coerces '' → None for these so SQLite stores NULL.
    # See CODE_REVIEW.md H5.
    TYPED_ENTRY_COLUMNS = frozenset({
        # Integer date/time columns
        'session_date', 'comm_date', 'absence_date', 'item_date',
        'upload_date', 'ledger_date', 'date_sent', 'date_paid',
        'locked_at', 'redacted_at', 'date_of_birth',
        # Other integer columns
        'session_number', 'duration', 'default_session_duration',
        'payee_id', 'category_id', 'statement_id',
        'guardian1_pays_percent', 'guardian2_pays_percent',
        # Boolean (stored as INTEGER) columns
        'is_minor', 'has_guardian2', 'is_consultation', 'is_pro_bono',
        'is_void', 'locked', 'is_redacted',
        # Real (money/percentage) columns
        'base_fee', 'tax_rate', 'fee', 'base_price',
        'base_amount', 'tax_amount', 'total_amount',
        'statement_total', 'statement_tax_total',
        'session_base', 'session_tax_rate', 'session_total',
        'guardian1_amount', 'guardian2_amount',
    })

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
                # Validate column name against whitelist
                if key not in self.ALLOWED_CLIENT_COLUMNS:
                    raise ValueError(f"Invalid column name: {key}")
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
        
        return True
    
    def search_clients(self, search_term: str) -> List[Dict[str, Any]]:
        """Search clients by name, file number, email, or phone."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Escape LIKE wildcards (% and _) and the escape character itself so
        # a search for e.g. '100%' matches literally instead of acting as a
        # wildcard (CODE_REVIEW.md L14).
        escaped_term = (search_term
                        .replace('\\', '\\\\')
                        .replace('%', '\\%')
                        .replace('_', '\\_'))

        # Search in client table and profile entries
        cursor.execute("""
            SELECT DISTINCT c.* FROM clients c
            LEFT JOIN entries e ON c.id = e.client_id AND e.class = 'profile'
            WHERE c.is_deleted = 0 AND (
                c.file_number LIKE ? ESCAPE '\\' OR
                c.first_name LIKE ? ESCAPE '\\' OR
                c.last_name LIKE ? ESCAPE '\\' OR
                e.email LIKE ? ESCAPE '\\' OR
                e.phone LIKE ? ESCAPE '\\'
            )
            ORDER BY c.file_number
        """, (f'%{escaped_term}%',) * 5)
        
        rows = cursor.fetchall()
        
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

    def get_unbilled_total(self, client_id: int) -> Decimal:
        """Total owing for this client's billable, locked, not-yet-billed entries.

        Mirrors the statement generator's find_unbilled predicate and fee
        resolution exactly (sessions/absences/items that are locked and have no
        statement_id, excluding consultations, pro bono, and zero-fee), but
        scoped to a single client with no date bound. This is the "what a
        statement would bill right now" figure. Unlike the bulk generation
        picker, it does NOT exclude Inactive clients — on an individual file you
        still want to see what an inactive client owes. Drafts (locked = 0) are
        excluded, since they aren't billable yet.
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT class, fee, base_fee, base_price
            FROM entries
            WHERE client_id = ?
            AND class IN ('session', 'absence', 'item')
            AND statement_id IS NULL
            AND locked = 1
            AND (
                (class = 'session' AND fee > 0)
                OR (class = 'absence' AND (fee > 0 OR base_fee > 0))
                OR (class = 'item' AND (fee != 0 OR base_price != 0))
            )
        """, (client_id,))

        total = dec(0)
        for row in cursor.fetchall():
            # Same fee resolution as find_unbilled: prefer fee, fall back to
            # base_price (items) / base_fee (absences).
            fee = row['fee']
            if not fee:
                if row['class'] == 'item':
                    fee = row['base_price'] or 0
                elif row['class'] == 'absence':
                    fee = row['base_fee'] or 0
                else:
                    fee = 0
            total += dec(fee)

        return quantize_cents(total)

    def get_outstanding_balance(self, client_id: int) -> Decimal:
        """Total still owing on this client's generated statement portions.

        Sum of (amount_due - amount_paid) over statement_portions that are not
        fully paid or written off — includes 'ready' (generated but not yet
        sent), 'sent', and 'partial'. Exact Decimal arithmetic via core.money.
        This is separate from get_unbilled_total: work that has been billed but
        not yet paid, vs. work not yet billed.
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT amount_due, amount_paid
            FROM statement_portions
            WHERE client_id = ?
            AND status NOT IN ('paid', 'written_off')
        """, (client_id,))

        total = dec(0)
        for row in cursor.fetchall():
            total += dec(row['amount_due']) - dec(row['amount_paid'] or 0)

        return quantize_cents(total)

    def get_prior_outstanding(self, client_id: int,
                              exclude_statement_entry_id: int,
                              guardian_number: Optional[int]) -> Decimal:
        """Balance still owing on statements BILLED BEFORE the given one.

        Sum of (amount_due - amount_paid) over this client's OTHER statement
        portions with status 'sent' or 'partial', scoped to the same payer
        (guardian_number, NULL-safe via IS). Used by the statement PDF's
        "Previous balance" line, so the scoping rules matter:

        - The current statement's own portion is excluded (it IS the
          "current charges").
        - 'ready' portions are excluded: a statement the client has never
          received is not a "previous balance" they've been ignoring —
          in particular, two statements generated in the same batch must
          not list each other.
        - 'paid'/'written_off' are excluded as settled.
        - Guardian scoping means each guardian's PDF shows only THEIR
          prior balance on a split statement.

        Display-only: nothing here changes amount_due or how payments and
        write-offs apply (each statement still settles separately).
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT amount_due, amount_paid
            FROM statement_portions
            WHERE client_id = ?
            AND statement_entry_id != ?
            AND guardian_number IS ?
            AND status IN ('sent', 'partial')
        """, (client_id, exclude_statement_entry_id, guardian_number))

        total = dec(0)
        for row in cursor.fetchall():
            total += dec(row['amount_due']) - dec(row['amount_paid'] or 0)

        return quantize_cents(total)

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
        
        return dict(row) if row else None
