import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        _("DTD") + ":Date:90",
        _("Bill No") + ":Link/Delivery Note:120",
        _("Item") + ":Link/Item:120",
        _("Item Name") + ":Data:180",
        _("Length") + ":Float:90",
        _("Dispatch PC") + ":Float:110",
        _("Qty") + ":Float:90",
        _("Truck No") + ":Data:120",
        _("PO No") + ":Data:120",
    ]


def get_data(filters):
    conditions = ""
    values = {}

    if filters.get("from_date"):
        conditions += " AND dn.posting_date >= %(from_date)s"
        values["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions += " AND dn.posting_date <= %(to_date)s"
        values["to_date"] = filters.get("to_date")

    if filters.get("delivery_note"):
        conditions += " AND dn.name = %(delivery_note)s"
        values["delivery_note"] = filters.get("delivery_note")
	# dn.docstatus = 1
    query = f"""
        SELECT
            dn.posting_date,
            dn.name AS delivery_note,
            dni.item_code,
            dni.item_name,
            dni.average_length,
            dni.pieces,
            dni.qty,
            dn.vehicle_no,
            dni.against_sales_order
        FROM
            `tabDelivery Note` dn
        INNER JOIN
            `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE
        	1 = 1
            {conditions}
        ORDER BY
            dn.posting_date, dn.name
    """

    rows = frappe.db.sql(query, values, as_dict=True)

    data = []
    so_po_map = {}

    for r in rows:
        po_no = ""

        if r.against_sales_order:
            if r.against_sales_order not in so_po_map:
                so_po_map[r.against_sales_order] = frappe.db.get_value(
                    "Sales Order",
                    r.against_sales_order,
                    "po_no"
                )
            po_no = so_po_map.get(r.against_sales_order) or ""

        data.append([
            r.posting_date,
            r.delivery_note,
            r.item_code,
            r.item_name,
            r.average_length or 0,
            r.pieces or 0,
            r.qty or 0,
            r.vehicle_no or "",
            po_no,
        ])

    return data
