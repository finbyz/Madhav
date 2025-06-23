import frappe
from frappe.utils import now




# def convert_item_quantity(item_code, from_uom, to_uom, qty):
#     item = frappe.get_doc("Item", item_code)
#     from_factor = None
#     to_factor = None

#     for row in item.uoms:
#         if row.uom == from_uom:
#             from_factor = row.conversion_factor
#         if row.uom == to_uom:
#             to_factor = row.conversion_factor

#     if from_factor is None:
#         frappe.throw(f"UOM '{from_uom}' not found for item {item_code}")
#     if to_factor is None:
#         frappe.throw(f"UOM '{to_uom}' not found for item {item_code}")

#     converted_qty = to_factor * qty / from_factor

#     return converted_qty


# def create_piece_stock_ledger_entry(self, method):
#     required_stock_in_pieces = frappe.db.get_value("Item", self.item_code, "required_stock_in_pieces")
#     if not required_stock_in_pieces:
#         return
    
#     psle = frappe.get_doc({
#         "doctype" : "Piece Stock Ledger Entry",
#         "item_code": self.item_code,
#         "warehouse": self.warehouse,
#         "posting_date": self.posting_date,
#         "posting_time": self.posting_time,
#         "voucher_type": self.voucher_type,
#         "voucher_no": self.voucher_no,
#         "serial_and_batch_bundle": self.serial_and_batch_bundle,
#         "actual_qty": self.pieces_qty,
#         "company": self.company,
#         "unit_of_measure": "Piece",
#         "is_cancelled" : self.is_cancelled,
#         "batch_no": self.batch_no,
#         "docstatus" : self.docstatus
#     }) 
#     psle.save()
        
#     if psle.is_cancelled:
#         frappe.db.sql(
#             """update `tabPiece Stock Ledger Entry` set is_cancelled=1,
#             modified=%s, modified_by=%s
#             where voucher_type=%s and voucher_no=%s and is_cancelled = 0""",
#             (now(), frappe.session.user, self.voucher_type, self.voucher_no),
#         )

import frappe

def create_piece_stock_ledger_entry(sle_doc, method):
    # Check if piece_qty exists in the parent document, else skip
    piece_qty = get_piece_qty(sle_doc)
    
    if piece_qty is None:
        return

    # Determine if the piece_qty should be negative based on context
    piece_qty = adjust_piece_qty_sign(sle_doc, piece_qty)
    # Create the new Piece Stock Ledger Entry
    piece_doc = frappe.new_doc("Piece Stock Ledger Entry")
    piece_doc.update({
        "posting_date": sle_doc.posting_date,
        "posting_time": sle_doc.posting_time,
        "item_code": sle_doc.item_code,
        "warehouse": sle_doc.warehouse,
        "voucher_type": sle_doc.voucher_type,
        "voucher_no": sle_doc.voucher_no,
        # "voucher_detail_no": sle_doc.voucher_detail_no,
        # "stock_uom": sle_doc.stock_uom,
        # "piece_qty": piece_qty,
        "serial_and_batch_bundle": sle_doc.serial_and_batch_bundle,
        "actual_qty": piece_qty,
        "incoming_rate": sle_doc.incoming_rate,
        "company": sle_doc.company,
        "unit_of_measure": "Piece",
        "is_cancelled": sle_doc.is_cancelled,
         "batch_no": sle_doc.batch_no,
        "docstatus" : sle_doc.docstatus
        # "stock_value": sle_doc.stock_value,
        # "stock_value_difference": sle_doc.stock_value_difference,
    })
    piece_doc.insert(ignore_permissions=True)

def get_piece_qty(sle_doc):
    
    """Try to fetch piece from relevant child table"""
    voucher_type = sle_doc.voucher_type
    detail_no = sle_doc.voucher_detail_no
    if not voucher_type or not detail_no:
        return None

    # Mapping of parent doctype -> child doctype
    mapping = {
        "Purchase Receipt": "Purchase Receipt Item",
        "Purchase Invoice": "Purchase Invoice Item",
        "Sales Invoice": "Sales Invoice Item",
        "Delivery Note": "Delivery Note Item",
        "Stock Entry": "Stock Entry Detail"
    }

    child_doctype = mapping.get(voucher_type)
    if not child_doctype:
        return None

    return frappe.db.get_value(child_doctype, detail_no, "pieces")
    
    # try:
    #     child_doctype = frappe.db.get_value("DocField", {
    #         "parent": sle_doc.voucher_type,
    #         "fieldname": "items"
    #     }, "options")
        
    #     if not child_doctype:
    #         return None

    #     piece_qty = frappe.db.get_value(child_doctype, sle_doc.voucher_detail_no, "pieces")
    #     return piece_qty
    # except Exception as e:
    #     frappe.log_error(f"Error fetching piece_qty: {e}")
    #     return None

def adjust_piece_qty_sign(sle_doc, piece_qty):
    """Make piece_qty negative for outgoing transactions"""
    if sle_doc.voucher_type == "Delivery Note":
        return -1 * abs(piece_qty)
    
    if sle_doc.voucher_type == "Sales Invoice":
        return -1 * abs(piece_qty)

    if sle_doc.voucher_type == "Stock Entry":
        # Get Stock Entry purpose
        purpose = frappe.db.get_value("Stock Entry", sle_doc.voucher_no, "purpose")

        if purpose in ["Material Issue", "Send to Subcontractor"]:
            return -1 * abs(piece_qty)
        elif purpose in ["Material Receipt", "Receive from Subcontractor"]:
            return abs(piece_qty)
        else:
            # For Material Transfer and others:
            # Incoming warehouse gets positive, outgoing gets negative
            return piece_qty if sle_doc.actual_qty > 0 else -1 * abs(piece_qty)

    # Default: assume incoming
    return abs(piece_qty)
