import frappe
from frappe.utils import now



def after_insert(self, method):
    if not self.stock_uom == "Piece":
        return
    try:
        psle = frappe.get_doc({
            "doctype" : "Piece Stock Ledger Entry",
            "item_code": self.item_code,
            "warehouse": self.warehouse,
            "posting_date": self.posting_date,
            "posting_time": self.posting_time,
            "voucher_type": self.voucher_type,
            "voucher_no": self.voucher_no,
            "actual_qty": self.actual_qty,
            "company": self.company,
            "unit_of_measure": self.stock_uom,
            "stock_ledger_entry": self.name,
            "is_cancelled" : self.is_cancelled
        }) 
        psle.save()
        
        if psle.is_cancelled:
            frappe.db.sql(
                """update `tabPiece Stock Ledger Entry` set is_cancelled=1,
                modified=%s, modified_by=%s
                where voucher_type=%s and voucher_no=%s and is_cancelled = 0""",
                (now(), frappe.session.user, self.voucher_type, self.voucher_no),
            )
    except Exception as e:
        frappe.log_error(
            "Failed Piece Stock Ledger Entry Creation",
            frappe.get_traceback(with_context=True)
        )
