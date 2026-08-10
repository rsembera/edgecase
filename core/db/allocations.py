"""Payment allocations — one payment, many statements.

Carry-forward statements PRESENT a balance-forward total while the system
TRACKS open items per statement portion. The two models disagree at exactly
one moment: when the client pays a lump sum covering several statements.
See docs/Payment_Allocation_Plan.md.

The model here is the standard receivables one (QuickBooks / Xero "Receive
Payment"): ONE ledger entry records the deposit that actually arrived, and
a sub-ledger row per statement portion records what it settled.

Table shape
-----------
Each row is a claim on a ledger entry:

- ``portion_id`` NOT NULL  -> an amount applied to that statement portion
- ``portion_id`` NULL      -> an unallocated remainder held as a CREDIT on
  the client's account (overpayment / prepayment)

The invariant for any entry written by record_payment is::

    SUM(payment_allocations.amount) == entries.total_amount

Credit is read from the explicit NULL-portion rows, never derived as
"total minus allocations" — legacy entries that predate this table (or that
the backfill could not resolve) have no rows at all, and must not be
mistaken for credit.

``entry_id`` (not ``income_entry_id``) because refunds allocate too, and a
refund is an expense-class entry with a negative allocation.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional

import sqlcipher3 as sqlite3

from core.money import dec, quantize_cents


class AllocationMixin:

    # ========================================================================
    # READS
    # ========================================================================

    def get_client_outstanding_portions(
            self, client_id: int,
            guardian_number: Optional[int]) -> List[Dict[str, Any]]:
        """Open statement portions for one payer, oldest statement first.

        The allocation set for a payment. Scoped exactly as
        get_prior_outstanding is (core/db/clients.py): status 'sent' or
        'partial' only, and the same guardian_number (NULL-safe via IS), so
        guardian 1's payment can never settle guardian 2's portion.

        'ready' is excluded for the same reason it is excluded from the
        PDF's Previous balance: a statement the client has never received
        is not something they are paying off.

        Each row carries the parent statement's total and tax so pro-rata
        tax can be computed PER ALLOCATION — two statements can have
        different tax rates, and one prorata call on the payment total
        would be silently wrong.
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT sp.id, sp.statement_entry_id, sp.client_id,
                   sp.guardian_number, sp.amount_due, sp.amount_paid,
                   sp.status, sp.created_at,
                   e.description AS statement_description,
                   e.created_at AS statement_date,
                   e.statement_total, e.statement_tax_total
            FROM statement_portions sp
            JOIN entries e ON sp.statement_entry_id = e.id
            WHERE sp.client_id = ?
            AND sp.guardian_number IS ?
            AND sp.status IN ('sent', 'partial')
            ORDER BY e.created_at ASC, sp.id ASC
        """, (client_id, guardian_number))

        portions = []
        for row in cursor.fetchall():
            portion = dict(row)
            portion['amount_owing'] = quantize_cents(
                dec(portion['amount_due']) - dec(portion['amount_paid']))
            portions.append(portion)
        return portions

    def get_payment_allocations(self, entry_id: int) -> List[Dict[str, Any]]:
        """All allocation rows for one ledger entry (credit row included)."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM payment_allocations
            WHERE entry_id = ?
            ORDER BY portion_id IS NULL, id
        """, (entry_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_portion_allocations(self, portion_id: int) -> List[Dict[str, Any]]:
        """All allocation rows that settled one statement portion."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM payment_allocations
            WHERE portion_id = ?
            ORDER BY created_at, id
        """, (portion_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_allocated_total(self, entry_id: int) -> Decimal:
        """Sum of every allocation row on an entry, credit row included.

        For an entry written by record_payment this equals the entry's
        total_amount — that is the invariant the table maintains.
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT amount FROM payment_allocations WHERE entry_id = ?
        """, (entry_id,))
        total = dec(0)
        for row in cursor.fetchall():
            total += dec(row[0])
        return quantize_cents(total)

    def get_client_credit(self, client_id: int,
                          guardian_number: Optional[int]) -> Decimal:
        """Unallocated credit held for one payer.

        Sum of the explicit NULL-portion rows, scoped to the same payer as
        the portions themselves. Guardian 1's overpayment must not reduce
        guardian 2's statement.
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT amount FROM payment_allocations
            WHERE client_id = ?
            AND guardian_number IS ?
            AND portion_id IS NULL
        """, (client_id, guardian_number))
        total = dec(0)
        for row in cursor.fetchall():
            total += dec(row[0])
        return quantize_cents(total)

    def get_credit_rows(self, client_id: int,
                        guardian_number: Optional[int]) -> List[Dict[str, Any]]:
        """Open credit rows for one payer, oldest first.

        Returned in the order they should be consumed by a new statement.
        """
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM payment_allocations
            WHERE client_id = ?
            AND guardian_number IS ?
            AND portion_id IS NULL
            AND amount > 0
            ORDER BY created_at ASC, id ASC
        """, (client_id, guardian_number))
        return [dict(row) for row in cursor.fetchall()]

    def get_client_credit_all_payers(self, client_id: int) -> Decimal:
        """Total credit across every payer scope for one client.

        For the client file's summary display only — allocation decisions
        always use the payer-scoped get_client_credit.
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT amount FROM payment_allocations
            WHERE client_id = ? AND portion_id IS NULL
        """, (client_id,))
        total = dec(0)
        for row in cursor.fetchall():
            total += dec(row[0])
        return quantize_cents(total)

    # ========================================================================
    # WRITES
    # ========================================================================

    def insert_allocation(self, cursor, entry_id: int,
                          portion_id: Optional[int], client_id: int,
                          guardian_number: Optional[int], amount,
                          tax_amount, now: int) -> int:
        """Write one allocation row on the CALLER'S cursor.

        Takes a cursor rather than opening its own connection so the whole
        payment — ledger entry, allocation rows, and the amount_paid /
        status updates on each portion — commits or rolls back as one
        transaction. A half-written payment would leave amount_paid
        disagreeing with the allocations that justify it.

        portion_id None writes a credit row (unallocated remainder).
        """
        from core.money import money_float

        cursor.execute("""
            INSERT INTO payment_allocations (
                entry_id, portion_id, client_id, guardian_number,
                amount, tax_amount, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entry_id, portion_id, client_id, guardian_number,
              money_float(amount),
              None if tax_amount is None else money_float(tax_amount),
              now))
        return cursor.lastrowid

    # ========================================================================
    # BACKFILL
    # ========================================================================

    def backfill_payment_allocations(self, verbose: bool = False) -> Dict[str, int]:
        """Give every pre-existing payment an allocation row. Idempotent.

        Payments recorded before this table existed carry their target as
        entries.statement_id — one statement, one payment, by construction
        (the old mark_paid could not express anything else). Each becomes a
        single allocation row for its full amount.

        Resolving the PORTION from the statement needs care on a guardian
        split, where one statement has two portions: the guardian is
        recovered from the description the old mark_paid wrote
        ("Client Payment (Guardian 1)"). An entry whose portion cannot be
        resolved unambiguously is SKIPPED rather than guessed — a wrong
        allocation is worse than a missing one, and a missing one is
        harmless because credit is read from explicit NULL-portion rows,
        never inferred from an absence.

        Safe to re-run: entries that already have any allocation row are
        left alone.

        Returns counts: created / skipped_ambiguous / already_allocated.
        """
        import re
        import time as _time

        conn = self.connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.id, e.total_amount, e.tax_amount, e.description,
                   e.statement_id
            FROM entries e
            WHERE e.class = 'income'
            AND e.statement_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM payment_allocations pa WHERE pa.entry_id = e.id
            )
            ORDER BY e.id
        """)
        candidates = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT COUNT(DISTINCT entry_id) FROM payment_allocations
        """)
        already = cursor.fetchone()[0]

        now = int(_time.time())
        created = 0
        skipped = 0

        for entry in candidates:
            cursor.execute("""
                SELECT id, client_id, guardian_number
                FROM statement_portions
                WHERE statement_entry_id = ?
                ORDER BY guardian_number
            """, (entry['statement_id'],))
            portions = [dict(row) for row in cursor.fetchall()]

            if not portions:
                skipped += 1
                continue

            if len(portions) == 1:
                target = portions[0]
            else:
                match = re.search(r'Guardian (\d+)',
                                  entry.get('description') or '')
                if not match:
                    skipped += 1
                    continue
                guardian = int(match.group(1))
                matches = [p for p in portions
                           if p['guardian_number'] == guardian]
                if len(matches) != 1:
                    skipped += 1
                    continue
                target = matches[0]

            self.insert_allocation(
                cursor, entry['id'], target['id'], target['client_id'],
                target['guardian_number'], entry['total_amount'],
                entry['tax_amount'], now)
            created += 1

        conn.commit()

        result = {'created': created, 'skipped_ambiguous': skipped,
                  'already_allocated': already}
        if verbose:
            print(f"Payment allocation backfill: {created} created, "
                  f"{skipped} skipped (ambiguous), "
                  f"{already} entries already allocated")
        return result
