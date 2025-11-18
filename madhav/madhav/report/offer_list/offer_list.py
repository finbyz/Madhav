# Copyright (c) 2025, Finbyz pvt. ltd. and contributors
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
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 250
		},
		{
			"fieldname": "lot_no",
			"label": _("Lot No."),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "po_no",
			"label": _("PO No."),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 120
		},
		{
			"fieldname": "grade",
			"label": _("GRADE"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "length_m",
			"label": _("LENGTH(m)"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "pieces",
			"label": _("Pieces"),
			"fieldtype": "Int",
			"width": 80
		},
		{
			"fieldname": "qty",
			"label": _("Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "tc_no",
			"label": _("TC NO."),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "colour_code",
			"label": _("COLOUR CODE"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "embossing",
			"label": _("EMBOSSING"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "sample_no",
			"label": _("SAMPLE NO."),
			"fieldtype": "Data",
			"width": 150
		},
	]
	return columns

def get_data(filters):
	"""Fetch data based on filters"""
	conditions = get_conditions(filters)
	
	data = []
	
	# Fetch Sales Orders based on filters
	sales_orders = frappe.get_all(
		"Sales Order",
		filters=conditions,
		fields=["name", "customer", "transaction_date"],
		order_by="transaction_date desc, name desc"
	)
	
	# Calculate total qty for summary row
	total_qty_sum = 0.0
	
	for so in sales_orders:
		# Fetch items from Sales Order
		items = frappe.get_all(
			"Sales Order Item",
			filters={"parent": so.name},
			fields=[
				"item_name",
				"item_code",
				"purchase_order",
				"length_size",
				"qty",
				"name",
				"idx"
			],
			order_by="idx"
		)
		
		for item in items:
			# Get lot_no - check if it's in Sales Order Item or related to batches
			lot_no = get_lot_no(item.item_code, so.name, item.name)
			
			# Get grade - check if it's in Item master or custom field
			grade = get_grade(item.item_code)
			
			# Get pieces - check if it's a custom field or from batches
			pieces = get_pieces(item.item_code, so.name, item.name)
			
			# Length in meters
			length_m = flt(item.length_size) if item.length_size else 0.0
			
			# Qty
			qty = flt(item.qty) if item.qty else 0.0
			total_qty_sum += qty
			
			row = {
				"item_name": item.item_name,
				"lot_no": lot_no,
				"po_no": item.purchase_order,
				"grade": grade,
				"length_m": length_m,
				"pieces": pieces,
				"qty": qty
			}
			data.append(row)
	
	# Add summary row at the end
	if data:
		summary_row = {
			"item_name": "<b>Total</b>",
			"lot_no": "",
			"po_no": "",
			"grade": "",
			"length_m": None,
			"pieces": None,
			"qty": total_qty_sum
		}
		data.append(summary_row)
	
	return data

def get_conditions(filters):
	"""Build conditions for Sales Order query"""
	conditions = {"docstatus": 1}  # Only submitted Sales Orders
	
	if filters.get("company"):
		conditions["company"] = filters.get("company")
	
	if filters.get("customer"):
		conditions["customer"] = filters.get("customer")
	
	if filters.get("sales_order"):
		conditions["name"] = filters.get("sales_order")
	
	# Handle date range
	if filters.get("from_date") and filters.get("to_date"):
		conditions["transaction_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
	elif filters.get("from_date"):
		conditions["transaction_date"] = [">=", filters.get("from_date")]
	elif filters.get("to_date"):
		conditions["transaction_date"] = ["<=", filters.get("to_date")]
	
	return conditions

def get_lot_no(item_code, sales_order, item_name):
	"""Get lot_no from Sales Order Item or related data"""
	# Check if lot_no is a custom field in Sales Order Item
	if frappe.db.has_column("Sales Order Item", "lot_no"):
		lot_no = frappe.db.get_value("Sales Order Item", item_name, "lot_no")
		if lot_no:
			return lot_no
	
	# Check if lot_no comes from Work Orders or other related documents
	# You may need to adjust this based on your business logic
	return ""

def get_grade(item_code):
	"""Get grade from Item master or custom field"""
	# Check if grade is a field in Item master
	if frappe.db.has_column("Item", "grade"):
		grade = frappe.db.get_value("Item", item_code, "grade")
		if grade:
			return grade
	
	# Check if it's a custom field
	if frappe.db.has_column("Item", "custom_grade"):
		grade = frappe.db.get_value("Item", item_code, "custom_grade")
		if grade:
			return grade
	
	return ""

def get_pieces(item_code, sales_order, item_name):
	"""Get pieces from Sales Order Item or related data"""
	# Check if pieces is a custom field in Sales Order Item
	if frappe.db.has_column("Sales Order Item", "pieces"):
		pieces = frappe.db.get_value("Sales Order Item", item_name, "pieces")
		if pieces:
			return int(pieces)
	
	# Check if pieces comes from batches or other related data
	# You may need to adjust this based on your business logic
	return 0
