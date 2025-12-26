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


def validate_pr_rejected_qty_has_return(doc, method=None):
	"""
	Block Purchase Invoice if linked Purchase Receipt has rejected qty
	but no Purchase Return exists against it.
	"""

	# Collect unique Purchase Receipts from PI items
	pr_names = {
		row.purchase_receipt
		for row in doc.items
		if row.purchase_receipt
	}

	if not pr_names:
		return

	for pr_name in pr_names:
		# 1. Check if PR has any rejected qty
		has_rejected_qty = frappe.db.sql(
			"""
			SELECT 1
			FROM `tabPurchase Receipt Item`
			WHERE parent = %s
			  AND IFNULL(rejected_qty, 0) > 0
			LIMIT 1
			""",
			pr_name,
		)

		if not has_rejected_qty:
			continue

		# 2. Check if Purchase Return exists against this PR
		return_pr_exists = frappe.db.exists(
			"Purchase Receipt",
			{
				"is_return": 1,
				"return_against": pr_name,
				"docstatus": ["!=", 2],
			},
		)

		# 3. Block PI save if return PR missing
		if not return_pr_exists:
			frappe.throw(
				_(
					"Cannot create Purchase Invoice.<br>"
					"Purchase Receipt <b>{0}</b> has rejected quantity, "
					"but no Purchase Return exists against it."
				).format(pr_name)
			)