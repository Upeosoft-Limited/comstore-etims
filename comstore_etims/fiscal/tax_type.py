"""Which eTIMS tax category an item belongs to."""

from decimal import Decimal

import frappe
from frappe.utils import flt

from comstore_etims.fiscal.codes import TAX_RATES, tax_letter
from comstore_etims.fiscal.config import ComstoreConfig


class TaxTypeResolver:
	"""One answer per item, used both to register it and to sell it.

	The device refuses a sale whose tax category differs from the one the item
	was registered with (E321), so the upload and the invoice must ask here.
	Order: the item's own eTIMS tax type, else its Item Tax Template's rate,
	else the shop's default.
	"""

	def __init__(self, config: ComstoreConfig):
		self.config = config

	def for_item(self, item_code: str) -> str:
		explicit = tax_letter(frappe.db.get_value("Item", item_code, "comstore_tax_type"))
		return explicit or self._from_template(item_code) or self.config.default_tax_type

	def _from_template(self, item_code: str) -> str | None:
		templates = frappe.get_all(
			"Item Tax", filters={"parent": item_code, "parenttype": "Item"}, pluck="item_tax_template"
		)
		if not templates:
			return None
		rates = frappe.get_all(
			"Item Tax Template Detail",
			filters={"parent": ["in", templates], "not_applicable": 0},
			pluck="tax_rate",
		)
		return self.for_rate(max((flt(r) for r in rates), default=0))

	def for_rate(self, percent: float) -> str:
		rate = Decimal(str(round(flt(percent), 2))) / 100
		for letter, known in TAX_RATES.items():
			if known and known == rate:
				return letter
		return self.config.zero_rate_tax_type if not rate else self.config.default_tax_type
