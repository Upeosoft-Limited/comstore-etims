"""How an item is named and keyed on the device.

The device matches a sale line to its registered item by name and barcode, so
the upload and the invoice must say both the same way. Both go through here.
"""

import re

MAX_NAME = 50

# eTIMS rejects anything outside plain ASCII (E034), and the device refuses
# "special characters" in an item name. Keep letters, digits, spaces and a few
# harmless marks; everything else becomes a space.
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9 .,()&/+%-]")


def device_name(item_name: str) -> str:
	cleaned = _NOT_ALLOWED.sub(" ", item_name or "")
	return " ".join(cleaned.split())[:MAX_NAME].strip()


def device_barcode(barcode: str | None, plu_no: int | str) -> str:
	"""The item's barcode, or its PLU number when it has none (as the device asks)."""
	return (barcode or "").strip() or str(plu_no)


def ascii_text(value: str | None, limit: int | None = None) -> str:
	cleaned = (value or "").encode("ascii", "ignore").decode().strip()
	return cleaned[:limit] if limit else cleaned
