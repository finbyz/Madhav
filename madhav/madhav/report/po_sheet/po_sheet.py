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


def get_current_warehouse_from_sle(sle_entries):
    for sle in sle_entries:
        if flt(sle.qty_after_transaction) > 0:
            return sle.warehouse
    return ""


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

                    for sre in sre_rows:
                        try:
                            sre_doc = frappe.get_doc("Stock Reservation Entry", sre.name)
                            if hasattr(sre_doc, "sb_entries"):
                                for sb in sre_doc.sb_entries:
                                    wh = sb.warehouse or sre.warehouse or ""
                                    if wh not in sre_qty_by_warehouse:
                                        sre_qty_by_warehouse[wh] = 0
                                    sre_qty_by_warehouse[wh] += flt(sb.qty)
                        except Exception:
                            continue

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
                # CURRENT WAREHOUSE (clean: only positive balance, no qty)
                # -----------------------------------
                pwo_warehouse_map = {}
                current_warehouses = set()

                for pwo in matching_pwo_rows:
                    batch_no = pwo_batch_map.get(pwo.name)

                    if not batch_no:
                        if pwo.target_warehouse:
                            pwo_warehouse_map[pwo.name] = pwo.target_warehouse
                            current_warehouses.add(pwo.target_warehouse)
                        continue

                    sle_entries = get_sle_by_batch(soi.item_code, batch_no)
                    current_wh = get_current_warehouse_from_sle(sle_entries)

                    if current_wh:
                        pwo_warehouse_map[pwo.name] = current_wh
                        current_warehouses.add(current_wh)
                    elif pwo.target_warehouse:
                        pwo_warehouse_map[pwo.name] = pwo.target_warehouse
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
                # NEW LOGIC: Calculate after_clr_rejected for Trading
                # Check each batch's current warehouse for rejected warehouse
                # ============================================
                after_clr_rejected = 0
                pr_rejected_qty_map = {}  # Track rejected qty per PR item
                
                for pr in pr_items:
                    batch_no = pr.batch_no or ""
                    pr_qty = flt(pr.qty)
                    
                    if not batch_no or pr_qty <= 0:
                        pr_rejected_qty_map[pr.name] = 0
                        continue
                    
                    # Get current warehouse for this batch
                    sle_entries = get_sle_by_batch(soi.item_code, batch_no)
                    current_wh = get_current_warehouse_from_sle(sle_entries)
                    
                    # If no SLE found, fall back to PR warehouse
                    if not current_wh:
                        current_wh = pr.warehouse or ""
                    
                    # Check if current warehouse is a rejected warehouse
                    if is_rejected_warehouse(current_wh):
                        pr_rejected_qty_map[pr.name] = pr_qty
                        after_clr_rejected += pr_qty
                    else:
                        pr_rejected_qty_map[pr.name] = 0
                
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
                # CURRENT WAREHOUSE (clean: only positive balance, no qty)
                # -----------------------------------
                current_warehouses = set()

                for batch in set(all_batches):
                    if not batch:
                        continue

                    sle_entries = get_sle_by_batch(soi.item_code, batch)
                    current_wh = get_current_warehouse_from_sle(sle_entries)

                    if current_wh:
                        current_warehouses.add(current_wh)

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
                for pwo in matching_pwo_rows:
                    pwo_batch_no = pwo_batch_map.get(pwo.name, "")
                    pwo_new_length = pwo_length_map.get(pwo.name, "")
                    wh_current = pwo_warehouse_map.get(pwo.name, "")
                    wh_target = pwo.target_warehouse or ""

                    # ============================================
                    # NEW LOGIC: Check if batch is in rejected warehouse
                    # ============================================
                    pwo_after_clr_rejected = 0
                    pwo_clearence = 0
                    pwo_pending_clr = 0
                    
                    # Check if current warehouse is a rejected warehouse
                    is_batch_in_rejected_wh = is_rejected_warehouse(wh_current)
                    
                    if is_batch_in_rejected_wh:
                        # If batch is in rejected warehouse, 
                        # entire ready qty goes to "After CLR (Rejected)"
                        pwo_after_clr_rejected = flt(pwo.ready_qty)
                        pwo_clearence = 0
                        pwo_pending_clr = 0
                    else:
                        # Normal calculation - batch is NOT in rejected warehouse
                        if wh_current == soi.warehouse:
                            reserved_qty = sre_qty_by_warehouse.get(soi.warehouse, clearence)
                            pwo_clearence = min(reserved_qty, flt(pwo.ready_qty))
                        else:
                            pwo_clearence = 0
                        
                        # Pending CLR = Ready Weight - Clearence
                        pwo_pending_clr = max(0, flt(pwo.ready_qty) - pwo_clearence)

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
                        "warehouse": wh_current,
                    })
            else:
                display_new_length = new_length_val if show_batch_wise_flag else ""
                display_batch_no = batch_no_val if show_batch_wise_flag else ""

                if soi.is_manufacture:
                    filtered_clearence = 0
                    if soi.warehouse and sre_qty_by_warehouse:
                        filtered_clearence = sre_qty_by_warehouse.get(soi.warehouse, 0)
                    elif soi.warehouse and clearence:
                        matching_sre = [sre for sre in sre_rows if sre.warehouse == soi.warehouse]
                        filtered_clearence = sum(flt(sre.reserved_qty) for sre in matching_sre)
                    clearence = filtered_clearence
                else:
                    # ============================================
                    # TRADING: Calculate clearence for non-rejected stock only
                    # ============================================
                    filtered_clearence = 0
                    
                    # Get non-rejected ready weight
                    non_rejected_ready_weight = ready_weight - after_clr_rejected
                    
                    if soi.warehouse in current_warehouses:
                        # Check if SO warehouse is a rejected warehouse
                        if not is_rejected_warehouse(soi.warehouse):
                            filtered_clearence = min(
                                sre_qty_by_warehouse.get(soi.warehouse, 0),
                                non_rejected_ready_weight
                            )
                    
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