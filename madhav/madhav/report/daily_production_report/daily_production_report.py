# Copyright (c) 2025, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, today, flt

# Map Target Scrap Warehouses to the respective report buckets.
# Update the warehouse names below as needed in your environment.
SCRAP_WAREHOUSE_BUCKETS = frappe._dict({
	# "Warehouse Name": "bucket_key"
	"Misroll Scrap - MS": "rm_scrap",
	"Cutting Scrap - MS": "rm_scrap",
	"Misroll(Cold Billet) - MS": "miss_roll",
	"Mis-Roll(Useable) - MS": "reusable_miss_roll",
})


def execute(filters=None):
	filters = filters or {}

	from_date = getdate(filters.get("from_date") or today())
	to_date = getdate(filters.get("to_date") or today())

	columns = get_columns()
	data = []

	plan_filters = {"docstatus": 1}
	# Always restrict to Raw Material Cut Plan as requested
	plan_filters["cut_plan_type"] = "Finished Cut Plan"
	if filters.get("company"):
		plan_filters["company"] = filters.get("company")
	# if filters.get("workflow_state"):
	# 	plan_filters["workflow_state"] = filters.get("workflow_state")

	plan_filters["date"] = ("between", [from_date, to_date])

	plans = frappe.get_all(
		"Cutting Plan",
		filters=plan_filters,
		fields=[
			"name",
			"date",
			"company",
			"cut_plan_type",
			"workflow_state",
			"stock_entry_reference",
			"ng",
			"insp_yard_mt",
			"kvah",
		],
		order_by="date asc, creation asc",
	)

	# Optional row-level filters
	filter_item = filters.get("item")
	filter_warehouse = filters.get("warehouse")
	filter_return_to_stock = filters.get("return_to_stock")
	filter_work_order = filters.get("work_order")

	# Aggregate by date
	by_date = {}

	for plan in plans:
		finish_rows = frappe.get_all(
			"Cutting Plan Finish",
			filters={
				"parent": plan.name,
				"parenttype": "Cutting Plan",
				"parentfield": "cutting_plan_finish",
			},
			fields=[
				"name",
				"item",
				"fg_item",
				"qty",
				"warehouse",
				"lot_no",
				"work_order_reference",
				"return_to_stock",
			],
			order_by="idx asc",
		)

		# Fetch RM detail to compute RM Qty per plan (in tonnes)
		rm_rows = frappe.get_all(
			"Cut Plan Detail",
			filters={
				"parent": plan.name,
				"parenttype": "Cutting Plan",
				"parentfield": "cut_plan_detail",
			},
			fields=["qty","is_finished_item", "item_code", "supplier_name"],
		)

		# Fetch scrap rows
		scrap_rows = frappe.get_all(
			"Cutting Plan Scrap Transfer",
			filters={
				"parent": plan.name,
				"parenttype": "Cutting Plan",
				"parentfield": "cutting_plan_scrap_transfer",
			},
			fields=["scrap_qty", "item_code", "target_scrap_warehouse"],
		)

		date_key = plan.get("date")
		agg = by_date.setdefault(
			date_key,
			{
				"date": date_key,
				"cutting_plans": set(),
				"rm_qty_mt": 0.0,
				"size": "",
				"a_col": None,
				"b_col": None,
				"fg_qty_mt": 0.0,
				"ng": 0,
				"ng_avg": 0.0,
				"_ng_length_total": 0.0,
				"_ng_pieces_total": 0,
				"rm_scrap": 0.0,
				"miss_roll_mt": 0.0,
				"end_cut_mt": 0.0,
				"insp_yard_mt": 0.0,
				"kvah": 0.0,
				"kvah_cum": 0.0,
				"rm_scrap_pct": 0.0,
				"miss_roll_pct": 0.0,
				"end_cut_pct": 0.0,
				"insp_yard_pct": 0.0,
				"total_scrap_mt": 0.0,
				"total_scrap_pct": 0.0,
				"reusable_miss_roll_mt": 0.0,
				"productivity": 0.0,
			},
		)

		# Track Cutting Plan name for grouped display
		agg["cutting_plans"].add(plan.get("name"))

		# RM Qty from cut_plan_detail
		for rm in rm_rows:
			if rm.is_finished_item != 1:
				qty = float(rm.get("qty") or 0)
				agg["rm_qty_mt"] += round(qty, 3)
				
				# Column A: Steel Authority Of India Ltd, Column B: All other suppliers
				supplier = rm.get("supplier_name") or ""
				if supplier == "Steel Authority Of India Ltd":
					if agg["a_col"] is None:
						agg["a_col"] = 0.0
					agg["a_col"] += qty
				else:
					if agg["b_col"] is None:
						agg["b_col"] = 0.0
					agg["b_col"] += round(qty,3)

		# SIZE from RM item names in cut_plan_detail
		item_codes = [r.get("item_code") for r in rm_rows if r.get("item_code") and r.is_finished_item==1]
		if item_codes:
			item_names = {}
			for it in frappe.get_all("Item", filters={"name": ("in", item_codes)}, fields=["name", "item_name"]):
				item_names[it.name] = it.item_name or it.name
			size_list = [item_names.get(c, c) for c in item_codes]
			if size_list:
				agg["size"] = ", ".join(sorted(set(size_list)))

		# FG from finish rows (exclude return_to_stock from FG), NG from Cutting Plan header
		size_tokens = set()

		for row in finish_rows:
			# Apply optional row-level filters
			if filter_item and (row.fg_item or row.item) != filter_item:
				continue
			if filter_warehouse and row.warehouse != filter_warehouse:
				continue
			if filter_return_to_stock is not None and int(filter_return_to_stock) != int(bool(row.return_to_stock)):
				continue
			if filter_work_order and row.work_order_reference != filter_work_order:
				continue

			display_item = row.get("fg_item") or row.get("item")

			# accumulate FG (exclude returns)
			qty_val = float(row.get("qty") or 0)
			if not int(bool(row.get("return_to_stock"))):
				agg["fg_qty_mt"] += qty_val
			
			# NG will be taken from header; pieces/length not used
			# collect size tokens from item or other attributes if available
			if display_item:
				size_tokens.add(str(display_item))

		# Add header-level NG, INSP+YARD, and KVAH
		agg["ng"] += int(plan.get("ng") or 0)
		agg["insp_yard_mt"] += float(plan.get("insp_yard_mt") or 0)
		agg["kvah"] += float(plan.get("kvah") or 0)

		# Scrap totals split by target warehouse bucket
		for sc in scrap_rows:
			qty = float(sc.get("scrap_qty") or 0)
			target_wh = sc.get("target_scrap_warehouse")
			bucket = get_scrap_bucket(target_wh)
			if bucket == "miss_roll":
				agg["miss_roll_mt"] += qty
			elif bucket == "reusable_miss_roll":
				agg["reusable_miss_roll_mt"] += qty
			else:
				agg["rm_scrap"] += qty

		# finalize derived fields for this date after processing the plan
		# Keep existing size if set from RM items; otherwise fallback to tokens from finish items
		# if not agg.get("size") and size_tokens:
		# 	agg["size"] = ", ".join(sorted(size_tokens))

	# compute percentages and totals
	for date_key in sorted(by_date.keys()):
		agg = by_date[date_key]
		# Solidify cutting plan names as comma-separated list of links
		if isinstance(agg.get("cutting_plans"), set):
			plan_names = sorted(agg["cutting_plans"]) if agg["cutting_plans"] else []
			links = [f'<a href="/app/cutting-plan/{name}" target="_blank">{name}</a>' for name in plan_names]
			agg["cutting_plans"] = ", ".join(links)
		total_scrap = (
			agg["rm_scrap"]
			+ agg["miss_roll_mt"]
			+ agg["end_cut_mt"]
			+ agg["insp_yard_mt"]
		)
		agg["total_scrap_mt"] = round(total_scrap, 3)
		rm_qty = float(agg["rm_qty_mt"] or 0)
		def pct(val, base):
			return round((float(val) / base * 100.0), 2) if base else 0.0
		agg["rm_scrap_pct"] = pct(agg["rm_scrap"], rm_qty)
		agg["miss_roll_pct"] = pct(agg["miss_roll_mt"], rm_qty)
		agg["end_cut_pct"] = pct(agg["end_cut_mt"], rm_qty)
		agg["insp_yard_pct"] = pct(agg["insp_yard_mt"], rm_qty)
		agg["total_scrap_pct"] = pct(agg["total_scrap_mt"], rm_qty)

		# Round supplier buckets to 3 decimals so UI doesn't show long floats
		if agg.get("a_col") is not None:
			agg["a_col"] = flt(agg.get("a_col") or 0, 3)
		if agg.get("b_col") is not None:
			agg["b_col"] = flt(agg.get("b_col") or 0, 3)

		# NG AVG = NG / FG Qty (Mt)
		fg_qty = float(agg.get("fg_qty_mt") or 0)
		ng_val = float(agg.get("ng") or 0)
		agg["ng_avg"] = round((ng_val / fg_qty), 3) if fg_qty else 0.0

		# KVAH CUM = KVAH / FG Qty (Mt)
		fg_qty = float(agg.get("fg_qty_mt") or 0)
		kvah_val = float(agg.get("kvah") or 0)
		agg["kvah_cum"] = round((kvah_val / fg_qty), 3) if fg_qty else 0.0

		# Productivity placeholder: FG Qty / shift hours? Leave as 0 until defined
		agg["productivity"] = float(agg.get("productivity") or 0)

		data.append(agg)

	# Append totals row
	if data:
		tot = {
			"date": "",
			"cut_plan": "",
			"rm_qty_mt": 0.0,
			"cutting_plans": "",
			"size": "",
			"a_col": 0.0,
			"b_col": 0.0,
			"fg_qty_mt": 0.0,
			"ng": 0,
			"ng_avg": 0.0,
			"rm_scrap": 0.0,
			"miss_roll_mt": 0.0,
			"end_cut_mt": 0.0,
			"insp_yard_mt": 0.0,
			"kvah": 0.0,
			"kvah_cum": 0.0,
			"rm_scrap_pct": 0.0,
			"miss_roll_pct": 0.0,
			"end_cut_pct": 0.0,
			"insp_yard_pct": 0.0,
			"total_scrap_mt": 0.0,
			"total_scrap_pct": 0.0,
			"reusable_miss_roll_mt": 0.0,
			"productivity": "",
			"is_total_row": 1,
		}

		for row in data:
			# sum straightforward numerics
			for key in [
				"rm_qty_mt",
				"fg_qty_mt",
				"ng",
				"rm_scrap",
				"miss_roll_mt",
				"end_cut_mt",
				"insp_yard_mt",
				"kvah",
				"total_scrap_mt",
				"reusable_miss_roll_mt",
				"a_col",
				"b_col",
			]:
				tot[key] += float(row.get(key) or 0)

		# totals percentages recomputed on totals
		rm_qty_total = float(tot["rm_qty_mt"] or 0)
		def pct(val, base):
			return round((float(val) / base * 100.0), 2) if base else 0.0
		tot["rm_scrap_pct"] = pct(tot["rm_scrap"], rm_qty_total)
		tot["miss_roll_pct"] = pct(tot["miss_roll_mt"], rm_qty_total)
		tot["end_cut_pct"] = pct(tot["end_cut_mt"], rm_qty_total)
		tot["insp_yard_pct"] = pct(tot["insp_yard_mt"], rm_qty_total)
		tot["total_scrap_pct"] = pct(tot["total_scrap_mt"], rm_qty_total)

		# NG AVG on totals = total NG / total FG Qty
		fg_total = float(tot.get("fg_qty_mt") or 0)
		ng_total = float(tot.get("ng") or 0)
		tot["ng_avg"] = round((ng_total / fg_total), 3) if fg_total else 0.0

		# KVAH CUM on totals = total KVAH / total FG Qty
		kvah_total = float(tot.get("kvah") or 0)
		tot["kvah_cum"] = round((kvah_total / fg_total), 3) if fg_total else 0.0

		tot["a_col"] = flt(tot.get("a_col") or 0, 3)
		tot["b_col"] = flt(tot.get("b_col") or 0, 3)

		data.append(tot)

	return columns, data


def get_columns():
		
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": _("Cutting Plans"), "fieldname": "cutting_plans", "fieldtype": "Data", "width": 220},
		{"label": _("RM Qty (Mt)"), "fieldname": "rm_qty_mt", "fieldtype": "Float", "width": 110},
		{"label": _("SIZE"), "fieldname": "size", "fieldtype": "Data", "width": 140},
		{"label": _("A"), "fieldname": "a_col", "fieldtype": "Data", "width": 80},
		{"label": _("B"), "fieldname": "b_col", "fieldtype": "Data", "width": 80},
		{"label": _("FG Qty (MT)"), "fieldname": "fg_qty_mt", "fieldtype": "Float", "width": 120},		
		{"label": _("NG"), "fieldname": "ng", "fieldtype": "Int", "width": 90},
		{"label": _("NG AVG"), "fieldname": "ng_avg", "fieldtype": "Float", "width": 90},
		# R.M Scrap group starts here (indices 7-9)
		{"label": _("R.M Scrap"), "fieldname": "rm_scrap", "fieldtype": "Float", "width": 100},
		{"label": _("MISS ROLL (MT)"), "fieldname": "miss_roll_mt", "fieldtype": "Float", "width": 110},
		{"label": _("END CUT (MT)"), "fieldname": "end_cut_mt", "fieldtype": "Float", "width": 110},
		# FG SCRAP group starts here (index 10)
		{"label": _("INSP + YARD (MT)"), "fieldname": "insp_yard_mt", "fieldtype": "Float", "width": 130},
		# Regular columns continue
		{"label": _("KVAH"), "fieldname": "kvah", "fieldtype": "Float", "width": 90},
		{"label": _("KVAH CUM"), "fieldname": "kvah_cum", "fieldtype": "Float", "width": 100},
		{"label": _("RM SCRAP %"), "fieldname": "rm_scrap_pct", "fieldtype": "Percent", "width": 110},
		{"label": _("MISS ROLL %"), "fieldname": "miss_roll_pct", "fieldtype": "Percent", "width": 110},
		{"label": _("END CUTTING %"), "fieldname": "end_cut_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("INSP+YARD %"), "fieldname": "insp_yard_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("TOTAL SCRAP MT"), "fieldname": "total_scrap_mt", "fieldtype": "Float", "width": 130},
		{"label": _("TOTAL SCRAP %"), "fieldname": "total_scrap_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("RE-USABLE MISS ROLL (MT)"), "fieldname": "reusable_miss_roll_mt", "fieldtype": "Float", "width": 170},
	]


def get_scrap_bucket(target_warehouse: str) -> str:
	"""Return the bucket key for a given target scrap warehouse."""
	if not target_warehouse:
		return "rm_scrap"

	return SCRAP_WAREHOUSE_BUCKETS.get(target_warehouse, "rm_scrap")