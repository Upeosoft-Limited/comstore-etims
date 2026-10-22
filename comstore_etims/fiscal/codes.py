"""eTIMS codes the device speaks, in one place."""

import re
from decimal import Decimal

# Tax category letter -> VAT rate. The device files each line under its letter
# and works out net and VAT per category itself, so the rate here must be the
# one the item is registered with on the device.
TAX_RATES = {
	"A": Decimal("0"),  # exempt
	"B": Decimal("0.16"),  # standard rate
	"C": Decimal("0"),  # zero rated
	"D": Decimal("0"),  # not subject to VAT
	"E": Decimal("0.08"),  # tourism (hotels, restaurants)
}

# The sign structure names each category's two fields like this.
TAX_FIELDS = {
	"A": "Vat A(Exempt)",
	"B": "Vat B(16.00%)",
	"C": "Vat C(0%)",
	"D": "Vat D(Non-VAT)",
	"E": "Vat E(8%)",
}

REFUND_REASONS = {
	"01": "Missing Quantity",
	"02": "Missing Data",
	"03": "Damaged / Wasted",
	"04": "Raw Material",
	"05": "Shortage",
	"06": "Refund",
}

PRODUCT_TYPES = {"01": "Raw Material", "02": "Finished Product", "03": "Service without stock"}


def tax_letter(value: str | None) -> str | None:
	""""B-16.00%", "b" or "B" -> "B"; anything unknown -> None."""
	letter = (value or "").strip()[:1].upper()
	return letter if letter in TAX_RATES else None


def code_prefix(value: str | None) -> str:
	"""The numeric code a label starts with: "06 Refund" or "02Finished Product" -> "06" / "02"."""
	found = re.match(r"\s*(\d+)", value or "")
	return found.group(1) if found else ""


# Operations a Comstore Request can carry. Each maps to one device endpoint.
SIGN_INVOICE = "Sign Invoice"
UPLOAD_ITEMS = "Upload Items"
UPLOAD_BUYERS = "Upload Buyers"
INVOICE_STATUS = "Invoice Status"
MANUAL_UPLOAD = "Manual Upload"
HEALTH = "Health"
INITIALISE = "Initialise"
RESTART = "Restart"

# Request states.
QUEUED = "Queued"
SENDING = "Sending"
DONE = "Done"
FAILED = "Failed"
