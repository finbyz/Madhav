import frappe

def validate(self,method):
    self.db_set("pending_pcs",self.pieces - self.completed_pcs)