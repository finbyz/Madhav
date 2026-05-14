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
    
def validate(self,method):
    for row in self.items:
        if row.blanket_order:
            row.against_blanket_order = 1
    if self.against_blanket_order and self.blanket_order:
        doc = frappe.get_doc("Blanket Order",self.blanket_order)
        self.blanket_order_qty = doc.items[0].qty - doc.items[0].ordered_qty
        for row in self.items:
            row.against_blanket_order = self.against_blanket_order
            row.blanket_order = self.blanket_order
            row.blanket_order_item = doc.items[0].name
            row.blanket_order_rate = doc.items[0].rate
            
def update_blanket_order_reference_in_item(self):
    if self.against_blanket_order and self.blanket_order:
        doc = frappe.get_doc("Blanket Order",self.blanket_order)
        for row in self.items:
            row.against_blanket_order = self.against_blanket_order
            row.blanket_order = self.blanket_order
            row.blanket_order_item = doc.items[0].name
            
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt

import json

@frappe.whitelist()
def make_purchase_order_from_blanket(source_name, target_doc=None, args=None):
    if args is None:
        args = {}
    elif isinstance(args, str):
        args = json.loads(args)

    def set_missing_values(source, target):
        target.supplier = source.supplier
        target.company = source.company
        target.against_blanket_order = 1

    def update_item(source, target, source_parent):
        remaining_qty = flt(source.qty) - flt(source.ordered_qty)
        if remaining_qty <= 0:
            return

        target.qty = remaining_qty
        target.rate = source.rate
        target.blanket_order_rate = source.rate
        target.blanket_order = source_parent.name
        target.blanket_order_item = source.name
        target.against_blanket_order = 1

    def select_item(item):
        filtered_items = args.get("filtered_children", [])
        child_filter = item.name in filtered_items if filtered_items else True
        return flt(item.qty) > flt(item.ordered_qty) and child_filter

    return get_mapped_doc(
        "Blanket Order",
        source_name,
        {
            "Blanket Order": {
                "doctype": "Purchase Order",
                "validation": {"docstatus": ["=", 1]},
                "field_map": {
                    "supplier": "supplier",
                    "company": "company"
                },
            },
            "Blanket Order Item": {
                "doctype": "Purchase Order Item",
                "field_map": {
                    "item_code": "item_code",
                    "item_name": "item_name",
                    "uom": "uom",
                    "rate": "rate",
                    "blanket_order_rate":"rate"
                },
                "postprocess": update_item,
                "condition": select_item,
            }
        },
        target_doc,
        set_missing_values
    )



@frappe.whitelist()
def get_blanket_order_items(doctype, txt, searchfield, start, page_len, filters):
    filters = frappe._dict(filters or {})

    return frappe.db.sql("""
        SELECT
            bo.name as name,
            bo.company as company,
            bo.supplier as supplier
        FROM `tabBlanket Order` bo
        WHERE
            bo.docstatus = 1
            AND bo.blanket_order_type = 'Purchasing'
            AND (%(supplier)s IS NULL OR bo.supplier = %(supplier)s)
            AND (%(company)s IS NULL OR bo.company = %(company)s)
            AND bo.name LIKE %(txt)s
            AND EXISTS (
                SELECT 1
                FROM `tabBlanket Order Item` boi
                WHERE boi.parent = bo.name
                  AND IFNULL(boi.qty, 0) > IFNULL(boi.ordered_qty, 0)
            )
        ORDER BY bo.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "supplier": filters.get("supplier"),
        "company": filters.get("company"),
        "start": int(start),
        "page_len": int(page_len)
    }, as_dict=1)
