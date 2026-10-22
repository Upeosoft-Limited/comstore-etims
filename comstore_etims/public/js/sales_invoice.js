// Copyright (c) 2026, Upeosoft Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		const status = frm.doc.comstore_status;
		if (status) {
			const colour = { Signed: "green", Queued: "blue", Failed: "red" }[status] || "grey";
			frm.dashboard.add_indicator(__("eTIMS: {0}", [__(status)]), colour);
		}
		if (frm.doc.docstatus === 1 && status !== "Signed") {
			frm.add_custom_button(status === "Failed" ? __("Retry eTIMS Signing") : __("Sign on eTIMS"), () => {
				frappe.call({
					method: "comstore_etims.api.sign_invoice",
					args: { invoice: frm.doc.name },
					freeze: true,
					callback: () => {
						frappe.show_alert({ message: __("Sent for signing."), indicator: "blue" });
						setTimeout(() => frm.reload_doc(), 3000);
					},
				});
			});
		}
	},
});
