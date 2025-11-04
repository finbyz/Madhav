import frappe
from frappe.utils import getdate, flt

def validate_cash_limit(doc, method):
    # Run only for Supplier, Cash account, and Pay type
    if doc.party_type != "Supplier" or doc.payment_type != "Pay":
        return

    if not doc.paid_from or not doc.party:
        frappe.throw("Please select both Party and Paid From account before saving the Payment Entry.")

    # Get company-specific Cash and Creditors accounts
    cash_account = frappe.db.get_value("Account", {"company": doc.company, "account_type": "Cash"})
    creditors_account = frappe.db.get_value("Account", {"company": doc.company, "account_type": "Payable"})

    # Ensure we only check if payment is from Cash
    if doc.paid_from != cash_account:
        return

    # Get is_transporter flag
    is_transporter = frappe.db.get_value("Supplier", doc.party, "is_transporter") or 0

    # Get total paid today for same supplier (excluding current draft/cancelled)
    total_paid_today = frappe.db.sql("""
        SELECT SUM(paid_amount)
        FROM `tabPayment Entry`
        WHERE 
            party_type = 'Supplier'
            AND paid_from = %s
            AND party = %s
            AND company = %s
            AND posting_date = %s
            AND name != %s
            AND docstatus < 2
    """, (cash_account, doc.party, doc.company, getdate(doc.posting_date), doc.name))

    total_paid_today = flt(total_paid_today[0][0]) if total_paid_today and total_paid_today[0][0] else 0
    total_with_current = total_paid_today + flt(doc.paid_amount)

    # Apply the limit
    limit = 35000 if is_transporter else 10000

    if total_with_current > limit:
        frappe.throw(
            f"⚠️ Total Cash payments for Supplier '{doc.party}' in company '{doc.company}' "
            f"on {getdate(doc.posting_date)} exceed ₹{limit:,})"
        )
