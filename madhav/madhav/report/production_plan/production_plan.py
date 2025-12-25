import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Party Name", "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 180},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data", "width": 100},
        {"label": "Grade", "fieldname": "grade", "fieldtype": "Data", "width": 120},
		{"label": "PO No", "fieldname": "po_no", "fieldtype": "Data", "width": 80},
		{"label": "Length in Meter", "fieldname": "length_size_m", "fieldtype": "Float", "width": 120},
		{"label": "SECTION WEIGHT", "fieldname": "section_weight", "fieldtype": "Data", "width": 160},
		{"label": "Qty in PCS", "fieldname": "pieces", "fieldtype": "Int", "width": 120},
        {"label": "QTY/MT", "fieldname": "planned_qty", "fieldtype": "Float", "width": 120},
    ]


def get_data(filters):
    if not filters or not filters.get("production_plan"):
        return []

    return frappe.db.sql("""
        SELECT
            customer_name,
            CASE 
                WHEN bom_no LIKE '%%X%%' 
                THEN SUBSTRING_INDEX(
                    SUBSTRING_INDEX(bom_no, ' ', -1),
                '-', 1)
                ELSE ''
            END AS size,

            CASE 
                WHEN bom_no LIKE '%% MS %%' AND bom_no LIKE '%%X%%' 
                THEN TRIM(
                    SUBSTRING_INDEX(
                        SUBSTRING_INDEX(bom_no, ' ', -3),
                    ' ', 2)
                )
                ELSE ''
            END AS grade,
			po_no,
			length_size_m,
			CASE 
				WHEN section_weight IS NOT NULL AND section_weight != ''
				THEN CONCAT(section_weight, ' KG/MTR')
				ELSE ''
			END AS section_weight,
			pieces,
            planned_qty
        FROM `tabProduction Plan Item`
        WHERE parent = %s
		AND parentfield = 'assembly_items_without_consolidate'
        ORDER BY idx
    """, (filters.production_plan,), as_dict=True)

