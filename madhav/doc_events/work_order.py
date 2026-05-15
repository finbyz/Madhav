import frappe
from frappe.utils import flt


def validate(self,method):
    self.db_set("pending_pcs",flt(self.pieces) - flt(self.completed_pcs))