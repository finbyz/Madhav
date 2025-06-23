import frappe
from frappe.utils import get_url_to_form

def after_submit(doc,method):
    create_batch_group(doc)

def create_batch_group(purchase_receipt):
    # Find all batches linked to this PR
    batch_list = frappe.get_all(
        "Batch",
        filters={
            "reference_doctype": "Purchase Receipt",
            "reference_name": purchase_receipt.name
        },
        fields=["name","pieces","weight_received","average_length","section_weight"]
    )

    if not batch_list:
        frappe.msgprint("No batches found to group.")
        return

    # Create Batch Group
    batch_group = frappe.new_doc("Batch Group")
    batch_group.reference_doctype = "Purchase Receipt"
    batch_group.reference_document_name = purchase_receipt.name

    for batch in batch_list:
        batch_group.append("batch_details", {
            "batch": batch.name,
            "lengthpieces": batch.pieces,
            "weight_received": batch.weight_received,
            "length_size": batch.average_length,
            # "length_weight_in_kg": batch.length_weight_in_kg,
            "section_weight": batch.section_weight,
        })

    batch_group.save()
    for batch in batch_list:
        frappe.db.set_value("Batch", batch.name, "batch_group_reference", batch_group.name)

    
    frappe.msgprint(f"✅ Batch Group <a href='/app/batch-group/{batch_group.name}' target='_blank'><b>{batch_group.name}</b></a> created with {len(batch_list)} batches.")
    
def calculate_weight_demand(doc, method):
    total_length_qty = 0

    for item in doc.items:
        if item.item_code and item.pieces and item.average_length:
            # Step 1: qty × length
            try:
                qty = float(item.pieces)
                average_length = float(item.average_length)
            except (TypeError, ValueError):
                frappe.throw(f"Invalid qty or length for item {item.item_code}: qty={item.qty}, length={item.length}")

            total_length_qty += qty * average_length

    # Step 2: Get weight_per_meter from Item master (use first item)
    if doc.items:
        first_item_code = doc.items[0].item_code
        weight_str = frappe.db.get_value("Item", first_item_code, "weight_per_meter") or "0"
        try:
            weight_per_meter = float(weight_str)
        except ValueError:
            frappe.throw(f"Invalid weight_per_meter for item {first_item_code}: '{weight_str}'")

        # Step 3: total × weight_per_meter
        doc.weight_demand = total_length_qty * weight_per_meter
    else:
        doc.weight_demand = 0
