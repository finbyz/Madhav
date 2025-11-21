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

