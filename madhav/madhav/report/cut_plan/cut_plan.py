import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        _("Cutting Plan") + ":Link/Cutting Plan:140",
        _("Item") + ":Link/Item:140",
        _("Item Name") + ":Data:180",
        _("Supplier") + ":Link/Supplier:140",
        _("Supplier Name") + ":Data:180",
        _("Pieces") + ":Int:80",
        _("Length Size (Inch)") + ":Float:120",
        _("Total Length (Inch)") + ":Float:140",
        _("Section Weight") + ":Float:120",
        _("Qty") + ":Float:100",
        _("Process Loss Qty") + ":Float:130",
        _("Qty After Loss") + ":Float:130",
        _("Target Warehouse") + ":Link/Warehouse:160",
        _("RM Reference Batch") + ":Link/Batch:160",
        _("Weight Per Length") + ":Float:120",
        _("Process Loss (%)") + ":Float:120",
        _("Remaining Weight") + ":Float:130",
        _("Semi FG Length") + ":Float:120",
        _("FG Cut Plan No Of Length Sizes") + ":Int:180",
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
            cpf.pieces,
            cpf.length_size_inch,
            cpf.total_length_in_meter_inch,
            cpf.section_weight,
            cpf.qty,
            cpf.process_loss_qty,
            cpf.qty_after_loss,
            cpf.warehouse,
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
