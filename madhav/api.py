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
    
    