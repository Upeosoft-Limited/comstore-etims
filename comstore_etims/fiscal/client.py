"""HTTP to the ComstoreFC4Api service on the shop's network."""

import json

import requests

from comstore_etims.fiscal.outcome import Outcome

# Signing waits on the device, which retries up to three times itself.
TIMEOUT = 90


class ComstoreClient:
	"""Sends one call and reports what happened. Never raises for a device refusal."""

	def __init__(self, base_url: str, api_key: str | None, session=None, timeout: int = TIMEOUT):
		self.base_url = (base_url or "").rstrip("/")
		self.api_key = api_key
		self.session = session or requests.Session()
		self.timeout = timeout

	def call(self, method: str, path: str, body: dict | None = None) -> Outcome:
		headers = {"Content-Type": "application/json"}
		if self.api_key:
			headers["X-API-KEY"] = self.api_key
		try:
			response = self.session.request(
				method, self.base_url + path, headers=headers,
				data=json.dumps(body) if body is not None else None, timeout=self.timeout,
			)
		except requests.RequestException as e:
			return Outcome(status=0, error=f"Could not reach the Comstore API at {self.base_url}: {e}")
		return Outcome(status=response.status_code, body=_json(response))


def _json(response) -> dict:
	try:
		data = response.json()
	except ValueError:
		return {"message": response.text[:500]}
	return data if isinstance(data, dict) else {"data": data}
