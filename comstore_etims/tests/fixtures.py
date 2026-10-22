"""Test set-up: a Kenyan company, a device, items, and a fake Comstore API."""

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.utils import getdate, nowdate

from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.install import RELAY_ROLE

COMPANY = "Comstore Test"
ABBR = "CMT"
SHOP_PIN = "P000111222Z"
SERIAL = "DEMO0001"
RELAY_USER = "comstore-relay@example.com"


def before_tests():
	"""A fresh ERPNext site has no company; finish the setup wizard for one."""
	if frappe.is_setup_complete():
		return
	year = getdate(nowdate()).year
	setup_complete({
		"language": "English", "email": "test@example.com", "full_name": "Test User", "password": "test",
		"country": "Kenya", "timezone": "Africa/Nairobi", "currency": "KES",
		"company_name": COMPANY, "company_abbr": ABBR, "chart_of_accounts": "Standard",
		"fy_start_date": f"{year}-01-01", "fy_end_date": f"{year}-12-31",
	})
	frappe.db.commit()


def company() -> str:
	return frappe.db.get_value("Company", {"abbr": ABBR}, "name") or frappe.defaults.get_global_default("company")


def give_shop_pin() -> None:
	frappe.db.set_value("Company", company(), "tax_id", SHOP_PIN)


def relay_user() -> str:
	if not frappe.db.exists("User", RELAY_USER):
		frappe.get_doc({"doctype": "User", "email": RELAY_USER, "first_name": "Relay",
						"send_welcome_email": 0, "roles": [{"role": RELAY_ROLE}]}).insert(ignore_permissions=True)
	return RELAY_USER


def device() -> "frappe.Document":
	if not frappe.db.exists("Comstore Device", SERIAL):
		frappe.get_doc({
			"doctype": "Comstore Device", "serial_number": SERIAL, "company": company(),
			"transport": "Relay", "relay_user": relay_user(), "device_ip": "192.168.1.100",
		}).insert(ignore_permissions=True)
	return frappe.get_doc("Comstore Device", SERIAL)


def settings(**values):
	give_shop_pin()
	doc = frappe.get_single("Comstore Settings")
	doc.update({"enabled": 1, "test_mode": 1, "sign_on_submit": 0, "default_device": device().name,
				"default_tax_type": "B-16.00%", "zero_rate_tax_type": "A-Exempt", **values})
	doc.save(ignore_permissions=True)
	return doc


def item(code: str, tax_type: str = "", stock: int = 0) -> str:
	if not frappe.db.exists("Item", code):
		frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code, "item_group": _leaf("Item Group"),
			"stock_uom": "Nos", "is_stock_item": stock, "is_sales_item": 1, "comstore_tax_type": tax_type,
		}).insert(ignore_permissions=True)
	return code


def vat_account() -> str:
	"""A 16% output VAT account to charge on net total."""
	found = frappe.db.get_value("Account", {"company": company(), "account_name": "Comstore VAT"}, "name")
	if found:
		return found
	parent = frappe.db.get_value("Account", {"company": company(), "account_name": "Duties and Taxes"}, "name")
	return frappe.get_doc({"doctype": "Account", "account_name": "Comstore VAT", "company": company(),
						   "parent_account": parent, "account_type": "Tax", "tax_rate": 16}).insert(ignore_permissions=True).name


def invoice(lines, taxes: str | None = None, customer: str | None = None, submit: bool = True, **extra):
	"""lines: [(item_code, qty, rate)]."""
	doc = frappe.get_doc({
		"doctype": "Sales Invoice", "company": company(), "customer": customer or _customer(),
		"posting_date": nowdate(), "due_date": nowdate(), "set_posting_time": 1,
		"items": [{"item_code": c, "qty": q, "rate": r} for c, q, r in lines], **extra,
	})
	if taxes:
		doc.append("taxes", {"charge_type": "On Net Total", "account_head": taxes, "rate": 16, "description": "VAT 16%"})
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _customer(name: str = "Comstore Buyer", tax_id: str = "") -> str:
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_group": _leaf("Customer Group"),
						"territory": _leaf("Territory"), "tax_id": tax_id}).insert(ignore_permissions=True)
	return name


def _leaf(doctype: str) -> str:
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft")


def customer(name: str, tax_id: str = "") -> str:
	return _customer(name, tax_id)


class FakeClient:
	"""Stands in for ComstoreClient: records calls, answers with a canned Outcome."""

	def __init__(self, outcome: Outcome):
		self.outcome = outcome
		self.calls = []

	def call(self, method, path, body=None):
		self.calls.append((method, path, body))
		return self.outcome


def signed_reply(invoice_name: str, cu_no: str = "0000101") -> Outcome:
	return Outcome(status=200, body={
		"success": True,
		"message": "Signature generated successfully (attempt 1)",
		"serial_number": SERIAL,
		"invoice_number": invoice_name,
		"scu_id": "KRACU0000000001",
		"cu-inv-no": cu_no,
		"internal-data": "TEST-INTL-DATA-0000-0000-0000-01",
		"Receipt Signature": "TEST-RCPT-SIGN-0001",
		"signature_link": "https://etims.example/receipt?Data=X",
		"transmit_status": "Invoice has been transmitted to eTIMS.",
	})
