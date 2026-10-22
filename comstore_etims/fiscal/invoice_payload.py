"""A Sales Invoice (or return) as the device's complete-workflow request."""

import re
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt

from comstore_etims.fiscal.codes import TAX_RATES, code_prefix
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.device_names import device_barcode, device_name
from comstore_etims.fiscal.money import cents, money_text
from comstore_etims.fiscal.sale_line import SaleLine
from comstore_etims.fiscal.tax import TaxBuckets
from comstore_etims.fiscal.tax_type import TaxTypeResolver

KRA_PIN = re.compile(r"^[A-Z]\d{9}[A-Z]$")
# What ERPNext's totals and the device's may differ by before we refuse.
TOLERANCE = Decimal("0.05")


class InvoicePayload:
	"""Builds the request body for one invoice. Refuses, in words, what the device would."""

	def __init__(self, invoice, serial_number: str, config: ComstoreConfig):
		self.invoice = invoice
		self.serial_number = serial_number
		self.config = config
		self.tax_types = TaxTypeResolver(config)
		self.buckets = TaxBuckets()

	def build(self) -> dict:
		lines = [self._line(row) for row in self.invoice.items]
		self._check_total()
		return {
			"sn": self.serial_number,
			"is_test": self.config.test_mode,
			"plu_data": [line.as_plu_data() for line in lines],
			"sign_structure": self._sign_structure(),
		}

	# --- lines -----------------------------------------------------------
	def _line(self, row) -> SaleLine:
		letter = self.tax_types.for_item(row.item_code)
		self._check_rate(row, letter)
		gross = cents(abs(flt(row.base_net_amount)) + abs(self._line_tax(row)))
		self.buckets.add(letter, gross)
		plu_no = frappe.db.get_value("Item", row.item_code, "comstore_plu_no")
		return SaleLine.of(
			name=device_name(row.item_name),
			barcode=device_barcode(row.barcode, plu_no or ""),
			qty=row.qty,
			gross=gross,
		)

	def _tax_rows(self, row):
		return [d for d in self.invoice.get("item_wise_tax_details") or [] if d.item_row == row.name]

	def _line_tax(self, row) -> float:
		return sum(flt(d.amount) for d in self._tax_rows(row))

	def _check_rate(self, row, letter: str) -> None:
		charged = Decimal(str(round(sum(flt(d.rate) for d in self._tax_rows(row)), 2)))
		expected = TAX_RATES[letter] * 100
		if charged != expected:
			frappe.throw(
				_("Row {0} ({1}) is charged {2}% tax but its eTIMS tax type {3} is {4}%. Set the "
				  "item's eTIMS Tax Type or its Item Tax Template so the two agree.").format(
					row.idx, row.item_code, charged, letter, expected
				)
			)

	def _check_total(self) -> None:
		invoice_total = abs(cents(self.invoice.base_grand_total))
		if abs(self.buckets.total - invoice_total) > TOLERANCE:
			frappe.throw(
				_("The lines come to {0} with their tax but the invoice total is {1}. Charges not "
				  "tied to an item (shipping, other taxes) cannot be sent to eTIMS.").format(
					money_text(self.buckets.total), money_text(invoice_total)
				)
			)

	# --- sign structure -----------------------------------------------------
	def _sign_structure(self) -> dict:
		cash, card = self._payments()
		structure = {
			"SignType": "0" if self.config.test_mode else "1",
			"DiscAmt": "0",
			"CashAmt": money_text(cash),
			"CheckAmt": "0",
			"CardAmt": money_text(card),
			"InvoiceType": "credit" if self.invoice.is_return else "original",
			"relevantInvoiceNumber": self._original_number(),
			"pinOfBuyer": self._buyer_pin(),
			"exemptionNumber": "",
			"pinOfshop": self._shop_pin(),
			"TraderSystemInvoiceNumber": self.invoice.name,
		}
		structure.update(self.buckets.fields())
		structure.update({
			"Schg F(10.00%) net": "", "Schg F(10.00%) value": "",
			"Levy G(2.00%) net": "", "Levy G(2.00%) value": "",
			"rfdRsnCd": self._refund_reason(),
			"NetTotal": "",
			"EXCHANGERate": "",
		})
		return structure

	def _payments(self) -> tuple[Decimal, Decimal]:
		"""(cash, card). Money not taken in cash counts as card; anything unpaid is cash,
		so the two always add up to the lines (E341)."""
		total = self.buckets.total
		card = sum(
			(abs(cents(p.base_amount)) for p in self.invoice.get("payments") or [] if p.type != "Cash"),
			Decimal("0"),
		)
		card = min(card, total)
		return total - card, card

	def _original_number(self) -> str:
		if not self.invoice.is_return:
			return ""
		number = frappe.db.get_value("Sales Invoice", self.invoice.return_against, "comstore_cu_invoice_no")
		if not number:
			frappe.throw(
				_("{0} has no eTIMS invoice number, so this return cannot be credited on eTIMS. "
				  "Sign the original first.").format(self.invoice.return_against)
			)
		return number.lstrip("0") or "0"

	def _refund_reason(self) -> str:
		if not self.invoice.is_return:
			return ""
		return code_prefix(self.invoice.get("comstore_refund_reason")) or self.config.default_refund_reason

	def _buyer_pin(self) -> str:
		pin = (self.invoice.get("tax_id") or "").strip().upper()
		return pin if KRA_PIN.match(pin) else ""

	def _shop_pin(self) -> str:
		pin = (self.invoice.get("company_tax_id")
			or frappe.db.get_value("Company", self.invoice.company, "tax_id") or "").strip().upper()
		if not KRA_PIN.match(pin):
			frappe.throw(
				_("Company {0} needs its KRA PIN (Tax ID, e.g. P000111222Z) before invoices can be "
				  "signed.").format(self.invoice.company)
			)
		return pin
