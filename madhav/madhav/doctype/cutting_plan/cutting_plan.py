# Copyright (c) 2025, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.model.naming import make_autoname


class CuttingPlan(Document):
    
    def autoname(doc):
        # Set naming series based on both cut_plan_type and company
        if doc.cut_plan_type == "Raw Material Cut Plan":
            if doc.company == "MADHAV UDYOG PRIVATE LIMITED":
                doc.naming_series = "MU.-RMCUT.-"
            elif doc.company == "MADHAV STELCO PRIVATE LIMITED":
                doc.naming_series = "MS.-RMCUT.-"
        elif doc.cut_plan_type == "Finished Cut Plan":
            if doc.company == "MADHAV UDYOG PRIVATE LIMITED":
                doc.naming_series = "MU.-FGCUT.-"
            elif doc.company == "MADHAV STELCO PRIVATE LIMITED":
                doc.naming_series = "MS.-FGCUT.-"   

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
            self.workflow_state in ["Cut plan pending", "Finished Cut Plan Pending"]):
            if self.cutting_plan_scrap_transfer:
                for row in self.cutting_plan_scrap_transfer:
                     # Skip validation if qty is zero or not set
                    if not row.scrap_qty or row.scrap_qty == 0:
                        continue

                    if not row.item_code:
                        frappe.throw(
                            _("Row #{0}: Item is mandatory for scrap transfer.").format(row.idx)
                        )
                    if not row.target_scrap_warehouse:
                        frappe.throw(
                            _("Row #{0}: Target Warehouse is mandatory for scrap transfer.").format(row.idx)
                        )

        if (self.has_value_changed("workflow_state") and 
            self.workflow_state in ["Finished Cut Plan Pending", "Cut plan pending"]):
            self.on_cut_plan_done()         

        if (self.has_value_changed("workflow_state") and 
            self.workflow_state in ["Cut-plan Done"]):
            update_finished_cut_plan_table(self) 

        if (self.has_value_changed("workflow_state") and 
            self.workflow_state in ["Finished Cut Plan Done"]):
            validate_completed_wo(self)        
            set_burning_loss(self)
            set_burning_loss_percentage(self)
        
        # If stock entry reference was set/changed, update table immediately
        if self.has_value_changed("stock_entry_reference"):
            update_finished_cut_plan_table(self)
                    
    def validate(self):
        # Auto-set customer if field exists and is empty
        # set_customer_on_cutting_plan(self)

        if self.cut_plan_type == "Raw Material Cut Plan":
            set_qty_cut_plan_detail(self)

        if self.workflow_state in ["RM Allocated( Material Transfer Submitted)", "Cut plan pending", "Cut-plan Done",]:
            self.validate_material_transfer_before_approve()

        if self.workflow_state == "Cut-plan Done":
            update_finished_cut_plan_table(self)       
        
        # Also react if user just set the reference field during edit
        if self.has_value_changed("stock_entry_reference"):
            update_finished_cut_plan_table(self)
        
        # Always ensure qty is calculated for cut_plan_finish rows on save
        calculate_qty_for_cut_plan_finish(self)

        # Validate that total Finish qty per Work Order does not exceed available qty from RM detail
        validate_finish_qty_against_work_order(self)
        
        # Validate that finish qty per rm_reference_batch does not exceed RM batch qty
        validate_finish_qty_by_rm_batch(self)

        # Validate cutting plan finish row constraints (semi_fg_length and length sizes)
        validate_cutting_plan_finish_row_constraints(self)

        # Validate return-to-stock finish rows use an existing length size for the same FG item
        validate_return_to_stock_length_sizes(self)

        # On save: update header totals and process loss for Finished Cut Plan
        if getattr(self, 'cut_plan_type', None) == "Finished Cut Plan":
            
            set_fgsection_weight(self)
            set_difference_percentage_for_finished_rows(self)
            validate_manual_qty_tolerance(self)
            update_process_loss_qty(self)
            update_header_totals_for_finished_cut_plan(self)
            set_burning_loss(self)
            set_burning_loss_percentage(self)
               
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
        
    def on_cut_plan_done(self):

        set_cutting_reference(self)

		
        """Auto create Repack Stock Entry when Cutting Plan is submitted"""
        # Validate required data
        if not self.cut_plan_detail:
            frappe.throw(_("Cut Plan Detail is required to create stock entry"))

        if not self.cutting_plan_finish:
            frappe.throw(_("Cut Plan Finish is required to create stock entry"))

        try:
            # Create Repack Stock Entry
            stock_entry = create_repack_stock_entry(self)
            # if stock_entry:
            #     set_stock_entry_reference_wo(self,stock_entry)

            # Update cutting plan with stock entry reference
            self.db_set('stock_entry_reference', stock_entry.name, update_modified=False)
            
            # Call update_finished_cut_plan_table since db_set bypasses on_update/validate
            update_finished_cut_plan_table(self)

            
            frappe.msgprint(
            _(f'Repack Stock Entry <a href="/app/stock-entry/{stock_entry.name}" style="font-weight:bold;">{stock_entry.name}</a> created successfully'),
                title="Stock Entry Created",
                indicator="green"
            )
            
        except Exception as e:
            error_message = f"Error creating repack entry for {self.name}: {str(e)}"
            
            # keep title short, details go into message
            frappe.log_error(
                title=f"Repack Error - {self.name}",
                message=error_message
            )

            frappe.throw(_("Error creating Repack Stock Entry: {0}").format(str(e)))

          
def validate_cut_plan_quantities(doc):
    
    if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
        for row in doc.cut_plan_detail:
            if row.wo_qty and row.qty:
                
                # Fetch tolerance from document field `material_transfer_tolerance`.
                # Fallback to 20% if not set. Normalize values greater than 1 (e.g., 20 -> 0.20).
                raw_tolerance = getattr(doc, 'material_transfer_tolerance', None)
                tolerance = float(raw_tolerance) if raw_tolerance not in (None, "",) else 0.20
                if tolerance > 1:
                    tolerance = tolerance / 100.0
                min_allowed = row.wo_qty * (1 - tolerance)
                max_allowed = row.wo_qty * (1 + tolerance)
                
                # Check if qty is within tolerance
                if not (min_allowed <= row.qty <= max_allowed):
                    percent = round(tolerance * 100, 2)
                    frappe.throw(
                        _("Row #{0}: Quantity ({1}) must be within {5}% tolerance of WO Quantity ({2}). "
                          "Allowed range: {3} to {4}").format(
                            row.idx, 
                            row.qty, 
                            row.wo_qty,
                            round(min_allowed, 2),
                            round(max_allowed, 2),
                            percent
                        )
                    )
            elif row.wo_qty and not row.qty:
                frappe.throw(
                    _("Row #{0}: Quantity is mandatory when WO Quantity is set.").format(row.idx)
                )

def create_repack_stock_entry(cutting_plan_doc):
    """Create Repack Stock Entry with batches"""

    if cutting_plan_doc.cut_plan_type == "Raw Material Cut Plan":
        stock_entry_type = "RM Transfer cum Cutting Entry"
    elif cutting_plan_doc.cut_plan_type == "Finished Cut Plan":
        stock_entry_type = "FG Free Length Transfer cum Cutting Entry"

    # Create Stock Entry document
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = stock_entry_type
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
        if cutting_plan_doc.cut_plan_type == "Finished Cut Plan":
            if source_item.item_code and source_item.qty > 0 and source_item.is_finished_item:
                source_entry = stock_entry.append("items", {})
                source_entry.item_code = source_item.item_code
                source_entry.qty = source_item.qty
                source_entry.pieces = source_item.pieces
                source_entry.average_length = source_item.length_size_inch
                source_entry.section_weight = source_item.section_weight
                source_entry.s_warehouse = source_item.get('source_warehouse')
                source_entry.uom = source_item.get('uom') or get_item_stock_uom(source_item.item_code)
                # source_entry.basic_rate = source_item.basic_rate
                source_entry.use_serial_batch_fields = 1

                # Add existing batch if available
                if source_item.get('batch'):
                    source_entry.batch_no = source_item.batch

                # Add serial and batch bundle if exists
                if source_item.get('serial_and_batch_bundle'):
                    source_entry.serial_and_batch_bundle = source_item.serial_and_batch_bundle

        if cutting_plan_doc.cut_plan_type == "Raw Material Cut Plan":
            if source_item.item_code and source_item.qty > 0:
                source_entry = stock_entry.append("items", {})
                source_entry.item_code = source_item.item_code
                source_entry.qty = source_item.qty
                source_entry.pieces = source_item.pieces
                source_entry.average_length = source_item.length_size_inch
                source_entry.section_weight = source_item.section_weight
                source_entry.s_warehouse = source_item.get('source_warehouse')
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
        if finish_item.item or finish_item.fg_item and finish_item.qty > 0:
            # Create new batch for finished item
            # batch_doc = create_batch_for_finish_item(cutting_plan_doc, finish_item)
            if finish_item.return_to_stock:
                default_target_warehouse = cutting_plan_doc.get('default_unplanned_warehouse')
            else:
                default_target_warehouse = cutting_plan_doc.get('default_finished_goods_warehouse')

            if cutting_plan_doc.cut_plan_type == "Finished Cut Plan":
                section_weight = frappe.db.get_value("Item", finish_item.fg_item, "weight_per_meter")
            else:
                section_weight = frappe.db.get_value("Item", finish_item.item, "weight_per_meter")
            
            target_entry = stock_entry.append("items", {})
            target_entry.item_code = finish_item.item if cutting_plan_doc.cut_plan_type == "Raw Material Cut Plan" else finish_item.fg_item
            target_entry.qty = finish_item.qty
            target_entry.pieces = finish_item.pieces
            target_entry.average_length = finish_item.length_size_inch if cutting_plan_doc.cut_plan_type == "Raw Material Cut Plan" else finish_item.length_size
            target_entry.section_weight = section_weight
            target_entry.lot_no = finish_item.lot_no
            target_entry.return_to_stock = finish_item.return_to_stock
            target_entry.semi_fg_length = finish_item.semi_fg_length
            target_entry.fg_item = finish_item.fg_item
            target_entry.t_warehouse = finish_item.get('warehouse') or default_target_warehouse
            # target_entry.uom = finish_item.get('uom') or get_item_stock_uom(finish_item.item_code)
            # target_entry.batch_no = batch_doc.name
            # target_entry.basic_rate = finish_item.get('rate') or 0
            target_entry.use_serial_batch_fields = 1
            target_entry.work_order_reference = finish_item.work_order_reference

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
                scrap_entry.pieces = scrap_item.pieces
                scrap_entry.average_length = scrap_item.length_size
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


@frappe.whitelist()
def get_total_qty_for_rm_cut_plan(cutting_plan: str | None = None):
	"""Return total qty from referenced RM Cutting Plan (excluding rows marked return_to_stock)."""

	if not cutting_plan:
		return 0

	total_qty = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(qty), 0)
		FROM `tabCutting Plan Finish`
		WHERE parent = %s
			AND IFNULL(return_to_stock, 0) = 0
		""",
		(cutting_plan,),
	)[0][0]

	return float(total_qty or 0)


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

def set_customer_on_cutting_plan(doc):
    """Populate `customer` on Cutting Plan if the field exists but is empty.

    Resolution order:
    1) From any row's `work_order_reference` -> related Sales Order -> Customer
    2) From header `work_order` link (if present)
    3) From Work Order's own `customer` (if customized)
    4) From linked Production Plan -> direct `customer` or first Sales Order -> Customer
    """
    # If there is no `customer` field on this DocType, or it's already set, do nothing
    if not hasattr(doc, "customer"):
        return
    if getattr(doc, "customer", None):
        return

    work_order_names = []
    # Collect WOs from child table
    if hasattr(doc, "cut_plan_detail") and doc.cut_plan_detail:
        for row in doc.cut_plan_detail:
            two_ref = getattr(row, "work_order_reference", None)
            if two_ref:
                work_order_names.append(two_ref)

    # Fallback to header-level work_order if provided
    if not work_order_names and getattr(doc, "work_order", None):
        work_order_names.append(doc.work_order)

    def fetch_customer_from_work_order(work_order_name):
        try:
            wo = frappe.get_doc("Work Order", work_order_name)
            # Try via Sales Order on Work Order
            so_name = getattr(wo, "sales_order", None) or getattr(wo, "sales_order_id", None)
            if so_name:
                customer = frappe.db.get_value("Sales Order", so_name, "customer")
                if customer:
                    return customer
            # Try direct customer on WO (if customized)
            customer_on_wo = getattr(wo, "customer", None)
            if customer_on_wo:
                return customer_on_wo
            # Try via Production Plan linked on WO
            pp_name = getattr(wo, "production_plan", None)
            if pp_name:
                try:
                    pp = frappe.get_doc("Production Plan", pp_name)
                    pp_customer = getattr(pp, "customer", None)
                    if pp_customer:
                        return pp_customer
                    rows = frappe.get_all(
                        "Production Plan Sales Order",
                        filters={"parent": pp_name},
                        fields=["sales_order"],
                        limit=1,
                    )
                    if rows:
                        so = rows[0].get("sales_order")
                        if so:
                            customer = frappe.db.get_value("Sales Order", so, "customer")
                            if customer:
                                return customer
                except Exception:
                    return None
        except Exception:
            return None
        return None

    # Try each collected Work Order for a customer
    for wo_name in work_order_names:
        customer = fetch_customer_from_work_order(wo_name)
        if customer:
            doc.customer = customer
            return

    # Final fallback via document's own Production Plan link
    pp_name = getattr(doc, "production_plan", None)
    if pp_name and not getattr(doc, "customer", None):
        try:
            pp = frappe.get_doc("Production Plan", pp_name)
            pp_customer = getattr(pp, "customer", None)
            if pp_customer:
                doc.customer = pp_customer
                return
            rows = frappe.get_all(
                "Production Plan Sales Order",
                filters={"parent": pp_name},
                fields=["sales_order"],
                limit=1,
            )
            if rows:
                so = rows[0].get("sales_order")
                if so:
                    customer = frappe.db.get_value("Sales Order", so, "customer")
                    if customer:
                        doc.customer = customer
                        return
        except Exception:
            return
            
def create_material_transfer_entry(self):
        # Validate per-row requested qty vs available batch qty in the specified warehouse
        _validate_rm_batch_availability(self)
        
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
                        "pieces": item.pieces,
                        "average_length": item.length_size_inch
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
            error_message = f"Error creating material transfer entry for {self.name}: {str(e)}"
            
            # keep title short, details go into message
            frappe.log_error(
                title=f"Material Transfer Error - {self.name}",
                message=error_message
            )

            frappe.throw(_("Failed to create Material Transfer Entry: {0}").format(str(e)))    


def _validate_rm_batch_availability(cutting_plan):
    """Validate that requested quantities don't exceed available batch stock in warehouse"""
    
    if not hasattr(cutting_plan, 'cut_plan_detail') or not cutting_plan.cut_plan_detail:
        return
    
    # Group items by batch and warehouse, summing quantities
    batch_warehouse_totals = {}
    batch_warehouse_rows = {}  # Track which rows use each batch-warehouse combo
    
    for idx, item in enumerate(cutting_plan.cut_plan_detail, start=1):
        batch_no = item.get('batch')
        source_warehouse = item.get('source_warehouse')
        requested_qty = float(item.qty or 0)
        
        # Skip if batch or warehouse is missing
        if not batch_no or not source_warehouse:
            continue
        
        # Create unique key for batch-warehouse combination
        key = (batch_no, source_warehouse)
        
        # Sum quantities for same batch-warehouse combination
        if key not in batch_warehouse_totals:
            batch_warehouse_totals[key] = 0.0
            batch_warehouse_rows[key] = []
        
        batch_warehouse_totals[key] += requested_qty
        batch_warehouse_rows[key].append(idx)
    
    # Now validate each unique batch-warehouse combination
    errors = []
    
    for (batch_no, source_warehouse), total_requested_qty in batch_warehouse_totals.items():
        # Get available quantity in tonnes for this batch in this warehouse
        available_qty = _get_available_tonnes_for_batch_warehouse(batch_no, source_warehouse)
        
        # Check if total requested quantity exceeds available quantity
        if total_requested_qty > available_qty:
            rows = batch_warehouse_rows[(batch_no, source_warehouse)]
            row_str = ", ".join([f"#{r}" for r in rows])
            errors.append(
                f"Batch {batch_no} in {source_warehouse} (Rows {row_str}) - "
                f"Total Requested: {total_requested_qty:.3f} tonnes, Available: {available_qty:.3f} tonnes"
            )
    
    # If there are any validation errors, throw them all at once
    if errors:
        error_msg = "<br>".join(errors)
        frappe.throw(
            _("Insufficient batch quantity in warehouse:<br>{0}").format(error_msg),
            title=_("Batch Availability Error")
        )


def _get_available_tonnes_for_batch_warehouse(batch_id: str, warehouse: str) -> float:
    """Get available quantity (in tonnes) for a given Batch in a specific warehouse.

    Uses Serial and Batch Bundle to get accurate batch quantities.
    """
    if not batch_id or not warehouse:
        return 0.0

    try:
        # Get item for this batch
        item_code = frappe.db.get_value("Batch", batch_id, "item")
        if not item_code:
            return 0.0

        # Fetch available stock using Serial and Batch Bundle
        result = frappe.db.sql("""
            SELECT ROUND(COALESCE(SUM(sbbe.qty), 0), 3) AS available_qty
            FROM `tabSerial and Batch Entry` sbbe
            INNER JOIN `tabSerial and Batch Bundle` sbb 
                ON sbbe.parent = sbb.name
            WHERE sbbe.batch_no = %(batch_no)s
              AND sbbe.warehouse = %(warehouse)s
              AND sbb.item_code = %(item_code)s
              AND sbb.docstatus = 1
              AND sbb.is_cancelled = 0
        """, {
            "item_code": item_code,
            "warehouse": warehouse,
            "batch_no": batch_id
        }, as_dict=True)
        
        if result and len(result) > 0:
            available_qty = float(result[0].available_qty or 0.0)
            return max(available_qty, 0.0)  # Ensure non-negative
        else:
            return 0.0

    except Exception as e:
        frappe.log_error(
            title=f"Batch Availability Error - {batch_id}",
            message=f"Error getting available quantity for batch {batch_id} in warehouse {warehouse}: {str(e)}\n{frappe.get_traceback()}"
        )
        return 0.0

def validate_completed_wo(self):
    try:
        # Collect unique work order references from cut_plan_detail
        work_orders = set()
        if hasattr(self, 'cut_plan_detail') and self.cut_plan_detail:
            for rm in self.cut_plan_detail:
                wo = getattr(rm, 'work_order_reference', None)
                if wo:
                    work_orders.add(wo)
        
        if not work_orders:
            return  # nothing to validate
        
        
        # Check status of each work order
        incomplete_wos = []
        for wo in work_orders:
            wo_doc = frappe.get_doc("Work Order", wo)
            if wo_doc.status != "Completed":
                incomplete_wos.append(
                    _(f"Work Order {wo} has status '{wo_doc.status}' (must be 'Completed')")
                )
        
        if incomplete_wos:
            frappe.throw("<br>".join(incomplete_wos))
            
    except frappe.DoesNotExistError as e:
        frappe.throw(_(f"Work Order not found: {str(e)}"))
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan WO Completion Validation Error",
            message=f"Doc: {getattr(self, 'name', '')} Error: {str(e)}"
        )
        frappe.throw(_("Error validating work order completion. Please check error logs."))

def update_finished_cut_plan_table(self):
    if self.stock_entry_reference:
        stock_entry_doc = frappe.get_doc("Stock Entry", self.stock_entry_reference)
        
        finished_items = [
            item for item in stock_entry_doc.items 
            if item.get("is_finished_item") == 1 and item.get("is_scrap_item") != 1 and item.get("return_to_stock") != 1
        ]
        # frappe.throw("finished_items: "+str(finished_items))
        # Clear existing entries in cut_plan_finish table (optional)
        # self.cut_plan_finish = []
        
        # Track which plan entry to use next per item so batches map to corresponding entries
        plan_entries_cache = {}
        plan_entry_index_by_item = {}

        # Process each finished item from stock entry
        for item in finished_items:
            if item.batch_no:  # Only if batch exists
                # Check if this batch is already in the table to avoid duplicates
                existing_batches = [row.batch for row in self.cut_plan_finish if row.batch]
                
                if item.batch_no not in existing_batches:
                    # Find corresponding cutting plan finish entries for this item
                    if item.item_code not in plan_entries_cache:
                        plan_entries_cache[item.item_code] = get_cutting_plan_entries_for_item(self, item.item_code)
                        plan_entry_index_by_item[item.item_code] = 0
                    cutting_plan_entries = plan_entries_cache.get(item.item_code, [])
                    
                    if cutting_plan_entries:
                        # Use the next corresponding plan entry for this item's batch
                        use_index = plan_entry_index_by_item.get(item.item_code, 0)
                        if use_index >= len(cutting_plan_entries):
                            use_index = len(cutting_plan_entries) - 1
                        plan_entry = cutting_plan_entries[use_index]
                        # Increment pointer for next batch of same item
                        if plan_entry_index_by_item.get(item.item_code, 0) < len(cutting_plan_entries) - 1:
                            plan_entry_index_by_item[item.item_code] = use_index + 1
                        no_of_sizes = getattr(plan_entry, "no_of_length_sizes", 0) or 1
                        max_slots = min(int(no_of_sizes), 5)
                        # Resolve section_weight from fg_item's Item.weight_per_meter
                        fg_item_code = getattr(item, "fg_item", None)
                        section_weight_from_fg = frappe.db.get_value("Item", fg_item_code, "weight_per_meter") if fg_item_code else None
                        root_radius_from_fg = frappe.db.get_value("Item", fg_item_code, "root_radius") if fg_item_code else None
                        # Get the pieces value from cutting_plan_finish (plan_entry)
                        # This is the total_pcs we want to use
                        total_pcs_value = getattr(plan_entry, "pieces", None)
                        for i in range(1, max_slots + 1):
                            pieces_field = f"pieces_{i}"
                            length_size_field = f"length_size_{i}"
                            pieces_value = getattr(plan_entry, pieces_field, None)
                            length_size_value = getattr(plan_entry, length_size_field, None)
                            if pieces_value or length_size_value:
                                # Compute qty in tonnes when all inputs are available
                                qty_tonnes_val = None
                                try:
                                    if pieces_value and length_size_value and section_weight_from_fg:
                                        qty_kg = float(pieces_value) * float(length_size_value) * float(section_weight_from_fg)*float(total_pcs_value)
                                        qty_tonnes_val = round(qty_kg / 1000.0, 3)
                                except Exception:
                                    qty_tonnes_val = None
                                self.append("cut_plan_finish", {
                                    "batch": item.batch_no,
                                    "item": item.item_code,
                                    "fg_item": getattr(item, "fg_item", None),
                                    "section_weight": section_weight_from_fg,
                                    "root_radius": root_radius_from_fg,
                                    "semi_fg_length": getattr(item, "semi_fg_length", None),
                                    "pieces": pieces_value,
                                    "total_pcs": total_pcs_value, 
                                    "length_size": length_size_value,
                                    "qty": qty_tonnes_val,
                                    "source_plan_entry": plan_entry.name if hasattr(plan_entry, 'name') else None,
                                    "work_order_reference": item.work_order_reference,
                                    "lot_no": item.lot_no
                                })
                            
                    else:
                        # If no cutting plan entries found, create a basic entry
                        fg_item_code = getattr(item, "fg_item", None)
                        section_weight_from_fg = frappe.db.get_value("Item", fg_item_code, "weight_per_meter") if fg_item_code else None
                        root_radius_from_fg = frappe.db.get_value("Item", fg_item_code, "root_radius") if fg_item_code else None
                        # Compute qty in tonnes when all inputs are available
                        qty_tonnes_val = None
                        try:
                            # In this minimal entry, we don't have pieces/length from plan; leave qty None
                            if False:
                                pass
                        except Exception:
                            qty_tonnes_val = None
                        self.append("cut_plan_finish", {
                            "batch": item.batch_no,
                            "item": item.item_code,
                            "fg_item": getattr(item, "fg_item", None),
                            "section_weight": section_weight_from_fg,
                            "root_radius": root_radius_from_fg,
                            "semi_fg_length": getattr(item, "semi_fg_length", None),
                            "qty": qty_tonnes_val,
                            "total_pcs": None, 
                            "work_order_reference": item.work_order_reference,
                            "lot_no": item.lot_no
                        })
        
        # Save the document to persist changes
        # self.save()


def get_cutting_plan_entries_for_item(doc, item_code):
    
    if hasattr(doc, 'cutting_plan_finish'):
        return [entry for entry in doc.cutting_plan_finish 
               if getattr(entry, 'item', None) == item_code]
    
    # Option 2: If cutting plan data is in a related document
    # Replace 'cutting_plan_reference' with your actual field name
    if hasattr(doc, 'cutting_plan_reference') and doc.cutting_plan_reference:
        cutting_plan_doc = frappe.get_doc("Cutting Plan", doc.cutting_plan_reference)
        return [entry for entry in cutting_plan_doc.cut_plan_finish 
               if getattr(entry, 'item', None) == item_code]
    
    # Option 3: If you need to query from database
    # return frappe.get_all("Cutting Plan Finish", 
    #                      filters={"item": item_code, "parent": doc.cutting_plan_reference},
    #                      fields=["*"])
    
    return []

def calculate_qty_for_cut_plan_finish(doc):
    """Calculate derived fields for rows in cutting_plan_finish on save.

    Mirrors client-side formulas so uploads/back-end updates stay consistent.

    - qty (tonnes) = pieces × length_size × section_weight ÷ 1000
    - total_length_in_meter = pieces × length_size
    - weight_per_length = section_weight × length_size
    - remaining_weight = weight_per_length − (process_loss% of weight_per_length)
    - semi_fg_length = remaining_weight ÷ Item.weight_per_meter (of fg_item)
    - Also sets header cut_plan_total_qty = sum(child.qty)
    """
    if doc.cut_plan_type == "Finished Cut Plan":
        return
    try:
        total_cut_plan_qty = 0.0

        if hasattr(doc, 'cutting_plan_finish') and doc.cutting_plan_finish:
            for row in doc.cutting_plan_finish:
                pieces = float(getattr(row, 'pieces', 0) or 0)
                length_size = float(getattr(row, 'length_size_inch', 0) or 0)
                section_weight = float(getattr(row, 'section_weight', 0) or 0)

                # Set lot_no as "lot_no_type - lot_number" when available
                try:
                    lot_no_type_val = getattr(row, 'lot_no_type', None)
                    lot_number_val = getattr(row, 'lot_number', None)
                    if hasattr(row, 'lot_no') and lot_no_type_val and lot_number_val:
                        composed_lot_no = f"{lot_no_type_val} - {lot_number_val}"
                        try:
                            row.db_set('lot_no', composed_lot_no, update_modified=False)
                        except Exception:
                            row.lot_no = composed_lot_no
                except Exception:
                    pass

                # qty and total_length_in_meter
                if pieces and length_size and section_weight:
                    qty_kg = pieces * length_size/39.37 * section_weight*39.37
                    qty_tonnes = round(qty_kg / 1000.0, 3)
                    try:
                        row.db_set('qty', qty_tonnes, update_modified=False)
                    except Exception:
                        row.qty = qty_tonnes
                    total_cut_plan_qty += qty_tonnes

                # Set total_length_in_meter if field exists
                if hasattr(row, 'total_length_in_meter_inch') and (pieces and length_size):
                    total_length_val = pieces * length_size
                    try:
                        row.db_set('total_length_in_meter_inch', total_length_val, update_modified=False)
                    except Exception:
                        row.total_length_in_meter_inch = total_length_val

                # weight_per_length = section_weight * length_size
                if hasattr(row, 'weight_per_length') and (section_weight and length_size):
                    wpl_val = section_weight * length_size
                    try:
                        row.db_set('weight_per_length', wpl_val, update_modified=False)
                    except Exception:
                        row.weight_per_length = wpl_val

                # remaining_weight with optional process_loss%
                process_loss = float(getattr(row, 'process_loss', 0) or 0)

                # if hasattr(row, 'qty') and process_loss:
                #     process_loss_qty = row.qty * process_loss / 100
                #     remaining_qty = row.qty - process_loss_qty
                #     try:
                #         row.db_set('process_loss_qty', process_loss_qty, update_modified=False)
                #     except Exception:
                #         row.process_loss_qty = process_loss_qty
                #     try:
                #         row.db_set('qty_after_loss', remaining_qty, update_modified=False)
                #     except Exception:
                #         row.qty_after_loss = remaining_qty
                #     total_cut_plan_qty += remaining_qty

                if hasattr(row, 'remaining_weight'):
                    if getattr(row, 'weight_per_length', None):
                        base_wpl = float(row.weight_per_length)
                    else:
                        base_wpl = section_weight * length_size  if (section_weight and length_size) else 0

                    if base_wpl:
                        remaining_val = base_wpl - (base_wpl * process_loss / 100.0)
                        try:
                            row.db_set('remaining_weight', remaining_val, update_modified=False)
                        except Exception:
                            row.remaining_weight = remaining_val

                # semi_fg_length = remaining_weight / item.weight_per_meter (using fg_item)
                if hasattr(row, 'semi_fg_length'):
                    remaining_weight = float(getattr(row, 'remaining_weight', 0) or 0)
                    fg_item = getattr(row, 'fg_item', None)
                    if remaining_weight and fg_item:
                        wpm = frappe.db.get_value("Item", fg_item, "weight_per_meter") or 0
                        try:
                            wpm = float(wpm or 0)
                        except Exception:
                            wpm = 0
                        if wpm:
                            semi_len_val = remaining_weight / wpm
                            try:
                                row.db_set('semi_fg_length', semi_len_val, update_modified=False)
                            except Exception:
                                row.semi_fg_length = semi_len_val

        # Update header total
        if hasattr(doc, 'cut_plan_total_qty'):
            try:
                doc.db_set('cut_plan_total_qty', round(total_cut_plan_qty, 3), update_modified=False)
            except Exception:
                doc.cut_plan_total_qty = round(total_cut_plan_qty, 3)

        # Also set scrap qty in scrap transfer table as (total_qty - cut_plan_total_qty)
        try:
            # Compute total_qty from cut_plan_detail
            total_qty_detail = 0.0
            if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
                for rm_row in doc.cut_plan_detail:
                    total_qty_detail += float(getattr(rm_row, 'qty', 0) or 0)

            # Use the freshly computed total_cut_plan_qty
            scrap_qty = round((total_qty_detail - (float(getattr(doc, 'cut_plan_total_qty', 0) or 0))), 3)

            if scrap_qty == 0:
                # Clear the entire scrap transfer table if zero
                doc.cutting_plan_scrap_transfer = []
            else:
                # Ensure child table exists; create first row if missing
                if not getattr(doc, 'cutting_plan_scrap_transfer', None):
                    doc.cutting_plan_scrap_transfer = []
                if len(doc.cutting_plan_scrap_transfer) == 0:
                    row = doc.append('cutting_plan_scrap_transfer', {})
                else:
                    row = doc.cutting_plan_scrap_transfer[0]
                try:
                    row.db_set('scrap_qty', scrap_qty, update_modified=False)
                except Exception:
                    row.scrap_qty = scrap_qty
        except Exception:
            pass

    except Exception as e:
        frappe.log_error(
            title="Cut Plan Finish Derived Fields Calc Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}"
        )


def validate_finish_qty_against_work_order(doc):
    """Ensure that total qty in cutting_plan_finish per work_order_reference
    does not exceed the total qty assigned to the same work order(s) in cut_plan_detail.

    Both sides use qty in tonnes as per existing conventions.
    """
    if doc.cut_plan_type == "Finished Cut Plan":
        return
    
    try:
        # Build allowed qty per WO from cut_plan_detail
        allowed_by_wo = {}
        if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
            for rm in doc.cut_plan_detail:
                wo = getattr(rm, 'work_order_reference', None)
                qty_val = float(getattr(rm, 'qty', 0) or 0)
                if wo:
                    allowed_by_wo[wo] = allowed_by_wo.get(wo, 0.0) + qty_val

        if not allowed_by_wo:
            return  # nothing to validate

        # Sum produced/finish qty per WO from cutting_plan_finish
        used_by_wo = {}
        if hasattr(doc, 'cutting_plan_finish') and doc.cutting_plan_finish:
            for fin in doc.cutting_plan_finish:
                wo = getattr(fin, 'work_order_reference', None)
                qty_val = float(getattr(fin, 'qty', 0) or 0)
                if wo:
                    used_by_wo[wo] = used_by_wo.get(wo, 0.0) + qty_val

        # Check for exceedances
        messages = []
        for wo, used_qty in used_by_wo.items():
            allowed_qty = allowed_by_wo.get(wo, 0.0)
            if allowed_qty and used_qty > allowed_qty + 1e-9:
                messages.append(
                    _(f"Work Order {wo}: Finish qty {used_qty:.3f} exceeds allowed {allowed_qty:.3f} from RM Detail.")
                )

        if messages:
            frappe.throw("<br>".join(messages))
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan WO Qty Validation Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}"
        )


def validate_finish_qty_by_rm_batch(doc):
    """Ensure that total qty in cutting_plan_finish per rm_reference_batch
    does not exceed the total qty available for the same batch in cut_plan_detail.

    Both sides use qty in tonnes as per existing conventions.
    """
    if doc.cut_plan_type == "Finished Cut Plan":
        return

    try:
        # Build allowed qty per RM batch from cut_plan_detail
        allowed_by_batch = {}
        if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
            for rm in doc.cut_plan_detail:
                batch_no = getattr(rm, 'batch', None)
                qty_val = float(getattr(rm, 'qty', 0) or 0)
                if batch_no:
                    allowed_by_batch[batch_no] = allowed_by_batch.get(batch_no, 0.0) + qty_val

        if not allowed_by_batch:
            return  # nothing to validate

        # Sum produced/finish qty per RM reference batch from cutting_plan_finish
        used_by_batch = {}
        if hasattr(doc, 'cutting_plan_finish') and doc.cutting_plan_finish:
            for fin in doc.cutting_plan_finish:
                ref_batch = getattr(fin, 'rm_reference_batch', None)
                qty_val = float(getattr(fin, 'qty', 0) or 0)
                if ref_batch:
                    used_by_batch[ref_batch] = used_by_batch.get(ref_batch, 0.0) + qty_val

        if not used_by_batch:
            return

        # Check for exceedances
        messages = []
        for batch_no, used_qty in used_by_batch.items():
            allowed_qty = allowed_by_batch.get(batch_no, 0.0)
            if allowed_qty and used_qty > allowed_qty + 1e-9:
                messages.append(
                    _(f"RM Batch {batch_no}: Finish qty {used_qty:.3f} exceeds available {allowed_qty:.3f} from RM Detail. Please adjust quantities.")
                )

        if messages:
            frappe.throw("<br>".join(messages))
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan RM Batch Qty Validation Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}"
        )

# def update_header_totals_for_finished_cut_plan(doc):
#     """Calculate and update header totals when cut_plan_type == 'Finished Cut Plan'.

#     - total_qty: sum of qty in `cut_plan_detail`
#     - cut_plan_total_qty: sum of qty in `cutting_plan_finish`
#     """
#     try:
#         total_qty_detail = 0.0
#         if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
#             for row in doc.cut_plan_detail:
#                 total_qty_detail += float(getattr(row, 'qty', 0) or 0)

#         total_qty_finish = 0.0
#         if hasattr(doc, 'cutting_plan_finish') and doc.cutting_plan_finish:
#             for row in doc.cutting_plan_finish:
#                 total_qty_finish += float(getattr(row, 'manual_qty', 0) or 0)

#         # Set header fields (rounded to 3 decimals to match UI behavior)
#         try:
#             doc.db_set('total_qty', round(total_qty_detail, 3), update_modified=False)
#         except Exception:
#             doc.total_qty = round(total_qty_detail, 3)

#         try:
#             doc.db_set('cut_plan_total_qty', round(total_qty_finish, 3), update_modified=False)
#         except Exception:
#             doc.cut_plan_total_qty = round(total_qty_finish, 3)

#         # Also update first row of cutting_plan_scrap_transfer.scrap_qty
#         # scrap_qty = total_qty - cut_plan_total_qty
#         try:
#             scrap_qty = round((total_qty_detail - total_qty_finish), 3)
#             if scrap_qty == 0:
#                 # Clear the entire scrap transfer table if zero
#                 doc.cutting_plan_scrap_transfer = []
#             else:
#                 # Ensure child table exists; create first row if missing
#                 if not getattr(doc, 'cutting_plan_scrap_transfer', None):
#                     doc.cutting_plan_scrap_transfer = []
#                 if len(doc.cutting_plan_scrap_transfer) == 0:
#                     row = doc.append('cutting_plan_scrap_transfer', {})
#                 else:
#                     row = doc.cutting_plan_scrap_transfer[0]
#                 try:
#                     row.db_set('scrap_qty', scrap_qty, update_modified=False)
#                 except Exception:
#                     row.scrap_qty = scrap_qty
#         except Exception:
#             pass
#     except Exception as e:
#         frappe.log_error(
#             title="Cutting Plan Header Totals Error",
#             message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}"
#         )

def update_header_totals_for_finished_cut_plan(doc):
    """Calculate and update header totals when cut_plan_type == 'Finished Cut Plan'.

    - total_qty: sum of qty in `cut_plan_detail`
    - cut_plan_total_qty: sum of manual_qty in `cutting_plan_finish`
    - scrap_qty (first row only): set once when empty/first created; user edits are preserved
    """
    try:
        # Calculate total qty from cut_plan_detail
        total_qty_detail = 0.0
        if hasattr(doc, 'cut_plan_detail') and doc.cut_plan_detail:
            for row in doc.cut_plan_detail:
                if row.is_finished_item != 1:
                    total_qty_detail += float(getattr(row, 'qty', 0) or 0)

        # Calculate total qty from cutting_plan_finish
        total_qty_finish = 0.0
        if hasattr(doc, 'cutting_plan_finish') and doc.cutting_plan_finish:
            for row in doc.cutting_plan_finish:
                total_qty_finish += float(getattr(row, 'manual_qty', 0) or 0)

        # Round to 3 decimals
        total_qty_detail = round(total_qty_detail, 3)
        total_qty_finish = round(total_qty_finish, 3)
        
        # Update header fields
        if doc.docstatus == 0:  # Draft
            doc.total_qty = total_qty_detail
            doc.cut_plan_total_qty = total_qty_finish
        else:  # Submitted or Cancelled
            doc.db_set('total_qty', total_qty_detail, update_modified=False)
            doc.db_set('cut_plan_total_qty', total_qty_finish, update_modified=False)

        # Set first-row scrap qty only once; do not overwrite user edits
        if not hasattr(doc, 'cutting_plan_scrap_transfer'):
            doc.cutting_plan_scrap_transfer = []

        if len(doc.cutting_plan_scrap_transfer) == 0:
            process_loss = float(getattr(doc, "process_loss_qty", 0) or 0)
            base_scrap_qty = round((total_qty_detail + process_loss) - total_qty_finish, 3)
            row = doc.append('cutting_plan_scrap_transfer', {})
            initial_scrap_qty = base_scrap_qty if base_scrap_qty > 0 else 0
            if doc.docstatus == 0:
                row.scrap_qty = initial_scrap_qty
            else:
                row.db_set('scrap_qty', initial_scrap_qty, update_modified=False)
        else:
            first_row = doc.cutting_plan_scrap_transfer[0]
            if first_row.get('scrap_qty') in (None, ""):
                process_loss = float(getattr(doc, "process_loss_qty", 0) or 0)
                base_scrap_qty = round((total_qty_detail + process_loss) - total_qty_finish, 3)
                initial_scrap_qty = base_scrap_qty if base_scrap_qty > 0 else 0
                if doc.docstatus == 0:
                    first_row.scrap_qty = initial_scrap_qty
                else:
                    first_row.db_set('scrap_qty', initial_scrap_qty, update_modified=False)

    except Exception as e:
        frappe.log_error(
            title="Cutting Plan Header Totals Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}\n{frappe.get_traceback()}"
        )


def update_process_loss_qty(doc):
    """Set process_loss_qty on Finished Cut Plans based on RM vs FG quantities.

    process_loss_qty = RM_cut_plan_qty (excluding return_to_stock)
                       - current Finished Cut Plan qty (cut_plan_total_qty)
    """
    try:
        if getattr(doc, "cut_plan_type", None) != "Finished Cut Plan":
            return

        rm_ref = getattr(doc, "reference_rm_cut_plan", None)
        if not rm_ref:
            # No reference → no process loss
            if hasattr(doc, "process_loss_qty"):
                if doc.docstatus == 0:
                    doc.process_loss_qty = 0
                else:
                    doc.db_set("process_loss_qty", 0, update_modified=False)
            return

        # RM quantity from referenced RM cut plan
        rm_qty = get_total_qty_for_rm_cut_plan(rm_ref)

        # FG quantity from this Finished Cut Plan - prefer header field if present
        fg_qty = float(getattr(doc, "total_qty", 0) or 0)
        if not fg_qty and getattr(doc, "cut_plan_detail", None):
            fg_qty = sum(float(getattr(row, "qty", 0) or 0) for row in doc.cutting_plan_finish)

        process_loss = rm_qty - fg_qty

        if hasattr(doc, "process_loss_qty"):
            if doc.docstatus == 0:
                doc.process_loss_qty = round(process_loss, 3)
            else:
                doc.db_set("process_loss_qty", round(process_loss, 3), update_modified=False)

    except Exception:
        frappe.log_error(
            title="Cutting Plan Process Loss Qty Error",
            message=f"Doc: {getattr(doc, 'name', '')}\n{frappe.get_traceback()}",
        )

def set_fgsection_weight(doc):
    for row in doc.cutting_plan_finish:
        if row.fg_item:  
                        
            section_weight = frappe.db.get_value("Item",row.fg_item,"weight_per_meter")
            row.db_set('section_weight', section_weight, update_modified=False)
            
            cal_qty =  row.pieces * row.length_size * float(row.section_weight)

            qty_in_kg = round(cal_qty / 1000, 3)
           
            row.db_set('qty', qty_in_kg, update_modified=False)


def set_qty_cut_plan_detail(doc):
    total_qty_detail = 0.0
        
    for row in doc.cut_plan_detail:
        row.db_set('length_size', row.length_size_inch/39.37, update_modified=False)
        row.db_set('section_weight', row.section_weight_inch*39.37, update_modified=False)
        
        cal_qty =  row.pieces * row.length_size * row.section_weight
        row.db_set('qty', cal_qty/1000, update_modified=False)

        total_qty_detail += float(getattr(row, 'qty', 0) or 0)

    doc.db_set('total_qty', total_qty_detail, update_modified=False)


def set_difference_percentage_for_finished_rows(doc):
    """For Finished Cut Plan: set difference_percentage per cutting_plan_finish row
    as percentage difference of manual_qty with respect to qty.
    difference_percentage = ((manual_qty - qty) / qty) * 100
    """
    try:
        if getattr(doc, 'cut_plan_type', None) != "Finished Cut Plan":
            return
        if not hasattr(doc, 'cutting_plan_finish') or not doc.cutting_plan_finish:
            return

        for row in doc.cutting_plan_finish:
            qty = float(getattr(row, 'qty', 0) or 0)
            manual = float(getattr(row, 'manual_qty', 0) or 0)
            
            if qty > 0:
                diff_pct = ((manual - qty) / qty) * 100.0
            else:
                # If qty is zero, set 0 to avoid divide-by-zero; adjust if you prefer 100 for any manual>0
                diff_pct = 0.0

            # Write with minimal side-effects
            try:
                row.db_set('difference', round(diff_pct, 2), update_modified=False)
            except Exception:
                row.difference = round(diff_pct, 2)
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan Difference % Calc Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}\n{frappe.get_traceback()}"
        )


def validate_manual_qty_tolerance(doc):
    """Ensure manual_qty stays within tolerance of qty for Finished Cut Plan.

    Allowed range: qty * (1 - tol%) to qty * (1 + tol%) where tol% = manual_qty_tolerance / 100
    If qty is zero, manual_qty must also be zero.
    """
    if getattr(doc, 'cut_plan_type', None) != "Finished Cut Plan":
        return

    try:
        tol_percent = float(getattr(doc, 'manual_qty_tolerance', 0) or 0)
        tol = tol_percent / 100.0

        if not hasattr(doc, 'cutting_plan_finish') or not doc.cutting_plan_finish:
            return

        errors = []
        for row in doc.cutting_plan_finish:
            qty = float(getattr(row, 'qty', 0) or 0)
            manual = float(getattr(row, 'manual_qty', 0) or 0)

            if qty <= 0:
                if abs(manual) > 1e-9:
                    errors.append(
                        _(f"Row #{row.idx}: Manual Qty {manual:.3f} must be 0 when Qty is 0.")
                    )
                continue

            min_allowed = qty * (1.0 - tol)
            max_allowed = qty * (1.0 + tol)

            if not (min_allowed - 1e-9 <= manual <= max_allowed + 1e-9):
                errors.append(
                    _(f"Row #{row.idx}: Manual Qty {manual:.3f} must be within ±{tol_percent:.2f}% of Qty {qty:.3f}. "
                      f"Allowed range: {min_allowed:.3f} to {max_allowed:.3f}.")
                )

        if errors:
            frappe.throw("<br>".join(errors), title=_("Manual Qty Tolerance Exceeded"))
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan Manual Qty Tolerance Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}\n{frappe.get_traceback()}"
        )


def validate_cutting_plan_finish_row_constraints(doc):
    """Validate constraints for cutting_plan_finish rows.
    
    Constraints:
    1. semi_fg_length must be <= 27
    2. Sum of length_size_1 through length_size_n (where n = no_of_length_sizes, max 5) 
       must be <= semi_fg_length (with 3 decimal precision)
    
    This mirrors the JavaScript validation in validate_cutting_plan_finish_row_constraints.
    """
    if not hasattr(doc, 'cutting_plan_finish') or not doc.cutting_plan_finish:
        return
    
    try:
        errors = []
        precision = 3
        
        for row in doc.cutting_plan_finish:
            semi = float(getattr(row, 'semi_fg_length', 0) or 0)
            count = int(getattr(row, 'no_of_length_sizes', 0) or 0)
            
            # Skip validation if semi_fg_length or no_of_length_sizes is not set
            if not semi or not count:
                continue
            
            # Constraint 1: semi_fg_length <= 27
            if semi > 27:
                errors.append(
                    _("Row #{0}: Semi-FG Length must be less than or equal to 27.").format(row.idx)
                )
                continue
            
            # Constraint 2: sum(length_size_1..n) <= semi_fg_length
            total = 0.0
            max_slots = min(count, 5)
            
            for i in range(1, max_slots + 1):
                length_field = f'length_size_{i}'
                val = float(getattr(row, length_field, 0) or 0)
                total += val
            
            # Round to 3 decimal places for comparison
            total_rounded = round(total, precision)
            semi_rounded = round(semi, precision)
            
            # Only error when total is strictly greater than semi (allows equality)
            if total_rounded > semi_rounded:
                errors.append(
                    _("Row #{0}: Sum of Length Sizes must be less than Semi-FG Length.").format(row.idx)
                )
        
        if errors:
            frappe.throw("<br>".join(errors), title=_("Cutting Plan Finish Constraints Validation"))
    
    except Exception as e:
        frappe.log_error(
            title="Cutting Plan Finish Row Constraints Validation Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}\n{frappe.get_traceback()}"
        )


def validate_return_to_stock_length_sizes(doc):
    """Ensure return_to_stock rows use a length_size that already exists for the same FG item.

    Applies only to Finished Cut Plan:
    - Collect length_size (rounded to 3dp) from non-return_to_stock rows per fg_item.
    - For rows marked return_to_stock, length_size must match one of the collected values.
    """
    if getattr(doc, 'cut_plan_type', None) != "Finished Cut Plan":
        return
    if not getattr(doc, 'cutting_plan_finish', None):
        return

    try:
        precision = 3
        allowed_by_fg = {}

        # Collect allowed lengths from non-return rows
        for row in doc.cutting_plan_finish:
            if getattr(row, "return_to_stock", 0):
                continue
            fg_item = getattr(row, "fg_item", None) or getattr(row, "item", None)
            length = getattr(row, "length_size", None)
            if fg_item and length is not None:
                length_val = round(float(length or 0), precision)
                allowed_by_fg.setdefault(fg_item, set()).add(length_val)

        if not allowed_by_fg:
            return

        errors = []
        for row in doc.cutting_plan_finish:
            if not getattr(row, "return_to_stock", 0):
                continue
            fg_item = getattr(row, "fg_item", None) or getattr(row, "item", None)
            length = getattr(row, "length_size", None)
            if not fg_item or length is None:
                continue

            length_val = round(float(length or 0), precision)
            allowed_lengths = allowed_by_fg.get(fg_item, set())

            if allowed_lengths and length_val not in allowed_lengths:
                allowed_display = ", ".join(f"{val:.3f}" for val in sorted(allowed_lengths))
                errors.append(
                    _(
                        "Row #{0}: Return to Stock length {1:.3f} m for FG Item {2} must match existing length size(s): {3}"
                    ).format(row.idx, length_val, fg_item, allowed_display)
                )

        if errors:
            frappe.throw("<br>".join(errors), title=_("Invalid Return to Stock Length Size"))

    except Exception as e:
        frappe.log_error(
            title="Cutting Plan Return-to-Stock Length Validation Error",
            message=f"Doc: {getattr(doc, 'name', '')} Error: {str(e)}\n{frappe.get_traceback()}"
        )


def set_burning_loss(self):

    rm_qty = float(getattr(self, 'total_qty', 0) or 0) + float(getattr(self, 'process_loss_qty', 0) or 0)
    fg_qty = float(getattr(self, 'cut_plan_total_qty', 0) or 0)

    # Initialize scrap quantities
    useable_scrap_qty = 0.0
    cold_billet_scrap_qty = 0.0
    overall_scrap_qty = 0.0
    misroll_scrap_qty = 0.0

    
    for item in self.get('cutting_plan_scrap_transfer', []):  
        target_warehouse = item.get('target_scrap_warehouse', '')
        scrap_qty = float(item.get('scrap_qty', 0) or 0)

        if target_warehouse == "Cutting Scrap - MS":
            overall_scrap_qty += scrap_qty
        elif target_warehouse == "Mis-Roll(Useable) - MS":
            useable_scrap_qty += scrap_qty
        elif target_warehouse == "Misroll(Cold Billet) - MS":
            cold_billet_scrap_qty += scrap_qty
        elif target_warehouse == "Misroll Scrap - MS":
            misroll_scrap_qty += scrap_qty
            
    useable_scrap_qty = round(useable_scrap_qty, 3)
    cold_billet_scrap_qty = round(cold_billet_scrap_qty, 3)
    overall_scrap_qty = round(overall_scrap_qty, 3)
    misroll_scrap_qty = round(misroll_scrap_qty, 3)
    
    actual_rm_qty = round(rm_qty - useable_scrap_qty - cold_billet_scrap_qty,3)
    
    burning_loss = round(actual_rm_qty - fg_qty, 3)
    burning_loss = round(burning_loss - overall_scrap_qty - misroll_scrap_qty, 3)
    
    self.db_set("burning_loss",burning_loss)


def set_burning_loss_percentage(self):
    """Set burning loss percentage using qty from referenced RM Cut Plan (excluding return to stock)."""
    rm_cut_plan = getattr(self, "reference_rm_cut_plan", None)
    burning_loss_qty = float(getattr(self, "burning_loss", 0) or 0)

    if not rm_cut_plan:
        percent = 0.0
    else:
        rm_qty = get_total_qty_for_rm_cut_plan(rm_cut_plan)
        percent = round((burning_loss_qty / rm_qty) * 100, 3) if rm_qty else 0.0

    if hasattr(self, "burning_loss_"):
        self.db_set("burning_loss_", percent)
