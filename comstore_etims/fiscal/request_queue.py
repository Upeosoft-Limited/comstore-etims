"""Comstore Requests: created from an operation, finished with the device's answer."""

import json

import frappe
from frappe.utils import now_datetime

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.operations import OPERATIONS, Operation
from comstore_etims.fiscal.outcome import Outcome

REQUEST = "Comstore Request"


class RequestQueue:
	"""The one way a call to the device is made and recorded."""

	@staticmethod
	def submit(operation: Operation, is_test: bool = False):
		"""Record the call, then hand it to the device's transport."""
		from comstore_etims.fiscal.transport import transport_for

		body = operation.body()
		request = frappe.get_doc({
			"doctype": REQUEST,
			"device": operation.device.name,
			"operation": operation.name,
			"status": codes.QUEUED,
			"method": operation.method,
			"path": operation.path(),
			"request_body": json.dumps(body, indent=1) if body is not None else "",
			"reference_doctype": operation.reference_doctype,
			"reference_name": operation.reference_name,
			"is_test": 1 if is_test else 0,
		}).insert(ignore_permissions=True)
		transport_for(operation.device).dispatch(request)
		return request

	@staticmethod
	def claim(request) -> None:
		request.db_set({
			"status": codes.SENDING,
			"claimed_at": now_datetime(),
			"attempts": (request.attempts or 0) + 1,
		})

	@staticmethod
	def finish(request, outcome: Outcome) -> None:
		request.db_set({
			"status": codes.DONE if outcome.ok else codes.FAILED,
			"http_status": outcome.status,
			"response_body": json.dumps(outcome.body, indent=1),
			"error": "" if outcome.ok else outcome.message[:1000],
			"completed_at": now_datetime(),
		})
		OPERATIONS[request.operation].apply(request, outcome)

	@staticmethod
	def body_of(request) -> dict | None:
		return json.loads(request.request_body) if request.request_body else None
