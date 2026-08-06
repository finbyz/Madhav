import frappe
from frappe.utils import flt


def validate(self,method):
    self.db_set("pending_pcs",flt(self.pieces) - flt(self.completed_pcs))
    self.db_set("pending_qty",flt(self.qty) - flt(self.produced_qty))

def update_so_pieces_from_work_order(doc, method=None):

    if not doc.sales_order_item:
        return

    # Existing SO values
    so_item = frappe.db.get_value(
        "Sales Order Item",
        doc.sales_order_item,
        ["pieces", "work_order_pieces"],
        as_dict=True
    )

    current_so_pieces = so_item.pieces or 0
    existing_wo_pieces = so_item.work_order_pieces or 0

    # Current WO pieces (parent field in Work Order)
    current_wo_pieces = doc.pieces or 0

    # Remaining SO pieces
    new_so_pieces = current_so_pieces - current_wo_pieces

    # Total WO pieces
    new_wo_total = existing_wo_pieces + current_wo_pieces

    frappe.db.set_value(
        "Sales Order Item",
        doc.sales_order_item,
        {
           
            "work_order_pieces": new_wo_total
        },
        update_modified=False
    )
    

def revert_so_pieces_from_work_order(doc, method=None):

    # Only WO from PP
    if not doc.production_plan:
        return

    if not doc.sales_order_item:
        return

    so_item = frappe.db.get_value(
        "Sales Order Item",
        doc.sales_order_item,
        ["pieces", "work_order_pieces"],
        as_dict=True
    )

    current_so_pieces = so_item.pieces or 0
    existing_wo_pieces = so_item.work_order_pieces or 0

    cancelled_wo_pieces = doc.pieces or 0

    restored_so_pieces = current_so_pieces + cancelled_wo_pieces
    new_wo_total = existing_wo_pieces - cancelled_wo_pieces

    frappe.db.set_value(
        "Sales Order Item",
        doc.sales_order_item,
        {
            "work_order_pieces": new_wo_total
        },
        update_modified=False
    )