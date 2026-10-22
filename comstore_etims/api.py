"""Desk actions: buttons on the Sales Invoice and the Comstore Device."""

import frappe
from frappe import _

from comstore_etims.fiscal import operations
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.registration import Buyer
from comstore_etims.fiscal.request_queue import RequestQueue
from comstore_etims.fiscal.signer import InvoiceSigner

MANAGERS = ("System Manager", "Accounts Manager")
ITEM_BATCH = 100
BUYER_BATCH = 500  # the device's own limit per request


def _device(name: str):
	frappe.only_for(MANAGERS)
	return frappe.get_doc("Comstore Device", name)


def _queued(request) -> dict:
	return {"request": request.name, "status": request.status}


@frappe.whitelist(methods=["POST"])
def sign_invoice(invoice: str) -> dict | None:
	"""Sign now, or try again after a failure."""
	frappe.get_doc("Sales Invoice", invoice).check_permission("submit")
	request = InvoiceSigner(invoice).sign()
	return _queued(request) if request else None


@frappe.whitelist(methods=["POST"])
def check_health(device: str) -> dict:
	return _queued(RequestQueue.submit(operations.Health(_device(device))))


@frappe.whitelist(methods=["POST"])
def check_invoice_status(device: str) -> dict:
	return _queued(RequestQueue.submit(operations.InvoiceStatus(_device(device))))


@frappe.whitelist(methods=["POST"])
def push_pending_invoices(device: str) -> dict:
	return _queued(RequestQueue.submit(operations.ManualUpload(_device(device))))


@frappe.whitelist(methods=["POST"])
def initialise(device: str) -> dict:
	doc = _device(device)
	if not doc.device_ip:
		frappe.throw(_("Set the device's IP address first."))
	return _queued(RequestQueue.submit(operations.Initialise(doc)))


@frappe.whitelist(methods=["POST"])
def restart(device: str) -> dict:
	doc = _device(device)
	if not doc.device_ip:
		frappe.throw(_("Set the device's IP address first."))
	return _queued(RequestQueue.submit(operations.Restart(doc)))


@frappe.whitelist(methods=["POST"])
def upload_items(device: str, only_new: int = 1) -> dict:
	"""Register selling items on the device, in batches. Items must be there before they can be sold."""
	doc = _device(device)
	filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
	if int(only_new):
		filters["comstore_uploaded"] = 0
	codes = frappe.get_all("Item", filters=filters, pluck="name", order_by="creation asc")
	config = ComstoreConfig()
	requests = [
		RequestQueue.submit(operations.UploadItems(doc, codes[i : i + ITEM_BATCH], config))
		for i in range(0, len(codes), ITEM_BATCH)
	]
	return {"items": len(codes), "requests": [r.name for r in requests]}


@frappe.whitelist(methods=["POST"])
def upload_buyers(device: str) -> dict:
	"""Register customers that have a valid KRA PIN."""
	doc = _device(device)
	customers = [c for c in frappe.get_all("Customer", filters={"disabled": 0}, pluck="name") if Buyer.eligible(c)]
	requests = [
		RequestQueue.submit(operations.UploadBuyers(doc, customers[i : i + BUYER_BATCH]))
		for i in range(0, len(customers), BUYER_BATCH)
	]
	return {"buyers": len(customers), "requests": [r.name for r in requests]}
