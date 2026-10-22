# Copyright (c) 2026, Upeosoft Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from comstore_etims.install import RELAY_ROLE


class ComstoreDevice(Document):
	def validate(self):
		self.serial_number = (self.serial_number or "").strip()
		self._check_api_url()
		self._check_relay_user()

	def _check_api_url(self):
		if self.transport != "Direct":
			return
		self.api_url = (self.api_url or "").strip().rstrip("/")
		if not self.api_url.startswith(("http://", "https://")):
			frappe.throw(_("The Comstore API URL must start with http:// or https://, e.g. http://192.168.1.50:4000"))

	def _check_relay_user(self):
		if self.transport != "Relay" or not self.relay_user:
			return
		if RELAY_ROLE not in frappe.get_roles(self.relay_user):
			frappe.throw(_("Give {0} the {1} role so the relay agent can sign in as them.").format(
				self.relay_user, RELAY_ROLE))
