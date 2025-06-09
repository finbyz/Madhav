import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.utils import flt

def get_sl_entries(self, d, args):
	sl_dict = frappe._dict(
		{
			"item_code": d.get("item_code", None),
			"warehouse": d.get("warehouse", None),
			"serial_and_batch_bundle": d.get("serial_and_batch_bundle"),
			"posting_date": self.posting_date,
			"posting_time": self.posting_time,
			"fiscal_year": get_fiscal_year(self.posting_date, company=self.company)[0],
			"voucher_type": self.doctype,
			"voucher_no": self.name,
			"voucher_detail_no": d.name,
			"actual_qty": (self.docstatus == 1 and 1 or -1) * flt(d.get("stock_qty")),
			"stock_uom": frappe.get_cached_value(
				"Item", args.get("item_code") or d.get("item_code"), "stock_uom"
			),
			"incoming_rate": 0,
			"company": self.company,
			"project": d.get("project") or self.get("project"),
			"is_cancelled": 1 if self.docstatus == 2 else 0,
		}
	)

	sl_dict.update(args)

	# Explicitly ensure pieces_qty is present
	if "pieces_qty" in args:
		sl_dict["pieces_qty"] = args["pieces_qty"]

	self.update_inventory_dimensions(d, sl_dict)

	if self.docstatus == 2:
		for field in ["serial_no", "batch_no"]:
			if d.get(field):
				sl_dict[field] = d.get(field)

	return sl_dict
