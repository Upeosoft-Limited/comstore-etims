"""Tax categories: which one a line is in, and the totals the device checks."""

from decimal import Decimal

from comstore_etims.fiscal.codes import TAX_FIELDS, TAX_RATES
from comstore_etims.fiscal.money import cents, money_text


class TaxBuckets:
	"""Gross amounts per category, turned into the net/VAT pairs of the sign structure.

	The device recomputes net as gross / (1 + rate) per category and rejects an
	invoice whose figures disagree (E341), so this does the same sum the same way.
	"""

	def __init__(self):
		self._gross: dict[str, Decimal] = {}

	def add(self, letter: str, gross) -> None:
		self._gross[letter] = self._gross.get(letter, Decimal("0")) + cents(gross)

	@property
	def total(self) -> Decimal:
		return sum(self._gross.values(), Decimal("0"))

	def split(self, letter: str) -> tuple[Decimal, Decimal]:
		"""(net, vat) for one category."""
		gross = self._gross.get(letter, Decimal("0"))
		net = cents(gross / (1 + TAX_RATES[letter]))
		return net, gross - net

	def fields(self) -> dict[str, str]:
		"""The sign structure's tax fields. A to D are always sent ("0" when unused);
		E is sent empty when unused, as the device's own examples do."""
		out = {}
		for letter, label in TAX_FIELDS.items():
			if letter == "E" and letter not in self._gross:
				out[f"{label} net"] = out[f"{label} value"] = ""
				continue
			net, vat = self.split(letter)
			out[f"{label} net"] = money_text(net) if letter in self._gross else "0"
			out[f"{label} value"] = money_text(vat) if letter in self._gross else "0"
		return out
