import frappe
from frappe.utils import getdate, flt

def validate_cash_limit(doc, method):
    # Check only for Supplier with Cash - MUPL
    
    if doc.party_type != "Supplier" or doc.paid_from != "Cash - MUPL":
        return

    if not doc.party:
        frappe.throw("Please select a Party before saving the Payment Entry.")

    # Get is_transporter flag
    is_transporter = frappe.db.get_value("Supplier", doc.party, "is_transporter") or 0

    # Get total paid today for same supplier (excluding current draft/cancelled)
    total_paid_today = frappe.db.sql("""
        SELECT SUM(paid_amount)
        FROM `tabPayment Entry`
        WHERE 
            party_type = 'Supplier'
            AND paid_to = 'Creditors - MUPL'
            AND party = %s
            AND posting_date = %s
            AND name != %s
            AND docstatus < 2
    """, (doc.party, getdate(doc.posting_date), doc.name))
    total_paid_today = flt(total_paid_today[0][0]) if total_paid_today and total_paid_today[0][0] else 0
    total_with_current = total_paid_today + flt(doc.paid_amount)
    # Apply the proper limit
    limit = 35000 if is_transporter else 10000

    if total_with_current > limit:
        frappe.throw(
            f"⚠️ Total Cash (Cash - MUPL) payments for Supplier '{doc.party}' on {getdate(doc.posting_date)} "
            f"exceed ₹{limit:,}. (Total: ₹{total_with_current:,.2f})"
        )
