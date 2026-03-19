import frappe
def execute():
    fields = frappe.get_meta("Batch").fields
    for f in fields:
        print(f"{f.fieldname}: {f.fieldtype}")
