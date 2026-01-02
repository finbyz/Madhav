# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

# import frappe


import copy
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import CombineDatetime, Sum
from frappe.utils import cint, flt, get_datetime
from erpnext.stock.stock_ledger import get_previous_sle

from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import get_stock_balance_for
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import (
    is_reposting_item_valuation_in_progress,
    update_included_uom_in_report,
)
from erpnext.stock.stock_ledger import get_previous_sle


def execute(filters=None):
    is_reposting_item_valuation_in_progress()
    include_uom = filters.get("include_uom")
    columns = get_columns(filters)
    items = get_items(filters)
    sl_entries = get_stock_ledger_entries(filters, items)
    item_details = get_item_details(items, sl_entries, include_uom)

    

    # ------- compute opening map by scanning SLEs before from_date -------
    opening_map = defaultdict(float)
    running_bal = defaultdict(float)

    if filters.get("from_date"):
        args = [filters.get("from_date")]
        item_condition = ""
        if items:
            item_condition = " AND item_code IN ({})".format(", ".join(["%s"] * len(items)))
            args.extend(items)

        if filters.get("warehouse"):
            item_condition += " AND warehouse = %s"
            args.append(filters.get("warehouse"))

        if filters.get("company"):
            item_condition += " AND company = %s"
            args.append(filters.get("company"))

        prev_sles = frappe.db.sql(
            f"""
            SELECT
                item_code, warehouse, posting_date, posting_time,
                actual_qty, qty_after_transaction, voucher_type, stock_value_difference,
                voucher_no, company
            FROM `tabStock Ledger Entry`
            WHERE docstatus < 2
              AND is_cancelled = 0
              AND posting_date < %s
              {item_condition}
            ORDER BY posting_date, posting_time, creation
            """,
            tuple(args),
            as_dict=True,
        )

        for d in prev_sles:
            key = d["item_code"]
            if d.get("voucher_type") == "Stock Reconciliation":
                qty_diff = flt(d.get("qty_after_transaction")) - flt(running_bal[key])
            else:
                qty_diff = flt(d.get("actual_qty"))

            running_bal[key] += qty_diff
            opening_map[key] += qty_diff
    # ---------------------------------------------------------------------

    precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))

    si_nos = [sle.voucher_no for sle in sl_entries if sle.voucher_type == "Sales Invoice"]

# Map of Sales Invoice -> is_return
    si_map = {}
    if si_nos:
        si_rows = frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", si_nos]},
            fields=["name", "is_return"],
        )
        si_map = {r.name: r.is_return for r in si_rows}
        # frappe.throw(str(si_map))

    pi_nos = [sle.voucher_no for sle in sl_entries if sle.voucher_type == "Purchase Invoice"]

# Map of Sales Invoice -> is_return
    pi_map = {}
    if pi_nos:
        pi_rows = frappe.get_all(
            "Purchase Invoice",
            filters={"name": ["in", pi_nos]},
            fields=["name", "is_return"],
        )
        pi_map = {r.name: r.is_return for r in pi_rows}
    

    item_wise_data = {}
    for sle in sl_entries:
        item_code = sle.item_code
        item_name = item_details[item_code].get("item_name")

        if item_code not in item_wise_data:
            item_wise_data[item_code] = {
                "item_code": item_code,
                "item_name": item_name,
                "stock_uom": item_details[item_code].get("stock_uom"),
                "item_group": item_details[item_code].get("item_group"),
                "brand": item_details[item_code].get("brand"),
                "description": item_details[item_code].get("description"),
                "opening_balance": flt(opening_map.get(item_code, 0.0)),
                "purchase_receipt_in": 0,
                "purchase_invoice": 0,
                "material_receipt": 0,
                "material_issue_return": 0,
                "delivery_note_in": 0,
                "send_to_subcontractor_in": 0,
                "disassemble": 0,
                "manufacture_in": 0,
                "repack_in": 0,
                "opening_stock_in": 0,
                "subcontract_receipt_in": 0,
                "stock_reconciliation": 0,
                "total_inward": 0,

                # OUTWARD
                "rm_transfer_cum_cutting": 0,
                "material_transfer_for_manufacture": 0,
                "send_to_subcontractor_out": 0,
                "fg_free_length_transfer": 0,
                "purchase_receipt_out": 0,
                "material_issue": 0,
                "manufacture_out": 0,
                "repack_out": 0,
                "subcontract_issue_out": 0,
                "purchase_invoice_out": 0,
                "total_outward": 0,

                "closing_balance": None,
                "purchase": 0,
                "manufacturer": 0,
                "sales": 0,
                "consumption": 0,
                "qty_after_transaction": 0,
                "warehouse": sle.warehouse,
                "batch_no": sle.batch_no,
                "serial_no": sle.serial_no,
                "project": sle.project,
                "incoming_rate": sle.incoming_rate or 0,
                "valuation_rate": sle.valuation_rate or 0,
                "in_out_rate": 0,
                "stock_value": 0,
                "stock_value_difference": 0,
            }
        if sle.actual_qty:
            item_wise_data[item_code]["in_out_rate"] = flt(
                sle.stock_value_difference / sle.actual_qty, precision
            )
        else:
            item_wise_data[item_code]["in_out_rate"] = sle.valuation_rate or 0
            
        row = item_wise_data[item_code]
        item_wise_data[item_code]["stock_value"] += flt(sle.stock_value or 0)
        item_wise_data[item_code]["stock_value_difference"] += flt(sle.stock_value_difference or 0)
        
        if sle.actual_qty:
            qty = flt(sle.actual_qty)

            # ---------------- INWARD ----------------
            if sle.voucher_type == "Purchase Receipt" and qty > 0:
                item_wise_data[item_code]["purchase_receipt_in"] += qty
            elif sle.voucher_type == "Purchase Invoice":
                if pi_map.get(sle.voucher_no):  # Purchase Return
                    row["purchase_invoice_out"] += abs(qty)
                else:  # Normal Purchase Invoice
                    row["purchase_invoice"] += qty
            elif sle.voucher_type == "Delivery Note" and qty > 0:
                item_wise_data[item_code]["delivery_note_in"] += qty
            # --- Stock Reconciliation ---
            elif sle.voucher_type == "Stock Reconciliation":
                row["stock_reconciliation"] += qty
            elif sle.voucher_type == "Stock Entry":
                se_type = frappe.db.get_value(
                    "Stock Entry", sle.voucher_no, "stock_entry_type"
                )

                if qty > 0:
                    # -------- INWARD --------
                    if se_type == "Material Receipt":
                        row["material_receipt"] += qty
                    elif se_type == "Material Issue Return":
                        row["material_issue_return"] += qty
                    elif se_type == "Send to Subcontractor":
                        row["send_to_subcontractor_in"] += qty
                    elif se_type == "Disassemble":
                        row["disassemble"] += qty
                    elif se_type == "Manufacture":
                        row["manufacture_in"] += qty
                    elif se_type == "Repack":
                        row["repack_in"] += qty
                    elif se_type == "Opening Stock":
                        row["opening_stock_in"] += qty
                    elif se_type == "Subcontract Receipt":
                        row["subcontract_receipt_in"] += qty

                else:
                    # -------- OUTWARD --------
                    qty = abs(qty)
                    if se_type == "Material Issue":
                        row["material_issue"] += qty
                    elif se_type == "RM Transfer cum Cutting Entry":
                        row["rm_transfer_cum_cutting"] += qty
                    elif se_type == "Material Transfer for Manufacture":
                        row["material_transfer_for_manufacture"] += qty
                    elif se_type == "Send to Subcontractor":
                        row["send_to_subcontractor_out"] += qty
                    elif se_type == "FG Free Length Transfer cum Cutting Entry":
                        row["fg_free_length_transfer"] += qty
                    elif se_type == "Manufacture":
                        row["manufacture_out"] += qty
                    elif se_type == "Repack":
                        row["repack_out"] += qty
                    elif se_type == "Subcontract Issue":
                        row["subcontract_issue_out"] += qty


            # ---------------- OUTWARD ----------------
            if sle.voucher_type == "Purchase Receipt" and qty < 0:
                item_wise_data[item_code]["purchase_receipt_out"] += abs(qty)

            elif sle.voucher_type == "Stock Entry":
                se_type = frappe.db.get_value(
                    "Stock Entry", sle.voucher_no, "stock_entry_type"
                )

                if se_type == "RM Transfer cum Cutting Entry":
                    item_wise_data[item_code]["rm_transfer_cum_cutting"] += abs(qty)

                elif se_type == "Material Transfer for Manufacture":
                    item_wise_data[item_code]["material_transfer_for_manufacture"] += abs(qty)

                elif se_type == "Send to Subcontractor":
                    item_wise_data[item_code]["send_to_subcontractor_out"] += abs(qty)

                elif se_type == "FG Free Length Transfer cum Cutting Entry":
                    item_wise_data[item_code]["fg_free_length_transfer"] += abs(qty)


        # Aggregate voucher types
        if sle.voucher_type == "Stock Entry":
            stock_entry_type = frappe.db.get_value("Stock Entry", sle.voucher_no, "stock_entry_type")

            if stock_entry_type == "Manufacture":
                if sle.actual_qty > 0:
                    item_wise_data[item_code]["manufacturer"] += flt(sle.actual_qty)

            if stock_entry_type == "Manufacture":
                if sle.actual_qty < 0:
                    item_wise_data[item_code]["consumption"] += flt(sle.actual_qty)

        elif sle.voucher_type == "Purchase Receipt":
            item_wise_data[item_code]["purchase"] += flt(sle.actual_qty)

        elif sle.voucher_type == "Sales Invoice" and si_map.get(sle.voucher_no):
            item_wise_data[item_code]["sales"] +=  flt(sle.actual_qty)
        
        elif sle.voucher_type == "Purchase Invoice" and pi_map.get(sle.voucher_no):
            item_wise_data[item_code]["manufacturer"] += flt(sle.actual_qty)


        elif sle.voucher_type == "Delivery Note":
            item_wise_data[item_code]["sales"] += flt(sle.actual_qty)
    # ------------------------------
    # Calculate Total Inward / Outward
    # ------------------------------
    for row in item_wise_data.values():
        row["total_inward"] = (
            row["purchase_receipt_in"]
            + row["purchase_invoice"]
            + row["material_receipt"]
            + row["material_issue_return"]
            + row["delivery_note_in"]
            + row["send_to_subcontractor_in"]
            + row["disassemble"]
            + row["manufacture_in"]
            + row["repack_in"]
            + row["opening_stock_in"]
            + row["subcontract_receipt_in"]
        )

        row["total_outward"] = (
            row["rm_transfer_cum_cutting"]
            + row["material_transfer_for_manufacture"]
            + row["send_to_subcontractor_out"]
            + row["fg_free_length_transfer"]
            + row["purchase_receipt_out"]
            + row["material_issue"]
            + row["manufacture_out"]
            + row["repack_out"]
            + row["subcontract_issue_out"]
        )

    # Compute closing balance
    for row in item_wise_data.values():
        row["closing_balance"] = (
            flt(row["opening_balance"])
            + flt(row["total_inward"])
            - flt(row["total_outward"])
        )

    # Final data
    data = list(item_wise_data.values())
    update_included_uom_in_report(columns, data, include_uom, [])
    return columns, data




 
def get_segregated_bundle_entries(sle, bundle_details, batch_balance_dict, filters):
    segregated_entries = []
    qty_before_transaction = sle.qty_after_transaction - sle.actual_qty
    stock_value_before_transaction = sle.stock_value - sle.stock_value_difference

    for row in bundle_details:
        new_sle = copy.deepcopy(sle)
        new_sle.update(row)
        new_sle.update(
            {
                "in_out_rate": flt(new_sle.stock_value_difference / row.qty) if row.qty else 0,
                "in_qty": row.qty if row.qty > 0 else 0,
                "out_qty": row.qty if row.qty < 0 else 0,
                "qty_after_transaction": qty_before_transaction + row.qty,
                "stock_value": stock_value_before_transaction + new_sle.stock_value_difference,
                "incoming_rate": row.incoming_rate if row.qty > 0 else 0,
            }
        )

        if filters.get("batch_no") and row.batch_no:
            if not batch_balance_dict.get(row.batch_no):
                batch_balance_dict[row.batch_no] = [0, 0]

            batch_balance_dict[row.batch_no][0] += row.qty
            batch_balance_dict[row.batch_no][1] += row.stock_value_difference

            new_sle.update(
                {
                    "qty_after_transaction": batch_balance_dict[row.batch_no][0],
                    "stock_value": batch_balance_dict[row.batch_no][1],
                }
            )

        qty_before_transaction += row.qty
        stock_value_before_transaction += new_sle.stock_value_difference

        new_sle.valuation_rate = (
            stock_value_before_transaction / qty_before_transaction if qty_before_transaction else 0
        )

        segregated_entries.append(new_sle)

    return segregated_entries


def get_serial_batch_bundle_details(sl_entries, filters=None):
    bundle_details = []
    for sle in sl_entries:
        if sle.serial_and_batch_bundle:
            bundle_details.append(sle.serial_and_batch_bundle)

    if not bundle_details:
        return frappe._dict({})

    query_filers = {"parent": ("in", bundle_details)}
    if filters.get("batch_no"):
        query_filers["batch_no"] = filters.batch_no

    _bundle_details = frappe._dict({})
    batch_entries = frappe.get_all(
        "Serial and Batch Entry",
        filters=query_filers,
        fields=["parent", "qty", "incoming_rate", "stock_value_difference", "batch_no", "serial_no"],
        order_by="parent, idx",
    )
    for entry in batch_entries:
        _bundle_details.setdefault(entry.parent, []).append(entry)

    return _bundle_details


def update_available_serial_nos(available_serial_nos, sle):
    serial_nos = get_serial_nos(sle.serial_no)
    key = (sle.item_code, sle.warehouse)
    if key not in available_serial_nos:
        stock_balance = get_stock_balance_for(
            sle.item_code, sle.warehouse, sle.posting_date, sle.posting_time
        )
        serials = get_serial_nos(stock_balance["serial_nos"]) if stock_balance["serial_nos"] else []
        available_serial_nos.setdefault(key, serials)

    existing_serial_no = available_serial_nos[key]
    for sn in serial_nos:
        if sle.actual_qty > 0:
            if sn in existing_serial_no:
                existing_serial_no.remove(sn)
            else:
                existing_serial_no.append(sn)
        else:
            if sn in existing_serial_no:
                existing_serial_no.remove(sn)
            else:
                existing_serial_no.append(sn)

    sle.balance_serial_no = "\n".join(existing_serial_no)


def get_columns(filters):
    columns = [
        # {"label": _("Date"), "fieldname": "date", "fieldtype": "Datetime", "width": 150},
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 100,
        },
        {"label": _("Item Name"), "fieldname": "item_name", "width": 100},
        {
            "label": _("Stock UOM"),
            "fieldname": "stock_uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 90,
        },
    ]

    for dimension in get_inventory_dimensions():
        columns.append(
            {
                "label": _(dimension.doctype),
                "fieldname": dimension.fieldname,
                "fieldtype": "Link",
                "options": dimension.doctype,
                "width": 110,
            }
        )

    columns.extend(
        [
            # {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
            # {
            # 	"label": _("Voucher #"),
            # 	"fieldname": "voucher_no",
            # 	"fieldtype": "Dynamic Link",
            # 	"options": "voucher_type",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Inward"),
            # 	"fieldname": "in_qty",
            # 	"fieldtype": "Float",
            # 	"width": 80,
            # 	"convertible": "qty",
            # },
            {
                "label": "Opening Balance", 
                "fieldname": "opening_balance", 
                "fieldtype": "Float",
                "width": 120
               },
            {
                "label": "Purchase Receipt (In)",
                "fieldname": "purchase_receipt_in",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Purchase Invoice",
                "fieldname": "purchase_invoice",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Material Receipt",
                "fieldname": "material_receipt",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Material Issue Return",
                "fieldname": "material_issue_return",
                "fieldtype": "Float",
                "width": 140,
            },
            {
                "label": "Delivery Note (In)",
                "fieldname": "delivery_note_in",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Send to Subcontractor (In)",
                "fieldname": "send_to_subcontractor_in",
                "fieldtype": "Float",
                "width": 160,
            },
            {
                "label": "Disassemble",
                "fieldname": "disassemble",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Manufacture (In)",
                "fieldname": "manufacture_in",
                "fieldtype": "Float",
                "width": 140,
            },
            {
                "label": "Repack (In)",
                "fieldname": "repack_in",
                "fieldtype": "Float",
                "width": 120,
            },
            {
                "label": "Opening Stock",
                "fieldname": "opening_stock_in",
                "fieldtype": "Float",
                "width": 130,
            },
            {
                "label": "Subcontract Receipt",
                "fieldname": "subcontract_receipt_in",
                "fieldtype": "Float",
                "width": 160,
            },
            {
                "label": "Stock Reconciliation",
                "fieldname": "stock_reconciliation",
                "fieldtype": "Float",
                "width": 150,
            },
            {
                "label": "Total Inward",
                "fieldname": "total_inward",
                "fieldtype": "Float",
                "width": 130,
            },
            {
                "label": "RM Transfer cum Cutting Entry",
                "fieldname": "rm_transfer_cum_cutting",
                "fieldtype": "Float",
                "width": 180,
            },
            {
                "label": "Material Transfer for Manufacture",
                "fieldname": "material_transfer_for_manufacture",
                "fieldtype": "Float",
                "width": 200,
            },
            {
                "label": "Send to Subcontractor (Out)",
                "fieldname": "send_to_subcontractor_out",
                "fieldtype": "Float",
                "width": 180,
            },
            {
                "label": "FG Free Length Transfer cum Cutting Entry",
                "fieldname": "fg_free_length_transfer",
                "fieldtype": "Float",
                "width": 220,
            },
            {
                "label": "Purchase Receipt (Out)",
                "fieldname": "purchase_receipt_out",
                "fieldtype": "Float",
                "width": 160,
            },
            {
                "label": "Material Issue",
                "fieldname": "material_issue",
                "fieldtype": "Float",
                "width": 130,
            },
            {
                "label": "Manufacture (Consumption)",
                "fieldname": "manufacture_out",
                "fieldtype": "Float",
                "width": 190,
            },
            {
                "label": "Repack (Consumption)",
                "fieldname": "repack_out",
                "fieldtype": "Float",
                "width": 170,
            },
            {
                "label": "Subcontract Issue",
                "fieldname": "subcontract_issue_out",
                "fieldtype": "Float",
                "width": 160,
            },
            {
                "label": "Purchase Invoice (Out)",
                "fieldname": "purchase_invoice_out",
                "fieldtype": "Float",
                "width": 160,
            },

            {
                "label": "Total Outward",
                "fieldname": "total_outward",
                "fieldtype": "Float",
                "width": 130,
            },
            {
                "label": "Closing Balance",
                "fieldname": "closing_balance",
                "fieldtype": "Float",
                "width": 130,
            },

            # {
            #     "label": "Purchase", 
            #     "fieldname": "purchase", 
            #     "fieldtype": "Float",
            #     "width": 120
            #    },
            # {
            #     "label": "Manufacturer",
            #     "fieldname": "manufacturer",
            #     "fieldtype": "Float",
            #     "width": 120
            # },
            # {
            # 	"label": _("Outward"),
            # 	"fieldname": "out_qty",
            # 	"fieldtype": "Float",
            # 	"width": 80,
            # 	"convertible": "qty",
            # },
            # {
            #     "label": "Sales",
            #     "fieldname": "sales", 
            #     "fieldtype": "Float",
            #     "width": 120
            # },
            
           
            #  {
            #     "label": "Consumption",
            #     "fieldname": "consumption",
            #     "fieldtype": "Float",
            #     "width": 120
            #   },
            
        
            # {
            #     "label": _("Balance Qty"),
            #     "fieldname": "qty_after_transaction",
            #     "fieldtype": "Float",
            #     "width": 100,
            #     "convertible": "qty",
            # },
            # {
            # 	"label": _("Warehouse"),
            # 	"fieldname": "warehouse",
            # 	"fieldtype": "Link",
            # 	"options": "Warehouse",
            # 	"width": 150,
            # },
            # {
            #     "label": _("Item Group"),
            #     "fieldname": "item_group",
            #     "fieldtype": "Link",
            #     "options": "Item Group",
            #     "width": 100,
            # },
            # {
            #     "label": _("Brand"),
            #     "fieldname": "brand",
            #     "fieldtype": "Link",
            #     "options": "Brand",
            #     "width": 100,
            # },
            # {"label": _("Description"), "fieldname": "description", "width": 200},
            # {
            #     "label": _("Incoming Rate"),
            #     "fieldname": "incoming_rate",
            #     "fieldtype": "Currency",
            #     "width": 110,
            #     "options": "Company:company:default_currency",
            #     "convertible": "rate",
            # },
            # {
            #     "label": _("Avg Rate (Balance Stock)"),
            #     "fieldname": "valuation_rate",
            #     "fieldtype": filters.valuation_field_type,
            #     "width": 180,
            #     "options": "Company:company:default_currency"
            #     if filters.valuation_field_type == "Currency"
            #     else None,
            #     "convertible": "rate",
            # },
            # {
            #     "label": _("Valuation Rate"),
            #     "fieldname": "in_out_rate",
            #     "fieldtype": filters.valuation_field_type,
            #     "width": 140,
            #     "options": "Company:company:default_currency"
            #     if filters.valuation_field_type == "Currency"
            #     else None,
            #     "convertible": "rate",
            # },
            # {
            #     "label": _("Balance Value"),
            #     "fieldname": "stock_value",
            #     "fieldtype": "Currency",
            #     "width": 110,
            #     "options": "Company:company:default_currency",
            # },
            # {
            #     "label": _("Value Change"),
            #     "fieldname": "stock_value_difference",
            #     "fieldtype": "Currency",
            #     "width": 110,
            #     "options": "Company:company:default_currency",
            # },
            # {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
            # {
            # 	"label": _("Voucher #"),
            # 	"fieldname": "voucher_no",
            # 	"fieldtype": "Dynamic Link",
            # 	"options": "voucher_type",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Batch"),
            # 	"fieldname": "batch_no",
            # 	"fieldtype": "Link",
            # 	"options": "Batch",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Serial No"),
            # 	"fieldname": "serial_no",
            # 	"fieldtype": "Link",
            # 	"options": "Serial No",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Serial and Batch Bundle"),
            # 	"fieldname": "serial_and_batch_bundle",
            # 	"fieldtype": "Link",
            # 	"options": "Serial and Batch Bundle",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Project"),
            # 	"fieldname": "project",
            # 	"fieldtype": "Link",
            # 	"options": "Project",
            # 	"width": 100,
            # },
            # {
            # 	"label": _("Company"),
            # 	"fieldname": "company",
            # 	"fieldtype": "Link",
            # 	"options": "Company",
            # 	"width": 110,
            # },
        ]
    )

    return columns


def get_stock_ledger_entries(filters, items):
    from_date = get_datetime(filters.from_date + " 00:00:00")
    to_date = get_datetime(filters.to_date + " 23:59:59")

    sle = frappe.qb.DocType("Stock Ledger Entry")
    query = (
        frappe.qb.from_(sle)
        .select(
            sle.item_code,
            sle.posting_datetime.as_("date"),
            sle.warehouse,
            sle.posting_date,
            sle.posting_time,
            sle.actual_qty,
            sle.incoming_rate,
            sle.valuation_rate,
            sle.company,
            sle.voucher_type,
            sle.qty_after_transaction,
            sle.stock_value_difference,
            sle.serial_and_batch_bundle,
            sle.voucher_no,
            sle.stock_value,
            sle.batch_no,
            sle.serial_no,
            sle.project,
        )
        .where((sle.docstatus < 2) & (sle.is_cancelled == 0) & (sle.posting_datetime[from_date:to_date]))
        .orderby(sle.posting_datetime)
        .orderby(sle.creation)
    )

    inventory_dimension_fields = get_inventory_dimension_fields()
    if inventory_dimension_fields:
        for fieldname in inventory_dimension_fields:
            query = query.select(fieldname)
            if fieldname in filters and filters.get(fieldname):
                query = query.where(sle[fieldname].isin(filters.get(fieldname)))

    if items:
        query = query.where(sle.item_code.isin(items))

    for field in ["voucher_no", "project", "company"]:
        if filters.get(field) and field not in inventory_dimension_fields:
            query = query.where(sle[field] == filters.get(field))

    if filters.get("batch_no"):
        bundles = get_serial_and_batch_bundles(filters)

        if bundles:
            query = query.where(
                (sle.serial_and_batch_bundle.isin(bundles)) | (sle.batch_no == filters.batch_no)
            )
        else:
            query = query.where(sle.batch_no == filters.batch_no)

    query = apply_warehouse_filter(query, sle, filters)

    return query.run(as_dict=True)


def get_serial_and_batch_bundles(filters):
    SBB = frappe.qb.DocType("Serial and Batch Bundle")
    SBE = frappe.qb.DocType("Serial and Batch Entry")

    query = (
        frappe.qb.from_(SBE)
        .inner_join(SBB)
        .on(SBE.parent == SBB.name)
        .select(SBE.parent)
        .where(
            (SBB.docstatus == 1)
            & (SBB.has_batch_no == 1)
            & (SBB.voucher_no.notnull())
            & (SBE.batch_no == filters.batch_no)
        )
    )

    return query.run(pluck=SBE.parent)


def get_inventory_dimension_fields():
    return [dimension.fieldname for dimension in get_inventory_dimensions()]


def get_items(filters):
    item = frappe.qb.DocType("Item")
    query = frappe.qb.from_(item).select(item.name)
    conditions = []

    if item_code := filters.get("item_code"):
        conditions.append(item.name == item_code)
    else:
        if brand := filters.get("brand"):
            conditions.append(item.brand == brand)
        if item_group := filters.get("item_group"):
            if condition := get_item_group_condition(item_group, item):
                conditions.append(condition)

    items = []
    if conditions:
        for condition in conditions:
            query = query.where(condition)
        items = [r[0] for r in query.run()]

    return items


def get_item_details(items, sl_entries, include_uom):
    item_details = {}
    if not items:
        items = list(set(d.item_code for d in sl_entries))

    if not items:
        return item_details

    item = frappe.qb.DocType("Item")
    query = (
        frappe.qb.from_(item)
        .select(item.name, item.item_name, item.description, item.item_group, item.brand, item.stock_uom)
        .where(item.name.isin(items))
    )

    if include_uom:
        ucd = frappe.qb.DocType("UOM Conversion Detail")
        query = (
            query.left_join(ucd)
            .on((ucd.parent == item.name) & (ucd.uom == include_uom))
            .select(ucd.conversion_factor)
        )

    res = query.run(as_dict=True)

    for item in res:
        item_details.setdefault(item.name, item)

    return item_details


def get_sle_conditions(filters):
    conditions = []
    if filters.get("warehouse"):
        warehouse_condition = get_warehouse_condition(filters.get("warehouse"))
        if warehouse_condition:
            conditions.append(warehouse_condition)
    if filters.get("voucher_no"):
        conditions.append("voucher_no=%(voucher_no)s")
    if filters.get("batch_no"):
        conditions.append("batch_no=%(batch_no)s")
    if filters.get("project"):
        conditions.append("project=%(project)s")

    for dimension in get_inventory_dimensions():
        if filters.get(dimension.fieldname):
            conditions.append(f"{dimension.fieldname} in %({dimension.fieldname})s")

    return "and {}".format(" and ".join(conditions)) if conditions else ""


def get_opening_balance_from_batch(filters, columns, sl_entries):
    query_filters = {
        "batch_no": filters.batch_no,
        "docstatus": 1,
        "is_cancelled": 0,
        "posting_date": ("<", filters.from_date),
        "company": filters.company,
    }

    for fields in ["item_code", "warehouse"]:
        if filters.get(fields):
            query_filters[fields] = filters.get(fields)

    opening_data = frappe.get_all(
        "Stock Ledger Entry",
        fields=["sum(actual_qty) as qty_after_transaction", "sum(stock_value_difference) as stock_value"],
        filters=query_filters,
    )[0]

    for field in ["qty_after_transaction", "stock_value", "valuation_rate"]:
        if opening_data.get(field) is None:
            opening_data[field] = 0.0

    table = frappe.qb.DocType("Stock Ledger Entry")
    sabb_table = frappe.qb.DocType("Serial and Batch Entry")
    query = (
        frappe.qb.from_(table)
        .inner_join(sabb_table)
        .on(table.serial_and_batch_bundle == sabb_table.parent)
        .select(
            Sum(sabb_table.qty).as_("qty"),
            Sum(sabb_table.stock_value_difference).as_("stock_value"),
        )
        .where(
            (sabb_table.batch_no == filters.batch_no)
            & (sabb_table.docstatus == 1)
            & (table.posting_date < filters.from_date)
            & (table.is_cancelled == 0)
        )
    )

    for field in ["item_code", "warehouse", "company"]:
        if filters.get(field):
            query = query.where(table[field] == filters.get(field))

    bundle_data = query.run(as_dict=True)

    if bundle_data:
        opening_data.qty_after_transaction += flt(bundle_data[0].qty)
        opening_data.stock_value += flt(bundle_data[0].stock_value)
        if opening_data.qty_after_transaction:
            opening_data.valuation_rate = flt(opening_data.stock_value) / flt(
                opening_data.qty_after_transaction
            )

    return {
        "item_code": _("'Opening'"),
        "qty_after_transaction": opening_data.qty_after_transaction,
        "valuation_rate": opening_data.valuation_rate,
        "stock_value": opening_data.stock_value,
    }


def get_opening_balance(filters, columns, sl_entries):
    if not (filters.item_code and filters.warehouse and filters.from_date):
        return

    from erpnext.stock.stock_ledger import get_previous_sle

    last_entry = get_previous_sle(
        {
            "item_code": filters.item_code,
            "warehouse_condition": get_warehouse_condition(filters.warehouse),
            "posting_date": filters.from_date,
            "posting_time": "00:00:00",
        }
    )

    # check if any SLEs are actually Opening Stock Reconciliation
    for sle in list(sl_entries):
        if (
            sle.get("voucher_type") == "Stock Reconciliation"
            and sle.posting_date == filters.from_date
            and frappe.db.get_value("Stock Reconciliation", sle.voucher_no, "purpose") == "Opening Stock"
        ):
            last_entry = sle
            sl_entries.remove(sle)

    row = {
        "item_code": _("'Opening'"),
        "qty_after_transaction": last_entry.get("qty_after_transaction", 0),
        "valuation_rate": last_entry.get("valuation_rate", 0),
        "stock_value": last_entry.get("stock_value", 0),
    }

    return row


def get_warehouse_condition(warehouse):
    warehouse_details = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"], as_dict=1)
    if warehouse_details:
        return f" exists (select name from `tabWarehouse` wh \
            where wh.lft >= {warehouse_details.lft} and wh.rgt <= {warehouse_details.rgt} and warehouse = wh.name)"

    return ""


def get_item_group_condition(item_group, item_table=None):
    item_group_details = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=1)
    if item_group_details:
        if item_table:
            ig = frappe.qb.DocType("Item Group")
            return item_table.item_group.isin(
                frappe.qb.from_(ig)
                .select(ig.name)
                .where(
                    (ig.lft >= item_group_details.lft)
                    & (ig.rgt <= item_group_details.rgt)
                    & (item_table.item_group == ig.name)
                )
            )
        else:
            return f"item.item_group in (select ig.name from `tabItem Group` ig \
                where ig.lft >= {item_group_details.lft} and ig.rgt <= {item_group_details.rgt} and item.item_group = ig.name)"


def check_inventory_dimension_filters_applied(filters) -> bool:
    for dimension in get_inventory_dimensions():
        if dimension.fieldname in filters and filters.get(dimension.fieldname):
            return True

    return False


