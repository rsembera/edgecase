"""
EdgeCase Money Primitives

All monetary arithmetic in EdgeCase goes through this module.

Design decision (see docs/Architecture_Decisions.md, "Money arithmetic"):
- Arithmetic is done in decimal.Decimal, quantized to cents with
  ROUND_HALF_UP at every boundary.
- Storage stays as SQLite REAL dollars. Every value written to the
  database passes through money_float(), so stored values are always
  exact cent quantities (float error < 2^-40 per value, never
  accumulated, and to_cents() recovers exact integer cents on read).
- Comparisons use integer cents (to_cents) — never float equality or
  epsilon fudges.
"""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')


def dec(value) -> Decimal:
    """Convert any numeric (or None/'' from the DB or a form) to Decimal.

    Floats are converted via str(), so a REAL read from SQLite becomes
    the decimal value it displays as, not its binary expansion.
    """
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_cents(value) -> Decimal:
    """Quantize a value to cents, rounding half up (0.005 -> 0.01)."""
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)


def to_cents(value) -> int:
    """Exact integer cents for comparisons (no float epsilon needed)."""
    return int(quantize_cents(value) * 100)


def money_float(value) -> float:
    """Quantize to cents and return a float for REAL-column storage."""
    return float(quantize_cents(value))


# ---------------------------------------------------------------------------
# Currency display helpers (CODE_REVIEW.md M13)
#
# Single source of truth for the currency-code → symbol table and the
# symbol+amount display format, previously triplicated across the PDF
# modules (pdf/generator.py, pdf/ledger_report.py, pdf/client_export.py).
# The historical copies differed in spacing/thousands behavior, so both
# are parameterized to preserve each PDF's existing appearance.
# ---------------------------------------------------------------------------

CURRENCY_SYMBOLS = {
    'CAD': '$', 'USD': '$', 'EUR': '€', 'GBP': '£',
    'AUD': '$', 'NZD': '$', 'JPY': '¥', 'CNY': '¥',
    'INR': '₹', 'MXN': '$', 'BRL': 'R$', 'CHF': 'CHF'
}


def get_currency_symbol(currency_code) -> str:
    """Convert a currency code to its display symbol (default '$')."""
    return CURRENCY_SYMBOLS.get(currency_code, '$')


def format_currency(amount, currency_code, thousands=True, space=False) -> str:
    """Format an amount with its currency symbol. None is treated as 0.

    Args:
        amount: numeric amount (None → 0)
        currency_code: e.g. 'CAD'; unknown codes fall back to '$'
        thousands: include thousands separators (1,234.56)
        space: put a space between symbol and amount ('$ 1,234.56')
    """
    symbol = get_currency_symbol(currency_code)
    if amount is None:
        amount = 0
    sep = ' ' if space else ''
    if thousands:
        return f"{symbol}{sep}{amount:,.2f}"
    return f"{symbol}{sep}{amount:.2f}"
