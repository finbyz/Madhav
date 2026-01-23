import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    return columns, data


def get_columns():
    return [
        {"label": "Party Name", "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 180},
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data", "width": 100},
        {"label": "Grade", "fieldname": "grade", "fieldtype": "Data", "width": 120},
        {"label": "PO No", "fieldname": "customers_purchase_order", "fieldtype": "Data", "width": 80},
        {"label": "Length in Meter", "fieldname": "length_size_m", "fieldtype": "Float", "width": 120},
        {"label": "SECTION WEIGHT", "fieldname": "section_weight", "fieldtype": "Data", "width": 160},
        {"label": "Qty in PCS", "fieldname": "pieces", "fieldtype": "Int", "width": 120},
        {"label": "QTY/MT", "fieldname": "planned_qty", "fieldtype": "Float", "width": 120},
        {"label": "Remark", "fieldname": "remark", "fieldtype": "Data", "width": 300},
    ]


def get_data(filters):
    conditions = []
    values = {}

    # Filter by Production Plan
    if filters.get("production_plan"):
        conditions.append("pp.name = %(production_plan)s")
        values["production_plan"] = filters["production_plan"]

    # Filter by date range
    if filters.get("from_date"):
        conditions.append("pp.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("pp.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    condition_sql = ""
    if conditions:
        condition_sql = " AND " + " AND ".join(conditions)

    return frappe.db.sql(f"""
        SELECT
            ppi.customer_name,
            ppi.item_code,
            it.item_name,

            CASE 
                WHEN ppi.bom_no LIKE '%%X%%' 
                THEN SUBSTRING_INDEX(
                    SUBSTRING_INDEX(ppi.bom_no, ' ', -1),
                '-', 1)
                ELSE ''
            END AS size,

            CASE 
                WHEN ppi.bom_no LIKE '%% MS %%' AND ppi.bom_no LIKE '%%X%%' 
                THEN TRIM(
                    SUBSTRING_INDEX(
                        SUBSTRING_INDEX(ppi.bom_no, ' ', -3),
                    ' ', 2)
                )
                ELSE ''
            END AS grade,

            ppi.customers_purchase_order,
            ppi.length_size_m,

            CASE 
                WHEN ppi.section_weight IS NOT NULL AND ppi.section_weight != ''
                THEN CONCAT(ppi.section_weight, ' KG/MTR')
                ELSE ''
            END AS section_weight,

            ppi.pieces,
            ppi.planned_qty,
            ppi.remark

        FROM `tabProduction Plan Item` ppi
        INNER JOIN `tabProduction Plan` pp ON pp.name = ppi.parent
        LEFT JOIN `tabItem` it ON it.name = ppi.item_code

        WHERE ppi.parentfield = 'assembly_items_without_consolidate'
        {condition_sql}

        ORDER BY pp.posting_date, ppi.idx
    """, values, as_dict=True)
