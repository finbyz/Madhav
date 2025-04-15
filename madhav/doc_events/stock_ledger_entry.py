import frappe
from frappe.utils import now




def convert_item_quantity(item_code, from_uom, to_uom, qty):
    item = frappe.get_doc("Item", item_code)
    from_factor = None
    to_factor = None

    for row in item.uoms:
        if row.uom == from_uom:
            from_factor = row.conversion_factor
        if row.uom == to_uom:
            to_factor = row.conversion_factor

    if from_factor is None:
        frappe.throw(f"UOM '{from_uom}' not found for item {item_code}")
    if to_factor is None:
        frappe.throw(f"UOM '{to_uom}' not found for item {item_code}")

    converted_qty = to_factor * qty / from_factor

    return converted_qty

def after_insert(self, method):
    required_stock_in_pieces = frappe.db.get_value("Item", self.item_code, "required_stock_in_pieces")
    if not required_stock_in_pieces:
        return
    psle = frappe.get_doc({
        "doctype" : "Piece Stock Ledger Entry",
        "item_code": self.item_code,
        "warehouse": self.warehouse,
        "posting_date": self.posting_date,
        "posting_time": self.posting_time,
        "voucher_type": self.voucher_type,
        "voucher_no": self.voucher_no,
        "actual_qty": convert_item_quantity(self.item_code, self.stock_uom, "Piece", self.actual_qty),
        "company": self.company,
        "unit_of_measure": "Piece",
        "is_cancelled" : self.is_cancelled,
        "docstatus" : self.docstatus
    }) 
    psle.save()
    
    if psle.is_cancelled:
        frappe.db.sql(
            """update `tabPiece Stock Ledger Entry` set is_cancelled=1,
            modified=%s, modified_by=%s
            where voucher_type=%s and voucher_no=%s and is_cancelled = 0""",
            (now(), frappe.session.user, self.voucher_type, self.voucher_no),
        )
