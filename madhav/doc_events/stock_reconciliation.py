import frappe
from frappe.utils import flt


def on_submit(self, method=None):
    for row in self.items:
        if not row.delivery_note_ref:
            continue

        frappe.db.sql(
            """
            UPDATE `tabDelivery Note Item`
            SET qty = %s,
                incoming_rate = %s
            WHERE parent = %s
            AND item_code = %s
            AND IFNULL(batch_no, '') = %s
        """,
            (
                row.qty,
                row.valuation_rate,
                row.delivery_note_ref,
                row.item_code,
                row.batch_no or "",
            ),
        )


def validate(self, method=None):

    for row in self.items:
        if row.delivery_note_ref:
            total_amount = flt(row.amount)

            if not row.current_rate:
                row.current_rate = row.current_valuation_rate or row.valuation_rate

            diff_qty = flt(row.difference_qty)
            new_qty = flt(row.current_qty) + diff_qty
            if new_qty > 0:
                row.qty = new_qty
                row.valuation_rate = row.current_amount / row.qty

            # row.amount = total_amount
