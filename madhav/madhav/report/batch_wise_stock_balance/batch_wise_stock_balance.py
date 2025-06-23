# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, get_table_name, getdate
from frappe.utils.deprecations import deprecated
from pypika import functions as fn

from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter

def execute(filters=None):
	if not filters:
		filters = {}

	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))

	float_precision = cint(frappe.db.get_default("float_precision")) or 3

	columns = get_columns(filters)
	item_map = get_item_details(filters)
	iwb_map = get_item_warehouse_batch_map(filters, float_precision)
	filter_company = filters.get("company")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	batch_group_filter = filters.get("batch_group")
 
	# Get batch group batches if batch_group filter is applied
	batch_group_batches = get_batch_group_batches(filters) if filters.get("batch_group") else []
	data = []

	for item in sorted(iwb_map):
		if filters.get("item") and filters["item"] != item:
			continue

		for wh in sorted(iwb_map[item]):
			for batch in sorted(iwb_map[item][wh]):
				# If batch_group is selected, only show batches from that group
				if filters.get("batch_group") and batch not in batch_group_batches:
					continue
 
				qty_dict = iwb_map[item][wh][batch]

				if any([qty_dict.bal_qty]):
					data.append([
						item,
						item_map[item]["item_name"],
						item_map[item]["description"],
						wh,
						batch,
						batch_group_filter or "",
						flt(qty_dict.bal_qty, float_precision),
						item_map[item]["stock_uom"],
						qty_dict.piece,
						qty_dict.weight_received,
						qty_dict.average_length,
						qty_dict.section_weight,
						f"""
							<button style='margin-left:5px;border:none;color:#fff; background-color:#1581e1; padding:3px 5px; border-radius:5px;'
								target="_blank" item_code='{item}' filter_company='{filter_company}'
								from_date='{from_date}' to_date='{to_date}' batch_no='{batch}'
								onClick="view_stock_ledger_report(
									this.getAttribute('item_code'),
									this.getAttribute('filter_company'),
									this.getAttribute('from_date'),
									this.getAttribute('to_date'),
									this.getAttribute('batch_no'))">
								View Stock Ledger Madhav
							</button>
						"""
					])
	
	return columns, data

def get_batch_group_batches(filters):
	"""Get list of batches from the selected Batch Group"""
	batch_group = filters.get("batch_group")
	
	if not batch_group:
		return []
	
	try:
		batch_list = frappe.get_all(
			"Batch Group Detail",
			filters={"parent": batch_group},
			fields=["batch"]
		)
		return [item.batch for item in batch_list if item.batch]
	except Exception as e:
		frappe.log_error(f"Error fetching batch group batches: {str(e)}")
		return []

def get_columns(filters):
	"""return columns based on filters"""

	columns = [
		_("Item") + ":Link/Item:100",
		_("Item Name") + "::150",
		_("Description") + "::150",
		_("Warehouse") + ":Link/Warehouse:100",
		_("Batch") + ":Link/Batch:100",
		_("Batch Group") + ":Link/Batch Group:150",
		# _("Opening Qty") + ":Float:90",
		# _("In Qty(per pieces)") + ":Float:150",
		# _("Out Qty(per pieces)") + ":Float:150",
		_("Balance Qty(per pieces)") + ":Float:150",
		_("UOM") + "::90",
		_("Length/Pieces") + ":Float:150",
		_("Weight Received") + ":Float:150",
		_("Length Size") + ":Float:150",
		# _("Length Weight In Kg") + ":Float:180",
		_("Section Weight") + ":Float:150",	
		_("Stock Legder Madhav") + ":button/Stock Ledger:120",

	]
	return columns


def get_stock_ledger_entries(filters):
	entries = get_stock_ledger_entries_for_batch_no(filters)

	entries += get_stock_ledger_entries_for_batch_bundle(filters)
	return entries


@deprecated
def get_stock_ledger_entries_for_batch_no(filters):
	if not filters.get("from_date"):
		frappe.throw(_("'From Date' is required"))
	if not filters.get("to_date"):
		frappe.throw(_("'To Date' is required"))

	posting_datetime = get_datetime(add_to_date(filters["to_date"], days=1))

	psle = frappe.qb.DocType("Piece Stock Ledger Entry")
	batch= frappe.qb.DocType("Batch")
	query = (
		frappe.qb.from_(psle)
		.inner_join(batch)
		.on(batch.name == psle.batch_no)
		.select(
			psle.item_code,
			psle.warehouse,
			psle.batch_no,
			psle.posting_date,
			fn.Sum(psle.actual_qty).as_("actual_qty"),
			batch.pieces
		)
		.where(
			(psle.docstatus < 2)
			& (psle.is_cancelled == 0)
			& (psle.item_code == batch.item )
			& (psle.posting_time < posting_datetime)
		)
		.groupby(psle.voucher_no, psle.batch_no, psle.item_code, psle.warehouse)
		.orderby(psle.item_code, psle.warehouse)
	)
	# Apply batch group filter at query level for better performance
	if filters.get("batch_group"):
		batch_group_batches = get_batch_group_batches(filters)
		if batch_group_batches:
			query = query.where(psle.batch_no.isin(batch_group_batches))
		else:
			# If batch group is selected but no batches found, return empty result
			return []

	query = apply_warehouse_filter(query, psle, filters)
	if filters.warehouse_type and not filters.warehouse:
		warehouses = frappe.get_all(
			"Warehouse",
			filters={"warehouse_type": filters.warehouse_type, "is_group": 0},
			pluck="name",
		)

		if warehouses:
			query = query.where(psle.warehouse.isin(warehouses))

	for field in ["item_code", "batch_no", "company"]:
		if filters.get(field):
			query = query.where(psle[field] == filters.get(field))
	return query.run(as_dict=True) or []


def get_stock_ledger_entries_for_batch_bundle(filters):
	psle = frappe.qb.DocType("Piece Stock Ledger Entry")
	batch_package = frappe.qb.DocType("Serial and Batch Entry")
	batch = frappe.qb.DocType("Batch")

	query = (
		frappe.qb.from_(psle)
		.inner_join(batch_package)
		.on(batch_package.parent == psle.serial_and_batch_bundle)
		.inner_join(batch)
		.on(batch.name == batch_package.batch_no)
		.select(
			psle.item_code,
			psle.warehouse,
			batch_package.batch_no,
			psle.posting_date,
			fn.Sum(psle.actual_qty).as_("actual_qty"),
			batch.pieces
		)
		.where(
			(psle.docstatus < 2)
			& (psle.is_cancelled == 0)
			& (psle.posting_date <= filters["to_date"])
		)
		.groupby(batch_package.batch_no, batch_package.warehouse)
		.orderby(psle.item_code, psle.warehouse)
	)

	# Apply batch group filter at query level for better performance
	if filters.get("batch_group"):
		batch_group_batches = get_batch_group_batches(filters)
		if batch_group_batches:
			query = query.where(batch_package.batch_no.isin(batch_group_batches))
		else:
			# If batch group is selected but no batches found, return empty result
			return []

	query = apply_warehouse_filter(query, psle, filters)
	if filters.warehouse_type and not filters.warehouse:
		warehouses = frappe.get_all(
			"Warehouse",
			filters={"warehouse_type": filters.warehouse_type, "is_group": 0},
			pluck="name",
		)

		if warehouses:
			query = query.where(psle.warehouse.isin(warehouses))

	for field in ["item_code", "batch_no", "company"]:
		if filters.get(field):
			if field == "batch_no":
				query = query.where(batch_package[field] == filters.get(field))
			else:
				query = query.where(psle[field] == filters.get(field))
	return query.run(as_dict=True) or []


def get_item_warehouse_batch_map(filters, float_precision):
	psle = get_stock_ledger_entries(filters)
	iwb_map = {}
	from_date = getdate(filters["from_date"])
	to_date = getdate(filters["to_date"])

	# Define fields to fetch from Batch
	batch_fields = [
		"pieces", "weight_received", "average_length", "section_weight"
	]
	existing_fields = [f for f in batch_fields if frappe.db.has_column("Batch", f)]

	for d in psle:
		batch_doc = {}
		if d.batch_no and existing_fields:
			batch_doc = frappe.get_value("Batch", d.batch_no, existing_fields, as_dict=True) or {}

		# Init nested structure
		iwb_map.setdefault(d.item_code, {}).setdefault(d.warehouse, {}).setdefault(
			d.batch_no, frappe._dict({
				"bal_qty": 0.0,
				"piece": batch_doc.get("pieces", 0),
				"weight_received": batch_doc.get("weight_received", 0),
				"section_weight": batch_doc.get("section_weight", 0),
				"average_length": batch_doc.get("average_length", 0),
			})
		)

		qty_dict = iwb_map[d.item_code][d.warehouse][d.batch_no]
		actual_qty = flt(d.actual_qty, float_precision)
		
		# Opening Qty (before from_date)
		# if d.posting_date < from_date:
		# 	qty_dict.opening_qty += actual_qty

		# In/Out Qty (between from_date and to_date)
		# if from_date <= d.posting_date <= to_date:
		# 	if actual_qty > 0:
		# 		qty_dict.in_qty += actual_qty
		# 	else:
		# 		qty_dict.out_qty += abs(actual_qty)

		# Balance Qty always
		qty_dict.bal_qty += actual_qty

	return iwb_map


def get_item_details(filters):
	"""Get item details like name, description, UOM"""
	item_map = {}
	
	query = frappe.qb.from_("Item").select("name", "item_name", "description", "stock_uom")
	
	# Apply item filter if specified
	if filters.get("item_code"):
		query = query.where(frappe.qb.DocType("Item").name == filters.get("item_code"))
	
	for item in query.run(as_dict=True):
		item_map[item.name] = item

	return item_map
