import frappe
from frappe import _
from frappe.utils import flt
from erpnext.controllers.status_updater import OverAllowanceError


def validate_limit_on_save(self, method):
    frappe.throw("validate_limit_on_save")
    """
    Trigger 'Limit Crossed' over-billing validation during Save for Purchase Invoice.
    Checks amount against linked Purchase Order Item with Accounts Settings allowance.
    """
    # Try the standard engine first (will often not flag on save as PO billed_amt isn't updated yet)
    if hasattr(self, "validate_qty"):
        try:
            self.validate_qty()
        except Exception:
            raise

    over_billing_allowance = (
        flt(frappe.db.get_single_value("Accounts Settings", "over_billing_allowance")) or 0.0
    )

    for d in self.get("items") or []:
        po_detail = d.get("po_detail")
        if not po_detail:
            continue

        po_item = frappe.db.get_value(
            "Purchase Order Item",
            po_detail,
            ["parent", "item_code", "amount"],
            as_dict=True,
        )
        if not po_item:
            continue

        po_amount = flt(po_item.get("amount") or 0.0, d.precision("amount"))
        if po_amount <= 0:
            continue

        # Sum already billed amount on other PIs (draft + submitted), exclude this invoice
        already_billed = frappe.db.sql(
            """
            SELECT COALESCE(SUM(pii.amount), 0)
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pii.po_detail = %s
              AND pi.docstatus < 2
              AND NOT (pii.parent = %s)
            """,
            (po_detail, self.name or ""),
        )[0][0]

        proposed_total = flt(already_billed) + flt(d.get("amount") or 0.0)
        max_allowed = po_amount * (100.0 + over_billing_allowance) / 100.0

        if proposed_total > max_allowed + 1e-9:
            reduce_by = proposed_total - max_allowed
            msg = _(
                "This document is over limit by {0} for item {1}. "
                "Are you making another {2} against the same {3}?"
            ).format(
                frappe.bold(f"{flt(reduce_by, d.precision('amount'))} Amount"),
                frappe.bold(d.get("item_code")),
                frappe.bold(_("Purchase Invoice")),
                frappe.bold(_("Purchase Order")),
            )
            action_msg = _(
                'To allow over billing, update "Over Billing Allowance" in Accounts Settings or the Item.'
            )
            frappe.throw(
                msg + "<br><br>" + action_msg,
                OverAllowanceError,
                title=_("Limit Crossed"),
            )
