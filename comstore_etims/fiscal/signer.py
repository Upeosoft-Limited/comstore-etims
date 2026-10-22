"""Signing a submitted Sales Invoice on the shop's device."""

import frappe
from frappe import _

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.operations import SignInvoice
from comstore_etims.fiscal.request_queue import REQUEST, RequestQueue
from comstore_etims.fiscal.signature import SIGNED, SignatureRecorder

DEVICE = "Comstore Device"


def device_for(company: str, config: ComstoreConfig):
	"""The company's enabled device: the default one if it is the company's, else its first."""
	default = config.default_device
	if default and frappe.db.get_value(DEVICE, default, ["company", "enabled"]) == (company, 1):
		return frappe.get_doc(DEVICE, default)
	name = frappe.db.get_value(DEVICE, {"company": company, "enabled": 1}, "name", order_by="creation")
	return frappe.get_doc(DEVICE, name) if name else None


class InvoiceSigner:
	"""Queues one invoice for signing, once. Says in words why it could not."""

	def __init__(self, invoice_name: str, config: ComstoreConfig | None = None):
		self.invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.config = config or ComstoreConfig()
		self.recorder = SignatureRecorder(invoice_name)

	def sign(self):
		if self.invoice.docstatus != 1:
			frappe.throw(_("Only a submitted invoice can be signed."))
		if self.invoice.get("comstore_status") == SIGNED:
			return None
		if self._in_flight():
			return None
		device = device_for(self.invoice.company, self.config)
		if not device:
			self.recorder.failed(_("No enabled Comstore Device for company {0}.").format(self.invoice.company))
			return None
		try:
			request = RequestQueue.submit(SignInvoice(device, self.invoice, self.config), self.config.test_mode)
		except frappe.ValidationError as e:
			# The invoice cannot be put to the device as it stands (no shop PIN, a tax
			# mismatch...). Say so on the invoice, where whoever fixes it will look.
			self.recorder.failed(str(e))
			return None
		self.recorder.queued()
		return request

	def _in_flight(self) -> bool:
		return bool(frappe.db.exists(REQUEST, {
			"reference_doctype": "Sales Invoice",
			"reference_name": self.invoice.name,
			"operation": codes.SIGN_INVOICE,
			"status": ["in", [codes.QUEUED, codes.SENDING]],
		}))


def sign_invoice(invoice_name: str) -> None:
	"""Background job queued when an invoice is submitted."""
	InvoiceSigner(invoice_name).sign()
