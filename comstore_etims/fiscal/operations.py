"""Each device call: what to send, and what to do with the answer.

A Comstore Request stores the method, path and body an operation built, so the
same request can be sent by the server (Direct) or by the shop's relay agent
(Relay). The answer comes back through ``apply`` either way.
"""

import json
from urllib.parse import quote

import frappe
from frappe.utils import cint, now_datetime

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.outcome import Outcome


class Operation:
	"""Base: a call with no reference document and nothing to record but the reply."""

	name = ""
	method = "GET"
	reference_doctype = None
	reference_name = None

	def __init__(self, device):
		self.device = device

	@property
	def serial(self) -> str:
		return quote(self.device.serial_number, safe="")

	def path(self) -> str:
		raise NotImplementedError

	def body(self) -> dict | None:
		return None

	@classmethod
	def apply(cls, request, outcome: Outcome) -> None:
		"""Record what the device said. Called once per finished request."""


class Health(Operation):
	name = codes.HEALTH

	def path(self):
		return "/api/health"

	@classmethod
	def apply(cls, request, outcome):
		frappe.db.set_value("Comstore Device", request.device, {
			"device_connection": outcome.get("deviceConnection") or ("Unreachable" if not outcome.status else ""),
			"api_version": outcome.get("version") or "",
			"last_seen": now_datetime() if outcome.status else None,
		})


class Initialise(Operation):
	name = codes.INITIALISE
	method = "POST"

	def path(self):
		return "/api/init"

	def body(self):
		return {"sn": self.device.serial_number, "ip": self.device.device_ip}


class InvoiceStatus(Operation):
	name = codes.INVOICE_STATUS

	def path(self):
		return f"/api/invoices/status/{self.serial}"

	@classmethod
	def apply(cls, request, outcome):
		if not outcome.ok:
			return
		frappe.db.set_value("Comstore Device", request.device, {
			"invoices_on_device": cint(outcome.get("invoices_on_device")),
			"invoices_uploaded": cint(outcome.get("invoices_uploaded_to_etims")),
			"pending_invoices": cint(outcome.get("pending_invoices")),
			"status_checked_on": now_datetime(),
		})


class ManualUpload(Operation):
	name = codes.MANUAL_UPLOAD
	method = "POST"

	def path(self):
		return f"/api/invoices/manually-upload/{self.serial}"


class Restart(Operation):
	name = codes.RESTART
	method = "POST"

	def path(self):
		return "/api/restart-device"

	def body(self):
		return {"ip_address": self.device.device_ip}


class UploadItems(Operation):
	name = codes.UPLOAD_ITEMS
	method = "POST"

	def __init__(self, device, item_codes: list[str], config: ComstoreConfig | None = None):
		super().__init__(device)
		self.item_codes = item_codes
		self.config = config or ComstoreConfig()

	def path(self):
		return "/api/upload-plu-data"

	def body(self):
		from comstore_etims.fiscal.registration import PluItem

		return {
			"sn": self.device.serial_number,
			"plu_items": [PluItem(code, self.config).as_dict() for code in self.item_codes],
			"from_no": 1,
			"end_no": 10000000,
			"update_flag": 0,
			"file_signal": "",
		}

	@classmethod
	def apply(cls, request, outcome):
		if not outcome.ok:
			return
		for plu in json.loads(request.request_body).get("plu_items", []):
			frappe.db.set_value("Item", {"comstore_plu_no": cint(plu["plu_no"])}, "comstore_uploaded", 1)


class UploadBuyers(Operation):
	name = codes.UPLOAD_BUYERS
	method = "POST"

	def __init__(self, device, customers: list[str]):
		super().__init__(device)
		self.customers = customers

	def path(self):
		return "/api/buyers/set"

	def body(self):
		from comstore_etims.fiscal.registration import Buyer

		buyers = [Buyer(c).as_dict() for c in self.customers]
		return {
			"SerialNumber": self.device.serial_number,
			"Buyers": buyers,
			"FromNumber": 1,
			"EndNumber": len(buyers),
			"UpdateFlag": 0,
		}


class SignInvoice(Operation):
	name = codes.SIGN_INVOICE
	method = "POST"
	reference_doctype = "Sales Invoice"

	def __init__(self, device, invoice, config: ComstoreConfig | None = None):
		super().__init__(device)
		self.invoice = invoice
		self.config = config or ComstoreConfig()
		self.reference_name = invoice.name

	def path(self):
		return "/api/complete-workflow"

	def body(self):
		from comstore_etims.fiscal.invoice_payload import InvoicePayload

		return InvoicePayload(self.invoice, self.device.serial_number, self.config).build()

	@classmethod
	def apply(cls, request, outcome):
		from comstore_etims.fiscal.signature import SignatureRecorder

		SignatureRecorder(request.reference_name).record(outcome)


OPERATIONS = {
	cls.name: cls
	for cls in (Health, Initialise, InvoiceStatus, ManualUpload, Restart, UploadItems, UploadBuyers, SignInvoice)
}
