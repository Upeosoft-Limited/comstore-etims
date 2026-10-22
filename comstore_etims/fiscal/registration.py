"""Items and buyers in the shape the device registers them."""

import frappe
from frappe.utils import cint

from comstore_etims.fiscal.codes import code_prefix
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.device_names import ascii_text, device_barcode, device_name
from comstore_etims.fiscal.invoice_payload import KRA_PIN
from comstore_etims.fiscal.money import money_text
from comstore_etims.fiscal.tax_type import TaxTypeResolver


def _next_number(doctype: str, field: str) -> int:
	return cint(frappe.db.sql(f"SELECT MAX(`{field}`) FROM `tab{doctype}`")[0][0]) + 1


class PluItem:
	"""One ERPNext Item as a device PLU record."""

	def __init__(self, item_code: str, config: ComstoreConfig):
		self.item = frappe.get_doc("Item", item_code)
		self.config = config

	def plu_no(self) -> int:
		"""Stable per item: given once, then reused on every upload and sale."""
		if not self.item.comstore_plu_no:
			self.item.db_set("comstore_plu_no", _next_number("Item", "comstore_plu_no"))
		return self.item.comstore_plu_no

	def as_dict(self) -> dict:
		plu_no = self.plu_no()
		defaults = self.config.item_defaults
		barcode = self.item.barcodes[0].barcode if self.item.get("barcodes") else ""
		return {
			"plu_no": str(plu_no),
			"barcode": device_barcode(barcode, plu_no),
			"plu_name": device_name(self.item.item_name),
			"unit_price": money_text(self._price()),
			"item_cls_code": self.item.comstore_item_cls_code or defaults["item_cls_code"],
			"pkg_unit_cd": self.item.comstore_pkg_unit or defaults["pkg_unit_cd"],
			"qty_unit_cd": self.item.comstore_qty_unit or defaults["qty_unit_cd"],
			"orgn_nat_cd": self.item.comstore_origin or defaults["orgn_nat_cd"],
			"btch_no": "",
			"add_info": "",
			"tax_type": TaxTypeResolver(self.config).for_item(self.item.name),
			"sfty_qty": "0",
			"type_code": code_prefix(self.item.comstore_type_code) or ("02" if self.item.is_stock_item else "03"),
			"isrc_aplcb_yn": "0",
			# The device keeps its own stock and refuses a sale it thinks is out of
			# stock (E090/E351). ERPNext owns the real stock, so a new item gets a
			# large allowance once; later uploads leave the device's count alone.
			"change_qty": "0" if self.item.comstore_uploaded else str(defaults["opening_stock"]),
			"stocks": "",
			"use_yor_n": "0" if self.item.disabled else "1",
		}

	def _price(self) -> float:
		return frappe.db.get_value(
			"Item Price", {"item_code": self.item.name, "selling": 1}, "price_list_rate"
		) or self.item.standard_rate or 0


class Buyer:
	"""One Customer with a KRA PIN as a device buyer record."""

	def __init__(self, customer: str):
		self.customer = frappe.get_doc("Customer", customer)

	@staticmethod
	def eligible(customer: str) -> bool:
		pin = (frappe.db.get_value("Customer", customer, "tax_id") or "").strip().upper()
		return bool(KRA_PIN.match(pin))

	def buyer_no(self) -> int:
		if not self.customer.comstore_buyer_no:
			self.customer.db_set("comstore_buyer_no", _next_number("Customer", "comstore_buyer_no"))
		return self.customer.comstore_buyer_no

	def as_dict(self) -> dict:
		return {
			"BuyerNo": str(self.buyer_no()),
			"BuyerPin": self.customer.tax_id.strip().upper(),
			"BuyerName": ascii_text(self.customer.customer_name, 50),
			"BuyerMobileNo": ascii_text(self.customer.get("mobile_no")) or "N/A",
			"Address": "N/A",
			"Email": ascii_text(self.customer.get("email_id")) or "N/A",
			"FaxNo": "N/A",
		}
