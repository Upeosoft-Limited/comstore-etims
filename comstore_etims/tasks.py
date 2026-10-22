"""Scheduled jobs: keep requests moving when a device or the relay drops out."""

import frappe
from frappe.utils import add_to_date, now_datetime

from comstore_etims.fiscal import codes, operations
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.fiscal.request_queue import REQUEST, RequestQueue
from comstore_etims.fiscal.transport import transport_for

# A claimed request with no answer after this long is presumed lost.
STALE_MINUTES = 10


def requeue_stale() -> None:
	"""A relay agent that claimed a request and went quiet gives it back.

	Re-sending a signature is safe: the device recognises a live invoice it has
	signed and returns the original signature (see SignatureRecorder).
	"""
	cutoff = add_to_date(now_datetime(), minutes=-STALE_MINUTES)
	for name in frappe.get_all(
		REQUEST, filters={"status": codes.SENDING, "claimed_at": ["<", cutoff]}, pluck="name"
	):
		frappe.db.set_value(REQUEST, name, "status", codes.QUEUED)


def retry_failed_signing() -> None:
	"""Send again the signatures that failed only because the device was out of reach."""
	config = ComstoreConfig()
	if not config.enabled:
		return
	for request in frappe.get_all(
		REQUEST,
		filters={"status": codes.FAILED, "operation": codes.SIGN_INVOICE, "attempts": ["<", config.retry_limit]},
		fields=["name", "reference_name", "http_status", "error"],
	):
		if not Outcome(status=request.http_status or 0, error=request.error or "").transient:
			continue
		if frappe.db.get_value("Sales Invoice", request.reference_name, "comstore_status") == "Signed":
			continue
		doc = frappe.get_doc(REQUEST, request.name)
		doc.db_set("status", codes.QUEUED)
		transport_for(frappe.get_doc("Comstore Device", doc.device)).dispatch(doc)


def check_devices() -> None:
	"""Hourly: ask each device how many invoices still wait to reach KRA."""
	if not ComstoreConfig().enabled:
		return
	for name in frappe.get_all("Comstore Device", filters={"enabled": 1}, pluck="name"):
		RequestQueue.submit(operations.InvoiceStatus(frappe.get_doc("Comstore Device", name)))
