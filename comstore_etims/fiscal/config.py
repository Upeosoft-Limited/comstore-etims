"""The one accessor for Comstore Settings."""

import frappe

from comstore_etims.fiscal.codes import code_prefix, tax_letter

SETTINGS = "Comstore Settings"


class ComstoreConfig:
	"""Read-only view of Comstore Settings, so no caller reads fields ad hoc."""

	def __init__(self, doc=None):
		self._doc = doc or frappe.get_cached_doc(SETTINGS)

	@property
	def enabled(self) -> bool:
		return bool(self._doc.enabled)

	@property
	def test_mode(self) -> bool:
		return bool(self._doc.test_mode)

	@property
	def sign_on_submit(self) -> bool:
		return bool(self._doc.sign_on_submit)

	@property
	def default_device(self) -> str | None:
		return self._doc.default_device

	@property
	def default_tax_type(self) -> str:
		return tax_letter(self._doc.default_tax_type) or "B"

	@property
	def zero_rate_tax_type(self) -> str:
		return tax_letter(self._doc.zero_rate_tax_type) or "A"

	@property
	def default_refund_reason(self) -> str:
		return code_prefix(self._doc.default_refund_reason) or "06"

	@property
	def retry_limit(self) -> int:
		return int(self._doc.retry_limit or 5)

	@property
	def item_defaults(self) -> dict:
		return {
			"item_cls_code": self._doc.default_item_cls_code or "99010000",
			"pkg_unit_cd": self._doc.default_pkg_unit or "BG-Bag",
			"qty_unit_cd": self._doc.default_qty_unit or "U-Pieces/item [Number]",
			"orgn_nat_cd": self._doc.default_origin or "KE-KENYA",
			"opening_stock": int(self._doc.opening_device_stock or 1000000),
		}
