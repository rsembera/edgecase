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
