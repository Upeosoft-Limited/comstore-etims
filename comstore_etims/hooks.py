app_name = "comstore_etims"
app_title = "Comstore eTIMS"
app_publisher = "Upeosoft Limited"
app_description = "Sign ERPNext sales invoices for KRA eTIMS through a Comstore Smart VSCU (FC4) device."
app_email = "upeosoft@gmail.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

after_install = "comstore_etims.install.after_install"
after_migrate = "comstore_etims.install.sync"
before_tests = "comstore_etims.tests.fixtures.before_tests"

doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
}

doc_events = {
	"Sales Invoice": {
		"on_submit": "comstore_etims.events.queue_signing",
	},
}

scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"comstore_etims.tasks.requeue_stale",
			"comstore_etims.tasks.retry_failed_signing",
		],
	},
	"hourly": ["comstore_etims.tasks.check_devices"],
}

jinja = {
	"methods": ["comstore_etims.jinja.comstore_qr"],
}
