import frappe
import json
from frappe.utils import flt
from frappe import _

def on_submit(doc, method=None):
    if not doc.items:
        return

    keys = {
        (d.item_code, d.warehouse, d.batch_no)
        for d in doc.items
        if d.item_code and d.warehouse and d.batch_no
    }

    if not keys:
        return

    item_codes = list({k[0] for k in keys})
    warehouses = list({k[1] for k in keys})
    batch_nos = list({k[2] for k in keys})

    sre_rows = frappe.db.sql(
        """
        SELECT
            parent.item_code,
            parent.warehouse,
            child.batch_no,
            parent.reserved_qty
        FROM `tabStock Reservation Entry` parent
        JOIN `tabSerial and Batch Entry` child
            ON child.parent = parent.name
        WHERE parent.docstatus = 1
          AND parent.item_code IN %(item_codes)s
          AND parent.warehouse IN %(warehouses)s
          AND child.batch_no IN %(batch_nos)s
        """,
        {
            "item_codes": item_codes,
            "warehouses": warehouses,
            "batch_nos": batch_nos,
        },
        as_dict=True,
    )

    reserved_lookup = {}
    for r in sre_rows:
        key = (r.item_code, r.warehouse, r.batch_no)
        reserved_lookup[key] = reserved_lookup.get(key, 0) + flt(r.reserved_qty)

    for row in doc.items:
        if not row.batch_no:
            continue

        key = (row.item_code, row.warehouse, row.batch_no)
        reserved_qty = flt(reserved_lookup.get(key))

        if reserved_qty and flt(row.qty) < reserved_qty:
            frappe.throw(
                _(
                    "Row {0}: Delivery qty {1} is less than reserved qty {2} "
                    "for Item {3}, Batch {4} in Warehouse {5}"
                ).format(
                    row.idx,
                    reserved_qty,
                    row.item_code,
                    row.batch_no,
                    row.warehouse,
                )
            )

@frappe.whitelist()
def get_sales_order_items_for_selector(filters=None):

    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    so_filters = [
        ["docstatus", "=", 1],
    ]

    # Handle filters from frontend (status, per_delivered, company, customer, project)
    for key, val in filters.items():
        if key in ("dynamic_filters", "project"):
            continue
        
        if val:
            if isinstance(val, list) and len(val) == 2:
                # Array format like ["not in", [...]] or ["<", 99.99]
                so_filters.append([key, val[0], val[1]])
            else:
                so_filters.append([key, "=", val])

    if filters.get("project"):
        so_filters.append(["project", "=", filters.get("project")])

    # Handle dynamic filters from FilterGroup
    if filters.get("dynamic_filters"):
        dynamic_filters = filters.get("dynamic_filters")
        if isinstance(dynamic_filters, str):
            dynamic_filters = json.loads(dynamic_filters)
        
        for df in dynamic_filters:
            if len(df) >= 4:
                # df format: [doctype, fieldname, operator, value]
                fieldname = df[1]
                operator = df[2]
                value = df[3]

                if operator == "Between" and isinstance(value, str) and " to " in value:
                    value = value.split(" to ")
                
                so_filters.append([fieldname, operator, value])

    sales_orders = frappe.get_all(
        "Sales Order",
        fields=["name", "customer", "transaction_date", "currency"],
        filters=so_filters,
        order_by="transaction_date desc",
    )

    if not sales_orders:
        return []

    so_names = [d.name for d in sales_orders]
    so_map = {d.name: d for d in sales_orders}

    # -------------------------
    # Fetch Sales Order Items + Item section weight
    # -------------------------

    items = frappe.db.sql(
        """
        SELECT
            soi.name,
            soi.parent,
            soi.item_code,
            soi.item_name,
            soi.qty,
            soi.rate,
            soi.amount,
            soi.billed_amt,
            soi.uom,
            soi.pieces,
            soi.length_size,
            soi.description,
            item.weight_per_meter as section_weight
        FROM `tabSales Order Item` soi
        LEFT JOIN `tabItem` item
            ON item.name = soi.item_code
        WHERE soi.parent IN %(so_names)s
        ORDER BY soi.parent asc, soi.idx asc
        """,
        {"so_names": so_names},
        as_dict=True,
    )

    # -----------------------------
    # Fetch reserved quantities
    # -----------------------------

    reservation_rows = frappe.db.sql(
        """
        SELECT
            sre.voucher_detail_no,
            SUM(sre.reserved_qty) AS reserved_qty,
            SUM(sbe.peices) AS reserved_pieces
        FROM `tabStock Reservation Entry` sre
        LEFT JOIN `tabSerial and Batch Entry` sbe
            ON sbe.parent = sre.name
        WHERE sre.docstatus = 1
        AND sre.voucher_type = 'Sales Order'
        GROUP BY sre.voucher_detail_no
        """,
        as_dict=True,
    )

    reservation_map = {
        r.voucher_detail_no: r for r in reservation_rows
    }

    rows = []

    for row in items:

        billed_qty = flt(row.billed_amt) / flt(row.rate) if flt(row.rate) else 0
        pending_qty = flt(row.qty) - billed_qty

        if pending_qty <= 0:
            continue

        so = so_map.get(row.parent) or {}

        reservation = reservation_map.get(row.name, {})

        rows.append(
            {
                "name": row.name,
                "parent": row.parent,
                "customer": so.get("customer"),
                "transaction_date": so.get("transaction_date"),

                "item_code": row.item_code,
                "item_name": row.item_name,

                "qty": flt(row.qty),
                "pending_qty": pending_qty,
                "uom": row.uom,

                "pieces": row.pieces,
                "length": row.length_size,

                # section weight from Item
                "section_weight": flt(row.section_weight),
                # reservation data
                "reserved_qty": flt(reservation.get("reserved_qty")),
                "reserved_pieces": flt(reservation.get("reserved_pieces")),
            }
        )

    return rows