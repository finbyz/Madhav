import frappe
from frappe.utils import flt


def round_off_stock_qty(doc, method=None):
	"""Round stock_qty for rows where UOM is Kg and stock UOM is Nos."""

	for row in doc.items or []:
		if (row.get("uom") or "").lower() == "kg" and (row.get("stock_uom") or "").lower() == "nos":
			if row.get("stock_qty") is not None:
				row.db_set("stock_qty",round(flt(row.stock_qty)))

