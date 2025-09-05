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
        
    def on_update(self):
        """Called on every save - check for workflow state change"""
        # Only proceed if workflow state actually changed to "RM Planned"
        if (self.has_value_changed("workflow_state") and 
            self.workflow_state == "RM Allocation pending( Rm Not Allocated yet)"):
            validate_cut_plan_quantities(self)
            create_material_transfer_entry(self)
        if (self.has_value_changed("workflow_state") and 
            self.workflow_state == "Cut plan pending"):
            if self.cutting_plan_scrap_transfer:
                for row in self.cutting_plan_scrap_transfer:
                    if not row.item_code:
                        frappe.throw(
                            _("Row #{0}: Item is mandatory for scrap transfer.").format(row.idx)
                        )
                    if not row.target_scrap_warehouse:
                        frappe.throw(
                            _("Row #{0}: Target Warehouse is mandatory for scrap transfer.").format(row.idx)
                        )
                    
                    
    def validate(self):
        if self.workflow_state in ["RM Allocated( Material Transfer Submitted)", "Cut plan pending", "Cut-plan Done",]:
            self.validate_material_transfer_before_approve()        
    
    def validate_material_transfer_before_approve(self):
        """Check if linked Material Transfer Stock Entry is submitted"""
        if not self.material_transfer_stock_entry:
            frappe.throw(
                _("Material Transfer Stock Entry is required before proceeding with this workflow action")
            )
        
        try:
            # Get the Stock Entry document
            stock_entry_doc = frappe.get_doc("Stock Entry", self.material_transfer_stock_entry)
            
            # Check if it's submitted (docstatus = 1)
            if stock_entry_doc.docstatus != 1:
                frappe.throw(
                    _("Material Transfer Stock Entry {0} must be submitted first. Current status: {1}")
                    .format(
                        frappe.bold(self.material_transfer_stock_entry),
                        frappe.bold("Draft" if stock_entry_doc.docstatus == 0 else "Cancelled")
                    )
                )
                
        except frappe.DoesNotExistError:
            frappe.throw(
                _("Material Transfer Stock Entry {0} does not exist. Please create it first.")
                .format(frappe.bold(self.material_transfer_stock_entry))
            )
        
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
            
def validate_cut_plan_quantities(doc):
    """Validate that qty is within 10% tolerance of wo_qty in cut plan detail table"""
    if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
        for row in doc.cut_plan_detail:
            if row.wo_qty and row.qty:
                # Calculate 10% tolerance range
                tolerance = 0.10
                min_allowed = row.wo_qty * (1 - tolerance)
                max_allowed = row.wo_qty * (1 + tolerance)
                
                # Check if qty is within tolerance
                if not (min_allowed <= row.qty <= max_allowed):
                    frappe.throw(
                        _("Row #{0}: Quantity ({1}) must be within 10% tolerance of WO Quantity ({2}). "
                          "Allowed range: {3} to {4}").format(
                            row.idx, 
                            row.qty, 
                            row.wo_qty,
                            round(min_allowed, 2),
                            round(max_allowed, 2)
                        )
                    )
            elif row.wo_qty and not row.qty:
                frappe.throw(
                    _("Row #{0}: Quantity is mandatory when WO Quantity is set.").format(row.idx)
                )

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
        default_source_warehouse = cutting_plan_doc.get('default_source_warehouse')
        if source_item.item_code and source_item.qty > 0:
            source_entry = stock_entry.append("items", {})
            source_entry.item_code = source_item.item_code
            source_entry.qty = source_item.qty
            source_entry.pieces = source_item.pieces
            source_entry.average_length = source_item.length_size
            source_entry.section_weight = source_item.section_weight
            source_entry.s_warehouse = default_source_warehouse
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
            if finish_item.return_to_stock:
                default_target_warehouse = cutting_plan_doc.get('default_unplanned_warehouse')
            else:
                default_target_warehouse = cutting_plan_doc.get('default_finished_goods_warehouse')
            
            target_entry = stock_entry.append("items", {})
            target_entry.item_code = finish_item.item
            target_entry.qty = finish_item.qty
            target_entry.pieces = finish_item.pieces
            target_entry.average_length = finish_item.length_size
            target_entry.section_weight = finish_item.section_weight
            target_entry.t_warehouse = finish_item.get('warehouse') or default_target_warehouse
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
                scrap_entry.is_finished_item = 0
                scrap_entry.is_scrap_item = 1
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
    stock_entry.submit()
    
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
            
def create_material_transfer_entry(self):
        """Create Stock Entry of type Material Transfer"""
        try:
            # Create new Stock Entry
            stock_entry = frappe.new_doc("Stock Entry")
            stock_entry.stock_entry_type = "Material Transfer"
            stock_entry.purpose = "Material Transfer"
            stock_entry.company = self.company
            stock_entry.to_warehouse = "Production Planning Yard - MS"
            # Set reference to cutting plan
            stock_entry.cutting_plan_reference = self.name
                     
            # Add items from cutting plan (assuming you have items table)
            if hasattr(self, 'cut_plan_detail') and self.cut_plan_detail:
                for item in self.cut_plan_detail:
                    stock_entry.append("items", {
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "uom": item.uom or frappe.db.get_value("Item", item.item_code, "stock_uom"),
                        "s_warehouse": item.get('source_warehouse'),
                        "t_warehouse": "Production Planning Yard - MS",
                        "batch_no": item.get('batch'),
                        "use_serial_batch_fields" : 1,
                        "pieces": item.pieces
                    })
            
            # Save the stock entry
            stock_entry.insert()
            # stock_entry.submit()
            self.material_transfer_stock_entry = stock_entry.name
            self.save(ignore_permissions=True)
            # Show success message
            frappe.msgprint(
                _("Material Transfer Entry {0} created successfully").format(
                    '<a href="/app/stock-entry/{0}">{0}</a>'.format(stock_entry.name)
                ),
                title="Stock Entry Created",
                indicator='green'
            )
            
        except Exception as e:
            error_message = f"Error creating repack entry for {self.name}: {str(e)}"
            
            # keep title short, details go into message
            frappe.log_error(
                title=f"Material Transfer Error - {self.name}",
                message=error_message
            )

            frappe.throw(_("Failed to create Material Transfer Entry: {0}").format(str(e)))    