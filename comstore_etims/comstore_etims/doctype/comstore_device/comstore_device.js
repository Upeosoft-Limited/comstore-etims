// Copyright (c) 2026, Upeosoft Limited and contributors
// For license information, please see license.txt

const COMSTORE_ACTIONS = [
	[__("Check Connection"), "check_health"],
	[__("Invoice Status"), "check_invoice_status"],
	[__("Push Pending Invoices to eTIMS"), "push_pending_invoices"],
	[__("Upload New Items"), "upload_items", { only_new: 1 }],
	[__("Upload All Items"), "upload_items", { only_new: 0 }],
	[__("Upload Buyers"), "upload_buyers"],
	[__("Initialise Device"), "initialise"],
];

frappe.ui.form.on("Comstore Device", {
	refresh(frm) {
		if (frm.is_new()) return;
		for (const [label, method, args] of COMSTORE_ACTIONS) {
			frm.add_custom_button(label, () => comstore_call(frm, method, args), __("Device"));
		}
		frm.add_custom_button(__("Restart Device"), () => {
			frappe.confirm(__("The device is unavailable for 1-2 minutes while it restarts. Continue?"),
				() => comstore_call(frm, "restart"));
		}, __("Device"));
		frm.add_custom_button(__("Requests"), () => {
			frappe.set_route("List", "Comstore Request", { device: frm.doc.name });
		});
	},
});

function comstore_call(frm, method, args) {
	frappe.call({
		method: `comstore_etims.api.${method}`,
		args: Object.assign({ device: frm.doc.name }, args || {}),
		freeze: true,
		callback: (r) => {
			frappe.show_alert({ message: __("Sent to the device. See Requests for the answer."), indicator: "blue" });
			setTimeout(() => frm.reload_doc(), 3000);
		},
	});
}
