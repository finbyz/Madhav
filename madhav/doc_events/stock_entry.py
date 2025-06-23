import frappe
from frappe.utils import get_url_to_form

def after_submit(doc,method):
    
    if doc.stock_entry_type == "Material Receipt":
        create_batch_group(doc)

def create_batch_group(doc):
    # Find all batches linked to this PR
    batch_list = frappe.get_all(
        "Batch",
        filters={
            "reference_doctype": "Stock Entry",
            "reference_name": doc.name
        },
        fields=["name","pieces","weight_received","average_length","section_weight"]
    )

    if not batch_list:
        frappe.msgprint("No batches found to group.")
        return

    # Create Batch Group
    batch_group = frappe.new_doc("Batch Group")
    batch_group.reference_doctype = "Stock Entry"
    batch_group.reference_document_name = doc.name

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