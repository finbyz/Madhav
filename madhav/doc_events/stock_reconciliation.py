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
                # Preserve value when stock already has a valuation; never wipe to 0
                # when current_amount is missing (e.g. empty warehouse at posting time).
                if flt(row.current_amount):
                    row.valuation_rate = flt(row.current_amount) / new_qty
                elif not flt(row.valuation_rate):
                    row.valuation_rate = (
                        flt(row.current_valuation_rate)
                        or flt(row.current_rate)
                        or flt(frappe.get_cached_value("Item", row.item_code, "valuation_rate"))
                        or 1
                    )

            # row.amount = total_amount
