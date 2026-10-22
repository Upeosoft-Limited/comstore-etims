"""Writing the device's signature onto the Sales Invoice."""

import frappe
from frappe.utils import now_datetime

from comstore_etims.fiscal.outcome import Outcome

SIGNED = "Signed"
FAILED = "Failed"
QUEUED = "Queued"


class SignatureRecorder:
	"""Puts a signing result on the invoice: the receipt fields, or why it failed."""

	def __init__(self, invoice_name: str):
		self.invoice_name = invoice_name

	def record(self, outcome: Outcome) -> None:
		if outcome.ok or self._already_signed(outcome):
			self._signed(outcome)
		else:
			self.failed(outcome.message or "The device did not sign the invoice.")

	def queued(self) -> None:
		self._set({"comstore_status": QUEUED, "comstore_error": ""})

	def failed(self, message: str) -> None:
		self._set({"comstore_status": FAILED, "comstore_error": message[:1000]})

	@staticmethod
	def _already_signed(outcome: Outcome) -> bool:
		"""The device refuses a live invoice it has signed before, and returns the
		original signature with the refusal. A retry after a lost reply lands here."""
		return "already signed" in outcome.message.lower() and bool(outcome.get("cu-inv-no"))

	def _signed(self, outcome: Outcome) -> None:
		self._set({
			"comstore_status": SIGNED,
			"comstore_error": "",
			"comstore_cu_invoice_no": outcome.get("cu-inv-no") or "",
			"comstore_scu_id": outcome.get("scu_id") or "",
			"comstore_internal_data": outcome.get("internal-data") or "",
			"comstore_receipt_signature": outcome.get("Receipt Signature") or "",
			"comstore_signature_link": outcome.get("signature_link") or "",
			"comstore_transmit_status": outcome.get("transmit_status") or "",
			"comstore_signed_on": now_datetime(),
		})

	def _set(self, values: dict) -> None:
		# A submitted invoice: these fields are allow-on-submit, and signing is not an
		# edit the user made, so the modified stamp stays as it was.
		frappe.db.set_value("Sales Invoice", self.invoice_name, values, update_modified=False)
