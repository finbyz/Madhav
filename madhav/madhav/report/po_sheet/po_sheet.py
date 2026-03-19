import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Party Name", "fieldname": "party_name", "fieldtype": "Data", "width": 180},
        {"label": "Grade", "fieldname": "grade", "fieldtype": "Data", "width": 80},
        {"label": "PO No", "fieldname": "po_no", "fieldtype": "Data", "width": 120},
        {"label": "Section", "fieldname": "section", "fieldtype": "Data", "width": 80},
        {"label": "Length", "fieldname": "length", "fieldtype": "Data", "width": 80},
        {"label": "PCS", "fieldname": "pcs", "fieldtype": "Float", "width": 60},
        {"label": "Total Weight", "fieldname": "total_weight", "fieldtype": "Float", "width": 120},
        {"label": "Ready PC", "fieldname": "ready_pc", "fieldtype": "Float", "width": 90},
        {"label": "Ready Weight", "fieldname": "ready_weight", "fieldtype": "Float", "width": 120},
        {"label": "Pending to Ready PC", "fieldname": "pending_ready_pc", "fieldtype": "Float", "width": 140},
        {"label": "Pending to Ready Weight", "fieldname": "pending_ready_weight", "fieldtype": "Float", "width": 170},
        {"label": "Clearence", "fieldname": "clearence", "fieldtype": "Float", "width": 120},
        {"label": "Dispatch PCS", "fieldname": "dispatch_pcs", "fieldtype": "Float", "width": 120},
        {"label": "Dispatch Weight", "fieldname": "dispatch_weight", "fieldtype": "Float", "width": 140},
        {"label": "Balance PCS", "fieldname": "balance_pcs", "fieldtype": "Float", "width": 120},
        {"label": "Balance Weight", "fieldname": "balance_weight", "fieldtype": "Float", "width": 140},
        {"label": "RFD", "fieldname": "rfd", "fieldtype": "Float", "width": 100},
        {"label": "Stock Qty", "fieldname": "stock_qty", "fieldtype": "Data", "width": 150},
        {"label": "PO Date", "fieldname": "po_date", "fieldtype": "Date", "width": 100},
        {"label": "Delivery Date", "fieldname": "delivery_date", "fieldtype": "Date", "width": 120},
        {"label": "Completion Date", "fieldname": "completion_date", "fieldtype": "Date", "width": 140},
        {"label": "Location", "fieldname": "location", "fieldtype": "Data", "width": 150},
    ]


def get_data(filters):
    filters = filters or {}

    so_filters = {}

    # Sales Order filter
    if filters.get("sales_order"):
        so_filters["name"] = filters.get("sales_order")

    # Delivery Date range
    if filters.get("from_date") and filters.get("to_date"):
        so_filters["delivery_date"] = ["between", [filters.get("from_date"), filters.get("to_date")]]
    elif filters.get("from_date"):
        so_filters["delivery_date"] = [">=", filters.get("from_date")]
    elif filters.get("to_date"):
        so_filters["delivery_date"] = ["<=", filters.get("to_date")]

    # Party Name (Customer)
    if filters.get("party_name"):
        so_filters["customer"] = filters.get("party_name")

    data = []

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=so_filters,
        fields=[
            "name",
            "customer_name",
            "po_no",
            "po_date",
            "delivery_date"
        ]
    )

    for so in sales_orders:

        so_items = frappe.get_all(
            "Sales Order Item",
            filters={"parent": so.name},
            fields=[
                "idx",
                "item_code",
                "item_name",
                "length_size",
                "total_weight",
                "pieces",
                "qty",
                "name",
                "projected_qty",
                "actual_qty"
            ]
        )


        for soi in so_items:
            # ---------------------------
            # Delivery Note aggregation
            # ---------------------------
            dn_item = frappe.get_all(
                "Delivery Note Item",
                filters={
                    "against_sales_order": so.name,
                    "item_code": soi.item_code,
                    "so_detail": soi.name,   # exact SO row match
                },
                fields=["qty", "pieces"],
                limit=1
            )

            if dn_item:
                ready_pc = flt(dn_item[0].pieces)
                ready_weight = flt(dn_item[0].qty)
            else:
                ready_pc = 0
                ready_weight = 0


            # ---------------------------
            # Sales Invoice aggregation
            # ---------------------------
            si_items = frappe.get_all(
                "Sales Invoice Item",
                filters={
                    "sales_order": so.name,
                    "item_code": soi.item_code,
                    "so_detail": soi.name,   # exact SO row match
                },
                fields=["qty", "pieces", "parent"],
                limit=1
            )

            if si_items:
                dispatch_pcs = flt(si_items[0].pieces)
                dispatch_weight = flt(si_items[0].qty)
            else:
                dispatch_pcs = 0
                dispatch_weight = 0

            balance_pcs = soi.pieces - dispatch_pcs


            # Completion date & location
            completion_date = None
            location = None

            if si_items:
                si = frappe.get_doc("Sales Invoice", si_items[0].parent)
                completion_date = si.due_date if si.docstatus == 1 else None
                location = si.place_of_supply

            pcs = 0
            pending_ready_pc = soi.pieces - ready_pc

            pending_ready_weight = (
                0 if (flt(soi.qty) - ready_weight) < 0
                else (flt(soi.qty) - ready_weight)
            )

            clearence = ready_weight
            balance_weight = flt(soi.qty) - dispatch_weight
            rfd = clearence - dispatch_weight
            grade, section = get_grade_and_section(soi.item_name)

            data.append({
                "party_name": so.customer_name,
                "grade": grade,
                "po_no": so.po_no,
                "section": section,
                "length": soi.length_size,
                # "pcs": pcs,
                "pcs": soi.pieces,
                "total_weight": soi.qty,
                "ready_pc": ready_pc,
                "ready_weight": ready_weight,
                "pending_ready_pc": pending_ready_pc,
                "pending_ready_weight": pending_ready_weight,
                "clearence": clearence,
                "dispatch_pcs": dispatch_pcs,
                "dispatch_weight": dispatch_weight,
                "balance_pcs": balance_pcs,
                "balance_weight": balance_weight,
                "rfd": rfd,
                "stock_qty": soi.actual_qty,
                "po_date": so.po_date,
                "delivery_date": so.delivery_date,
                "completion_date": completion_date,
                "location": location,
            })

    return data

def get_grade_and_section(item_name):
    if not item_name:
        return "", ""

    parts = item_name.split()

    section = parts[-1] if len(parts) >= 1 else ""
    grade = ""

    if len(parts) >= 3:
        grade = " ".join(parts[-3:-1])

    return grade, section
