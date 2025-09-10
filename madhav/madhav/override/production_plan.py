import frappe
from frappe import _
from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan as ERPNextProductionPlan

class CustomProductionPlan(ERPNextProductionPlan):

    def validate(self):
        super().validate()
        self.validate_production_plan()

    def validate_production_plan(self):
        for row in self.get("po_items"):   # check correct child table name
            if isinstance(row.length, str):
                row.length = row.length.strip()
            if row.pieces:
                row.pieces = int(row.pieces)

    @frappe.whitelist()
    def get_items(self):
        super().get_items()

        # after fetching items, also pull custom fields from Sales Order Item
        for row in self.get("po_items"):   # adjust child table name if needed
            if row.sales_order and row.sales_order_item:
                so_item = frappe.db.get_value(
                    "Sales Order Item",
                    row.sales_order_item,
                    ["pieces", "length_size"],
                    as_dict=True
                )
                if so_item:
                    row.pieces = so_item.pieces or 0
                    row.length = so_item.length_size or 0.0   # ✅ float, no strip