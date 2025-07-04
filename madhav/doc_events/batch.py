import frappe
from frappe.model.naming import make_autoname

def autoname(doc, method):
    if doc.reference_doctype and doc.reference_name:
        
        company = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "company")
        if company == "MADHAV UDYOG PRIVATE LIMITED":
            doc.naming_series = "MUBT.-"
        elif company == "MADHAV STELCO PRIVATE LIMITED":
            doc.naming_series = "MSBT.-"

    # Actually generate the name using the selected naming_series
    doc.name = make_autoname(doc.naming_series)
    doc.batch_id = doc.name