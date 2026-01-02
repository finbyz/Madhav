import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": "Date",
            "fieldname": "delivery_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": "Party Name",
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": "P.O. No.",
            "fieldname": "po_no",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Sales Order Qty",
            "fieldname": "so_qty",
            "fieldtype": "Float",
            "width": 140
        },
        {
            "label": "Sales Invoice Qty",
            "fieldname": "si_qty",
            "fieldtype": "Float",
            "width": 160
        },
        {
            "label": "Weight / MT",
            "fieldname": "balance_qty",
            "fieldtype": "Float",
            "width": 130
        }
    ]


def get_data(filters):
    conditions = []
    values = {}

    conditions.append("so.docstatus = 1")

    if filters.get("company"):
        conditions.append("so.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("sales_order"):
        conditions.append("so.name = %(sales_order)s")
        values["sales_order"] = filters["sales_order"]

    if filters.get("customer"):
        conditions.append("so.customer = %(customer)s")
        values["customer"] = filters["customer"]

    if filters.get("from_date"):
        conditions.append("so.delivery_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("so.delivery_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    condition_sql = " AND ".join(conditions)

    query = f"""
        SELECT
            so.delivery_date,
            so.customer_name,
            so.po_no,
            so.total_qty AS so_qty,

            IFNULL(
                (
                    SELECT SUM(sii.qty)
                    FROM `tabSales Invoice Item` sii
                    INNER JOIN `tabSales Invoice` si
                        ON si.name = sii.parent
                    WHERE
                        sii.sales_order = so.name
                        AND si.docstatus = 1
                ),
                0
            ) AS si_qty,

            so.total_qty - IFNULL(
                (
                    SELECT SUM(sii.qty)
                    FROM `tabSales Invoice Item` sii
                    INNER JOIN `tabSales Invoice` si
                        ON si.name = sii.parent
                    WHERE
                        sii.sales_order = so.name
                        AND si.docstatus = 1
                ),
                0
            ) AS balance_qty

        FROM `tabSales Order` so
        WHERE {condition_sql}
        ORDER BY so.delivery_date
    """

    return frappe.db.sql(query, values, as_dict=True)
