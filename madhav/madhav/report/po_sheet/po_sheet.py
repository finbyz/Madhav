import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": "Customer",
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 180
        },
        {
            "label": "Party Name",
            "fieldname": "party_name",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "Sales Order",
            "fieldname": "sales_order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "width": 180
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
            "label": "Assorted Length",
            "fieldname": "assorted_length",
            "fieldtype": "Data",
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
            "label": "After MFG",
            "fieldname": "after_mfg",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Pending CLR",
            "fieldname": "pending_clr",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "After CLR (Rejected)",
            "fieldname": "after_clr_rejected",
            "fieldtype": "Float",
            "width": 160
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

    # -----------------------------------
    # TYPE FILTER (Manufacturing / Trading)
    # -----------------------------------
    type_filter = filters.get("type")

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
                "rate",
                "assorted_length",
                "is_manufacture",
                "warehouse",
                "stock_reserved_qty"
            ]
        )

        for soi in so_items:

            # -----------------------------------
            # TYPE FILTER LOGIC
            # -----------------------------------
            if type_filter == "Manufacturing" and not soi.is_manufacture:
                continue
            if type_filter == "Trading" and soi.is_manufacture:
                continue

            # ===================================
            # MANUFACTURING ITEMS (is_manufacture = 1)
            # ===================================
            if soi.is_manufacture:

                # -----------------------------------
                # TOTAL PCS / TOTAL WEIGHT
                # -----------------------------------
                # These must always come from the Sales Order Item row itself.
                # A single Sales Order can have multiple item rows with the
                # SAME item_code but different length_size (e.g. 5.65m and
                # 5.95m of the same section). Summing Work Order qty/pieces
                # by sales_order + production_item alone lumps every such
                # row together and gives identical (wrong) totals on every
                # line, so we no longer derive total_pcs/total_weight from
                # Work Order at all.
                total_pcs = flt(soi.pieces)
                total_weight = flt(soi.qty)

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

                ready_pc = 0
                ready_weight = 0

                wo_names = [wo.name for wo in work_orders]

                for wo in work_orders:

                    # -----------------------------------
                    # READY PC / READY WEIGHT
                    # -----------------------------------
                    # Pending Work Orders rows carry their own "sales_order"
                    # reference (the actual link back to the Sales Order)
                    # plus "item" and "length_size"/"pieces". When an SO has
                    # two lines for the same item_code, this is the only way
                    # to tell which line a given Pending Work Orders row
                    # belongs to, so match on sales_order + item + length_size
                    # (the SO Item's own length/section identity), not just
                    # work_order name.
                    pwo_rows = frappe.get_all(
                        "Pending Work Orders",
                        filters={
                            "work_order": wo.name,
                            "sales_order": so.name,
                            "item": soi.item_code,
                            "length_size": soi.length_size,
                            "docstatus": 1
                        },
                        fields=[
                            "ready_pieces",
                            "ready_qty",
                            "sales_order",
                            "item",
                            "item_name",
                            "length_size",
                            "pieces",
                            "qty",
                            "target_warehouse",
                            "stock_entry_reference"
                        ]
                    )

                    for pwo in pwo_rows:
                        # Extra safety net: if item naming differs (e.g. a
                        # variant got renamed) don't count it as a match
                        # even though the item code lined up.
                        if pwo.item_name and soi.item_name and pwo.item_name != soi.item_name:
                            continue

                        ready_pc += flt(pwo.ready_pieces)
                        ready_weight += flt(pwo.ready_qty)

                # Clearance
                # PRIMARY SOURCE: the Sales Order Item's own
                # "stock_reserved_qty" field. This is maintained
                # automatically by Frappe per SO Item row whenever a Stock
                # Reservation Entry is created/cancelled against it, so it
                # is already correct on a per-line basis even when two SO
                # Item rows share the same item_code + warehouse (e.g. two
                # different lengths of the same section). Re-deriving this
                # from Stock Reservation Entry by item_code/warehouse (the
                # old approach) lumps such rows together and was giving
                # identical, wrong clearance on every line.
                clearence = flt(soi.stock_reserved_qty)

                if not clearence:
                    # Fallback only if stock_reserved_qty isn't populated
                    # (e.g. very old records): use the exact SO Item row
                    # match via voucher_detail_no. Do NOT fall back further
                    # to item_code/warehouse-only matching -- that strategy
                    # cannot distinguish between SO Item rows that share an
                    # item_code and is what caused the bleed-across-rows
                    # bug in the first place.
                    sre_rows = frappe.get_all(
                        "Stock Reservation Entry",
                        filters={
                            "voucher_type": "Sales Order",
                            "voucher_no": so.name,
                            "voucher_detail_no": soi.name,
                            "docstatus": ["in", [1, 2]]
                        },
                        fields=["reserved_qty", "delivered_qty"]
                    )
                    clearence = sum(flt(sre.reserved_qty) for sre in sre_rows)

                # ===================================
                # AFTER CLR (REJECTED) - Stock Transfer to Rejected Warehouse
                # ===================================
                # Flow: Stock Transfer -> transfer_item -> source_document_name (Stock Entry) -> work_order -> sales_order
                after_clr_rejected = 0

                if wo_names:
                    # Get all Stock Entries linked to these Work Orders
                    stock_entries = frappe.get_all(
                        "Stock Entry",
                        filters={
                            "work_order": ["in", wo_names],
                            "docstatus": 1
                        },
                        fields=["name"]
                    )
                    se_names = [se.name for se in stock_entries]

                    if se_names:
                        # Get Stock Transfers that reference these Stock Entries
                        # and transfer to a rejected warehouse
                        stock_transfers = frappe.get_all(
                            "Stock Transfer",
                            filters={
                                "docstatus": 1,
                                "target_warehouse": ["!=", ""]
                            },
                            fields=["name", "target_warehouse"]
                        )

                        for st in stock_transfers:
                            # Check if target warehouse is rejected warehouse
                            is_rejected = frappe.db.get_value(
                                "Warehouse",
                                st.target_warehouse,
                                "is_rejected_warehouse"
                            )

                            if is_rejected:
                                # Get transfer items that match our item and source Stock Entry
                                st_items = frappe.get_all(
                                    "Stock Transfer Item",
                                    filters={
                                        "parent": st.name,
                                        "item_code": soi.item_code,
                                        "source_document_type": "Stock Entry",
                                        "source_document_name": ["in", se_names]
                                    },
                                    fields=["qty"]
                                )

                                for sti in st_items:
                                    after_clr_rejected += flt(sti.qty)

            # ===================================
            # TRADING ITEMS (is_manufacture = 0)
            # ===================================
            else:
                # For trading items, no Work Orders exist
                total_pcs = flt(soi.pieces)
                total_weight = flt(soi.qty)

                # Ready PC / Ready Weight from Purchase Receipt
                # ONLY if PR warehouse == SO Item warehouse
                pr_items = frappe.get_all(
                    "Purchase Receipt Item",
                    filters={
                        "sales_order": so.name,
                        "sales_order_item": soi.name,
                        "warehouse": soi.warehouse,
                        "docstatus": 1
                    },
                    fields=["qty", "pieces", "received_qty"]
                )

                ready_pc = sum(flt(pr.pieces) for pr in pr_items)
                ready_weight = sum(flt(pr.qty) for pr in pr_items)

                # Clearance from Purchase Receipt qty (only if warehouse matches)
                clearence = ready_weight

                # For trading items, no rejected warehouse logic
                after_clr_rejected = 0

            # -----------------------------------
            # FORMULAS FOR CALCULATED FIELDS
            # -----------------------------------

            # Pending to Ready PC = Total PCS - Ready PC
            pending_ready_pc = total_pcs - ready_pc

            # Pending to Ready Weight = Total Weight - Ready Weight
            pending_ready_weight = total_weight - ready_weight

            # After MFG = Ready Weight - Clearence - After CLR (Rejected)
            after_mfg = ready_weight - clearence - after_clr_rejected

            # Pending CLR = max(0, After MFG) -- treat negative as 0
            pending_clr = max(0, after_mfg)

            # -----------------------------------
            # GRADE & SECTION
            # -----------------------------------
            grade, section = get_grade_and_section(
                soi.item_code,
                soi.item_name
            )

            # -----------------------------------
            # SALES INVOICE (DISPATCH)
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
            # BALANCE
            # -----------------------------------
            balance_pcs = total_pcs - dispatch_pcs
            balance_weight = total_weight - dispatch_weight

            # RFD = Clearence - Dispatch Weight
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
                "customer": so.customer,
                "party_name": so.customer_name,
                "sales_order": so.name,
                "grade": grade,
                "po_no": so.po_no,
                "section": section,
                "length": soi.length_size,
                "pcs": total_pcs,
                "assorted_length": soi.assorted_length,
                "total_weight": total_weight,
                "ready_pc": ready_pc,
                "ready_weight": ready_weight,
                "pending_ready_pc": pending_ready_pc,
                "pending_ready_weight": pending_ready_weight,
                "clearence": clearence,
                "after_mfg": after_mfg,
                "pending_clr": pending_clr,
                "after_clr_rejected": after_clr_rejected,
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