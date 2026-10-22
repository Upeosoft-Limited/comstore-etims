"""The relay endpoints, and registering items and buyers on the device."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from comstore_etims import relay
from comstore_etims.fiscal import codes, operations
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.fiscal.request_queue import RequestQueue
from comstore_etims.fiscal.signer import InvoiceSigner
from comstore_etims.tests import fixtures as fx


class TestRelay(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fx.settings()
		cls.item = fx.item("CMS-RELAY", tax_type="A-Exempt")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _queued_invoice(self):
		inv = fx.invoice([(self.item, 1, 20)])
		return inv, InvoiceSigner(inv.name).sign()

	def test_the_relay_user_collects_and_answers(self):
		inv, request = self._queued_invoice()
		frappe.set_user(fx.RELAY_USER)
		claimed = relay.pull(fx.SERIAL, limit=20)
		mine = next(c for c in claimed if c["name"] == request.name)
		self.assertEqual((mine["method"], mine["path"]), ("POST", "/api/complete-workflow"))
		self.assertEqual(mine["body"]["sign_structure"]["TraderSystemInvoiceNumber"], inv.name)
		self.assertEqual(frappe.db.get_value("Comstore Request", request.name, "status"), codes.SENDING)

		relay.push(request.name, 200, json.dumps(fx.signed_reply(inv.name).body))
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "comstore_status"), "Signed")

	def test_another_user_cannot_collect(self):
		self._queued_invoice()
		frappe.set_user("Administrator")  # not the relay user
		with self.assertRaises(frappe.PermissionError):
			relay.pull(fx.SERIAL)

	def test_an_answer_needs_a_claimed_request(self):
		_inv, request = self._queued_invoice()
		frappe.set_user(fx.RELAY_USER)
		with self.assertRaises(frappe.ValidationError):
			relay.push(request.name, 200, "{}")

	def test_heartbeat_shows_the_device_alive(self):
		frappe.set_user(fx.RELAY_USER)
		relay.heartbeat(fx.SERIAL, 200, json.dumps({"status": "OK", "version": "3.6.3",
													 "deviceConnection": "Connected"}))
		frappe.set_user("Administrator")
		row = frappe.db.get_value("Comstore Device", fx.SERIAL,
								  ["device_connection", "api_version", "relay_seen"], as_dict=True)
		self.assertEqual((row.device_connection, row.api_version), ("Connected", "3.6.3"))
		self.assertTrue(row.relay_seen)


class TestRegistration(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fx.settings()

	def test_a_new_item_gets_a_plu_number_and_opening_stock_once(self):
		code = fx.item("CMS-REG-NEW", tax_type="C-0%", stock=1)
		request = RequestQueue.submit(operations.UploadItems(fx.device(), [code], ComstoreConfig()))
		plu = json.loads(request.request_body)["plu_items"][0]
		self.assertEqual(plu["tax_type"], "C")
		self.assertEqual(plu["type_code"], "02")
		self.assertEqual(plu["change_qty"], "1000000")
		self.assertEqual(plu["barcode"], plu["plu_no"])
		self.assertTrue(int(plu["plu_no"]) > 0)

		RequestQueue.claim(request)
		RequestQueue.finish(request, Outcome(status=200, body={"success": True, "items_processed": 1}))
		self.assertEqual(frappe.db.get_value("Item", code, "comstore_uploaded"), 1)

		again = RequestQueue.submit(operations.UploadItems(fx.device(), [code], ComstoreConfig()))
		plu_again = json.loads(again.request_body)["plu_items"][0]
		self.assertEqual(plu_again["plu_no"], plu["plu_no"], "the PLU number never changes")
		self.assertEqual(plu_again["change_qty"], "0", "a re-upload leaves the device's stock alone")

	def test_a_service_item_and_template_tax(self):
		code = fx.item("CMS-REG-SERVICE")  # no eTIMS tax type: falls to the default
		plu = operations.UploadItems(fx.device(), [code]).body()["plu_items"][0]
		self.assertEqual((plu["tax_type"], plu["type_code"]), ("B", "03"))

	def test_only_customers_with_a_valid_pin_are_buyers(self):
		from comstore_etims.fiscal.registration import Buyer

		good = fx.customer("Reg Buyer Good", "P000333444Y")
		self.assertTrue(Buyer.eligible(good))
		self.assertFalse(Buyer.eligible(fx.customer("Reg Buyer None")))
		body = operations.UploadBuyers(fx.device(), [good]).body()
		self.assertEqual(body["Buyers"][0]["BuyerPin"], "P000333444Y")
		self.assertEqual((body["FromNumber"], body["EndNumber"]), (1, 1))

	def test_device_status_is_recorded(self):
		request = RequestQueue.submit(operations.InvoiceStatus(fx.device()))
		self.assertEqual(request.path, f"/api/invoices/status/{fx.SERIAL}")
		RequestQueue.claim(request)
		RequestQueue.finish(request, Outcome(status=200, body={
			"success": True, "invoices_on_device": 120, "invoices_uploaded_to_etims": 118, "pending_invoices": 2}))
		self.assertEqual(frappe.db.get_value("Comstore Device", fx.SERIAL, "pending_invoices"), 2)
