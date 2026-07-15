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
            "label": "SO Warehouse",
            "fieldname": "so_warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 180
        },
        {
            "label": "Length",
            "fieldname": "length",
            "fieldtype": "Data",
            "width": 90
        },
    ]

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
            "fieldtype": "Link",
            "options": "Batch",
            "width": 120
        })
        columns.append({
           "label": "Warehouse",
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
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


def get_sle_by_batch(item_code, batch_no):
    """
    Get Stock Ledger Entries for a batch.
    Handles ERPNext v15 where batch is in Serial and Batch Bundle.
    Returns list of SLE dicts with warehouse and qty_after_transaction.
    """
    sle_entries = []

    # v15 path: query via Serial and Batch Bundle
    sabb_entries = frappe.get_all(
        "Serial and Batch Entry",
        filters={
            "batch_no": batch_no,
            "docstatus": 1
        },
        fields=["parent"],
        order_by="creation DESC"
    )

    matching_sabb_names = list(set([e.parent for e in sabb_entries]))

    if matching_sabb_names:
        sle_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "item_code": item_code,
                "serial_and_batch_bundle": ["in", matching_sabb_names],
                "is_cancelled": 0
            },
            fields=["warehouse", "qty_after_transaction", "posting_date", "posting_time", "creation"],
            order_by="posting_date DESC, posting_time DESC, creation DESC"
        )

    # Fallback: direct batch_no (older ERPNext or if SABB returns nothing)
    if not sle_entries:
        sle_entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={
                "item_code": item_code,
                "batch_no": batch_no,
                "is_cancelled": 0
            },
            fields=["warehouse", "qty_after_transaction", "posting_date", "posting_time", "creation"],
            order_by="posting_date DESC, posting_time DESC, creation DESC"
        )

    return sle_entries


def get_warehouse_qty_map_from_sle(sle_entries):
    """
    Return {warehouse: current_positive_qty} for every warehouse that
    currently holds stock for this batch, based on the most recent SLE
    in EACH warehouse (not just the single most-recent SLE overall).
    A batch can legitimately be split across multiple warehouses
    (e.g. partly in Quality Inspection, partly in Finished Goods, partly
    in Rejected) at the same time.
    """
    latest_qty_by_warehouse = {}
    for sle in sle_entries:
        wh = sle.warehouse
        # sle_entries is sorted DESC, so the first time we see a warehouse
        # here is its most recent (i.e. current) entry.
        if wh not in latest_qty_by_warehouse:
            latest_qty_by_warehouse[wh] = flt(sle.qty_after_transaction)

    return {wh: qty for wh, qty in latest_qty_by_warehouse.items() if qty > 0}


def get_current_warehouses_from_sle(sle_entries):
    """
    Return ALL warehouses that currently hold a positive balance for this
    batch (sorted, names only -- for display purposes).
    """
    return sorted(get_warehouse_qty_map_from_sle(sle_entries).keys())


def get_current_warehouse_from_sle(sle_entries):
    """
    Backwards-compatible single-warehouse helper.
    Returns the primary (most recent) warehouse only.
    Kept for any other callers that still expect a single value.
    """
    current_whs = get_current_warehouses_from_sle(sle_entries)
    return current_whs[0] if current_whs else ""


def get_rejected_qty_from_warehouse_map(wh_qty_map):
    """
    Given {warehouse: qty}, sum the qty sitting specifically in
    warehouses flagged is_rejected_warehouse. This lets a batch that is
    split across warehouses count ONLY its rejected-warehouse portion
    toward 'After CLR (Rejected)', instead of treating the whole batch
    as rejected/not-rejected based on a single warehouse.
    """
    return sum(
        qty for wh, qty in wh_qty_map.items() if is_rejected_warehouse(wh)
    )


def is_rejected_warehouse(warehouse):
    """Check if warehouse is a rejected warehouse"""
    if not warehouse:
        return False
    return frappe.db.get_value("Warehouse", warehouse, "is_rejected_warehouse") or False


def get_data(filters):
    filters = filters or {}

    so_filters = {}

    if filters.get("sales_order"):
        so_filters["name"] = filters.get("sales_order")

    if filters.get("from_date") and filters.get("to_date"):
        so_filters["delivery_date"] = [
            "between",
            [filters.get("from_date"), filters.get("to_date")]
        ]
    elif filters.get("from_date"):
        so_filters["delivery_date"] = [">=", filters.get("from_date")]
    elif filters.get("to_date"):
        so_filters["delivery_date"] = ["<=", filters.get("to_date")]

    if filters.get("party_name"):
        customers = filters.get("party_name")
        if isinstance(customers, str):
            customers = frappe.parse_json(customers)
        so_filters["customer"] = ["in", customers]

    if filters.get("po_no"):
        so_filters["po_no"] = ["like", f"%{filters.get('po_no')}%"]

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=so_filters,
        fields=[
            "name", "customer", "customer_name", "po_no",
            "po_date", "delivery_date", "customer_address"
        ]
    )

    data = []
    item_filter = []

    if filters.get("item_code"):
        item_filter = filters.get("item_code")
        if isinstance(item_filter, str):
            item_filter = frappe.parse_json(item_filter)

    type_filter = filters.get("type")
    show_batch_wise_flag = filters.get("show_batch_wise")

    for so in sales_orders:

        so_item_filters = {"parent": so.name}
        if item_filter:
            so_item_filters["item_code"] = ["in", item_filter]

        so_items = frappe.get_all(
            "Sales Order Item",
            filters=so_item_filters,
            fields=[
                "name", "item_code", "item_name", "length_size",
                "qty", "pieces", "rate", "assorted_length",
                "is_manufacture", "warehouse", "stock_reserved_qty"
            ]
        )

        for soi in so_items:

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
            warehouse_display = ""

            # ===================================
            # MANUFACTURING ITEMS
            # ===================================
            if soi.is_manufacture:

                work_orders = frappe.get_all(
                    "Work Order",
                    filters={
                        "sales_order": so.name,
                        "production_item": soi.item_code,
                        "docstatus": 1
                    },
                    fields=["name", "qty", "pieces", "pending_pcs", "produced_qty"]
                )

                wo_names = [wo.name for wo in work_orders]

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
                        "name", "ready_pieces", "ready_qty", "sales_order",
                        "item", "item_name", "length_size", "pieces", "qty",
                        "target_warehouse", "stock_entry_reference", "work_order",
                        "variation", "old_sales_order"
                    ]
                )

                matching_pwo_rows = []
                for pwo in all_pwo_rows:
                    if pwo.item_name and soi.item_name and pwo.item_name != soi.item_name:
                        continue

                    is_direct_match = (
                        pwo.sales_order == so.name
                        and flt(pwo.variation) == 0
                        and flt(pwo.length_size) == flt(soi.length_size)
                    )
                    is_variation = (
                        (pwo.old_sales_order == so.name or pwo.sales_order == so.name)
                        and flt(pwo.variation) == 1
                    )

                    if is_direct_match or is_variation:
                        matching_pwo_rows.append(pwo)

                all_wo_names = list(set(
                    wo_names + [pwo.work_order for pwo in matching_pwo_rows if pwo.work_order]
                ))

                total_ready_pc = sum(flt(pwo.ready_pieces) for pwo in matching_pwo_rows)
                total_ready_weight = sum(flt(pwo.ready_qty) for pwo in matching_pwo_rows)

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

                sre_qty_by_warehouse = {}
                if sre_rows:
                    for sre in sre_rows:
                        wh = sre.warehouse or ""
                        if wh not in sre_qty_by_warehouse:
                            sre_qty_by_warehouse[wh] = 0
                        sre_qty_by_warehouse[wh] += flt(sre.reserved_qty)


                if all_wo_names:
                    stock_entries = frappe.get_all(
                        "Stock Entry",
                        filters={"work_order": ["in", all_wo_names], "docstatus": 1},
                        fields=["name"]
                    )
                    se_names = [se.name for se in stock_entries]

                    if se_names:
                        stock_transfers = frappe.get_all(
                            "Stock Transfer",
                            filters={"docstatus": 1, "target_warehouse": ["!=", ""]},
                            fields=["name", "target_warehouse"]
                        )

                        for st in stock_transfers:
                            is_rejected = frappe.db.get_value(
                                "Warehouse", st.target_warehouse, "is_rejected_warehouse"
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

                all_batches = []
                all_lengths = []
                pwo_batch_map = {}
                pwo_length_map = {}

                for pwo in matching_pwo_rows:
                    if pwo.stock_entry_reference:
                        se_items = frappe.get_all(
                            "Stock Entry Detail",
                            filters={
                                "parent": pwo.stock_entry_reference,
                                "item_code": soi.item_code,
                            },
                            fields=["batch_no", "length"],
                            limit=1
                        )
                        if se_items:
                            batch_no = se_items[0].batch_no or ""
                            length_val = ""
                            if se_items[0].length:
                                length_val = str(se_items[0].length)
                            elif batch_no:
                                batch_length = frappe.db.get_value("Batch", batch_no, "average_length")
                                length_val = str(batch_length) if batch_length else ""

                            if batch_no:
                                all_batches.append(batch_no)
                                pwo_batch_map[pwo.name] = batch_no
                            if length_val:
                                all_lengths.append(length_val)
                                pwo_length_map[pwo.name] = length_val

                batch_no_val = ", ".join(sorted(set(all_batches))) if all_batches else ""
                new_length_val = ", ".join(sorted(set(all_lengths))) if all_lengths else ""

                # -----------------------------------
                # CURRENT WAREHOUSE(S)
                # Each PWO row's batch may currently be split across
                # multiple warehouses -- keep the FULL list for display,
                # and a "primary" (first) warehouse for the existing
                # rejected/reservation matching logic below.
                # -----------------------------------
                pwo_warehouse_map = {}
                pwo_warehouse_qty_map = {}
                current_warehouses = set()

                for pwo in matching_pwo_rows:
                    batch_no = pwo_batch_map.get(pwo.name)

                    if not batch_no:
                        if pwo.target_warehouse:
                            pwo_warehouse_map[pwo.name] = [pwo.target_warehouse]
                            current_warehouses.add(pwo.target_warehouse)
                        continue

                    sle_entries = get_sle_by_batch(soi.item_code, batch_no)
                    wh_qty_map = get_warehouse_qty_map_from_sle(sle_entries)
                    current_whs = sorted(wh_qty_map.keys())

                    if current_whs:
                        pwo_warehouse_map[pwo.name] = current_whs
                        pwo_warehouse_qty_map[pwo.name] = wh_qty_map
                        current_warehouses.update(current_whs)
                    elif pwo.target_warehouse:
                        pwo_warehouse_map[pwo.name] = [pwo.target_warehouse]
                        current_warehouses.add(pwo.target_warehouse)

                warehouse_display = ", ".join(sorted(current_warehouses)) if current_warehouses else ""

            # ===================================
            # TRADING ITEMS
            # ===================================
            else:
                pr_items = frappe.get_all(
                    "Purchase Receipt Item",
                    filters={
                        "sales_order": so.name,
                        "sales_order_item": soi.name,
                        "docstatus": 1
                    },
                    fields=[
                        "name", "qty", "pieces", "received_qty",
                        "batch_no", "warehouse", "length_size_inch", "average_length"
                    ]
                )

                ready_pc = sum(flt(pr.pieces) for pr in pr_items)
                ready_weight = sum(flt(pr.qty) for pr in pr_items)

                # ============================================
                # Calculate after_clr_rejected for Trading
                # Check each batch's current (primary) warehouse for
                # rejected warehouse. Also collect ALL current
                # warehouses per batch for the display column.
                # ============================================
                after_clr_rejected = 0
                pr_rejected_qty_map = {}  # Track rejected qty per PR item
                pr_current_warehouses_map = {}  # Full warehouse list per PR item (for display)

                for pr in pr_items:
                    batch_no = pr.batch_no or ""
                    pr_qty = flt(pr.qty)

                    if not batch_no or pr_qty <= 0:
                        pr_rejected_qty_map[pr.name] = 0
                        continue

                    # Get qty currently sitting in EACH warehouse for this batch
                    sle_entries = get_sle_by_batch(soi.item_code, batch_no)
                    wh_qty_map = get_warehouse_qty_map_from_sle(sle_entries)
                    current_whs = sorted(wh_qty_map.keys())

                    if current_whs:
                        pr_current_warehouses_map[pr.name] = current_whs
                    elif pr.warehouse:
                        pr_current_warehouses_map[pr.name] = [pr.warehouse]

                    if wh_qty_map:
                        # Sum only the qty sitting in warehouses that have
                        # is_rejected_warehouse ticked -- a batch split
                        # across warehouses only counts its rejected
                        # portion here, not the whole batch.
                        rejected_qty = get_rejected_qty_from_warehouse_map(wh_qty_map)
                        # Can't exceed what this PR line represents
                        rejected_qty = min(rejected_qty, pr_qty)
                    else:
                        # No SLE found -- fall back to the PR's own warehouse
                        rejected_qty = pr_qty if is_rejected_warehouse(pr.warehouse or "") else 0

                    pr_rejected_qty_map[pr.name] = rejected_qty
                    after_clr_rejected += rejected_qty

                # Clearence should only be for non-rejected stock
                clearence = ready_weight - after_clr_rejected

                sre_rows = frappe.get_all(
                    "Stock Reservation Entry",
                    filters={
                        "voucher_type": "Sales Order",
                        "voucher_no": so.name,
                        "voucher_detail_no": soi.name,
                        "docstatus": ["in", [1, 2]]
                    },
                    fields=["name", "reserved_qty", "warehouse"]
                )

                sre_qty_by_warehouse = {}

                for sre in sre_rows:
                    wh = sre.warehouse or ""
                    sre_qty_by_warehouse[wh] = sre_qty_by_warehouse.get(wh, 0) + flt(sre.reserved_qty)

                    try:
                        sre_doc = frappe.get_doc("Stock Reservation Entry", sre.name)
                        if hasattr(sre_doc, "sb_entries"):
                            for sb in sre_doc.sb_entries:
                                wh = sb.warehouse or wh
                                sre_qty_by_warehouse[wh] = (
                                    sre_qty_by_warehouse.get(wh, 0) + flt(sb.qty)
                                )
                    except Exception:
                        pass

                all_batches = []
                all_lengths = []
                pr_batch_map = {}
                pr_length_map = {}
                pr_warehouse_map = {}

                for pr in pr_items:
                    batch_no = pr.batch_no or ""
                    length_val = ""

                    if pr.average_length:
                        length_val = str(pr.average_length)
                    elif batch_no:
                        batch_length = frappe.db.get_value("Batch", batch_no, "average_length")
                        length_val = str(batch_length) if batch_length else ""

                    if batch_no:
                        all_batches.append(batch_no)
                        pr_batch_map[pr.name] = batch_no
                    if length_val:
                        all_lengths.append(length_val)
                        pr_length_map[pr.name] = length_val
                    if pr.warehouse:
                        pr_warehouse_map[pr.name] = pr.warehouse

                batch_no_val = ", ".join(sorted(set(all_batches))) if all_batches else ""
                new_length_val = ", ".join(sorted(set(all_lengths))) if all_lengths else ""

                # -----------------------------------
                # CURRENT WAREHOUSE(S) -- show every warehouse the
                # batch(es) currently sit in, not just one.
                # -----------------------------------
                current_warehouses = set()

                for batch in set(all_batches):
                    if not batch:
                        continue

                    sle_entries = get_sle_by_batch(soi.item_code, batch)
                    current_whs = get_current_warehouses_from_sle(sle_entries)

                    if current_whs:
                        current_warehouses.update(current_whs)

                if current_warehouses:
                    warehouse_display = ", ".join(sorted(current_warehouses))
                elif pr_warehouse_map:
                    warehouse_display = ", ".join(sorted(set(pr_warehouse_map.values())))
                else:
                    warehouse_display = ""

            # -----------------------------------
            # FORMULAS
            # -----------------------------------
            pending_ready_pc = total_pcs - ready_pc
            after_mfg = max(0, total_weight - ready_weight)
            pending_ready_weight = after_mfg + after_clr_rejected
            pending_clr = max(
                    0,
                    ready_weight - clearence - after_clr_rejected
                )

            grade, section = get_grade_and_section(soi.item_code, soi.item_name)

            si_items = frappe.get_all(
                "Sales Invoice Item",
                filters={"sales_order": so.name, "item_code": soi.item_code},
                fields=["qty", "pieces"]
            )

            dispatch_pcs = sum(flt(d.pieces) for d in si_items)
            dispatch_weight = sum(flt(d.qty) for d in si_items)

            balance_pcs = total_pcs - dispatch_pcs
            balance_weight = total_weight - dispatch_weight

            location = ""
            if so.customer_address:
                location = frappe.db.get_value("Address", so.customer_address, "city") or ""

            # -----------------------------------
            # APPEND DATA
            # -----------------------------------
            if soi.is_manufacture and show_batch_wise_flag and matching_pwo_rows:

                # ============================================
                # DIAGNOSTIC: Show warehouse mismatch
                # ============================================
                frappe.msgprint({
                    "SO Warehouse": soi.warehouse,
                    "Reserved Map": str(sre_qty_by_warehouse),
                    "PWO Warehouse Map": str(pwo_warehouse_map)
                })

                # ============================================
                # FIX: Track remaining reserved qty per ACTUAL
                # (primary) warehouse, not per soi.warehouse.
                # Each PWO row may sit in a different warehouse
                # than what the SO line says.
                # ============================================
                remaining_reserved_by_wh = dict(sre_qty_by_warehouse)

                for pwo in matching_pwo_rows:
                    pwo_batch_no = pwo_batch_map.get(pwo.name, "")
                    pwo_new_length = pwo_length_map.get(pwo.name, "")

                    wh_current_list = pwo_warehouse_map.get(pwo.name, [])
                    wh_qty_map = pwo_warehouse_qty_map.get(pwo.name, {})
                    # Primary warehouse (most recent) drives the reservation
                    # lookup below when some of the batch remains clearable.
                    wh_current = wh_current_list[0] if wh_current_list else ""
                    # Display value shows EVERY warehouse the batch
                    # currently sits in.
                    wh_display = ", ".join(wh_current_list) if wh_current_list else ""

                    wh_target = pwo.target_warehouse or ""
                    ready_qty = flt(pwo.ready_qty)

                    # ============================================
                    # Sum only the qty sitting in warehouses that have
                    # is_rejected_warehouse ticked, instead of treating
                    # the whole ready_qty as rejected/not based on a
                    # single warehouse.
                    # ============================================
                    pwo_clearence = 0
                    pwo_pending_clr = 0

                    if wh_qty_map:
                        pwo_after_clr_rejected = min(
                            get_rejected_qty_from_warehouse_map(wh_qty_map), ready_qty
                        )
                    else:
                        pwo_after_clr_rejected = ready_qty if is_rejected_warehouse(wh_current) else 0

                    remaining_ready_qty = max(0, ready_qty - pwo_after_clr_rejected)

                    if remaining_ready_qty <= 0:
                        pwo_clearence = 0
                        pwo_pending_clr = 0
                    else:
                        # Use the first non-rejected warehouse for the
                        # reservation lookup (falls back to the primary
                        # warehouse if all are rejected, or none found).
                        non_rejected_wh = next(
                            (wh for wh in wh_current_list if not is_rejected_warehouse(wh)),
                            wh_current
                        )

                        # ============================================
                        # FIX: Look up reservation using the batch's
                        # actual (non-rejected) warehouse, NOT soi.warehouse
                        # (which may be a different warehouse like Stores).
                        # Also fall back to soi.warehouse if no match found.
                        # ============================================
                        reserved_for_this_wh = remaining_reserved_by_wh.get(non_rejected_wh, 0)

                        # Fallback: if no reservation found for actual warehouse,
                        # try the SO warehouse
                        if not reserved_for_this_wh and non_rejected_wh != soi.warehouse:
                            reserved_for_this_wh = remaining_reserved_by_wh.get(soi.warehouse, 0)

                        pwo_clearence = min(reserved_for_this_wh, remaining_ready_qty)

                        # Deduct from the warehouse we actually used for lookup
                        used_wh = non_rejected_wh if remaining_reserved_by_wh.get(non_rejected_wh, 0) > 0 else soi.warehouse
                        remaining_reserved_by_wh[used_wh] = max(
                            0, remaining_reserved_by_wh.get(used_wh, 0) - pwo_clearence
                        )

                        pwo_pending_clr = max(0, remaining_ready_qty - pwo_clearence)

                    data.append({
                        "customer": so.customer,
                        "party_name": so.customer_name,
                        "sales_order": so.name,
                        "grade": grade,
                        "po_no": so.po_no,
                        "section": section,
                        "so_warehouse": soi.warehouse,
                        "length": soi.length_size,
                        "new_length": pwo_new_length,
                        "batch_no": pwo_batch_no,
                        "pcs": total_pcs,
                        "assorted_length": soi.assorted_length,
                        "total_weight": total_weight,
                        "ready_pc": flt(pwo.ready_pieces),
                        "ready_weight": flt(pwo.ready_qty),
                        "pending_ready_pc": total_pcs - flt(pwo.ready_pieces),
                        "pending_ready_weight": max(0, total_weight - flt(pwo.ready_qty)) + pwo_after_clr_rejected,
                        "clearence": pwo_clearence,
                        "after_mfg": max(0, total_weight - flt(pwo.ready_qty)),
                        "pending_clr": pwo_pending_clr,
                        "after_clr_rejected": pwo_after_clr_rejected,
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
                        "warehouse": wh_display,
                    })
            else:
                display_new_length = new_length_val if show_batch_wise_flag else ""
                display_batch_no = batch_no_val if show_batch_wise_flag else ""

                if soi.is_manufacture:
                    filtered_clearence = 0
                    # ============================================
                    # FIX: Try SO warehouse first, then try actual
                    # current warehouses (where batches actually sit)
                    # ============================================
                    if sre_qty_by_warehouse:
                        filtered_clearence = sre_qty_by_warehouse.get(soi.warehouse, 0)

                    # If no match on SO warehouse, sum reservations
                    # from all actual current warehouses
                    if not filtered_clearence and current_warehouses:
                        for wh in current_warehouses:
                            filtered_clearence += sre_qty_by_warehouse.get(wh, 0)

                    # Last fallback: sum all reservations if still zero
                    if not filtered_clearence and sre_qty_by_warehouse:
                        filtered_clearence = sum(sre_qty_by_warehouse.values())

                    clearence = filtered_clearence
                else:
                    # ============================================
                    # TRADING: Calculate clearence for non-rejected stock only
                    # ============================================
                    filtered_clearence = 0

                    # Get non-rejected ready weight
                    non_rejected_ready_weight = ready_weight - after_clr_rejected

                    # Try SO warehouse first
                    if soi.warehouse and sre_qty_by_warehouse:
                        if not is_rejected_warehouse(soi.warehouse):
                            filtered_clearence = min(
                                sre_qty_by_warehouse.get(soi.warehouse, 0),
                                non_rejected_ready_weight
                            )

                    # Fallback: try actual current warehouses
                    if not filtered_clearence and current_warehouses and sre_qty_by_warehouse:
                        for wh in current_warehouses:
                            if not is_rejected_warehouse(wh):
                                wh_reserved = sre_qty_by_warehouse.get(wh, 0)
                                filtered_clearence += min(wh_reserved, non_rejected_ready_weight - filtered_clearence)

                    clearence = filtered_clearence

                    # Recalculate pending_clr with updated clearence
                    pending_clr = max(0, non_rejected_ready_weight - clearence)

                data.append({
                    "customer": so.customer,
                    "party_name": so.customer_name,
                    "sales_order": so.name,
                    "grade": grade,
                    "po_no": so.po_no,
                    "section": section,
                    "so_warehouse": soi.warehouse,
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
                    "warehouse": warehouse_display,
                })

    return data


def get_grade_and_section(item_code, item_name):
    if not item_code:
        return "", ""

    grade = ""
    attributes = frappe.get_all(
        "Item Variant Attribute",
        filters={"parent": item_code, "attribute": "Grade"},
        fields=["attribute_value"],
        limit=1
    )
    if attributes:
        grade = attributes[0].attribute_value or ""

    section = item_name or ""
    if grade and grade in section:
        section = section.replace(grade, "").strip()

    return grade, section