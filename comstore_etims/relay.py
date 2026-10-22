"""Endpoints the relay agent on the shop's PC calls, with its own API key.

The agent signs in as the device's Relay User and can only see and answer
requests for devices that name that user.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.operations import Health
from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.fiscal.request_queue import REQUEST, RequestQueue

MAX_BATCH = 20


def _own_device(device: str):
	doc = frappe.get_doc("Comstore Device", device)
	if doc.relay_user != frappe.session.user or not doc.enabled:
		frappe.throw(_("This user is not the relay for device {0}.").format(device), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["POST"])
def pull(device: str, limit: int = 5) -> list[dict]:
	"""Claim the device's waiting requests, oldest first."""
	_own_device(device)
	names = frappe.get_all(
		REQUEST, filters={"device": device, "status": codes.QUEUED},
		order_by="creation asc", limit=min(cint(limit) or 5, MAX_BATCH), pluck="name",
	)
	claimed = []
	for name in names:
		request = frappe.get_doc(REQUEST, name, for_update=True)
		if request.status != codes.QUEUED:
			continue
		RequestQueue.claim(request)
		claimed.append({
			"name": request.name,
			"method": request.method,
			"path": request.path,
			"body": RequestQueue.body_of(request),
		})
	return claimed


@frappe.whitelist(methods=["POST"])
def push(request: str, status: int, body: str | dict | None = None, error: str | None = None) -> dict:
	"""Record the device's answer to a claimed request."""
	doc = frappe.get_doc(REQUEST, request, for_update=True)
	_own_device(doc.device)
	if doc.status != codes.SENDING:
		frappe.throw(_("Request {0} is not waiting for an answer.").format(request))
	RequestQueue.finish(doc, Outcome(status=cint(status), body=_as_dict(body), error=error or ""))
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def heartbeat(device: str, status: int = 0, body: str | dict | None = None) -> dict:
	"""The agent's regular health check of the device, so the desk shows it is alive."""
	doc = _own_device(device)
	request = frappe._dict(device=doc.name)
	Health.apply(request, Outcome(status=cint(status), body=_as_dict(body)))
	frappe.db.set_value("Comstore Device", doc.name, "relay_seen", now_datetime())
	return {"ok": True}


def _as_dict(body) -> dict:
	if isinstance(body, dict):
		return body
	if not body:
		return {}
	try:
		data = json.loads(body)
	except ValueError:
		return {"message": str(body)[:500]}
	return data if isinstance(data, dict) else {"data": data}
