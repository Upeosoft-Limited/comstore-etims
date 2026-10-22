"""What came back from the device, read the same way however it travelled."""

import re
from dataclasses import dataclass, field

_DEVICE_CODE = re.compile(r"\(Code (-?\d+)\)")
# A refusal that says nothing about the invoice itself: try again later.
_UNREACHABLE = ("not connected", "connection test failed", "not initialized", "connection error")


@dataclass
class Outcome:
	"""One device response. ``status`` 0 means the device API was never reached."""

	status: int
	body: dict = field(default_factory=dict)
	error: str = ""

	def get(self, key: str, default=None):
		"""Body fields are lower-case on some endpoints and PascalCase on others."""
		for k, v in self.body.items():
			if k.lower() == key.lower():
				return v
		return default

	@property
	def ok(self) -> bool:
		return self.status == 200 and bool(self.get("success"))

	@property
	def message(self) -> str:
		return self.error or str(self.get("message") or self.get("error") or self.get("errormessage") or "")

	@property
	def device_code(self) -> str | None:
		found = _DEVICE_CODE.search(self.message)
		return found.group(1) if found else None

	@property
	def transient(self) -> bool:
		"""True when the device or its API could not be reached, not when it said no."""
		if self.status in (0, 502, 503, 504):
			return True
		text = self.message.lower()
		return any(marker in text for marker in _UNREACHABLE)
