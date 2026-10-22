"""One invoice line in the device's shape."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from comstore_etims.fiscal.money import CENT, cents, money_text, text, to_decimal


@dataclass
class SaleLine:
	"""A line the device can check: price x qty - discount must equal the amount (E322).

	ERPNext's tax-inclusive line amount rarely divides evenly by the quantity, so
	the unit price is rounded UP to the cent and the few cents over go in the
	discount field. The amount then matches the invoice exactly, which keeps the
	payments and tax totals equal to it as well (E341).
	"""

	name: str
	barcode: str
	qty: Decimal
	gross: Decimal

	@classmethod
	def of(cls, name: str, barcode: str, qty, gross) -> "SaleLine":
		return cls(name=name, barcode=barcode or "", qty=abs(to_decimal(qty)), gross=abs(cents(gross)))

	@property
	def unit_price(self) -> Decimal:
		if not self.qty:
			return self.gross
		return (self.gross / self.qty).quantize(CENT, rounding=ROUND_CEILING)

	@property
	def discount(self) -> Decimal:
		return cents(self.unit_price * self.qty - self.gross)

	def as_plu_data(self) -> dict:
		return {
			"item_Name": self.name,
			"Barcode": self.barcode,
			"SalePrice": money_text(self.unit_price),
			"SaleQty": text(self.qty),
			"SaleAmount": money_text(self.gross),
			"ItemDisCount(%)": "0",
			"ItemDisCount": money_text(self.discount),
			"Schg": "0",
			"Levy": "0",
		}
