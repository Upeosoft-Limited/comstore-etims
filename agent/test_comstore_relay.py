"""The relay agent's loop, with ERPNext and the device faked."""

import configparser
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import comstore_relay as agent  # noqa: E402


def _config(**agent_values):
	parser = configparser.ConfigParser()
	parser.read_dict({
		"erpnext": {"url": "https://erp.example.com/", "api_key": "k", "api_secret": "s", "device": "DEMO0001"},
		"comstore": {"url": "http://127.0.0.1:4000", "api_key": "device-key"},
		"agent": {"heartbeat_seconds": "60", **agent_values},
	})
	return agent.Config(parser)


class FakeHttp:
	def __init__(self, replies):
		self.replies = replies  # url suffix -> (status, body) or an exception
		self.sent = []

	def __call__(self, method, url, headers, body=None, timeout=30):
		self.sent.append((method, url, headers, body))
		for suffix, reply in self.replies.items():
			if url.endswith(suffix):
				if isinstance(reply, Exception):
					raise reply
				return reply
		raise AssertionError(f"unexpected call {url}")


class TestRelay(unittest.TestCase):
	def setUp(self):
		self.config = _config()
		self.erp_http = FakeHttp({
			"relay.heartbeat": (200, {"message": {"ok": True}}),
			"relay.pull": (200, {"message": [
				{"name": "req1", "method": "POST", "path": "/api/complete-workflow", "body": {"sn": "DEMO0001"}},
			]}),
			"relay.push": (200, {"message": {"status": "Done"}}),
		})
		self.device_http = FakeHttp({
			"/api/health": (200, {"status": "OK", "deviceConnection": "Connected"}),
			"/api/complete-workflow": (200, {"success": True, "cu-inv-no": "0000101"}),
		})
		self.relay = agent.Relay(self.config, agent.ErpNext(self.config, self.erp_http),
								 agent.Device(self.config, self.device_http), clock=lambda: 1000)

	def test_a_request_is_carried_to_the_device_and_answered(self):
		self.assertEqual(self.relay.run_once(), 1)
		method, url, headers, body = self.device_http.sent[-1]
		self.assertEqual((method, url), ("POST", "http://127.0.0.1:4000/api/complete-workflow"))
		self.assertEqual(headers["X-API-KEY"], "device-key")
		self.assertEqual(body, {"sn": "DEMO0001"})
		push = self.erp_http.sent[-1]
		self.assertTrue(push[1].endswith("relay.push"))
		self.assertEqual(push[3]["request"], "req1")
		self.assertEqual(push[3]["status"], 200)
		self.assertEqual(json.loads(push[3]["body"])["cu-inv-no"], "0000101")

	def test_erpnext_sees_the_relay_users_token(self):
		self.relay.run_once()
		self.assertEqual(self.erp_http.sent[0][2]["Authorization"], "token k:s")
		self.assertTrue(self.erp_http.sent[0][1].startswith("https://erp.example.com/api/method/"))

	def test_heartbeat_once_a_minute(self):
		self.relay.run_once()
		self.relay.run_once()
		beats = [s for s in self.erp_http.sent if s[1].endswith("relay.heartbeat")]
		self.assertEqual(len(beats), 1)

	def test_a_device_that_does_not_answer_is_reported_not_raised(self):
		self.device_http.replies["/api/complete-workflow"] = OSError("timed out")
		self.relay.run_once()
		push = self.erp_http.sent[-1][3]
		self.assertEqual(push["status"], 0)
		self.assertIn("Could not reach", push["error"])

	def test_erpnext_refusing_is_an_error(self):
		self.erp_http.replies["relay.pull"] = (403, {"exception": "PermissionError"})
		with self.assertRaises(RuntimeError):
			self.relay.run_once()


if __name__ == "__main__":
	unittest.main()
