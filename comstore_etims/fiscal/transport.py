"""How a request reaches the device.

Direct: this server calls the Comstore API itself. Only possible when the
server can reach the shop's network (an on-premise ERPNext, or a VPN).

Relay: the request waits here; the relay agent on the shop's PC collects it
over HTTPS, calls the API on the shop's network, and posts the answer back.
Nothing at the shop has to accept incoming connections.
"""

import frappe

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.client import ComstoreClient
from comstore_etims.fiscal.request_queue import REQUEST, RequestQueue

DIRECT = "Direct"
RELAY = "Relay"


class DirectTransport:
	def dispatch(self, request) -> None:
		# After commit: the job must find the request, and a rolled-back sale must
		# never be signed.
		frappe.enqueue(
			"comstore_etims.fiscal.transport.send_direct",
			queue="short",
			request_name=request.name,
			enqueue_after_commit=True,
		)


class RelayTransport:
	def dispatch(self, request) -> None:
		"""Nothing to do: the agent pulls Queued requests for its device."""


TRANSPORTS = {DIRECT: DirectTransport, RELAY: RelayTransport}


def transport_for(device):
	return TRANSPORTS[device.transport or RELAY]()


def send_direct(request_name: str, client: ComstoreClient | None = None) -> None:
	"""Background job: send one request from this server and record the answer."""
	request = frappe.get_doc(REQUEST, request_name)
	if request.status not in (codes.QUEUED, codes.FAILED):
		return
	device = frappe.get_doc("Comstore Device", request.device)
	client = client or ComstoreClient(device.api_url, device.get_password("api_key", raise_exception=False))
	RequestQueue.claim(request)
	outcome = client.call(request.method, request.path, RequestQueue.body_of(request))
	RequestQueue.finish(request, outcome)
