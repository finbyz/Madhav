# Copyright (c) 2025, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.naming import make_autoname


class CuttingPlan(Document):
    
    def autoname(doc):
        if doc.company == "MADHAV UDYOG PRIVATE LIMITED":
                doc.naming_series = "MUCUT.-"
        elif doc.company == "MADHAV STELCO PRIVATE LIMITED":
                doc.naming_series = "MSCUT.-"

        # Actually generate the name using the selected naming_series
        doc.name = make_autoname(doc.naming_series)
        
    def on_submit(doc):
        
        set_cutting_reference(doc)

		
        """Auto create Repack Stock Entry when Cutting Plan is submitted"""
        # Validate required data
        if not doc.cut_plan_detail:
            frappe.throw(_("Cut Plan Detail is required to create stock entry"))

        if not doc.cutting_plan_finish:
            frappe.throw(_("Cut Plan Finish is required to create stock entry"))

        try:
            # Create Repack Stock Entry
            stock_entry = create_repack_stock_entry(doc)
            
            if stock_entry:
                set_stock_entry_reference_wo(doc,stock_entry)

            # Update cutting plan with stock entry reference
            doc.db_set('stock_entry_reference', stock_entry.name, update_modified=False)

            
            frappe.msgprint(
            _(f'Repack Stock Entry <a href="/app/stock-entry/{stock_entry.name}" style="font-weight:bold;">{stock_entry.name}</a> created successfully'),
                title="Stock Entry Created",
                indicator="green"
            )
            
        except Exception as e:
            error_message = f"Error creating repack entry for {doc.name}: {str(e)}"
            
            # keep title short, details go into message
            frappe.log_error(
                title=f"Repack Error - {doc.name}",
                message=error_message
            )

            frappe.throw(_("Error creating Repack Stock Entry: {0}").format(str(e)))


def create_repack_stock_entry(cutting_plan_doc):
    """Create Repack Stock Entry with batches"""

    # Create Stock Entry document
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Repack"
    stock_entry.purpose = "Repack"
    stock_entry.company = cutting_plan_doc.company
    stock_entry.posting_date = cutting_plan_doc.get('date') or frappe.utils.today()
    stock_entry.posting_time = frappe.utils.nowtime()
    stock_entry.remarks = f"Auto created from Cutting Plan: {cutting_plan_doc.name}"
    stock_entry.cutting_plan_reference = cutting_plan_doc.name

    # Set additional fields if available
    if cutting_plan_doc.get('cost_center'):
        stock_entry.cost_center = cutting_plan_doc.cost_center

    if cutting_plan_doc.get('project'):
        stock_entry.project = cutting_plan_doc.project

    created_batches = []

    # Add SOURCE items (Items being consumed from cut_plan_detail)
    for source_item in cutting_plan_doc.cut_plan_detail:
        if source_item.item_code and source_item.qty > 0:
            source_entry = stock_entry.append("items", {})
            source_entry.item_code = source_item.item_code
            source_entry.qty = source_item.qty
            source_entry.pieces = source_item.pieces
            source_entry.average_length = source_item.length_size
            source_entry.section_weight = source_item.section_weight
            source_entry.s_warehouse = source_item.source_warehouse
            source_entry.uom = source_item.get('uom') or get_item_stock_uom(source_item.item_code)
            # source_entry.basic_rate = source_item.basic_rate
            source_entry.use_serial_batch_fields = 1

            # Add existing batch if available
            if source_item.get('batch'):
                source_entry.batch_no = source_item.batch

            # Add serial and batch bundle if exists
            if source_item.get('serial_and_batch_bundle'):
                source_entry.serial_and_batch_bundle = source_item.serial_and_batch_bundle
        
    # Add TARGET items (Items being produced from cut_plan_finish)
    for finish_item in cutting_plan_doc.cutting_plan_finish:
        if finish_item.item and finish_item.qty > 0:
            # Create new batch for finished item
            # batch_doc = create_batch_for_finish_item(cutting_plan_doc, finish_item)
            
            target_entry = stock_entry.append("items", {})
            target_entry.item_code = finish_item.item
            target_entry.qty = finish_item.qty
            target_entry.pieces = finish_item.pieces
            target_entry.average_length = finish_item.length_size
            target_entry.section_weight = finish_item.section_weight
            target_entry.t_warehouse = finish_item.get('warehouse') or cutting_plan_doc.get('default_finished_goods_warehouse')
            # target_entry.uom = finish_item.get('uom') or get_item_stock_uom(finish_item.item_code)
            # target_entry.batch_no = batch_doc.name
            # target_entry.basic_rate = finish_item.get('rate') or 0
            target_entry.use_serial_batch_fields = 1

            # Update finish item with created batch 
            # finish_item.batch_no = batch_doc

            # created_batches.append({
            #     'item': finish_item.item,
            #     'batch': batch_doc,
            #     'batch_id': batch_doc,
            #     'qty': finish_item.qty
            # })
            
            # Store reference parent batch in a custom field for batch naming
            if finish_item.get('rm_reference_batch'):
                target_entry.reference_parent_batch = finish_item.rm_reference_batch
                
    # Add SCRAP items (Items being transferred to scrap warehouse)
    if hasattr(cutting_plan_doc, 'cutting_plan_scrap_transfer') and cutting_plan_doc.cutting_plan_scrap_transfer:
        for scrap_item in cutting_plan_doc.cutting_plan_scrap_transfer:
            if scrap_item.item_code and scrap_item.scrap_qty > 0:
                scrap_entry = stock_entry.append("items", {})
                scrap_entry.item_code = scrap_item.item_code
                scrap_entry.qty = scrap_item.scrap_qty
                scrap_entry.t_warehouse = scrap_item.target_scrap_warehouse
                scrap_entry.uom = scrap_item.get('uom') or get_item_stock_uom(scrap_item.item_code)
                # scrap_entry.basic_rate = scrap_item.get('basic_rate') or 0
                scrap_entry.use_serial_batch_fields = 1
                
                # Add batch information if available
                # if scrap_item.get('batch'):
                #     scrap_entry.batch_no = scrap_item.batch
                
                # Add serial and batch bundle if exists
                # if scrap_item.get('serial_and_batch_bundle'):
                #     scrap_entry.serial_and_batch_bundle = scrap_item.serial_and_batch_bundle

    # Insert and submit stock entry
    stock_entry.insert()
    # stock_entry.submit()
    
    # cutting_plan_doc.save()

    return stock_entry


def create_batch_for_finish_item(cutting_plan_doc, finish_item):
    """Create batch for finished items using make_batch"""

    from erpnext.stock.doctype.batch.batch import make_batch

    # Prepare batch data
    dct = {
        "item": finish_item.get("item"),
        "reference_doctype": "Cutting Plan",
        "reference_name": cutting_plan_doc.name,
        "manufacturing_date": frappe.utils.today(),
    }

    # Add custom fields from finish item if available
    custom_fields = [
        'pieces', 'weight_received', 'average_length', 'section_weight',
        'length_weight_in_kg', 'no_of_packages', 'batch_yield', 'concentration'
    ]

    for field in custom_fields:
        if finish_item.get(field):
            if field == 'weight_received':
                dct[field] = finish_item.get('qty')  # Map qty to weight_received
            else:
                dct[field] = finish_item.get(field)

    # Create and return batch
    return make_batch(frappe._dict(dct))


def get_item_stock_uom(item_code):
    """Get stock UOM for item"""
    return frappe.db.get_value("Item", item_code, "stock_uom")

def set_cutting_reference(doc):
    if not doc.cut_plan_detail:
            frappe.throw(_("Cut Plan Detail is required to create stock entry"))
            
    for rm_item in doc.cut_plan_detail:
        if rm_item.work_order_reference:
            work_order = frappe.get_doc("Work Order", rm_item.work_order_reference)
            work_order.db_set("cutting_plan_reference", doc.name)
            work_order.save()

def set_stock_entry_reference_wo(doc,stock_entry):
    for row in doc.cut_plan_detail:
        if row.work_order_reference:
            wo = frappe.get_doc("Work Order", row.work_order_reference)
            wo.db_set("repack_stock_entry_reference",stock_entry.name)
            wo.save()
            
    