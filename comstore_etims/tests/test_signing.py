"""Signing a Sales Invoice: the request built, the answer recorded, the failures handled."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from comstore_etims.fiscal import codes
from comstore_etims.fiscal.config import ComstoreConfig
from comstore_etims.fiscal.invoice_payload import InvoicePayload
from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.fiscal.signer import InvoiceSigner
from comstore_etims.fiscal.transport import send_direct
from comstore_etims.tasks import requeue_stale, retry_failed_signing
from comstore_etims.tests import fixtures as fx


def _request_for(invoice):
	return frappe.get_last_doc("Comstore Request", filters={"reference_name": invoice})


class SigningCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fx.settings()
		cls.exempt = fx.item("CMS-EXEMPT", tax_type="A-Exempt")
		cls.vatable = fx.item("CMS-VAT", tax_type="B-16.00%")
		cls.vat = fx.vat_account()

	def payload(self, invoice, **settings):
		return InvoicePayload(invoice, fx.SERIAL, ComstoreConfig(fx.settings(**settings))).build()


class TestInvoicePayload(SigningCase):
	def test_an_exempt_sale(self):
		inv = fx.invoice([(self.exempt, 2, 55)])
		body = self.payload(inv)
		self.assertEqual(body["sn"], fx.SERIAL)
		self.assertTrue(body["is_test"])
		self.assertEqual(body["plu_data"][0]["item_Name"], "CMS-EXEMPT")
		self.assertEqual(body["plu_data"][0]["SaleAmount"], "110.00")
		sign = body["sign_structure"]
		self.assertEqual(sign["SignType"], "0")
		self.assertEqual(sign["InvoiceType"], "original")
		self.assertEqual(sign["pinOfshop"], fx.SHOP_PIN)
		self.assertEqual(sign["TraderSystemInvoiceNumber"], inv.name)
		self.assertEqual((sign["Vat A(Exempt) net"], sign["Vat B(16.00%) net"]), ("110.00", "0"))
		self.assertEqual(sign["CashAmt"], "110.00")

	def test_a_vat_sale_uses_erpnexts_own_tax(self):
		inv = fx.invoice([(self.vatable, 3, 100)], taxes=self.vat)
		self.assertEqual(inv.base_grand_total, 348)
		sign = self.payload(inv)["sign_structure"]
		self.assertEqual((sign["Vat B(16.00%) net"], sign["Vat B(16.00%) value"]), ("300.00", "48.00"))
		self.assertEqual(sign["CashAmt"], "348.00")

	def test_live_mode_signs_for_real(self):
		inv = fx.invoice([(self.exempt, 1, 10)])
		body = self.payload(inv, test_mode=0)
		self.assertFalse(body["is_test"])
		self.assertEqual(body["sign_structure"]["SignType"], "1")
		fx.settings()

	def test_a_tax_mismatch_is_refused_in_words(self):
		"""Marked exempt, charged 16%: the device would answer E321. Say it here instead."""
		inv = fx.invoice([(self.exempt, 1, 100)], taxes=self.vat)
		with self.assertRaises(frappe.ValidationError) as caught:
			self.payload(inv)
		self.assertIn("CMS-EXEMPT", str(caught.exception))

	def test_a_buyer_pin_is_sent_only_when_valid(self):
		good = fx.invoice([(self.exempt, 1, 10)], customer=fx.customer("Pinned Buyer", "P000333444Y"))
		bad = fx.invoice([(self.exempt, 1, 10)], customer=fx.customer("Bad Pin Buyer", "P00033344"))
		self.assertEqual(self.payload(good)["sign_structure"]["pinOfBuyer"], "P000333444Y")
		self.assertEqual(self.payload(bad)["sign_structure"]["pinOfBuyer"], "")


class TestSigningFlow(SigningCase):
	def test_signing_records_the_receipt_fields(self):
		inv = fx.invoice([(self.exempt, 1, 50)])
		request = InvoiceSigner(inv.name).sign()
		self.assertEqual(request.status, codes.QUEUED)
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "comstore_status"), "Queued")

		fake = fx.FakeClient(fx.signed_reply(inv.name))
		send_direct(request.name, client=fake)

		self.assertEqual(fake.calls[0][:2], ("POST", "/api/complete-workflow"))
		row = frappe.db.get_value("Sales Invoice", inv.name,
								  ["comstore_status", "comstore_cu_invoice_no", "comstore_receipt_signature"], as_dict=True)
		self.assertEqual((row.comstore_status, row.comstore_cu_invoice_no), ("Signed", "0000101"))
		self.assertEqual(row.comstore_receipt_signature, "TEST-RCPT-SIGN-0001")
		self.assertEqual(frappe.db.get_value("Comstore Request", request.name, "status"), codes.DONE)

	def test_an_invoice_is_signed_once(self):
		inv = fx.invoice([(self.exempt, 1, 50)])
		first = InvoiceSigner(inv.name).sign()
		self.assertIsNone(InvoiceSigner(inv.name).sign(), "a second request while the first is queued")
		send_direct(first.name, client=fx.FakeClient(fx.signed_reply(inv.name)))
		self.assertIsNone(InvoiceSigner(inv.name).sign(), "a request for a signed invoice")

	def test_the_devices_duplicate_answer_counts_as_signed(self):
		"""A retry after a lost reply: the device refuses and returns the first signature."""
		inv = fx.invoice([(self.exempt, 1, 50)])
		request = InvoiceSigner(inv.name).sign()
		duplicate = fx.signed_reply(inv.name)
		duplicate.status = 500
		duplicate.body["success"] = False
		duplicate.body["message"] = f"Document already signed: Invoice {inv.name} has already been processed"
		send_direct(request.name, client=fx.FakeClient(duplicate))
		self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "comstore_status"), "Signed")

	def test_a_device_refusal_is_shown_and_not_retried(self):
		inv = fx.invoice([(self.exempt, 1, 50)])
		request = InvoiceSigner(inv.name).sign()
		refusal = Outcome(status=500, body={"success": False, "message": "SaleAmount is error (Code 322)"})
		send_direct(request.name, client=fx.FakeClient(refusal))
		row = frappe.db.get_value("Sales Invoice", inv.name, ["comstore_status", "comstore_error"], as_dict=True)
		self.assertEqual(row.comstore_status, "Failed")
		self.assertIn("Code 322", row.comstore_error)
		retry_failed_signing()
		self.assertEqual(frappe.db.get_value("Comstore Request", request.name, "status"), codes.FAILED)

	def test_an_unreachable_device_is_retried(self):
		inv = fx.invoice([(self.exempt, 1, 50)])
		request = InvoiceSigner(inv.name).sign()
		send_direct(request.name, client=fx.FakeClient(Outcome(status=0, error="Could not reach")))
		retry_failed_signing()
		self.assertEqual(frappe.db.get_value("Comstore Request", request.name, "status"), codes.QUEUED)

	def test_a_missing_shop_pin_fails_on_the_invoice_not_the_submit(self):
		frappe.db.set_value("Company", fx.company(), "tax_id", "")
		try:
			inv = fx.invoice([(self.exempt, 1, 50)])
			self.assertIsNone(InvoiceSigner(inv.name).sign())
			row = frappe.db.get_value("Sales Invoice", inv.name, ["comstore_status", "comstore_error"], as_dict=True)
			self.assertEqual(row.comstore_status, "Failed")
			self.assertIn("KRA PIN", row.comstore_error)
		finally:
			fx.give_shop_pin()

	def test_a_return_is_a_credit_note_against_the_original(self):
		original = fx.invoice([(self.exempt, 2, 50)])
		send_direct(InvoiceSigner(original.name).sign().name,
					client=fx.FakeClient(fx.signed_reply(original.name, cu_no="0000102")))
		ret = fx.invoice([(self.exempt, -1, 50)], is_return=1, return_against=original.name,
						 comstore_refund_reason="03 Damaged / Wasted")
		body = json.loads(InvoiceSigner(ret.name).sign().request_body)
		sign = body["sign_structure"]
		self.assertEqual(sign["InvoiceType"], "credit")
		self.assertEqual(sign["relevantInvoiceNumber"], "102")
		self.assertEqual(sign["rfdRsnCd"], "03")
		self.assertEqual(body["plu_data"][0]["SaleQty"], "1")

	def test_a_return_of_an_unsigned_invoice_is_refused(self):
		original = fx.invoice([(self.exempt, 1, 50)])
		ret = fx.invoice([(self.exempt, -1, 50)], is_return=1, return_against=original.name)
		self.assertIsNone(InvoiceSigner(ret.name).sign())
		self.assertIn(original.name, frappe.db.get_value("Sales Invoice", ret.name, "comstore_error"))

	def test_a_claimed_request_with_no_answer_goes_back_in_the_queue(self):
		inv = fx.invoice([(self.exempt, 1, 50)])
		request = InvoiceSigner(inv.name).sign()
		frappe.db.set_value("Comstore Request", request.name,
							{"status": codes.SENDING, "claimed_at": "2020-01-01 00:00:00"})
		requeue_stale()
		self.assertEqual(frappe.db.get_value("Comstore Request", request.name, "status"), codes.QUEUED)


class TestSubmitHook(SigningCase):
	def test_submit_queues_signing_only_when_switched_on(self):
		with patch("comstore_etims.events.frappe.enqueue") as enqueue:
			fx.invoice([(self.exempt, 1, 10)])
			enqueue.assert_not_called()
			fx.settings(sign_on_submit=1)
			try:
				inv = fx.invoice([(self.exempt, 1, 10)])
			finally:
				fx.settings()
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["invoice_name"], inv.name)
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
