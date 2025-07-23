import frappe
from frappe import _
from frappe.utils import get_url_to_form

def create_qi(self,method):
    
    created_quality_inspections = []
    for row in self.items:
        
        # Skip if already linked
        if row.quality_inspection:
            continue
        
        if frappe.db.get_value("Item",row.item_code,"inspection_required_before_purchase") == 1:
            if self.company and not self.is_return and frappe.db.get_value("Item",row.item_code,"is_stock_item") == 1 and frappe.db.get_value("Item",row.item_code,"inspection_required_before_purchase") == 1:
                default_quality_inspection_warehouse=frappe.db.get_value("Company",self.company,"default_quality_inspection_warehouse")
                if default_quality_inspection_warehouse:
                    row.warehouse = default_quality_inspection_warehouse
                    
                    row.quality_inspection = make_quality_inspection(self,row)
                    created_quality_inspections.append(row.quality_inspection)
                 
    if created_quality_inspections:
        links = ''.join(
			f'<a href="/app/quality-inspection/{name}" target="_blank">{name}</a>,'
			for name in created_quality_inspections
		)
        
        frappe.msgprint(f"<b>Quality Inspections created:</b>{links}", title="Quality Inspections", indicator="green")


def make_quality_inspection(se_doc, item):
    
    doc = frappe.new_doc("Quality Inspection")
    doc.update({
        "inspection_type": "Incoming",
        "reference_type": se_doc.doctype,
        "reference_name": se_doc.name,
        "item_code": item.item_code,
        # "item_name": item.item_name,
        "ref_item": item.name,
        "description": item.description,
        "batch_no": item.batch_no,
        # "lot_no": item.lot_no,
        # "ar_no": item.ar_no,
        "sample_size": item.qty
    })

    doc.flags.ignore_mandatory = True
    doc.flags.ignore_permissions = True
    doc.flags.ignore_links = True

    doc.save()
    
    return doc.name


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
    frappe.msgprint(f"{batch_list}.testing for batch list")
    if not batch_list:        
        return
        
    for batch in batch_list:
        if batch.pieces == 0 or batch.average_length == 0.0 or batch.section_weight == 0.0:            
            return

    # Create Batch Group
    batch_group = frappe.new_doc("Batch Group")
    batch_group.reference_doctype = "Purchase Receipt"
    batch_group.reference_document_name = purchase_receipt.name
    batch_group.total_length_in_meter = purchase_receipt.total_length_in_meter
    weight_received_kg = purchase_receipt.weight_received * 1000
    batch_group.section_weight = round(weight_received_kg/purchase_receipt.total_length_in_meter, 2)

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
            "This Purchase Receipt is subject to approval and cannot be submitted."
        ).format(item_code, received_section_weight))

    
    