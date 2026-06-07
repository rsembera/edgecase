"""
EdgeCase Billing Calculations

Pure functions for statement totals, guardian splits, payment
application, and pro-rata tax. Extracted from web/blueprints/statements.py
so the money logic is testable without a Flask request context
(CODE_REVIEW.md M1: the previous float arithmetic accumulated rounding
error and needed a `<= 0.01` fudge to decide when a balance was paid).

All arithmetic is Decimal via core.money; callers convert to floats for
storage with money_float().
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from core.money import dec, quantize_cents, to_cents


def entry_fee(entry: Dict[str, Any]) -> Decimal:
    """Billable fee for an entry, with legacy fallbacks per class."""
    fee = dec(entry.get('fee'))
    if fee:
        return quantize_cents(fee)
    if entry.get('class') == 'item':
        return quantize_cents(dec(entry.get('base_price')))
    if entry.get('class') == 'absence':
        return quantize_cents(dec(entry.get('base_fee')))
    return Decimal('0.00')


def entry_tax(entry: Dict[str, Any]) -> Decimal:
    """Tax portion of an entry's fee (fee - base), never negative."""
    fee = entry_fee(entry)
    cls = entry.get('class')
    if cls == 'session':
        base = dec(entry.get('base_fee'))
    elif cls == 'absence':
        base = dec(entry.get('base_fee')) or dec(entry.get('base_price'))
    elif cls == 'item':
        base = dec(entry.get('base_price'))
    else:
        return Decimal('0.00')
    tax = quantize_cents(fee - quantize_cents(base))
    return max(Decimal('0.00'), tax)


def compute_statement_totals(entries: List[Dict[str, Any]]) -> Tuple[Decimal, Decimal]:
    """Statement total and total tax across billable entries."""
    total = Decimal('0.00')
    total_tax = Decimal('0.00')
    for e in entries:
        total += entry_fee(e)
        total_tax += entry_tax(e)
    return total, total_tax


def split_guardian_amounts(entries: List[Dict[str, Any]],
                           profile: Dict[str, Any],
                           total: Decimal) -> List[Tuple[int, Decimal]]:
    """Compute guardian portions for a minor's statement.

    Items with explicit guardian amounts use those; everything else is
    split by guardian1_pays_percent, with guardian 2 receiving the EXACT
    remainder (so the portions always sum to the percentage total —
    odd cents go to guardian 2 by construction).

    Returns a list of (guardian_number, amount) with amount > 0, except
    guardian 1 is always present (even at 0 due) to carry the billing
    relationship.
    """
    has_g2 = bool(profile.get('has_guardian2') and profile.get('guardian2_name'))

    if not has_g2:
        # Single guardian pays the full statement amount; the percent
        # field is hidden in the UI in this case (CODE_REVIEW.md H3).
        return [(1, quantize_cents(total))]

    g1_percent = dec(profile.get('guardian1_pays_percent', 100) or 100)

    g1_explicit = Decimal('0.00')
    g2_explicit = Decimal('0.00')
    g1_from_percent = Decimal('0.00')
    g2_from_percent = Decimal('0.00')

    for e in entries:
        if e.get('class') == 'item' and e.get('guardian1_amount') is not None:
            g1_explicit += quantize_cents(dec(e.get('guardian1_amount')))
            g2_explicit += quantize_cents(dec(e.get('guardian2_amount')))
        else:
            # Split PER LINE ITEM so the itemized statement PDFs (which
            # show each guardian's share per line) sum to exactly these
            # portion amounts. Guardian 2 gets the exact remainder of
            # each line, so g1 + g2 always equals the line fee.
            fee = entry_fee(e)
            g1_line = quantize_cents(fee * g1_percent / 100)
            g1_line = min(g1_line, fee)  # sanity: never exceed the line
            g1_from_percent += g1_line
            g2_from_percent += fee - g1_line

    g1_amount = quantize_cents(g1_explicit + g1_from_percent)
    g2_amount = max(Decimal('0.00'), quantize_cents(g2_explicit + g2_from_percent))

    portions = [(1, g1_amount)]
    if g2_amount > 0:
        portions.append((2, g2_amount))
    return portions


def apply_payment(amount_due, amount_paid, payment_amount) -> Tuple[Decimal, Decimal, str]:
    """Apply a payment (negative = refund) to a portion.

    Returns (new_amount_paid, amount_owing, status) where status is
    'paid' when the owing balance is exactly zero cents or less —
    no floating-point fudge required.
    """
    new_paid = quantize_cents(dec(amount_paid) + dec(payment_amount))
    owing = quantize_cents(dec(amount_due) - new_paid)
    status = 'paid' if to_cents(owing) <= 0 else 'partial'
    return new_paid, owing, status


def prorata_tax(payment_amount, statement_tax, statement_total) -> Decimal:
    """Tax portion of a payment, pro-rated against the statement.

    Used for both payments (tax collected) and refunds (tax reversed —
    CODE_REVIEW.md L11). Returns 0 when the statement has no tax.
    """
    total = dec(statement_total)
    tax = dec(statement_tax)
    if to_cents(total) <= 0 or to_cents(tax) <= 0:
        return Decimal('0.00')
    return quantize_cents(dec(payment_amount) * tax / total)
