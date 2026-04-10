import frappe
from frappe import _
from frappe.utils import flt
from erpnext.controllers.status_updater import OverAllowanceError

def validate_limit_on_save(self, method):
	"""
	Ensure 'Limit Crossed' validation triggers on Save for Purchase Orders.
	1) Try the standard StatusUpdater.validate_qty() if available.
	2) Additionally enforce against Material Request balance (draft+submitted POs) to catch on save.
	"""
	if hasattr(self, "validate_qty"):
		try:
			self.validate_qty()
		except Exception:
			# If standard path raises, rethrow; otherwise continue to our explicit check.
			raise

	# Explicit MR-based check to ensure early error on Save
	mr_qty_allowance = flt(frappe.db.get_single_value("Stock Settings", "mr_qty_allowance")) or 0.0

	for d in self.get("items") or []:
		mr_item = d.get("material_request_item")
		if not mr_item:
			continue

		# Fetch MR stock_qty reference
		mr_row = frappe.db.get_value(
			"Material Request Item",
			mr_item,
			["parent", "item_code", "stock_qty"],
			as_dict=True,
		)
		if not mr_row:
			continue

		mr_stock_qty = flt(mr_row.get("stock_qty") or 0.0, d.precision("stock_qty"))
		if mr_stock_qty <= 0:
			continue

		# Sum already ordered qty across other POs (draft + submitted), exclude this row
		already_ordered = frappe.db.sql(
			"""
			select coalesce(sum(poi.stock_qty), 0)
			from `tabPurchase Order Item` poi
			join `tabPurchase Order` po on po.name = poi.parent
			where poi.material_request_item = %s
			  and po.docstatus < 2
			  and not (poi.parent = %s)
			""",
			(mr_item, self.name or ""),
		)[0][0]

		# Proposed total including current row's qty
		proposed_total = flt(already_ordered) + flt(d.get("stock_qty") or 0.0)

		# Allowed with tolerance
		max_allowed = mr_stock_qty * (100.0 + mr_qty_allowance) / 100.0

		if proposed_total > max_allowed + 1e-9:
			reduce_by = proposed_total - max_allowed
			msg = _(
				"This document is over limit by {0} for item {1}. Are you making another {2} against the same {3}?"
			).format(
				frappe.bold(f"{flt(reduce_by, d.precision('stock_qty'))} Qty"),
				frappe.bold(d.get("item_code")),
				frappe.bold(_("Purchase Order")),
				frappe.bold(_("Material Request")),
			)
			action_msg = _(
				'To allow over ordering, update "Over Order Allowance" in Stock Settings or the Item.'
			)
			frappe.throw(msg + "<br><br>" + action_msg, OverAllowanceError, title=_("Limit Crossed"))

def round_off_stock_qty(doc, method=None):
	"""Round stock_qty for rows where UOM is Kg and stock UOM is Nos."""

	for row in doc.items or []:
		if (row.get("uom") or "").lower() == "kg" and (row.get("stock_uom") or "").lower() == "nos":
			if row.get("stock_qty") is not None:
				row.db_set("stock_qty",round(flt(row.stock_qty)))
    
    
from frappe.model.mapper import get_mapped_doc
import frappe
import json


@frappe.whitelist()
def make_purchase_order_from_blanket(source_name, target_doc=None, args=None):
    def set_missing_values(source, target):

        target.supplier = source.supplier
        target.company = source.company

        # Set flag if the field exists in Purchase Order
        if hasattr(target, "against_blanket_order"):
            target.against_blanket_order = 1


    def update_item(source, target, source_parent):
        # Calculate remaining quantity to order
        # remaining_qty = Total qty in blanket order - Already ordered qty
        remaining_qty = source.qty - (source.ordered_qty or 0)

        # Set the quantity for this Purchase Order
        target.qty = remaining_qty
        
        # Set the rate from blanket order
        target.rate = source.rate
        
        # Store the blanket order rate for reference
        if hasattr(target, "blanket_order_rate"):
            target.blanket_order_rate = source.rate
        
        # Link back to the source Blanket Order
        target.blanket_order = source_parent.name
        target.blanket_order_item = source.name

        # Set flag if the field exists
        if hasattr(target, "against_blanket_order"):
            target.against_blanket_order = 1


    # Use get_mapped_doc to handle the mapping
    doc = get_mapped_doc(
        "Blanket Order",                          
        source_name,                               
        {
            # Map parent Blanket Order to Purchase Order
            "Blanket Order": {
                "doctype": "Purchase Order",
                
                # Only map from docstatus = 1 (Submitted) blanket orders
                "validation": {
                    "docstatus": ["=", 1]          
                },
                
                # Map these fields from Blanket Order to Purchase Order
                "field_map": {
                    "name": "name", 
                    "supplier": "supplier", 
                    "company": "company"
                },
            },
            
            # Map child items from Blanket Order Item to Purchase Order Item
            "Blanket Order Item": {
                "doctype": "Purchase Order Item",
                
                # Run update_item function after mapping to calculate remaining qty
                "postprocess": update_item,
                
                # IMPORTANT: Only map item_code, item_name, and rate
                # Do NOT map qty or ordered_qty - postprocess calculates remaining_qty
                "field_map": {
                    "item_code": "item_code", 
                    "item_name": "item_name", 
                    "rate": "rate"
                },
                
                # Filter: Only include items with remaining quantity to order
                # This ensures only items where ordered_qty < qty are included
                "filter": lambda item: (
                    item.qty and 
                    (item.ordered_qty is None or item.ordered_qty < item.qty)
                ),    
            }
        },
        target_doc,
        set_missing_values
    )
    
    # Log the result for debugging
    frappe.logger().info(
        f"Created Purchase Order with {len(doc.items)} items from Blanket Order {source_name}"
    )
    
    return doc


@frappe.whitelist()
def get_blanket_order_items(doctype, txt, searchfield, start, page_len, filters):
    data = frappe.db.sql("""
        SELECT
            bo.name as name,
            bo.name as parent,    
            bo.company as company,
            bo.supplier as supplier,
            boi.name as child_name,
            boi.item_code,
            boi.item_name,
            boi.qty,
            boi.ordered_qty,
            boi.rate
        FROM `tabBlanket Order` bo
        JOIN `tabBlanket Order Item` boi
            ON bo.name = boi.parent
        WHERE
            bo.docstatus = 1
            AND IFNULL(boi.qty, 0) > IFNULL(boi.ordered_qty, 0)
            AND (%(supplier)s IS NULL OR bo.supplier = %(supplier)s)
            AND (%(company)s IS NULL OR bo.company = %(company)s)
            AND bo.name LIKE %(txt)s
        ORDER BY bo.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "supplier": filters.get("supplier"),
        "company": filters.get("company"),
        "start": int(start),
        "page_len": int(page_len)
    }, as_dict=1)   # 🔥 THIS IS THE MAIN FIX

    return data