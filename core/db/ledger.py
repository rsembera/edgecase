"""Ledger — practice accounting: payees, expense categories, and ledger entry
queries (income/expense reporting, tax summaries).

Extracted from core/database.py (Step 3). Relies on self.connect() and the
shared entry methods (add_entry etc.) from the base Database class.
"""
import time

import sqlcipher3 as sqlite3


class LedgerMixin:

    # EdgeCase Ledger - Database Methods

    # ============================================================================
    # PAYEE OPERATIONS
    # ============================================================================

    def add_payee(self, name: str) -> int:
        """Add a new payee to the payees table."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO payees (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        payee_id = cursor.lastrowid
        conn.commit()
        return payee_id

    def get_payee(self, payee_id: int) -> dict:
        """Get a single payee by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees WHERE id = ?", (payee_id,))
        payee = cursor.fetchone()
        
        return dict(payee) if payee else None

    def get_all_payees(self) -> list:
        """Get all payees ordered by name."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payees ORDER BY name ASC")
        payees = [dict(row) for row in cursor.fetchall()]
        
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
        return success

    def delete_payee(self, payee_id: int) -> bool:
        """Delete a payee (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this payee
        cursor.execute("SELECT COUNT(*) FROM entries WHERE payee_id = ?", (payee_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM payees WHERE id = ?", (payee_id,))
        success = cursor.rowcount > 0
        conn.commit()
        return success


    # ============================================================================
    # EXPENSE CATEGORY OPERATIONS
    # ============================================================================

    def add_expense_category(self, name: str) -> int:
        """Add a new expense category."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO expense_categories (name, created_at)
            VALUES (?, ?)
        """, (name, int(time.time())))
        
        category_id = cursor.lastrowid
        conn.commit()
        return category_id

    def get_expense_category(self, category_id: int) -> dict:
        """Get a single expense category by ID."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories WHERE id = ?", (category_id,))
        category = cursor.fetchone()
        
        return dict(category) if category else None

    def get_all_expense_categories(self) -> list:
        """Get all expense categories ordered by name."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories ORDER BY name ASC")
        categories = [dict(row) for row in cursor.fetchall()]
        
        return categories

    def get_expense_category_by_name(self, name: str) -> dict:
        """Get an expense category by name (case-insensitive)."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM expense_categories WHERE LOWER(name) = LOWER(?)", (name,))
        category = cursor.fetchone()
        
        return dict(category) if category else None

    def get_distinct_payee_names(self) -> list:
        """Get payee names from payees table for autocomplete."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM payees
            ORDER BY name ASC
        """)
        
        return [row[0] for row in cursor.fetchall()]

    def add_payee_if_new(self, name: str) -> int:
        """Add payee to table if it doesn't exist. Returns payee ID."""
        if not name:
            return None
        conn = self.connect()
        cursor = conn.cursor()
        # Check if exists first
        cursor.execute("SELECT id FROM payees WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return row[0]
        # Insert new
        cursor.execute("INSERT INTO payees (name, created_at) VALUES (?, ?)",
                       (name, int(time.time())))
        conn.commit()
        return cursor.lastrowid

    def get_distinct_payor_sources(self) -> list:
        """Get payor names from income_payors table for autocomplete."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM income_payors
            ORDER BY name ASC
        """)
        
        return [row[0] for row in cursor.fetchall()]

    def add_income_payor_if_new(self, name: str) -> None:
        """Add payor to income_payors table if it doesn't exist."""
        if not name:
            return
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO income_payors (name, created_at) VALUES (?, ?)",
                       (name, int(time.time())))
        conn.commit()

    def delete_income_payor(self, name: str) -> bool:
        """Delete a payor from income_payors table."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM income_payors WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

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
        return success

    def delete_expense_category(self, category_id: int) -> bool:
        """Delete an expense category (only if no expenses reference it)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Check if any expenses use this category
        cursor.execute("SELECT COUNT(*) FROM entries WHERE category_id = ?", (category_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            return False  # Cannot delete - has expenses
        
        cursor.execute("DELETE FROM expense_categories WHERE id = ?", (category_id,))
        success = cursor.rowcount > 0
        conn.commit()
        return success


    # ============================================================================
    # LEDGER ENTRY OPERATIONS
    # ============================================================================

    def get_all_ledger_entries(self, ledger_type: str = None) -> list:
        """
        Get all ledger entries (income and/or expense).
        
        Includes attachment_count via JOIN for performance.
        Joins payee and category names for display.
        
        Args:
            ledger_type: Optional filter - 'income' or 'expense' or None for both
        
        Returns:
            List of ledger entries sorted by date (newest first), then created_at
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT entries.*, 
                       COUNT(attachments.id) as attachment_count,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type = ?
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """, (ledger_type,))
        else:
            cursor.execute("""
                SELECT entries.*, 
                       COUNT(attachments.id) as attachment_count,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN attachments ON attachments.entry_id = entries.id
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type IN ('income', 'expense')
                GROUP BY entries.id
                ORDER BY entries.ledger_date DESC, entries.created_at DESC
            """)
        
        entries = [dict(row) for row in cursor.fetchall()]
        
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
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if ledger_type:
            cursor.execute("""
                SELECT entries.*,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type = ?
                AND entries.ledger_date BETWEEN ? AND ?
                ORDER BY entries.ledger_date ASC, entries.created_at ASC
            """, (ledger_type, start_date, end_date))
        else:
            cursor.execute("""
                SELECT entries.*,
                       payees.name as payee_name,
                       expense_categories.name as category_name
                FROM entries
                LEFT JOIN payees ON payees.id = entries.payee_id
                LEFT JOIN expense_categories ON expense_categories.id = entries.category_id
                WHERE entries.ledger_type IN ('income', 'expense')
                AND entries.ledger_date BETWEEN ? AND ?
                ORDER BY entries.ledger_date ASC, entries.created_at ASC
            """, (start_date, end_date))
        
        entries = [dict(row) for row in cursor.fetchall()]
        
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
