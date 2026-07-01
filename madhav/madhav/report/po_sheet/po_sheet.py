import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


def get_columns(filters=None):
    filters = filters or {}
    show_batch_wise_flag = filters.get("show_batch_wise")

    columns = [
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
    ]

    # New Length / Batch No columns are only shown when "Show Batch Wise" is ticked
    if show_batch_wise_flag:
        columns.append({
            "label": "New Length",
            "fieldname": "new_length",
            "fieldtype": "Data",
            "width": 100
        })
        columns.append({
            "label": "Batch No",
            "fieldname": "batch_no",
            "fieldtype": "Data",
            "width": 120
        })

    columns += [
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

    return columns


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
    show_batch_wise_flag = filters.get("show_batch_wise")

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

            total_pcs = flt(soi.pieces)
            total_weight = flt(soi.qty)
            ready_pc = 0
            ready_weight = 0
            clearence = 0
            after_clr_rejected = 0
            new_length_val = ""
            batch_no_val = ""

            # ===================================
            # MANUFACTURING ITEMS (is_manufacture = 1)
            # ===================================
            if soi.is_manufacture:

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

                wo_names = [wo.name for wo in work_orders]

                # -----------------------------------
                # FETCH ALL PWOS FOR THIS SO ITEM (INCLUDING VARIATIONS)
                # Use or_filters for OR condition between sales_order and old_sales_order
                # -----------------------------------
                pwo_base_filters = [
                    ["item", "=", soi.item_code],
                    ["docstatus", "=", 1]
                ]

                pwo_or_filters = [
                    ["sales_order", "=", so.name],
                    ["old_sales_order", "=", so.name]
                ]

                all_pwo_rows = frappe.get_all(
                    "Pending Work Orders",
                    filters=pwo_base_filters,
                    or_filters=pwo_or_filters,
                    fields=[
                        "name",
                        "ready_pieces",
                        "ready_qty",
                        "sales_order",
                        "item",
                        "item_name",
                        "length_size",
                        "pieces",
                        "qty",
                        "target_warehouse",
                        "stock_entry_reference",
                        "work_order",
                        "variation",
                        "old_sales_order"
                    ]
                )

                # Filter PWOs to only those matching this SO item
                matching_pwo_rows = []
                for pwo in all_pwo_rows:
                    # Filter by item_name if both exist and differ
                    if pwo.item_name and soi.item_name and pwo.item_name != soi.item_name:
                        continue

                    # A PWO matches this SO item if:
                    # 1. It's a direct match (same SO, same length, not a variation)
                    # 2. It's a variation (old_sales_order matches, variation=1)
                    is_direct_match = (
                        pwo.sales_order == so.name
                        and flt(pwo.variation) == 0
                        and flt(pwo.length_size) == flt(soi.length_size)
                    )
                    is_variation = (
                        pwo.old_sales_order == so.name
                        and flt(pwo.variation) == 1
                    )

                    if is_direct_match or is_variation:
                        matching_pwo_rows.append(pwo)

                # -----------------------------------
                # ACTIVE (STILL PENDING) PWO ROWS
                # A PWO whose linked Work Order has already been fully
                # completed (pending_pcs <= 0) is no longer "pending" — it
                # has already been produced/reserved/dispatched and should
                # not show up as its own extra row in the batch-wise
                # breakdown. It is still counted in the aggregate totals
                # below (Ready PC / Ready Weight), just not split out as a
                # separate completed row.
                # -----------------------------------
                wo_pending_map = {wo.name: flt(wo.pending_pcs) for wo in work_orders}

                active_pwo_rows = [
                    pwo for pwo in matching_pwo_rows
                    if not pwo.work_order or wo_pending_map.get(pwo.work_order, 0) > 0
                ]

                # All WO names (from original fetch + from matching PWOs)
                all_wo_names = list(set(
                    wo_names + [pwo.work_order for pwo in matching_pwo_rows if pwo.work_order]
                ))

                # -----------------------------------
                # TOTALS FROM MATCHING PWOS
                # -----------------------------------
                total_ready_pc = sum(flt(pwo.ready_pieces) for pwo in matching_pwo_rows)
                total_ready_weight = sum(flt(pwo.ready_qty) for pwo in matching_pwo_rows)


                # -----------------------------------
                # CLEARANCE / STOCK RESERVATION
                # -----------------------------------
                clearence = flt(soi.stock_reserved_qty)

                sre_rows = frappe.get_all(
                    "Stock Reservation Entry",
                    filters={
                        "voucher_type": "Sales Order",
                        "voucher_no": so.name,
                        "voucher_detail_no": soi.name,
                        "docstatus": ["in", [1, 2]]
                    },
                    fields=["name", "reserved_qty", "delivered_qty", "warehouse"]
                )

                if not clearence:
                    clearence = sum(flt(sre.reserved_qty) for sre in sre_rows)

                # -----------------------------------
                # FETCH BATCH NOS + LENGTHS FROM SRE CHILD TABLE (sb_entries)
                # New Length comes directly from the batch's own length
                # (sb_entries.length), not from the PWO variation flag.
                # -----------------------------------
                sre_batches_by_warehouse = {}
                sre_qty_by_warehouse = {}
                sre_lengths_by_warehouse = {}

                if sre_rows:
                    # Initialize warehouse mappings from parent SRE
                    for sre in sre_rows:
                        wh = sre.warehouse or ""
                        if wh not in sre_batches_by_warehouse:
                            sre_batches_by_warehouse[wh] = []
                            sre_qty_by_warehouse[wh] = 0
                            sre_lengths_by_warehouse[wh] = []
                        sre_qty_by_warehouse[wh] += flt(sre.reserved_qty)

                    # Fetch child table entries via get_doc for reliability
                    for sre in sre_rows:
                        try:
                            sre_doc = frappe.get_doc("Stock Reservation Entry", sre.name)
                            if hasattr(sre_doc, "sb_entries"):
                                for sb in sre_doc.sb_entries:
                                    wh = sb.warehouse or sre.warehouse or ""
                                    if wh not in sre_batches_by_warehouse:
                                        sre_batches_by_warehouse[wh] = []
                                        sre_qty_by_warehouse[wh] = 0
                                        sre_lengths_by_warehouse[wh] = []
                                    if sb.batch_no:
                                        sre_batches_by_warehouse[wh].append(sb.batch_no)
                                    if sb.length:
                                        sre_lengths_by_warehouse[wh].append(sb.length)
                                    sre_qty_by_warehouse[wh] += flt(sb.qty)
                        except Exception:
                            continue

                # ===================================
                # AFTER CLR (REJECTED)
                # ===================================
                if all_wo_names:
                    stock_entries = frappe.get_all(
                        "Stock Entry",
                        filters={
                            "work_order": ["in", all_wo_names],
                            "docstatus": 1
                        },
                        fields=["name"]
                    )
                    se_names = [se.name for se in stock_entries]

                    if se_names:
                        stock_transfers = frappe.get_all(
                            "Stock Transfer",
                            filters={
                                "docstatus": 1,
                                "target_warehouse": ["!=", ""]
                            },
                            fields=["name", "target_warehouse"]
                        )

                        for st in stock_transfers:
                            is_rejected = frappe.db.get_value(
                                "Warehouse",
                                st.target_warehouse,
                                "is_rejected_warehouse"
                            )

                            if is_rejected:
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

                ready_pc = total_ready_pc
                ready_weight = total_ready_weight

                # -----------------------------------
                # NEW LENGTH: pulled directly from the batch
                # (distinct lengths recorded on sb_entries), not from PWO variation
                # -----------------------------------
                all_lengths = []
                for lengths in sre_lengths_by_warehouse.values():
                    all_lengths.extend(lengths)
                new_length_val = ", ".join(
                    sorted(set(str(l) for l in all_lengths))
                ) if all_lengths else ""

                all_batches = []
                for batches in sre_batches_by_warehouse.values():
                    all_batches.extend(batches)
                batch_no_val = ", ".join(list(set(all_batches))) if all_batches else ""

            # ===================================
            # TRADING ITEMS (is_manufacture = 0)
            # ===================================
            else:
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

                clearence = ready_weight

                after_clr_rejected = 0

            # -----------------------------------
            # FORMULAS FOR CALCULATED FIELDS
            # -----------------------------------

            pending_ready_pc = total_pcs - ready_pc
            after_mfg = max(0, total_weight - ready_weight)
            pending_ready_weight = after_mfg + after_clr_rejected
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
            if soi.is_manufacture and show_batch_wise_flag and active_pwo_rows:
                # Batch-wise view: one row per still-pending (not yet fully
                # completed) PWO
                for pwo in active_pwo_rows:
                    wh = pwo.target_warehouse or ""
                    batches = sre_batches_by_warehouse.get(wh, [])
                    pwo_batch_no = ", ".join(batches) if batches else ""
                    pwo_clearence = sre_qty_by_warehouse.get(wh, clearence)

                    # New Length per row: directly from the batch's own
                    # length recorded for this warehouse, not PWO variation
                    pwo_lengths = sre_lengths_by_warehouse.get(wh, [])
                    pwo_new_length = ", ".join(
                        sorted(set(str(l) for l in pwo_lengths))
                    ) if pwo_lengths else ""

                    data.append({
                        "customer": so.customer,
                        "party_name": so.customer_name,
                        "sales_order": so.name,
                        "grade": grade,
                        "po_no": so.po_no,
                        "section": section,
                        "length": soi.length_size,
                        "new_length": pwo_new_length,
                        "batch_no": pwo_batch_no,
                        "pcs": total_pcs,
                        "assorted_length": soi.assorted_length,
                        "total_weight": total_weight,
                        "ready_pc": flt(pwo.ready_pieces),
                        "ready_weight": flt(pwo.ready_qty),
                        "pending_ready_pc": total_pcs - flt(pwo.ready_pieces),
                        "pending_ready_weight": max(0, total_weight - flt(pwo.ready_qty)) + after_clr_rejected,
                        "clearence": pwo_clearence,
                        "after_mfg": max(0, total_weight - flt(pwo.ready_qty)),
                        "pending_clr": max(0, total_weight - flt(pwo.ready_qty)),
                        "after_clr_rejected": after_clr_rejected,
                        "dispatch_pcs": dispatch_pcs,
                        "dispatch_weight": dispatch_weight,
                        "balance_pcs": total_pcs - dispatch_pcs,
                        "balance_weight": total_weight - dispatch_weight,
                        "rfd": pwo_clearence - dispatch_weight,
                        "po_date": so.po_date,
                        "item_code": soi.item_code,
                        "delivery_date": so.delivery_date,
                        "rate": soi.rate,
                        "location": location,
                    })
            else:
                # Normal aggregated view
                # New Length / Batch No are only shown when "show_batch_wise"
                # is ticked; otherwise leave them blank.
                display_new_length = new_length_val if show_batch_wise_flag else ""
                display_batch_no = batch_no_val if show_batch_wise_flag else ""

                data.append({
                    "customer": so.customer,
                    "party_name": so.customer_name,
                    "sales_order": so.name,
                    "grade": grade,
                    "po_no": so.po_no,
                    "section": section,
                    "length": soi.length_size,
                    "new_length": display_new_length,
                    "batch_no": display_batch_no,
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
                    "rfd": clearence - dispatch_weight,
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