import frappe

def mark_item_as_manufacture(doc, method=None):
    if not doc.item:
        return

    # Update Item checkbox
    frappe.db.set_value("Item", doc.item, "is_manufacture", 1)

    # Optional: clear cache so Desk reflects immediately
    frappe.clear_document_cache("Item", doc.item)