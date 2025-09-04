import frappe
from frappe import _
from frappe.utils import get_url_to_form

def after_submit(doc,method):
    
    if doc.stock_entry_type == "Material Receipt":
        create_batch_group(doc)
        
    if doc.stock_entry_type == "Material Transfer" and doc.get('cutting_plan_reference'):
        update_cutting_plan_workflow(doc.cutting_plan_reference, doc.name)
        update_source_warehouse(doc.cutting_plan_reference, doc.name)
        
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
    batch_group.total_length_in_meter = doc.total_length_in_meter
    weight_received_kg = doc.weight_received * 1000
    batch_group.section_weight = round(weight_received_kg/doc.total_length_in_meter, 2)

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
    
def auto_calculation(doc, method):
    
    if doc.stock_entry_type != "Material Receipt":
        return
        
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

        # Step 3: total × weight_per_meter → in kg
        weight_in_kg = total_length_qty * weight_per_meter

        # Convert to tonnes
        doc.weight_demand = round(weight_in_kg / 1000, 4)  # 4 decimals for tonne accuracy
    else:
        doc.weight_demand = 0

def validation_section_weight(doc, method):
    if doc.stock_entry_type != "Material Receipt":
        return
    
    if not doc.items or not doc.weight_received or not doc.total_length_in_meter:
        return

    item_code = doc.items[0].item_code
    standard_section_weight = frappe.db.get_value("Item", item_code, "weight_per_meter")

    if not standard_section_weight:
        frappe.throw(_("Standard section weight not found for item {0}").format(item_code))

    try:
        weight_received_kg = float(doc.weight_received) * 1000
        received_section_weight = round(weight_received_kg/ doc.total_length_in_meter, 2)
    except ZeroDivisionError:
        frappe.throw(_("Total Length in Meter cannot be zero."))

    # ±1.5% tolerance check
    lower_bound = received_section_weight * 0.985
    upper_bound = received_section_weight * 1.015

    if float(standard_section_weight) < lower_bound or float(standard_section_weight) > upper_bound:
        frappe.throw(_(
            "Standard section weight for item {0} is outside ±1.5% of received section weight ({1}).\n"
            "This Stock Entry is subject to approval and cannot be submitted."
        ).format(item_code, received_section_weight))    

def update_cutting_plan_workflow(cutting_plan_name, stock_entry_name):
    from frappe.model.workflow import apply_workflow
    cutting_plan = frappe.get_doc("Cutting Plan", cutting_plan_name)
        
    if cutting_plan.workflow_state == "RM Allocation pending( Rm Not Allocated yet)":
            
            
            apply_workflow(cutting_plan, "Approve")
            
            cutting_plan.material_transfer_stock_entry = stock_entry_name
            cutting_plan.save(ignore_permissions=True)
            
            cutting_plan.add_comment(
                "Workflow", 
                f"Material Transfer {stock_entry_name} submitted - Status updated automatically"
            )
            
            frappe.msgprint(
                _("Cutting Plan {0} updated to 'RM Allocated' status").format(cutting_plan_name),
                alert=True
            )

def update_source_warehouse(cutting_plan_name, stock_entry_name):
        
    # Get the cutting plan document
    cutting_plan = frappe.get_doc("Cutting Plan", cutting_plan_name)
    
    # Get the stock entry document to fetch to_warehouse
    stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
    
    if cutting_plan.cut_plan_detail:
        for row in cutting_plan.cut_plan_detail:
            # Set source_warehouse as the to_warehouse from stock entry
            row.source_warehouse = stock_entry.to_warehouse
    
    # Save the cutting plan with updated source warehouses
    cutting_plan.save()
    
    frappe.msgprint(
        _("Source warehouse updated to {0} for all items in Cutting Plan {1}")
        .format(frappe.bold(stock_entry.to_warehouse), frappe.bold(cutting_plan_name))
    )