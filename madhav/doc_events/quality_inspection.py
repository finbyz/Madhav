
import frappe

def update_purchase_receipt_quantities(qi, method):
    # Only for Purchase Receipt reference
    if qi.reference_type != "Purchase Receipt":
        return

    if not qi.reference_name or not qi.item_code:
        return

    # Fetch corresponding Purchase Receipt Item row
    pr_item_name = frappe.db.get_value(
        "Purchase Receipt Item",
        {
            "parent": qi.reference_name,
            "item_code": qi.item_code
        },
        "name"
    )

    if not pr_item_name:
        frappe.throw(
            f"No Purchase Receipt Item found for {qi.reference_name} and item {qi.item_code}"
        )

    # Load the Purchase Receipt Item document
    pr_item = frappe.get_doc("Purchase Receipt Item", pr_item_name)

    # accepted_qty = sample_size
    pr_item.qty = qi.sample_size or 0

    # rejected_qty = rejected_qty from QI
    pr_item.rejected_qty = qi.rejected_qty or 0

    # Save the child table row (commits automatically if inside a larger transaction)
    pr_item.save()
