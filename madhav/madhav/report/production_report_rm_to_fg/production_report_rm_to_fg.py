# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	"""Define report columns"""
	columns = [
		
		{
			"fieldname": "date",
			"label": _("RECEIVED DATE"),
			"fieldtype": "Date",
			"width": 140
		},
		{
			"fieldname": "supplier_name",
			"label": _("Supplier Name"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "master_batch",
			"label": _("Master Batch No."),
			"fieldtype": "Data",
			"width": 140
		},
		{
			"fieldname": "child_batch",
			"label": _("Child Batch No."),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "rm_item",
			"label": _("RM Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 250
		},
		{
			"fieldname": "rm_qty",
			"label": _("Opening RM Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "issued_rm_qty",
			"label": _("Issued RM Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "balance_qty",
			"label": _("Balance Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "production_date",
			"label": _("Production Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "finish_qty",
			"label": _("Finish Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "lot_no",
			"label": _("LOT NO."),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "party_name",
			"label": _("Party Name"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "partywise_qty",
			"label": _("Partywise Qty"),
			"fieldtype": "Float",
			"width": 100
		},
	]
	return columns

def get_data(filters):
	"""Fetch data based on filters"""
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Please select From Date and To Date"))
	
	data = []
	
	# Fetch Cutting Plans within date range
	cutting_plans = frappe.get_all(
		"Cutting Plan",
		filters={
			"cut_plan_type": "Raw Material Cut Plan",
			"docstatus": 1,  # Only submitted documents
			"creation": ["between", [filters.get("from_date"), filters.get("to_date")]]
		},
		fields=["name", "creation"]
	)
	
	for plan in cutting_plans:
		
		# Fetch all child batches produced under this plan from Cut Plan Finish (Second)
		child_batches = frappe.get_all(
			"Cutting plan Finish Second",
			filters={"parent": plan.name},
			fields=["batch"],
			order_by="idx"
		)
		child_batch_list = [cb.get("batch") for cb in child_batches if cb.get("batch")]
		child_batch_csv = ", ".join(sorted(set(child_batch_list))) if child_batch_list else None
		
		cut_plan_details = frappe.get_all(
			"Cut Plan Detail",
			filters={"parent": plan.name},
			fields=["item_name","supplier_detail", "name", "batch", "qty", "work_order_reference"],
			order_by="idx"
		)
		
		# If no details found, skip this plan
		if not cut_plan_details:
			continue
		for detail in cut_plan_details:
			# Get opening qty from parent batch
			opening_qty = 0.0
			parent_batch = detail.get("batch")
			if parent_batch:
				batch_qty = frappe.db.get_value("Batch", parent_batch, "batch_qty")
				opening_qty = flt(batch_qty) if batch_qty else 0.0
			
			# Get issued qty from Cut Plan Detail
			issued_qty = flt(detail.get("qty")) if detail.get("qty") else 0.0
			
			# Calculate balance qty
			balance_qty = opening_qty - issued_qty
			
			row = {
				"date": plan.creation.date() if plan.creation else None,
				"supplier_name": detail.supplier_detail,
				"rm_item": detail.item_name,
				# Master batch comes from Cut Plan Detail.batch (RM used)
				"master_batch": parent_batch,
				# Child batches aggregated from Cut Plan Finish Second for the same plan
				"child_batch": child_batch_csv,
				# Opening RM Qty from parent batch
				"rm_qty": opening_qty,
				# Issued RM Qty from Cut Plan Detail
				"issued_rm_qty": issued_qty,
				# Balance Qty (difference between opening and issued)
				"balance_qty": balance_qty,
				# FG columns should be empty for RM detail rows
				"production_date": None,
				"finish_qty": None,
				"lot_no": None,
				"party_name": None,
				"partywise_qty": None
			}
			data.append(row)
			
			# Add rows based on work_order_reference
			work_order_ref = detail.get("work_order_reference")
			work_order_ref_doc = frappe.get_doc("Work Order", work_order_ref)
			if work_order_ref and work_order_ref_doc.docstatus == 1 and work_order_ref_doc.status == "Completed":
				# Get cutting_plan_reference from Work Order
				cutting_plan_ref = frappe.db.get_value("Work Order", work_order_ref, "cutting_plan_reference")
				
				if cutting_plan_ref:
					# Get cutting plan details
					cutting_plan_doc = frappe.get_doc("Cutting Plan", cutting_plan_ref)
					production_date = cutting_plan_doc.modified.date() if cutting_plan_doc.modified else None
					finish_qty = flt(cutting_plan_doc.cut_plan_total_qty) if cutting_plan_doc.cut_plan_total_qty else 0.0
					
					# Get cutting_plan_finish rows (Cutting plan Finish Second)
					cutting_plan_finish_rows = frappe.get_all(
						"Cutting Plan Finish",
						filters={"parent": cutting_plan_ref},
						fields=["lot_no", "remarks", "qty"],
						order_by="idx"
					)
					
					# Group by remarks and calculate totals
					remarks_dict = {}
					for finish_row in cutting_plan_finish_rows:
						remarks = finish_row.get("remarks") or ""
						lot_no = finish_row.get("lot_no") or ""
						qty = flt(finish_row.get("qty")) if finish_row.get("qty") else 0.0
						
						if remarks not in remarks_dict:
							remarks_dict[remarks] = {
								"lot_nos": set(),
								"total_qty": 0.0
							}
						
						remarks_dict[remarks]["total_qty"] += qty
						# Collect all unique lot_no values for each remarks group
						if lot_no:
							remarks_dict[remarks]["lot_nos"].add(lot_no)
					
					# Create a row for each unique remarks - these are the NEXT rows after RM detail
					for remarks, remarks_data in remarks_dict.items():
						# Combine all lot_no values with comma separator
						lot_no_str = ", ".join(sorted(remarks_data["lot_nos"])) if remarks_data["lot_nos"] else ""
						
						# FG row - only FG columns populated, RM columns can be empty or minimal context
						finish_row = {
							"date": None,
							"supplier_name": None,
							"rm_item": None,
							"master_batch": None,
							"child_batch": None,
							"rm_qty": None,
							"issued_rm_qty": None,
							"balance_qty": None,
							# FG columns populated from next row onwards
							"production_date": production_date,
							"finish_qty": finish_qty,
							"lot_no": lot_no_str,
							"party_name": remarks,
							"partywise_qty": remarks_data["total_qty"]
						}
						data.append(finish_row)
	
	return data