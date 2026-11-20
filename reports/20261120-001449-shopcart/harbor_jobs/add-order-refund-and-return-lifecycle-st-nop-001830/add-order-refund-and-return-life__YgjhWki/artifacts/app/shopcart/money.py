"""Money helpers. All amounts are Decimal values rounded to cents."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(value: Decimal | int | float | str) -> Decimal:
    """Convert a number to a Decimal rounded half-up to two places."""
    if isinstance(value, float):
        value = repr(value)
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, percent: Decimal | int | str) -> Decimal:
    """Return `percent` percent of `amount`, rounded to cents."""
    return to_money(Decimal(amount) * Decimal(percent) / Decimal(100))
