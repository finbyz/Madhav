import frappe
from frappe.utils import flt


def on_submit(self, method=None):
	"""Sync DN item weight after SR for Deliver-as-Qty overage.

	Only update qty / incoming_rate — never pieces (physical PC must stay).
	Match DN rows via Serial and Batch Bundle + batch, not bare item_code
	(same FG can appear on multiple DN lines with different lengths).
	"""
	for row in self.items:
		if not row.delivery_note_ref:
			continue

		dn_item_name = _find_dn_item_for_sr_row(row)
		if not dn_item_name:
			continue

		frappe.db.set_value(
			"Delivery Note Item",
			dn_item_name,
			{
				"qty": flt(row.qty),
				"incoming_rate": flt(row.valuation_rate),
			},
			update_modified=False,
		)


def _find_dn_item_for_sr_row(row):
	"""Resolve the exact DN item this SR row belongs to."""
	dn_name = row.delivery_note_ref
	item_code = row.item_code
	batch_no = row.batch_no or ""

	if batch_no:
		matched = frappe.db.sql(
			"""
			SELECT dni.name
			FROM `tabDelivery Note Item` dni
			INNER JOIN `tabSerial and Batch Entry` sbe
				ON sbe.parent = dni.serial_and_batch_bundle
				AND sbe.parenttype = 'Serial and Batch Bundle'
			WHERE dni.parent = %s
			  AND dni.item_code = %s
			  AND sbe.batch_no = %s
			LIMIT 1
			""",
			(dn_name, item_code, batch_no),
		)
		if matched:
			return matched[0][0]

	# Fallback: unique DN line for this item (no batch / single row)
	names = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": dn_name, "item_code": item_code},
		pluck="name",
	)
	if len(names) == 1:
		return names[0]

	return None


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
