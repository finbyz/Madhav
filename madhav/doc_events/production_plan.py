import frappe
from frappe import _


def duplicate_po_items_to_assembly_items_without_consolidate(doc, method):

    if not getattr(doc, "po_items", None):
        return

    fields_to_copy = [
        "item_code",
        "section_weight",
        "bom_no",
        "planned_qty",
        "pending_qty",
        "pieces",
        "length",
        "length_size_m",
        "stock_uom",
        "warehouse",
        "planned_start_date",
        "product_bundle_item",
        "sales_order",
        "sales_order_item",
        "description",
        "customer",
        "customer_name",
        "customers_purchase_order",
    ]

    # Build index of existing target rows
    existing_map = {
        (row.item_code, row.sales_order_item): row
        for row in doc.get("assembly_items_without_consolidate", [])
    }

    for row in doc.get("po_items"):
        key = (row.item_code, row.sales_order_item)

        if key in existing_map:
            # Update existing row → no reset
            target_row = existing_map[key]
        else:
            # Append new row
            target_row = doc.append("assembly_items_without_consolidate", {})

        for field in fields_to_copy:
            target_row.set(field, getattr(row, field, None))

def consolidate_assembly_items(doc, method):

    if not doc.po_items:
        return

    consolidated = {}

    for row in doc.po_items:
        key = row.item_code

        if key not in consolidated:
            consolidated[key] = row
        else:
            base = consolidated[key]

            base.planned_qty += row.planned_qty or 0
            base.pieces += row.pieces or 0
            base.length += row.length or 0
            base.length_size_m += row.length_size_m or 0

            # Remove duplicate rows safely
            doc.remove(row)

    # Only update calculated fields, never delete rows
    for row in consolidated.values():
        row.section_weight = frappe.db.get_value(
            "Item", row.item_code, "weight_per_meter"
        )