import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.manufacturing.doctype.blanket_order.blanket_order import BlanketOrder as _BlanketOrder

class BlanketOrder(_BlanketOrder):
	def update_ordered_qty(self):
		ref_doctype = "Sales Order" if self.blanket_order_type == "Selling" else "Purchase Order"

		trans = frappe.qb.DocType(ref_doctype)
		trans_item = frappe.qb.DocType(f"{ref_doctype} Item")

		item_ordered_qty = frappe._dict(
			(
				frappe.qb.from_(trans_item)
				.from_(trans)
				.select(trans_item.blanket_order_item, Sum(trans_item.stock_qty).as_("qty"))
				.where(
					(trans.name == trans_item.parent)
					& (trans_item.blanket_order == self.name)
					& (trans.docstatus == 1)
					& (trans.status.notin(["Stopped", "Closed"]))
				)
				.groupby(trans_item.blanket_order_item)
			).run()
		)

		for d in self.items:
			d.db_set("ordered_qty", item_ordered_qty.get(d.name, 0))

@frappe.whitelist()
def make_order(source_name):
	doctype = frappe.flags.args.doctype

	def update_doc(source_doc, target_doc, source_parent):
		if doctype == "Quotation":
			target_doc.quotation_to = "Customer"
			target_doc.party_name = source_doc.customer

	def update_item(source, target, source_parent):
		target_qty = source.get("qty") - source.get("ordered_qty")
		target.qty = target_qty if not flt(target_qty) < 0 else 0
		target.rate = source.get("rate")
		item = get_item_defaults(target.item_code, source_parent.company)
		if item:
			target.item_name = item.get("item_name")
			target.description = item.get("description")
			target.uom = item.get("stock_uom")
			target.against_blanket_order = 1
			target.blanket_order = source_name

	target_doc = get_mapped_doc(
		"Blanket Order",
		source_name,
		{
			"Blanket Order": {"doctype": doctype, "postprocess": update_doc},
			"Blanket Order Item": {
				"doctype": doctype + " Item",
				"field_map": {"rate": "blanket_order_rate", "parent": "blanket_order","name": "blanket_order_item"},
				"postprocess": update_item,
				"condition": lambda item: not (flt(item.qty)) or (flt(item.qty) - flt(item.ordered_qty)) > 0,
			},
		},
	)

	if target_doc.doctype == "Purchase Order":
		target_doc.set_missing_values()

	return target_doc

def validate_against_blanket_order(order_doc):
	
	if order_doc.doctype in ("Sales Order", "Purchase Order"):
		order_data = {}

		for item in order_doc.get("items"):
			if item.against_blanket_order and item.blanket_order:
				if item.blanket_order in order_data:
					if item.blanket_order_item in order_data[item.blanket_order]:
						order_data[item.blanket_order][item.blanket_order_item] += item.qty
					else:
						order_data[item.blanket_order][item.blanket_order_item] = item.qty
				else:
					order_data[item.blanket_order] = {item.blanket_order_item: item.qty}

		if order_data:
			allowance = flt(
				frappe.db.get_single_value(
					"Selling Settings" if order_doc.doctype == "Sales Order" else "Buying Settings",
					"blanket_order_allowance",
				)
			)
			for bo_name, item_data in order_data.items():
				# frappe.throw(str(bo_name) + "hello" + str(item_data))
				bo_doc = frappe.get_doc("Blanket Order", bo_name)
				for item in bo_doc.get("items"):
					# frappe.throw(str(item_data))
					if item.name in item_data:
						remaining_qty = item.qty - item.ordered_qty
						allowed_qty = remaining_qty + (remaining_qty * (allowance / 100))
						if item.qty and allowed_qty < item_data[item.name]:
							frappe.throw(
								_(
									"Item {0} cannot be ordered more than {1} against Blanket Order {2}."
								).format(item.item_code, allowed_qty, bo_name)
							)