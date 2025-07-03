import frappe

def autoname(doc, method):
    if doc.reference_doctype and doc.reference_document_name:
        company = frappe.db.get_value(doc.reference_doctype, doc.reference_document_name, "company")
        if company == "MADHAV UDYOG PRIVATE LIMITED":
            doc.naming_series = "MUBT.YY.-"
        elif company == "MADHAV STELCO PRIVATE LIMITED":
            doc.naming_series = "MSBT.YY.-"
