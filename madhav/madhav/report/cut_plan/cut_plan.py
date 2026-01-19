import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Cutting Plan"),
            "fieldname": "cutting_plan",
            "fieldtype": "Link",
            "options": "Cutting Plan",
            "width": 140,
        },
        {
            "label": _("Item"),
            "fieldname": "item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Supplier"),
            "fieldname": "supplier",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 140,
        },
        {
            "label": _("Supplier Name"),
            "fieldname": "supplier_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Sales Order"),
            "fieldname": "sales_order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "width": 140,
        },
        {
            "label": _("Pieces"),
            "fieldname": "pieces",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "label": _("Length Size (Inch)"),
            "fieldname": "length_size_inch",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Total Length (Inch)"),
            "fieldname": "total_length_in_meter_inch",
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "label": _("Section Weight"),
            "fieldname": "section_weight",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Qty"),
            "fieldname": "qty",
            "fieldtype": "Float",
            "width": 100,
        },
        {
            "label": _("Length Size 1"),
            "fieldname": "length_size_1",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Length Size 2"),
            "fieldname": "length_size_2",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Length Size 3"),
            "fieldname": "length_size_3",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Length Size 4"),
            "fieldname": "length_size_4",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Length Size 5"),
            "fieldname": "length_size_5",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Process Loss Qty"),
            "fieldname": "process_loss_qty",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": _("Qty After Loss"),
            "fieldname": "qty_after_loss",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": _("Target Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
        {
            "label": _("Root Radius"),
            "fieldname": "root_radius",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Lot No"),
            "fieldname": "lot_no",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("RM Reference Batch"),
            "fieldname": "rm_reference_batch",
            "fieldtype": "Link",
            "options": "Batch",
            "width": 160,
        },
        {
            "label": _("Weight Per Length"),
            "fieldname": "weight_per_length",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Process Loss (%)"),
            "fieldname": "process_loss",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Remaining Weight"),
            "fieldname": "remaining_weight",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": _("Semi FG Length"),
            "fieldname": "semi_fg_length",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("FG Cut Plan No Of Length Sizes"),
            "fieldname": "no_of_length_sizes",
            "fieldtype": "Int",
            "width": 180,
        },
    ]


def get_data(filters):
    conditions = ""
    values = {}

    if filters.get("date"):
        conditions += " AND cp.date = %(date)s"
        values["date"] = filters["date"]

    if filters.get("cutting_plan"):
        conditions += " AND cp.name = %(cutting_plan)s"
        values["cutting_plan"] = filters["cutting_plan"]

    query = f"""
        SELECT
            cp.name AS cutting_plan,
            cpf.item,
            cpf.item_name,
            cpf.supplier,
            cpf.supplier_name,
            cpf.sales_order,              -- ✅ NEW

            cpf.pieces,
            cpf.length_size_inch,
            cpf.total_length_in_meter_inch,
            cpf.section_weight,

            cpf.qty,
            cpf.length_size_1,             -- ✅ NEW
            cpf.length_size_2,             -- ✅ NEW
            cpf.length_size_3,             -- ✅ NEW
            cpf.length_size_4,             -- ✅ NEW
            cpf.length_size_5,             -- ✅ NEW
            
            cpf.process_loss_qty,
            cpf.qty_after_loss,

            cpf.warehouse,
            cpf.root_radius,               -- ✅ NEW
            cpf.lot_no,

            cpf.rm_reference_batch,
            cpf.weight_per_length,
            cpf.process_loss,
            cpf.remaining_weight,
            cpf.semi_fg_length,
            cpf.no_of_length_sizes
        FROM
            `tabCutting Plan Finish` cpf
        INNER JOIN
            `tabCutting Plan` cp
            ON cp.name = cpf.parent
        WHERE
            cp.docstatus < 2
            AND IFNULL(cpf.return_to_stock, 0) = 0
            {conditions}
        ORDER BY
            cp.date DESC, cp.name DESC
    """


    return frappe.db.sql(query, values, as_dict=True)
