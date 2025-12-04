
import frappe

def update_purchase_receipt_quantities(qi, method):
    # Only for Purchase Receipt reference
    if qi.reference_type != "Purchase Receipt":
        return

    if not qi.reference_name or not qi.item_code:
        return

    # Fetch corresponding Purchase Receipt Item row
    pr_item = frappe.db.get_value(
        "Purchase Receipt Item",
        {
            "parent": qi.reference_name,
            "item_code": qi.item_code
        },
        "name"
    )

    if not pr_item:
        frappe.throw(
            f"No Purchase Receipt Item found for {qi.reference_name} and item {qi.item_code}"
        )

    # accepted_qty = sample_size
    accepted_qty = qi.sample_size or 0

    # rejected_qty = rejected_qty from QI
    rejected_qty = qi.rejected_qty or 0

    # Update Purchase Receipt Item fields
    frappe.db.set_value("Purchase Receipt Item", pr_item, {
        "qty": accepted_qty,
        "rejected_qty": rejected_qty
    })

    frappe.db.commit()

    frappe.msgprint(
        f"Updated Purchase Receipt Item:<br>"
        f"<b>Accepted Qty:</b> {accepted_qty}<br>"
        f"<b>Rejected Qty:</b> {rejected_qty}"
    )
