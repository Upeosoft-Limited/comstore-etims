"""Custom fields and the relay role, created on install and on every migrate."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from comstore_etims.fiscal.codes import PRODUCT_TYPES, REFUND_REASONS, TAX_FIELDS

RELAY_ROLE = "Comstore Relay"

TAX_TYPE_OPTIONS = "\n" + "\n".join(f"{k}-{v.split('(')[1].rstrip(')')}" for k, v in TAX_FIELDS.items())
REFUND_OPTIONS = "\n" + "\n".join(f"{k} {v}" for k, v in REFUND_REASONS.items())
TYPE_OPTIONS = "\n" + "\n".join(f"{k} {v}" for k, v in PRODUCT_TYPES.items())


def _signed_field(fieldname, label, fieldtype="Data", **extra):
	"""A field the device's answer fills in after submit."""
	return dict(
		fieldname=fieldname, label=label, fieldtype=fieldtype, read_only=1,
		allow_on_submit=1, no_copy=1, print_hide=1, **extra,
	)


SALES_INVOICE = [
	dict(fieldname="comstore_section", label="eTIMS (Comstore)", fieldtype="Section Break",
		 insert_after="remarks", collapsible=1),
	dict(fieldname="comstore_refund_reason", label="eTIMS Refund Reason", fieldtype="Select",
		 options=REFUND_OPTIONS, depends_on="is_return", insert_after="comstore_section", no_copy=1,
		 print_hide=1, description="Sent with a credit note. Defaults to the reason in Comstore Settings."),
	_signed_field("comstore_status", "eTIMS Status", "Select", options="\nQueued\nSigned\nFailed",
				  insert_after="comstore_refund_reason", in_standard_filter=1),
	_signed_field("comstore_cu_invoice_no", "CU Invoice No", insert_after="comstore_status"),
	_signed_field("comstore_scu_id", "SCU ID", insert_after="comstore_cu_invoice_no"),
	_signed_field("comstore_signed_on", "Signed On", "Datetime", insert_after="comstore_scu_id"),
	dict(fieldname="comstore_column", fieldtype="Column Break", insert_after="comstore_signed_on"),
	_signed_field("comstore_internal_data", "Internal Data", insert_after="comstore_column"),
	_signed_field("comstore_receipt_signature", "Receipt Signature", insert_after="comstore_internal_data"),
	_signed_field("comstore_signature_link", "eTIMS Link", "Small Text", insert_after="comstore_receipt_signature"),
	_signed_field("comstore_transmit_status", "Transmit Status", "Small Text", insert_after="comstore_signature_link"),
	_signed_field("comstore_error", "eTIMS Error", "Small Text", insert_after="comstore_transmit_status"),
]

ITEM = [
	dict(fieldname="comstore_section", label="eTIMS (Comstore)", fieldtype="Section Break",
		 insert_after="taxes", collapsible=1),
	dict(fieldname="comstore_tax_type", label="eTIMS Tax Type", fieldtype="Select", options=TAX_TYPE_OPTIONS,
		 insert_after="comstore_section",
		 description="Leave blank to follow the Item Tax Template, else the default in Comstore Settings."),
	dict(fieldname="comstore_type_code", label="eTIMS Product Type", fieldtype="Select", options=TYPE_OPTIONS,
		 insert_after="comstore_tax_type", description="Blank: Finished Product for stock items, else Service."),
	dict(fieldname="comstore_item_cls_code", label="eTIMS Item Class Code", fieldtype="Data",
		 insert_after="comstore_type_code"),
	dict(fieldname="comstore_column", fieldtype="Column Break", insert_after="comstore_item_cls_code"),
	dict(fieldname="comstore_pkg_unit", label="eTIMS Package Unit", fieldtype="Data",
		 insert_after="comstore_column", description="e.g. BG-Bag, BX-Box, CT-Carton"),
	dict(fieldname="comstore_qty_unit", label="eTIMS Quantity Unit", fieldtype="Data",
		 insert_after="comstore_pkg_unit", description="e.g. U-Pieces/item [Number], KG-Kilogram"),
	dict(fieldname="comstore_origin", label="eTIMS Country of Origin", fieldtype="Data",
		 insert_after="comstore_qty_unit", description="e.g. KE-KENYA"),
	dict(fieldname="comstore_plu_no", label="Device PLU No", fieldtype="Int", read_only=1, no_copy=1,
		 insert_after="comstore_origin", search_index=1),
	dict(fieldname="comstore_uploaded", label="On Device", fieldtype="Check", read_only=1, no_copy=1,
		 insert_after="comstore_plu_no"),
]

CUSTOMER = [
	dict(fieldname="comstore_buyer_no", label="Device Buyer No", fieldtype="Int", read_only=1, no_copy=1,
		 insert_after="tax_id"),
]


def after_install():
	sync()


def sync():
	create_custom_fields(
		{"Sales Invoice": SALES_INVOICE, "Item": ITEM, "Customer": CUSTOMER}, update=True
	)
	if not frappe.db.exists("Role", RELAY_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": RELAY_ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)
