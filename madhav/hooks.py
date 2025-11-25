app_name = "madhav"
app_title = "Madhav"
app_publisher = "Finbyz pvt. ltd."
app_description = "App for Madhav Group"
app_email = "info@finbyz.tech"
app_license = "gpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "madhav",
# 		"logo": "/assets/madhav/logo.png",
# 		"title": "Madhav",
# 		"route": "/madhav",
# 		"has_permission": "madhav.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/madhav/css/madhav.css"
# app_include_js = "/assets/madhav/js/madhav.js"

# include js, css files in header of web template
# web_include_css = "/assets/madhav/css/madhav.css"
# web_include_js = "/assets/madhav/js/madhav.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "madhav/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {
    "Attendance" : "public/js/attendance.js",
    "Stock Entry": "public/js/stock_entry.js",
    "BOM": "public/js/bom.js",
    "Sales Order": "public/js/sales_order.js",
    "Work Order": "public/js/work_order.js",
    "Production Plan": "public/js/production_plan.js"
    # "Purchase Receipt": "public/js/purchase_receipt.js"
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
    "Attendance" : "public/js/attendance_list.js",
    "Purchase Order" : "public/js/purchase_order.js"
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}
doctype_calendar_js = {"Shift Assignment":"public/js/shift_assignment_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "madhav/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "madhav.utils.jinja_methods",
# 	"filters": "madhav.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "madhav.install.before_install"
# after_install = "madhav.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "madhav.uninstall.before_uninstall"
# after_uninstall = "madhav.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "madhav.utils.before_app_install"
# after_app_install = "madhav.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "madhav.utils.before_app_uninstall"
# after_app_uninstall = "madhav.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "madhav.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

override_doctype_class = {
    "Attendance":"madhav.madhav.override.attendance.Attendance",
    "BOM":"madhav.madhav.override.bom.BOM",
    "Production Plan":"madhav.madhav.override.production_plan.CustomProductionPlan",
    "Purchase Receipt": "madhav.madhav.override.purchase_receipt.PurchaseReceipt",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Stock Ledger Entry": {
        "on_submit": "madhav.doc_events.stock_ledger_entry.create_piece_stock_ledger_entry",
	},
    "Stock Entry":{
        "before_validate": "madhav.doc_events.stock_entry.auto_calculation",
        "on_submit": "madhav.doc_events.stock_entry.after_submit",
        "before_submit": "madhav.doc_events.stock_entry.validation_section_weight",
        "before_cancel": "madhav.doc_events.stock_entry.cancel_linked_psles",
        "validate": "madhav.doc_events.stock_entry.validate"
    },
    "Purchase Invoice": {
        "before_save": "madhav.doc_events.purchase_invoice.validate_limit_on_saved_before_submit"
    },
    "Purchase Receipt": {
        "before_save": [
            "madhav.doc_events.purchase_receipt.set_actual_rate_per_kg",
            "madhav.doc_events.purchase_receipt.round_off_stock_qty",
            "madhav.doc_events.purchase_receipt.validate_limit_on_save",
            # "madhav.doc_events.purchase_receipt.prevent_edit_after_quality_inspection"
        ],
        "before_validate": [
            "madhav.doc_events.purchase_receipt.auto_calculation",
            "madhav.doc_events.purchase_receipt.create_qi"
            ],
        "before_submit": [
            "madhav.doc_events.purchase_receipt.validation_section_weight",
            # "madhav.doc_events.purchase_receipt.ensure_quality_inspections_submitted"
        ],
        "on_submit": "madhav.doc_events.purchase_receipt.after_submit",
        "before_cancel": "madhav.doc_events.stock_entry.cancel_linked_psles"
    },
    "Purchase Order": {
        "before_save": [
            "madhav.doc_events.purchase_order.validate_limit_on_save"
        ]
    },
    "Batch Group":{
        "autoname":"madhav.doc_events.batch_group.autoname"
    },
    "Batch":{
        "autoname":"madhav.doc_events.batch.autoname"
    },
    "Sales Order":{
        "before_validate":"madhav.doc_events.sales_order.calculate_qty_in_tonne"
    },
    "Sales Invoice": {
        "before_cancel": "madhav.doc_events.stock_entry.cancel_linked_psles"
    },
    "Delivery Note": {
        "before_cancel": "madhav.doc_events.stock_entry.cancel_linked_psles"
    },
    "Purchase Invoice": {
        "before_cancel": "madhav.doc_events.stock_entry.cancel_linked_psles"
    },
    "Attendance":{
      "validate":"madhav.doc_events.attendance.set_status",
      "after_insert":"madhav.doc_events.attendance.set_short_leave_count",
      "on_update_after_submit": "madhav.doc_events.attendance.set_short_leave_count"     
    },
    "Production Plan": {
        "before_save": [
            "madhav.doc_events.production_plan.duplicate_po_items_to_assembly_items_without_consolidate",
            "madhav.doc_events.production_plan.consolidate_assembly_items",
        ]
        },
    "Payment Entry": {
        "validate": "madhav.doc_events.payment_entry.validate_cash_limit",
        "on_submit": "madhav.doc_events.payment_entry.validate_cash_limit",
        
    } 
}

from erpnext.stock.serial_batch_bundle import SerialBatchCreation
from madhav.madhav.monkey_patch.serial_batch_bundle import create_batch
SerialBatchCreation.create_batch = create_batch

# from erpnext.controllers.buying_controller import BuyingController
# from madhav.madhav.monkey_patch.buying_controller import update_stock_ledger
# BuyingController.update_stock_ledger = update_stock_ledger

# from erpnext.controllers.selling_controller import SellingController
# from madhav.madhav.monkey_patch.selling_controller import update_stock_ledger
# SellingController.update_stock_ledger = update_stock_ledger

# from erpnext.controllers.selling_controller import SellingController
# from madhav.madhav.monkey_patch.selling_controller import get_sle_for_source_warehouse
# SellingController.get_sle_for_source_warehouse = get_sle_for_source_warehouse

# from erpnext.controllers.selling_controller import SellingController
# from madhav.madhav.monkey_patch.selling_controller import get_sle_for_target_warehouse
# SellingController.get_sle_for_target_warehouse = get_sle_for_target_warehouse

# from erpnext.controllers.selling_controller import SellingController
# from madhav.madhav.monkey_patch.selling_controller import get_item_list
# SellingController.get_item_list = get_item_list

# from erpnext.controllers.stock_controller import StockController
# from madhav.madhav.monkey_patch.stock_controller import get_sl_entries
# StockController.get_sl_entries = get_sl_entries


from erpnext.controllers import item_variant
from madhav.api import custom_make_variant_item_code
item_variant.make_variant_item_code = custom_make_variant_item_code

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"madhav.tasks.all"
# 	],
# 	"daily": [
# 		"madhav.tasks.daily"
# 	],
# 	"hourly": [
# 		"madhav.tasks.hourly"
# 	],
# 	"weekly": [
# 		"madhav.tasks.weekly"
# 	],
# 	"monthly": [
# 		"madhav.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "madhav.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry": "madhav.madhav.override.work_order.make_stock_entry"
}

# after_migrate = [
#     "madhav.madhav.monkey_patch.ignore_psle_links.setup_ignore_links"
# ]
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "madhav.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------
# ignore_links_on_delete = ["Communication", "ToDo"]
ignore_links_on_delete = ["Piece Stock Ledger Entry"]

# Request Events
# ----------------
# before_request = ["madhav.utils.before_request"]
# after_request = ["madhav.utils.after_request"]

# Job Events
# ----------
# before_job = ["madhav.utils.before_job"]
# after_job = ["madhav.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"madhav.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {
        "dt": "Custom Field",
        "filters": {"module": ["in", ["Madhav"]]},
    },
    {
        "dt": "Property Setter",
        "filters": {"module": ["in", ["Madhav"]]},
    }
]