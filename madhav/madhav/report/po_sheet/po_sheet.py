import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": "Party Name",
            "fieldname": "party_name",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "Grade",
            "fieldname": "grade",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "PO No",
            "fieldname": "po_no",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Section",
            "fieldname": "section",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": "Length",
            "fieldname": "length",
            "fieldtype": "Data",
            "width": 90
        },
        {
            "label": "PCS",
            "fieldname": "pcs",
            "fieldtype": "Float",
            "width": 90
        },
        {
            "label": "Total Weight",
            "fieldname": "total_weight",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Ready PC",
            "fieldname": "ready_pc",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": "Ready Weight",
            "fieldname": "ready_weight",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Pending to Ready PC",
            "fieldname": "pending_ready_pc",
            "fieldtype": "Float",
            "width": 160
        },
        {
            "label": "Pending to Ready Weight",
            "fieldname": "pending_ready_weight",
            "fieldtype": "Float",
            "width": 180
        },
        {
            "label": "Clearence",
            "fieldname": "clearence",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Dispatch PCS",
            "fieldname": "dispatch_pcs",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Dispatch Weight",
            "fieldname": "dispatch_weight",
            "fieldtype": "Float",
            "width": 140
        },
        {
            "label": "Balance PCS",
            "fieldname": "balance_pcs",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Balance Weight",
            "fieldname": "balance_weight",
            "fieldtype": "Float",
            "width": 140
        },
        {
            "label": "RFD",
            "fieldname": "rfd",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": "PO Date",
            "fieldname": "po_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": "Item Code",
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "label": "Delivery Date",
            "fieldname": "delivery_date",
            "fieldtype": "Date",
            "width": 120
        },
        {
            "label": "Rate",
            "fieldname": "rate",
            "fieldtype": "Currency",
            "width": 100
        },
        {
            "label": "Location",
            "fieldname": "location",
            "fieldtype": "Data",
            "width": 150
        },
    ]


def get_data(filters):
    filters = filters or {}

    so_filters = {}

    # -----------------------------------
    # FILTERS
    # -----------------------------------

    if filters.get("sales_order"):
        so_filters["name"] = filters.get("sales_order")

    if filters.get("from_date") and filters.get("to_date"):
        so_filters["delivery_date"] = [
            "between",
            [filters.get("from_date"), filters.get("to_date")]
        ]

    elif filters.get("from_date"):
        so_filters["delivery_date"] = [
            ">=",
            filters.get("from_date")
        ]

    elif filters.get("to_date"):
        so_filters["delivery_date"] = [
            "<=",
            filters.get("to_date")
        ]

    # -----------------------------------
    # MULTI CUSTOMER FILTER
    # -----------------------------------

    if filters.get("party_name"):
        customers = filters.get("party_name")

        if isinstance(customers, str):
            customers = frappe.parse_json(customers)

        so_filters["customer"] = ["in", customers]

    # -----------------------------------
    # PO NO FILTER
    # -----------------------------------

    if filters.get("po_no"):
        so_filters["po_no"] = ["like", f"%{filters.get('po_no')}%"]
    # -----------------------------------
    # SALES ORDERS
    # -----------------------------------

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=so_filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "po_no",
            "po_date",
            "delivery_date",
            "customer_address"
        ]
    )

    data = []

    # -----------------------------------
    # ITEM FILTER
    # -----------------------------------

    item_filter = []

    if filters.get("item_code"):
        item_filter = filters.get("item_code")

        if isinstance(item_filter, str):
            item_filter = frappe.parse_json(item_filter)

    for so in sales_orders:

        so_item_filters = {
            "parent": so.name
        }

        if item_filter:
            so_item_filters["item_code"] = ["in", item_filter]

        so_items = frappe.get_all(
            "Sales Order Item",
            filters=so_item_filters,
            fields=[
                "name",
                "item_code",
                "item_name",
                "length_size",
                "qty",
                "pieces",
                "rate"
            ]
        )

        for soi in so_items:

            # -----------------------------------
            # WORK ORDERS
            # -----------------------------------

            work_orders = frappe.get_all(
                "Work Order",
                filters={
                    "sales_order": so.name,
                    "production_item": soi.item_code,
                    "docstatus": 1
                },
                fields=[
                    "name",
                    "qty",
                    "pieces",
                    "pending_pcs",
                    "produced_qty"
                ]
            )

            total_pcs = 0
            total_weight = 0

            pending_ready_pc = 0
            pending_ready_weight = 0

            ready_pc = 0
            ready_weight = 0

            for wo in work_orders:

                total_pcs += flt(wo.pieces)

                total_weight += flt(wo.qty)

                pending_ready_pc += flt(wo.pending_pcs)

                pending_ready_weight += (
                    flt(wo.qty) - flt(wo.produced_qty)
                )

                # -----------------------------------
                # PENDING WORK ORDERS
                # -----------------------------------

                pwo_rows = frappe.get_all(
                    "Pending Work Orders",
                    filters={
                        "work_order": wo.name
                    },
                    fields=[
                        "ready_pieces",
                        "ready_qty"
                    ]
                )

                for pwo in pwo_rows:

                    ready_pc += flt(pwo.ready_pieces)

                    ready_weight += flt(pwo.ready_qty)

            # -----------------------------------
            # FALLBACK IF NO WO
            # -----------------------------------

            if not total_pcs:
                total_pcs = flt(soi.pieces)

            if not total_weight:
                total_weight = flt(soi.qty)

            # -----------------------------------
            # GRADE & SECTION
            # -----------------------------------

            grade, section = get_grade_and_section(
                soi.item_code,
                soi.item_name
            )

            # -----------------------------------
            # SALES INVOICE
            # -----------------------------------

            si_items = frappe.get_all(
                "Sales Invoice Item",
                filters={
                    "sales_order": so.name,
                    "item_code": soi.item_code
                },
                fields=[
                    "qty",
                    "pieces"
                ]
            )

            dispatch_pcs = sum(
                flt(d.pieces) for d in si_items
            )

            dispatch_weight = sum(
                flt(d.qty) for d in si_items
            )

            # -----------------------------------
            # CLEARANCE
            # -----------------------------------

            clearence = ready_weight

            # -----------------------------------
            # BALANCE
            # -----------------------------------

            balance_pcs = total_pcs - dispatch_pcs

            balance_weight = total_weight - dispatch_weight

            rfd = clearence - dispatch_weight

            # -----------------------------------
            # LOCATION
            # -----------------------------------

            location = ""

            if so.customer_address:

                location = frappe.db.get_value(
                    "Address",
                    so.customer_address,
                    "city"
                ) or ""

            # -----------------------------------
            # APPEND DATA
            # -----------------------------------

            data.append({
                "party_name": so.customer_name,
                "grade": grade,
                "po_no": so.po_no,
                "section": section,
                "length": soi.length_size,
                "pcs": total_pcs,
                "total_weight": total_weight,
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
                "po_date": so.po_date,
                "item_code": soi.item_code,
                "delivery_date": so.delivery_date,
                "rate": soi.rate,
                "location": location,
            })

    return data


def get_grade_and_section(item_code, item_name):

    if not item_code:
        return "", ""

    grade = ""

    attributes = frappe.get_all(
        "Item Variant Attribute",
        filters={
            "parent": item_code,
            "attribute": "Grade"
        },
        fields=["attribute_value"],
        limit=1
    )

    if attributes:
        grade = attributes[0].attribute_value or ""

    section = item_name or ""

    if grade and grade in section:
        section = section.replace(grade, "").strip()

    return grade, section