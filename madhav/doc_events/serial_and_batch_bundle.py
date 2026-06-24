import frappe

def before_cancel(self,method):
    delink_serial_and_batch_bundle(self)

def delink_serial_and_batch_bundle(self):
    sles = frappe.get_all("Piece Stock Ledger Entry", filters={"serial_and_batch_bundle": self.name})

    for sle in sles:
        frappe.db.set_value("Piece Stock Ledger Entry", sle.name, "serial_and_batch_bundle", None)