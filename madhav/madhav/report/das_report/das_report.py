# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	# frappe.throw(str(columns))
	return columns, data

def get_columns():
    return [
        {
            "fieldname": "date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "particulars",
            "label": _("Particulars"),
            "fieldtype": "Data",
            "width": 250
        },
        {
            "fieldname": "voucher_type",
            "label": _("Voucher Type"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "voucher_no",
            "label": _("Voucher No."),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 150
        },
        {
            "fieldname": "voucher_ref_no",
            "label": _("Voucher Ref. No."),
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "order_no_date",
            "label": _("Order No. & Date"),
            "fieldtype": "Data",
            "width": 180
        },
        {
            "fieldname": "terms_of_payment",
            "label": _("Terms of Payment"),
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "other_references",
            "label": _("Other References"),
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "terms",
            "label": _("Terms of Delivery"),
            "fieldtype": "Data",
            "width": 150
        },
		{
            "fieldname": "vehicle_no",
            "label": _("Vehicle No"),
            "fieldtype": "Data",
            "width": 100
        },
		{
            "fieldname": "total_qty",
            "label": _("Total Quantity"),
            "fieldtype": "Float",
            "width": 100
        },
		{
            "fieldname": "grand_total",
            "label": _("Grand Total"),
            "fieldtype": "Currency",
            "width": 100
        }
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    
    data = frappe.db.sql("""
        SELECT
            si.posting_date as date,
            si.customer_name as particulars,
            'Sales Invoice' as voucher_type,
            si.name as voucher_no,
            '' as voucher_ref_no,
            si.vehicle_no as vehicle_no,
            si.total_qty as total_qty,
            si.grand_total as grand_total,
            CASE 
                WHEN so.name IS NOT NULL AND so.transaction_date IS NOT NULL 
                THEN CONCAT(so.name, ' / ', DATE_FORMAT(so.transaction_date, '%%d-%%b-%%y'))
                WHEN si.po_no IS NOT NULL AND si.po_date IS NOT NULL 
                THEN CONCAT(si.po_no, ' / ', DATE_FORMAT(si.po_date, '%%d-%%b-%%y'))
                WHEN si.po_no IS NOT NULL 
                THEN si.po_no
                ELSE ''
            END as order_no_date,
            IFNULL(si.payment_terms_template, '') as terms_of_payment,
            '' as other_references,
            si.tc_name as terms
        FROM
            `tabSales Invoice` si
        LEFT JOIN
            `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN
            `tabSales Order` so ON so.name = sii.sales_order
        WHERE
            si.docstatus = 1
            {conditions}
        GROUP BY
            si.name
        ORDER BY
            si.posting_date, si.name
    """.format(conditions=conditions), filters, as_dict=1)
    
    # Add totals row
    if data:
        data.append({
            "date": "",
            "particulars": "<b>Total</b>",
            "voucher_type": "",
            "voucher_no": "",
            "voucher_ref_no": "",
            "order_no_date": "",
            "terms_of_payment": "",
            "other_references": "",
            "terms": "",
            "vehicle_no": "",
            "total_qty": sum([row.get('total_qty', 0) or 0 for row in data]),
            "grand_total": sum([row.get('grand_total', 0) or 0 for row in data])
        })
    
    return data

def get_conditions(filters):
    conditions = []
    
    if filters.get("from_date"):
        conditions.append("posting_date >= %(from_date)s")
    
    if filters.get("to_date"):
        conditions.append("posting_date <= %(to_date)s")
    
    if filters.get("customer"):
        conditions.append("customer = %(customer)s")
    
    if filters.get("company"):
        conditions.append("company = %(company)s")
    
    return " AND " + " AND ".join(conditions) if conditions else ""