import frappe
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc
from erpnext.stock.get_item_details import get_bin_details, get_default_bom, get_price_list_rate


def round_off_stock_qty(doc, method=None):
	"""Round stock_qty for rows where UOM is Kg and stock UOM is Nos."""

	for row in doc.items or []:
		if (row.get("uom") or "").lower() == "kg" and (row.get("stock_uom") or "").lower() == "nos":
			if row.get("stock_qty") is not None:
				row.db_set("stock_qty",round(flt(row.stock_qty)))


@frappe.whitelist()
def make_material_request(source_name, target_doc=None, selected_items=None):
	requested_item_qty = get_requested_item_qty(source_name)

	# Parse selected child item names if passed from child selection dialog
	selected_item_names = []
	if selected_items:
		items = frappe.parse_json(selected_items)
		selected_item_names = [d.get("name") or d for d in items] if isinstance(items, list) else []

	def postprocess(source, target):
		if source.tc_name and frappe.db.get_value("Terms and Conditions", source.tc_name, "buying") != 1:
			target.tc_name = None
			target.terms = None

	def get_remaining_qty(so_item):
		return flt(
			flt(so_item.qty)
			- flt(requested_item_qty.get(so_item.name, {}).get("qty"))
			- max(
				flt(so_item.get("delivered_qty"))
				- flt(requested_item_qty.get(so_item.name, {}).get("received_qty")),
				0,
			)
		)

	def get_remaining_pieces(so_item, remaining_qty):
		already_requested_pieces = flt(requested_item_qty.get(so_item.name, {}).get("pieces"))

		if already_requested_pieces:
			# subtract already-requested pieces directly
			return flt(flt(so_item.pieces) - already_requested_pieces)
		elif flt(so_item.qty):
			# fallback: proportional (first-time request, nothing requested yet)
			return flt(flt(so_item.pieces) * (flt(remaining_qty) / flt(so_item.qty)))
		return 0

	def update_item(source, target, source_parent):
		target.project = source_parent.project

		remaining_qty = get_remaining_qty(source)
		target.qty = remaining_qty
		target.stock_qty = flt(target.qty) * flt(target.conversion_factor)
		target.pieces = get_remaining_pieces(source, remaining_qty)

		target.actual_qty = get_bin_details(
			target.item_code, target.warehouse, source_parent.company, True
		).get("actual_qty", 0)

		args = target.as_dict().copy()
		args.update(
			{
				"company": source_parent.get("company"),
				"price_list": frappe.db.get_single_value("Buying Settings", "buying_price_list"),
				"currency": source_parent.get("currency"),
				"conversion_rate": source_parent.get("conversion_rate"),
			}
		)

		target.rate = flt(
			get_price_list_rate(args=args, item_doc=frappe.get_cached_doc("Item", target.item_code)).get(
				"price_list_rate"
			)
		)
		target.amount = target.qty * target.rate

	def item_condition(item):
		# If specific child rows were selected, only include those
		if selected_item_names and item.name not in selected_item_names:
			return False

		return (
			not frappe.db.exists("Product Bundle", {"name": item.item_code, "disabled": 0})
			and get_remaining_qty(item) > 0
		)

	doc = get_mapped_doc(
		"Sales Order",
		source_name,
		{
			"Sales Order": {"doctype": "Material Request", "validation": {"docstatus": ["=", 1]}},
			"Packed Item": {
				"doctype": "Material Request Item",
				"field_map": {"parent": "sales_order", "uom": "stock_uom"},
				"postprocess": update_item,
			},
			"Sales Order Item": {
				"doctype": "Material Request Item",
				"field_map": {
					"name": "sales_order_item",
					"parent": "sales_order",
					"delivery_date": "schedule_date",
					"bom_no": "bom_no",
					"length_size": "length_size",
					"pieces": "pieces",
					"assorted_length": "assorted_length",
				},
				"condition": item_condition,
				"postprocess": update_item,
			},
		},
		target_doc,
		postprocess,
	)

	return doc

def get_requested_item_qty(source_name):
	result = frappe.db.sql(
		"""
		SELECT
			mri.sales_order_item,
			SUM(mri.qty)          AS qty,
			SUM(mri.pieces)       AS pieces,
			SUM(mri.received_qty) AS received_qty
		FROM `tabMaterial Request Item` mri
		JOIN `tabMaterial Request` mr ON mr.name = mri.parent
		WHERE
			mri.sales_order = %s
			AND mr.docstatus = 1
			AND mr.material_request_type = 'Purchase'
		GROUP BY mri.sales_order_item
		""",
		source_name,
		as_dict=1,
	)

	return frappe._dict({row.sales_order_item: row for row in result})