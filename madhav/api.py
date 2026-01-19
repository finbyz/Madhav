import frappe


@frappe.whitelist()
def get_so_item_pieces_and_length(so_detail: str):
	"""Return pieces, length_size and qty from Sales Order Item.

	This is used by the Delivery Note client script to safely fetch
	values without calling frappe.client.get_value from JS.
	"""
	if not so_detail:
		return {}

	pieces, length_size, qty = frappe.db.get_value(
		"Sales Order Item",
		so_detail,
		["pieces", "length_size", "qty"],
	) or (None, None, None)

	return {
		"pieces": pieces,
		"length_size": length_size,
		"qty": qty,
	}

import frappe

import frappe
from frappe.utils import get_datetime, get_datetime_str
from datetime import datetime, timedelta

@frappe.whitelist()
def get_employee_checkin_entries(employee, attendance_date):
    # Convert string to datetime and define start and end of the day
    start_date = get_datetime(attendance_date)
    end_date = start_date + timedelta(days=1)

    # Fetch first check-in (earliest)
    in_time_doc = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": employee,
            "time": ["between", [start_date, end_date]]
        },
        fields=["time"],
        order_by="time asc",
        limit_page_length=1
    )

    # Fetch last check-in (latest)
    out_time_doc = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": employee,
            "time": ["between", [start_date, end_date]]
        },
        fields=["time"],
        order_by="time desc",
        limit_page_length=1
    )

    return {
        "in_time": in_time_doc[0].time if in_time_doc else None,
        "out_time": out_time_doc[0].time if out_time_doc else None
    }

@frappe.whitelist()
def get_offday_status(employee, attendance_date,attendance):
    
    from datetime import datetime
    
    if isinstance(attendance_date, str):
        date_obj = datetime.strptime(attendance_date, "%Y-%m-%d").date()
    else:
        date_obj = attendance_date
    
    # Step 1: Check Holiday List
    holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
    if holiday_list:
        if frappe.db.exists("Holiday", {"holiday_date": date_obj, "parent": holiday_list}):
            holiday_doc = frappe.get_doc("Holiday List",holiday_list)

            for holiday in holiday_doc.holidays:
                if attendance:
                    if holiday.weekly_off:
                        frappe.db.set_value("Attendance", attendance, {
                        "status": "Weekly Off",
                        "leave_type": None
                        })
                        frappe.db.commit()
                        return "Weekly Off"
                    else:
                        frappe.db.set_value("Attendance", attendance, {
                            "status": "Holiday",
                            "leave_type": None
                            })
                        frappe.db.commit()
                        return "Holiday"            
    
    # Step 2: Check Shift Assignment for weekly off

    shift_assignment = frappe.get_all(
    "Shift Assignment",
    filters={
        "employee": employee,
        "start_date": ["<=", date_obj],
    },
    fields=["name", "shift_type", "off_day", "end_date"]
    )

    valid_shift_assignments = []

    for shift in shift_assignment:
        if not shift["end_date"] or shift["end_date"] >= date_obj:
            valid_shift_assignments.append(shift)

    if valid_shift_assignments:
        weekday = date_obj.strftime('%A')
        emp_offday = valid_shift_assignments[0]["off_day"]

        if weekday == emp_offday:
            if attendance:
                frappe.db.set_value("Attendance", attendance, {
                    "status": "Weekly Off",
                    "leave_type": None
                })
                frappe.db.commit()
            return "Weekly Off"

def custom_make_variant_item_code(template_item_code, template_item_name, variant):
    
    from frappe.utils import cstr
    import re
    
    """Uses template's item code and abbreviations to make variant's item code"""
    if variant.item_code:
        return
 
    abbreviations = []
    for attr in variant.attributes:
        item_attribute = frappe.db.sql(
            """select i.numeric_values, v.abbr
            from `tabItem Attribute` i left join `tabItem Attribute Value` v
                on (i.name=v.parent)
            where i.name=%(attribute)s and (v.attribute_value=%(attribute_value)s or i.numeric_values = 1)""",
            {"attribute": attr.attribute, "attribute_value": attr.attribute_value},
            as_dict=True,
        )
 
        if not item_attribute:
            continue
            # frappe.throw(_('Invalid attribute {0} {1}').format(frappe.bold(attr.attribute),
            #   frappe.bold(attr.attribute_value)), title=_('Invalid Attribute'),
            #   exc=InvalidItemAttributeValueError)
 
        abbr_or_value = (
            cstr(attr.attribute_value) if item_attribute[0].numeric_values else item_attribute[0].abbr
        )
        abbreviations.append(abbr_or_value)
 
    if abbreviations:
        # variant.item_code = "{}-{}".format(template_item_code, "-".join(abbreviations))
        variant.item_name = "{} {}".format(template_item_name, " ".join(abbreviations))
    
    # Use the same series used by standard items
    # item_series = frappe.get_meta("Item").get_field("naming_series").options.split("\n")[0]

    # from frappe.model.naming import make_autoname
    # variant.item_code = make_autoname(item_series)
    
    # Extract prefix and numeric part from template_item_code
    match = re.match(r"^([A-Z]+)(\d{5,6})$", template_item_code)
    
    if not match:
        frappe.throw("Template Item Code must be in the format PREFIX000001 (e.g., RM000001)")

    prefix, base_number = match.groups()
    base_number = int(base_number)
    
    # Get all items starting with this prefix
    existing_codes = frappe.get_all(
        "Item",
        filters={"item_code": ["like", f"{prefix}%"]},
        pluck="item_code"
    )

    # Extract numeric parts of matching codes
    suffixes = []
    for code in existing_codes:
        m = re.match(rf"^{prefix}(\d{{6}})$", code)
        if m:
            suffixes.append(int(m.group(1)))
            
    if prefix == "RM":
        
        all_numbers = sorted(set(suffixes + [base_number]))

        # Find next missing number
        next_number = None
        for i in range(1, all_numbers[-1] + 2):
            if i not in all_numbers:
                next_number = i
                break

        if not next_number:
            frappe.throw("Unable to determine next item code")
    else:
        next_number = max(suffixes or [base_number]) + 1
        
    suffix_str = f"{next_number:06d}"  # Pad to 6 digits like 000002

    # Set new item_code
    variant.item_code = f"{prefix}{suffix_str}"
    
import frappe
from frappe.utils import flt

@frappe.whitelist()
# def get_filtered_batches(doctype, txt, searchfield, start, page_len, filters):
#     from frappe.utils import cint
#     min_avg_length = flt(filters.get("average_length") or 0)
#     item_code = filters.get("item_code")
#     warehouse = filters.get("warehouse")
#     include_expired = cint(filters.get("include_expired") or 0)
    
#     conditions = ["average_length >= %(min_avg_length)s"]
    
#     if item_code:
#         conditions.append("item = %(item_code)s")

#     if warehouse:
#         conditions.append("warehouse = %(warehouse)s")

#     if not include_expired:
#         conditions.append("(expiry_date IS NULL OR expiry_date >= CURDATE())")

#     return frappe.db.sql(f"""
#         SELECT
#             name,
#             CONCAT(
#                 '<b>P:</b> ', CAST(IFNULL(pieces, 0) AS CHAR), ', ',
#                 '<b>L:</b> ', CAST(ROUND(IFNULL(average_length, 0), 2) AS CHAR), ', ',
#                 '<b>SW:</b> ', CAST(ROUND(IFNULL(section_weight, 0), 2) AS CHAR), ', ',
#                 CAST(ROUND(IFNULL(batch_qty, 0), 2) AS CHAR), ', ',
#                 IFNULL(batch_group_reference, 'N/A')
#             ) AS custom_label
#         FROM `tabBatch`
#         WHERE
#             {" AND ".join(conditions)} AND
#             name LIKE %(txt)s
#         ORDER BY name
#         LIMIT %(page_len)s OFFSET %(start)s
#     """, {
#         "min_avg_length": min_avg_length,
#         "txt": f"%{txt}%",
#         "start": start,
#         "page_len": page_len,
#         "item_code": item_code
#     })
    
def get_filtered_batches(doctype, txt, searchfield, start, page_len, filters):
    from frappe.utils import flt, cint

    min_avg_length = flt(filters.get("average_length") or 0)
    item_code = filters.get("item_code")
    warehouse = filters.get("warehouse")
    include_expired = cint(filters.get("include_expired") or 0)

    conditions = ["b.average_length >= %(min_avg_length)s"]

    if item_code:
        conditions.append("b.item = %(item_code)s")

    if not include_expired:
        conditions.append("(b.expiry_date IS NULL OR b.expiry_date >= CURDATE())")

    return frappe.db.sql(f"""
        SELECT
            b.name,
            CONCAT(
                '<b>P:</b> ', CAST(IFNULL(b.pieces, 0) AS CHAR), ', ',
                '<b>L:</b> ', CAST(ROUND(IFNULL(b.average_length, 0), 2) AS CHAR), ', ',
                '<b>SW:</b> ', CAST(ROUND(IFNULL(b.section_weight, 0), 2) AS CHAR), ', ',
                CAST(ROUND(IFNULL(b.batch_qty, 0), 2) AS CHAR), ', ',
                IFNULL(b.batch_group_reference, 'N/A')
            ) AS custom_label
        FROM `tabBatch` b
        WHERE
            {" AND ".join(conditions)}
            AND EXISTS (
                SELECT 1
                FROM `tabPiece Stock Ledger Entry` sle
                JOIN `tabSerial and Batch Bundle` sb ON sb.name = sle.serial_and_batch_bundle
                JOIN `tabSerial and Batch Entry` sb_entry ON sb_entry.parent = sb.name
                WHERE sb_entry.batch_no = b.name
                  {f"AND sle.warehouse = %(warehouse)s" if warehouse else ""}
                  AND sb_entry.qty > 0
            )
            AND b.name LIKE %(txt)s
        ORDER BY b.name
        LIMIT %(page_len)s OFFSET %(start)s
    """, {
        "min_avg_length": min_avg_length,
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len,
        "item_code": item_code,
        "warehouse": warehouse
    })         

@frappe.whitelist()
def get_cutting_plan_batches(doctype, txt, searchfield, start, page_len, filters):
    """
    Get batches for cutting plan with rich presentation format
    No length filtering - shows all batches for the item and warehouse
    """
    from frappe.utils import cint

    item_code = filters.get("item_code")
    warehouse = filters.get("warehouse")
    supplier_name = (filters.get("supplier_name") or "").strip()
    include_expired = cint(filters.get("include_expired") or 0)

    conditions = []

    if item_code:
        conditions.append("b.item = %(item_code)s")

    if not include_expired:
        conditions.append("(b.expiry_date IS NULL OR b.expiry_date >= CURDATE())")

    # Build WHERE clause
    where_clause = ""
    if conditions:
        where_clause = " AND ".join(conditions) + " AND "
    
    # Optional supplier filter via PR linkage (and Stock Entry custom supplier)
    supplier_join = ""
    supplier_condition = ""
    if supplier_name:
        supplier_join = """
            LEFT JOIN `tabPurchase Receipt` pr
                ON pr.name = b.reference_name
                AND b.reference_doctype = 'Purchase Receipt'
            LEFT JOIN `tabStock Entry` se
                ON se.name = b.reference_name
                AND b.reference_doctype = 'Stock Entry'
        """
        supplier_condition = """
            AND (
                (pr.name IS NOT NULL AND (pr.supplier_name = %(supplier_name)s OR pr.supplier = %(supplier_name)s))
                OR (se.name IS NOT NULL AND se.custom_supplier = %(supplier_name)s)
            )
        """

    return frappe.db.sql(f"""
        SELECT
            b.name,
            CONCAT(
                '<b>P:</b> ', CAST(IFNULL(b.pieces, 0) AS CHAR), ', ',
                '<b>L:</b> ', CAST(ROUND(IFNULL(b.average_length, 0), 2) AS CHAR), ', ',
                '<b>SW:</b> ', CAST(ROUND(IFNULL(b.section_weight, 0), 2) AS CHAR), ', ',
                CAST(ROUND(IFNULL(b.batch_qty, 0), 2) AS CHAR), ', ',
                IFNULL(b.batch_group_reference, 'N/A')
            ) AS custom_label
        FROM `tabBatch` b
        {supplier_join}
        WHERE
            {where_clause}
            EXISTS (
                SELECT 1
                FROM `tabPiece Stock Ledger Entry` sle
                JOIN `tabSerial and Batch Bundle` sb ON sb.name = sle.serial_and_batch_bundle
                JOIN `tabSerial and Batch Entry` sb_entry ON sb_entry.parent = sb.name
                WHERE sb_entry.batch_no = b.name
                  {f"AND sle.warehouse = %(warehouse)s" if warehouse else ""}
                  AND sb_entry.qty > 0
            )
            AND b.name LIKE %(txt)s
            {supplier_condition}
            AND b.batch_qty > 0
        ORDER BY b.name
        LIMIT %(page_len)s OFFSET %(start)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len,
        "item_code": item_code,
        "warehouse": warehouse,
        "supplier_name": supplier_name
    })

@frappe.whitelist()    
def get_work_order_details(work_orders):
    """
    Fetch detailed information for selected work orders
    """
    import json
    
    if isinstance(work_orders, str):
        work_orders = json.loads(work_orders)
    
    items = []
    
    for wo_data in work_orders:
        work_order_name = wo_data.get('work_order')
        
        # Fetch work order details
        work_order = frappe.get_doc('Work Order', work_order_name)
        
        for wo_items in work_order.required_items:
            items.append({
            'item_code': wo_items.item_code,
            'item_name': wo_items.item_name,
            'source_warehouse': wo_items.source_warehouse,
            'qty': wo_items.get('required_qty', 0),
            'basic_rate': wo_items.get('basic_rate', 0),
            'work_order_reference':work_order_name,
            'sales_order': work_order.sales_order,
            'production_item': work_order.production_item
            })
    return items

@frappe.whitelist()
def get_production_items_from_work_orders(work_orders):
    """
    Get production items from selected work orders
    """
    import json
    
    if isinstance(work_orders, str):
        work_orders = json.loads(work_orders)
    
    production_items = []
    
    for work_order_name in work_orders:
        # Fetch work order details
        work_order = frappe.get_doc('Work Order', work_order_name)
        
        # Add production item to the list
        if work_order.production_item and work_order.production_item not in production_items:
            production_items.append({
                "fg_item": work_order.production_item,
                "work_order_reference": work_order.name
            })  
    
    return production_items

@frappe.whitelist()
def get_work_orders_by_rm(rm_item, filters=None):
    """
    Get work orders that have a specific raw material in their required items
    """
    if not filters:
        filters = {}

    if isinstance(filters, str):
        import json
        filters = json.loads(filters)

    query = """
        SELECT DISTINCT wo.name, wo.production_item, wo.item_name
        FROM `tabWork Order` wo
        INNER JOIN `tabWork Order Item` woi ON wo.name = woi.parent
        WHERE woi.item_code = %(rm_item)s
    """

    conditions = []
    params = {"rm_item": rm_item}

    # ✅ Fix: expand status NOT IN list into placeholders
    if filters.get("status"):
        status_filter = filters["status"]
        if isinstance(status_filter, list) and len(status_filter) == 2 and status_filter[0] == "not in":
            placeholders = []
            for i, status in enumerate(status_filter[1]):
                key = f"status_{i}"
                placeholders.append(f"%({key})s")
                params[key] = status
            conditions.append(f"wo.status NOT IN ({', '.join(placeholders)})")

    if filters.get("docstatus") is not None:
        conditions.append("wo.docstatus = %(docstatus)s")
        params["docstatus"] = filters["docstatus"]

    if filters.get("production_item"):
        conditions.append("wo.production_item = %(production_item)s")
        params["production_item"] = filters["production_item"]

    if filters.get("name") and isinstance(filters["name"], list) and filters["name"][0] == "like":
        conditions.append("wo.name LIKE %(work_order_name)s")
        params["work_order_name"] = filters["name"][1]

    if conditions:
        query += " AND " + " AND ".join(conditions)

    query += " ORDER BY wo.creation DESC LIMIT 20"

    # 🔍 Debugging log
    frappe.log_error(f"Query: {query}\nParams: {params}", "get_work_orders_by_rm Debug")

    return frappe.db.sql(query, params, as_dict=True)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_scrap_items(doctype, txt, searchfield, start, page_len, filters):
    import json
    
    # Parse filters if it's a JSON string
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    allowed_items = filters.get('allowed_items', []) if filters else []
    
    conditions = []
    values = []
    
    # Search condition
    if txt:
        conditions.append(f"`tabItem`.`{searchfield}` LIKE %s")
        values.append(f"%{txt}%")
    
    # Build OR condition for allowed items or SCRAP group
    or_conditions = ["`tabItem`.`item_group` = %s"]
    values.append('SCRAP')
    
    if allowed_items and len(allowed_items) > 0:
        placeholders = ', '.join(['%s'] * len(allowed_items))
        or_conditions.append(f"`tabItem`.`name` IN ({placeholders})")
        values.extend(allowed_items)
    
    conditions.append(f"({' OR '.join(or_conditions)})")
    
    # Exclude FINISH GOODS
    conditions.append("`tabItem`.`item_group` != %s")
    values.append('FINISH GOODS')
    
    where_clause = ' AND '.join(conditions)
    
    return frappe.db.sql(f"""
        SELECT `tabItem`.`name`, `tabItem`.`item_name`
        FROM `tabItem`
        WHERE {where_clause}
        ORDER BY
            CASE WHEN `tabItem`.`name` LIKE %s THEN 0 ELSE 1 END,
            `tabItem`.`name`
        LIMIT %s OFFSET %s
    """, tuple(values + [f"{txt}%", page_len, start]))

@frappe.whitelist()
def get_items_from_cut_plan(work_order):
    
    if not work_order:
        return []

    cut_plan_ref = frappe.get_doc("Work Order", work_order).cutting_plan_reference
    fg_item = frappe.get_doc("Work Order", work_order).production_item
    rows = frappe.get_all(
        "Cutting plan Finish Second",
        filters={"work_order_reference": work_order, "fg_item": fg_item,"parent":cut_plan_ref},
        fields=[
            "item as item_code",
            "batch as batch_no",
            "qty",
            # "warehouse as t_warehouse",
            "pieces",
            "length_size as average_length",
            "section_weight",
            "lot_no",
            "fg_item",
            "semi_fg_length",
            "work_order_reference",
            "total_pcs",
        ],
        order_by="creation asc",
    )

    # Enrich with UOM metadata and batch flags needed by Stock Entry Detail
    for row in rows:
        row["use_serial_batch_fields"] = 1
        row["required_stock_in_pieces"] = 1
        # Default conversion factor and stock/uom
        stock_uom = frappe.db.get_value("Item", row.get("item_code"), "stock_uom")
        row["stock_uom"] = stock_uom
        row["uom"] = stock_uom
        row["conversion_factor"] = 1
        row["basic_rate"] = 0

    return rows


@frappe.whitelist()
def get_finished_cut_plan_from_mtm(work_orders):
    """
    For Finished Cut Plan: gather Stock Entry (Material Transfer for Manufacture) items
    linked to given Work Orders and prepare:
    - detail_rows: consolidated by (item_code, batch_no, s_warehouse)
    - finish_rows: non-consolidated, one row per stock entry item

    work_orders: list of work order names or JSON string
    """
    import json

    if isinstance(work_orders, str):
        work_orders = json.loads(work_orders)

    if not work_orders:
        return {"detail_rows": [], "finish_rows": []}

    # Pre-fetch WO -> FG item map
    wo_to_fg = {}
    for wo_name in work_orders:
        try:
            wo_to_fg[wo_name] = frappe.db.get_value("Work Order", wo_name, "production_item")
        except Exception:
            wo_to_fg[wo_name] = None

    # Fetch submitted MTM Stock Entries for provided WOs
    se_list = frappe.get_all(
        "Stock Entry",
        filters={
            "docstatus": 1,
            "work_order": ["in", work_orders],
            "stock_entry_type": "Material Transfer for Manufacture",
        },
        fields=["name", "work_order", "posting_date", "posting_time"],
        order_by="posting_date asc, posting_time asc, name asc",
    )

    detail_key_to_row = {}
    finish_rows = []

    for se in se_list:
        # Get items
        items = frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": se["name"]},
            fields=[
                "item_code",
                "item_name",
                "s_warehouse",
                "t_warehouse",
                "qty",
                "batch_no",
                # custom fields if present
                "pieces",
                "average_length",
                "section_weight",
                "lot_no"
            ],
            order_by="idx asc",
        )

        for it in items:
            item_code = it.get("item_code")
            batch_no = it.get("batch_no")
            s_wh = it.get("t_warehouse")

            # Consolidated key for detail table
            key = (item_code or "", batch_no or "", s_wh or "")
            if key not in detail_key_to_row:
                detail_key_to_row[key] = {
                    "item_code": item_code,
                    "item_name": it.get("item_name"),
                    "source_warehouse": s_wh,
                    "qty": 0.0,
                    "pieces": 0.0,
                    "length_size": it.get("average_length"),
                    "section_weight": it.get("section_weight"),
                    "lot_no": it.get("lot_no"),
                    "batch": batch_no,
                    "work_order_reference": se.get("work_order"),
                }
            # Sum quantities/pieces
            row = detail_key_to_row[key]
            row["qty"] = float(row.get("qty") or 0) + float(it.get("qty") or 0)
            row["pieces"] = float(row.get("pieces") or 0) + float(it.get("pieces") or 0)

            # Keep length/section_weight consistent if same, else drop to None
            if row.get("length_size") != it.get("average_length"):
                row["length_size"] = row.get("length_size") if row.get("length_size") == it.get("average_length") else row.get("length_size")
            if row.get("section_weight") != it.get("section_weight"):
                row["section_weight"] = row.get("section_weight") if row.get("section_weight") == it.get("section_weight") else row.get("section_weight")

            # Non-consolidated finish row
            finish_rows.append({
                "item": item_code,
                "batch": batch_no,
                "qty": it.get("qty"),
                "pieces": it.get("pieces"),
                "length_size": it.get("average_length"),
                # "section_weight": it.get("section_weight"),
                "lot_no": it.get("lot_no"),
                "rm_reference_batch": batch_no,
                "work_order_reference": se.get("work_order"),
                "fg_item": wo_to_fg.get(se.get("work_order")),
                "section_weight":frappe.db.get_value("Item", wo_to_fg.get(se.get("work_order")),'weight_per_meter')
            })

    detail_rows = list(detail_key_to_row.values())
    return {"detail_rows": detail_rows, "finish_rows": finish_rows}


@frappe.whitelist()
def get_finished_cut_plan_from_manufacturing(work_orders):
    """
    For Finished Cut Plan: gather finished items from submitted Manufacture Stock Entries
    linked to given Work Orders and prepare rows to append into `cut_plan_detail`.

    - Only finished item rows are considered (FG lines). We identify them as rows where
      the `item_code` matches the Work Order's `production_item` and the row has a
      target warehouse (t_warehouse). These are the produced outputs.
    - Rows are consolidated by (item_code, batch_no, t_warehouse) so that "batch * qty"
      is represented as one row per batch with total qty.

    Parameters
    ----------
    work_orders: list[str] | str
        List of Work Order names, or a JSON-encoded list.
    """
    import json

    if isinstance(work_orders, str):
        work_orders = json.loads(work_orders)

    if not work_orders:
        return {"detail_rows": [], "finish_rows": []}

    # Pre-fetch WO -> FG item map
    wo_to_fg = {}
    for wo_name in work_orders:
        try:
            wo_to_fg[wo_name] = frappe.db.get_value("Work Order", wo_name, "production_item")
        except Exception:
            wo_to_fg[wo_name] = None

    # Fetch submitted Manufacture Stock Entries for provided WOs
    se_list = frappe.get_all(
        "Stock Entry",
        filters={
            "docstatus": 1,
            "work_order": ["in", work_orders],
            "stock_entry_type": "Manufacture",
        },
        fields=["name", "work_order", "posting_date", "posting_time"],
        order_by="posting_date asc, posting_time asc, name asc",
    )

    detail_key_to_row = {}
    finish_rows = []

    for se in se_list:
        work_order_name = se.get("work_order")
        fg_item_code = wo_to_fg.get(work_order_name)

        # Get items on this Stock Entry
        items = frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": se["name"]},
            fields=[
                "item_code",
                "item_name",
                "s_warehouse",
                "t_warehouse",
                "qty",
                "batch_no",
                # optional/custom fields used in UI
                "pieces",
                "total_pcs",
                "average_length",
                "lot_no",
            ],
            order_by="idx asc",
        )

        for it in items:
            item_code = it.get("item_code")
            batch_no = it.get("batch_no")
            t_wh = it.get("t_warehouse")

            # FINISHED rows: only FG item with incoming qty (t_warehouse present)
            if fg_item_code and item_code == fg_item_code and t_wh:
                key = (item_code or "", batch_no or "", t_wh or "")
                if key not in detail_key_to_row:
                    detail_key_to_row[key] = {
                        "item_code": item_code,
                        "item_name": it.get("item_name"),
                        # For Finished items, use t_warehouse as the source for subsequent planning
                        "source_warehouse": t_wh,
                        "qty": 0.0,
                        "pieces": 0.0,
                        "batch": batch_no,
                        "work_order_reference": work_order_name,
                        # Use FG item's section weight if available
                        "section_weight": frappe.db.get_value("Item", fg_item_code, "weight_per_meter"),
                    }
                row = detail_key_to_row[key]
                row["qty"] = float(row.get("qty") or 0) + float(it.get("qty") or 0)
                row["pieces"] = float(row.get("pieces") or 0) + float(it.get("total_pcs") or it.get("pieces") or 0)
                continue

            # NON-FINISHED rows: append to finish_rows for Cutting Plan Finish table
            finish_rows.append({
                "item": item_code,
                "batch": batch_no,
                "qty": it.get("qty"),
                "pieces": int(it.get("total_pcs")),
                "length_size": it.get("average_length"),
                "lot_no": it.get("lot_no"),
                "rm_reference_batch": batch_no,
                "work_order_reference": work_order_name,
                "fg_item": fg_item_code,
                # For consumed components, use source warehouse
                "warehouse": it.get("s_warehouse"),
            })

    detail_rows = list(detail_key_to_row.values())
    
    return {"detail_rows": detail_rows, "finish_rows": finish_rows}


@frappe.whitelist()
def get_material_request_for_item(item_code):
    # You can safely use ignore_permissions=True here
    res = frappe.db.get_value("Material Request Item", {"item_code": item_code}, "parent", as_dict=True)
    return res


@frappe.whitelist()
def get_items_with_material_request(doctype, txt, searchfield, start, page_len, filters):
    allowed_groups = filters.get("item_groups", [])
    if isinstance(allowed_groups, str):
        allowed_groups = frappe.parse_json(allowed_groups)

    return frappe.db.sql("""
        SELECT DISTINCT i.name, i.item_name
        FROM `tabItem` i
        INNER JOIN `tabMaterial Request Item` mri ON mri.item_code = i.name
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE i.item_group IN %(groups)s
          AND mr.docstatus = 1
          AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
        ORDER BY i.name
        LIMIT %(start)s, %(page_len)s
    """, {
        "groups": tuple(allowed_groups),
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })


