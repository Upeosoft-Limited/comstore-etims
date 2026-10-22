"""Document events wired in hooks.py."""

import frappe

from comstore_etims.fiscal.config import ComstoreConfig


def queue_signing(doc, method=None):
	"""Sales Invoice on_submit: sign after the submit has committed.

	Never inside the submit itself: a device that is off or unreachable must not
	stop the shop from trading. The invoice shows Queued, then Signed or Failed.
	"""
	config = ComstoreConfig()
	if not (config.enabled and config.sign_on_submit):
		return
	frappe.enqueue(
		"comstore_etims.fiscal.signer.sign_invoice",
		queue="short",
		invoice_name=doc.name,
		enqueue_after_commit=True,
	)
