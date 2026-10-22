#!/usr/bin/env python3
"""Comstore relay agent: carries ERPNext's eTIMS requests to the device on this network.

Runs on the PC beside ComstoreFC4Api. It only makes outgoing connections: it
asks ERPNext (over HTTPS) for waiting requests, sends each one to the Comstore
API on this network, and posts the answer back. The device's API key stays on
this PC.

Standard library only, Python 3.8+.

    python comstore_relay.py [path/to/comstore_relay.ini]
"""

from __future__ import annotations

import configparser
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("comstore_relay")

API = "/api/method/comstore_etims.relay."


class Config:
	"""Settings from the .ini file next to this script (see comstore_relay.example.ini)."""

	def __init__(self, parser: configparser.ConfigParser):
		self.site_url = parser.get("erpnext", "url").rstrip("/")
		self.api_key = parser.get("erpnext", "api_key")
		self.api_secret = parser.get("erpnext", "api_secret")
		self.device = parser.get("erpnext", "device")
		self.comstore_url = parser.get("comstore", "url", fallback="http://127.0.0.1:4000").rstrip("/")
		self.comstore_key = parser.get("comstore", "api_key", fallback="")
		self.poll_seconds = parser.getfloat("agent", "poll_seconds", fallback=3)
		self.heartbeat_seconds = parser.getfloat("agent", "heartbeat_seconds", fallback=60)
		self.batch = parser.getint("agent", "batch", fallback=5)
		# Signing waits on the device, which retries up to three times itself.
		self.device_timeout = parser.getfloat("agent", "device_timeout", fallback=90)

	@classmethod
	def load(cls, path: Path) -> Config:
		parser = configparser.ConfigParser()
		if not parser.read(path):
			raise SystemExit(f"Config file not found: {path}")
		return cls(parser)


def _http(method: str, url: str, headers: dict, body=None, timeout: float = 30):
	"""(status, parsed JSON or {"message": text}). Raises OSError when nothing answered."""
	data = json.dumps(body).encode() if body is not None else None
	request = urllib.request.Request(url, data=data, method=method, headers=headers)
	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			return response.status, _parse(response.read())
	except urllib.error.HTTPError as e:
		return e.code, _parse(e.read())


def _parse(raw: bytes) -> dict:
	try:
		data = json.loads(raw or b"{}")
	except ValueError:
		return {"message": raw[:500].decode(errors="replace")}
	return data if isinstance(data, dict) else {"data": data}


class ErpNext:
	"""The relay endpoints on the ERPNext site, called as the device's Relay User."""

	def __init__(self, config: Config, http=_http):
		self.config = config
		self.http = http

	def call(self, endpoint: str, **args):
		status, body = self.http(
			"POST", self.config.site_url + API + endpoint,
			{"Authorization": f"token {self.config.api_key}:{self.config.api_secret}",
			 "Content-Type": "application/json", "Accept": "application/json"},
			args,
		)
		if status != 200:
			raise RuntimeError(f"ERPNext {endpoint} answered {status}: {body.get('exception') or body}")
		return body.get("message")


class Device:
	"""The ComstoreFC4Api service on this network."""

	def __init__(self, config: Config, http=_http):
		self.config = config
		self.http = http

	def call(self, method: str, path: str, body=None) -> tuple[int, dict, str]:
		"""(status, body, error). Status 0: the Comstore API did not answer at all."""
		headers = {"Content-Type": "application/json"}
		if self.config.comstore_key:
			headers["X-API-KEY"] = self.config.comstore_key
		try:
			status, reply = self.http(method, self.config.comstore_url + path, headers, body,
									  timeout=self.config.device_timeout)
		except OSError as e:
			return 0, {}, f"Could not reach the Comstore API at {self.config.comstore_url}: {e}"
		return status, reply, ""


class Relay:
	"""One loop: report health now and then, collect waiting requests, answer each."""

	def __init__(self, config: Config, erpnext: ErpNext, device: Device, clock=time.monotonic):
		self.config = config
		self.erpnext = erpnext
		self.device = device
		self.clock = clock
		self._last_heartbeat = None

	def run_once(self) -> int:
		"""Returns how many requests were answered."""
		self._heartbeat_if_due()
		requests = self.erpnext.call("pull", device=self.config.device, limit=self.config.batch) or []
		for request in requests:
			self._answer(request)
		return len(requests)

	def _answer(self, request: dict) -> None:
		status, body, error = self.device.call(request["method"], request["path"], request.get("body"))
		log.info("%s %s -> %s %s", request["method"], request["path"], status, error or body.get("message", ""))
		self.erpnext.call("push", request=request["name"], status=status, body=json.dumps(body), error=error)

	def _heartbeat_if_due(self) -> None:
		now = self.clock()
		if self._last_heartbeat is not None and now - self._last_heartbeat < self.config.heartbeat_seconds:
			return
		status, body, _error = self.device.call("GET", "/api/health")
		self.erpnext.call("heartbeat", device=self.config.device, status=status, body=json.dumps(body))
		self._last_heartbeat = now

	def run_forever(self) -> None:
		log.info("Relaying for device %s to %s", self.config.device, self.config.site_url)
		backoff = self.config.poll_seconds
		while True:
			try:
				answered = self.run_once()
				backoff = self.config.poll_seconds
			except (OSError, RuntimeError) as e:
				# ERPNext unreachable or refusing: say so and slow down. Claimed requests
				# that never got their answer go back in ERPNext's queue on their own.
				log.warning("%s", e)
				answered, backoff = 0, min(backoff * 2, 60)
			if not answered:
				time.sleep(backoff)


def main(argv: list[str]) -> None:
	path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("comstore_relay.ini")
	logging.basicConfig(
		level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
		handlers=[logging.StreamHandler(), logging.FileHandler(path.with_suffix(".log"))],
	)
	config = Config.load(path)
	Relay(config, ErpNext(config), Device(config)).run_forever()


if __name__ == "__main__":
	main(sys.argv)
