"""Money and number formatting for the device, which takes every figure as text."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value) -> Decimal:
	return Decimal(str(value or 0))


def cents(value) -> Decimal:
	return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def text(value) -> str:
	"""A Decimal as the device wants it: no exponent, no trailing zeros past the point."""
	d = to_decimal(value)
	s = format(d, "f")
	if "." in s:
		s = s.rstrip("0").rstrip(".")
	return s or "0"


def money_text(value) -> str:
	return format(cents(value), "f")
