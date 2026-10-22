"""The figures the device checks, worked the way it works them."""

import unittest
from decimal import Decimal

from comstore_etims.fiscal.codes import code_prefix, tax_letter
from comstore_etims.fiscal.device_names import device_barcode, device_name
from comstore_etims.fiscal.outcome import Outcome
from comstore_etims.fiscal.sale_line import SaleLine
from comstore_etims.fiscal.tax import TaxBuckets


class TestTaxBuckets(unittest.TestCase):
	def test_standard_rate_splits_like_the_device(self):
		"""The vendor's own example: 484,499.99 gross at 16%."""
		buckets = TaxBuckets()
		buckets.add("B", "484499.99")
		fields = buckets.fields()
		self.assertEqual(fields["Vat B(16.00%) net"], "417672.41")
		self.assertEqual(fields["Vat B(16.00%) value"], "66827.58")

	def test_unused_categories_are_zero_and_E_is_blank(self):
		buckets = TaxBuckets()
		buckets.add("B", 100)
		fields = buckets.fields()
		self.assertEqual(fields["Vat A(Exempt) net"], "0")
		self.assertEqual(fields["Vat C(0%) value"], "0")
		self.assertEqual(fields["Vat E(8%) net"], "")

	def test_eight_percent_and_exempt(self):
		buckets = TaxBuckets()
		buckets.add("E", 100)
		buckets.add("A", 100)
		self.assertEqual(buckets.split("E"), (Decimal("92.59"), Decimal("7.41")))
		self.assertEqual(buckets.split("A"), (Decimal("100.00"), Decimal("0.00")))
		self.assertEqual(buckets.total, Decimal("200.00"))


class TestSaleLine(unittest.TestCase):
	def test_price_times_qty_less_discount_is_the_amount(self):
		"""E322: the device recomputes the amount. A 100.00 line of 3 cannot be 33.33 x 3."""
		line = SaleLine.of("Soap", "", 3, "100.00")
		self.assertEqual(line.unit_price, Decimal("33.34"))
		self.assertEqual(line.unit_price * line.qty - line.discount, line.gross)
		plu = line.as_plu_data()
		self.assertEqual((plu["SalePrice"], plu["SaleQty"], plu["SaleAmount"], plu["ItemDisCount"]),
						 ("33.34", "3", "100.00", "0.02"))

	def test_an_even_line_has_no_discount(self):
		plu = SaleLine.of("Bread", "123", 2, 110).as_plu_data()
		self.assertEqual((plu["SalePrice"], plu["ItemDisCount"]), ("55.00", "0.00"))

	def test_a_return_line_is_sent_positive(self):
		line = SaleLine.of("Bread", "", -2, -110)
		self.assertEqual((line.qty, line.gross), (Decimal("2"), Decimal("110.00")))

	def test_weighed_quantity_keeps_its_decimals(self):
		self.assertEqual(SaleLine.of("Sugar", "", "1.250", 250).as_plu_data()["SaleQty"], "1.25")


class TestDeviceNames(unittest.TestCase):
	def test_name_is_plain_ascii_and_at_most_50(self):
		self.assertEqual(device_name("Café  Crème — 500g"), "Caf Cr me 500g")
		self.assertEqual(len(device_name("x" * 80)), 50)

	def test_barcode_falls_back_to_plu_number(self):
		self.assertEqual(device_barcode("", 17), "17")
		self.assertEqual(device_barcode(" 6161 ", 17), "6161")


class TestCodes(unittest.TestCase):
	def test_tax_letter(self):
		self.assertEqual(tax_letter("B-16.00%"), "B")
		self.assertEqual(tax_letter("e"), "E")
		self.assertIsNone(tax_letter("Z"))
		self.assertIsNone(tax_letter(""))

	def test_code_prefix(self):
		self.assertEqual(code_prefix("06 Refund"), "06")
		self.assertEqual(code_prefix("02Finished Product"), "02")
		self.assertEqual(code_prefix(""), "")


class TestOutcome(unittest.TestCase):
	def test_reads_either_case(self):
		pascal = Outcome(status=200, body={"Success": True, "Message": "Retrieved 1"})
		self.assertTrue(pascal.ok)
		self.assertEqual(pascal.message, "Retrieved 1")

	def test_device_code_and_refusal_are_not_transient(self):
		refused = Outcome(status=500, body={"success": False, "message": "SaleAmount is error (Code 322)"})
		self.assertEqual(refused.device_code, "322")
		self.assertFalse(refused.transient)

	def test_unreachable_is_transient(self):
		self.assertTrue(Outcome(status=0, error="Could not reach").transient)
		self.assertTrue(Outcome(status=500, body={"message": "Device not connected. Call /api/init first"}).transient)
		self.assertTrue(Outcome(status=503, body={"error": "API authentication is not configured."}).transient)
