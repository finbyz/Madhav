from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def _get_item_weight_per_meter(item_code: str | None) -> float:
	if not item_code:
		return 0

	return flt(frappe.db.get_value("Item", item_code, "weight_per_meter"))


def _normalize_range(min_value: float | None = None, max_value: float | None = None) -> tuple[float | None, float | None]:
	min_bound = flt(min_value) if min_value not in (None, "") else None
	max_bound = flt(max_value) if max_value not in (None, "") else None

	if min_bound is not None and max_bound is not None and min_bound > max_bound:
		min_bound, max_bound = max_bound, min_bound

	return min_bound, max_bound


def _get_batch_constraints(
	voucher_type: str | None, voucher_detail_no: str | None, item_code: str | None = None
) -> frappe._dict:
	constraints = frappe._dict(
		{
			"min_length": None,
			"max_length": None,
			"min_section_weight": None,
			"max_section_weight": None,
		}
	)

	if voucher_type != "Sales Order" or not voucher_detail_no:
		return constraints

	if not frappe.db.has_column("Sales Order Item", "length_size"):
		return constraints

	length_size = flt(frappe.db.get_value("Sales Order Item", voucher_detail_no, "length_size"))
	item_code = item_code or frappe.db.get_value("Sales Order Item", voucher_detail_no, "item_code")
	section_weight = _get_item_weight_per_meter(item_code)
	flag_constraints = (
		getattr(frappe.flags, "stock_reservation_item_ranges", {}).get(voucher_detail_no, {})
		if getattr(frappe.flags, "stock_reservation_item_ranges", None)
		else {}
	)

	min_length, max_length = _normalize_range(
		length_size if length_size > 0 else None, flag_constraints.get("max_length")
	)
	min_section_weight, max_section_weight = _normalize_range(
		section_weight if section_weight > 0 else None,
		flag_constraints.get("max_section_weight"),
	)

	constraints.update(
		{
			"min_length": min_length,
			"max_length": max_length,
			"min_section_weight": min_section_weight,
			"max_section_weight": max_section_weight,
		}
	)
	return constraints


def _get_eligible_batches(
	batch_nos,
	min_length=None,
	max_length=None,
	min_section_weight=None,
	max_section_weight=None,
):

	if not batch_nos:
		return set()

	# normalize values
	min_length = flt(min_length) if min_length not in (None, "") else None
	max_length = flt(max_length) if max_length not in (None, "") else None
	min_section_weight = flt(min_section_weight) if min_section_weight not in (None, "") else None
	max_section_weight = flt(max_section_weight) if max_section_weight not in (None, "") else None

	filters = {
		"name": ["in", list(set(batch_nos))]
	}

	# length filters
	if frappe.db.has_column("Batch", "average_length"):
		if min_length is not None:
			filters["average_length"] = [">=", min_length]
		if max_length is not None:
			filters["average_length"] = ["<=", max_length]

	# section weight filters
	if frappe.db.has_column("Batch", "section_weight"):
		if min_section_weight is not None:
			filters["section_weight"] = [">=", min_section_weight]
		if max_section_weight is not None:
			filters["section_weight"] = ["<=", max_section_weight]
		return set(
			frappe.get_all(
				"Batch",
				filters=filters,
				pluck="name",
			)
		)

def _get_filtered_available_qty(item_code: str, warehouse: str, constraints: frappe._dict) -> float:
	from erpnext.stock.doctype.batch.batch import get_available_batches

	kwargs = frappe._dict(
		{
			"item_code": item_code,
			"warehouse": warehouse,
			"qty": 0,
			"based_on": frappe.db.get_single_value("Stock Settings", "pick_serial_and_batch_based_on"),
		}
	)
	batchwise_qty = get_available_batches(kwargs)
	if not batchwise_qty:
		return 0

	eligible_batches = _get_eligible_batches(
		list(batchwise_qty.keys()),
		min_length=constraints.get("min_length"),
		max_length=constraints.get("max_length"),
		min_section_weight=constraints.get("min_section_weight"),
		max_section_weight=constraints.get("max_section_weight"),
	)
	return sum(flt(qty) for batch_no, qty in batchwise_qty.items() if batch_no in eligible_batches)


def _get_batch_debug_details(item_code: str, warehouse: str, constraints: frappe._dict) -> frappe._dict:
	from erpnext.stock.doctype.batch.batch import get_available_batches

	kwargs = frappe._dict(
		{
			"item_code": item_code,
			"warehouse": warehouse,
			"qty": 0,
			"based_on": frappe.db.get_single_value("Stock Settings", "pick_serial_and_batch_based_on"),
		}
	)
	batchwise_qty = get_available_batches(kwargs) or {}
	available_batch_nos = list(batchwise_qty.keys())
	eligible_batch_nos = list(
		_get_eligible_batches(
			available_batch_nos,
			min_length=constraints.get("min_length"),
			max_length=constraints.get("max_length"),
			min_section_weight=constraints.get("min_section_weight"),
			max_section_weight=constraints.get("max_section_weight"),
		)
	)

	return frappe._dict(
		{
			"warehouse": warehouse,
			"available_batches": available_batch_nos,
			"eligible_batches": eligible_batch_nos,
			"batchwise_qty": batchwise_qty,
		}
	)


def _filter_sb_entries_by_batch_constraints(doc, constraints: frappe._dict) -> None:
	if not doc.get("has_batch_no") or not doc.get("sb_entries"):
		return

	batch_nos = [d.batch_no for d in doc.sb_entries if d.batch_no]
	eligible_batches = _get_eligible_batches(
		batch_nos,
		min_length=constraints.get("min_length"),
		max_length=constraints.get("max_length"),
		min_section_weight=constraints.get("min_section_weight"),
		max_section_weight=constraints.get("max_section_weight"),
	)

	target_qty = abs(flt(doc.get("reserved_qty")))
	target_pieces = abs(flt(doc.get("pieces")))

	picked_qty = 0
	picked_pieces = 0
	filtered_rows = []

	for entry in doc.sb_entries:
		if entry.batch_no and entry.batch_no in eligible_batches:

			qty = 1 if doc.get("has_serial_no") else flt(entry.qty)
			pieces = flt(entry.get("pieces")) or 0

			if target_qty > 0:
				if picked_qty >= target_qty:
					continue

			if target_pieces > 0:
				if picked_pieces >= target_pieces:
					continue

			if target_qty > 0 and not doc.get("has_serial_no"):
				qty = min(qty, target_qty - picked_qty)

			if target_pieces > 0:
				pieces = min(pieces, target_pieces - picked_pieces)

			if qty <= 0:
				continue

			filtered_rows.append(
				{
					"serial_no": entry.serial_no,
					"batch_no": entry.batch_no,
					"qty": qty,
					"pieces": pieces,
					"warehouse": entry.warehouse or doc.warehouse,
				}
			)

			picked_qty += qty
			picked_pieces += pieces
		
	doc.set("sb_entries", [])
	for row in filtered_rows:
		doc.append("sb_entries", row)


def create_stock_reservation_entries_for_so_items(
	sales_order,
	items_details=None,
	from_voucher_type=None,
	notify=True,
):
	"""Patch ERPNext creation flow to apply per-item batch constraints."""
	items_details = list(items_details or [])
	frappe.flags.stock_reservation_item_ranges = {}

	try:
		if items_details:
			updated_items_details = []
			filtered_out_items = []
			for row in items_details:
				row = frappe._dict(row)
				so_item = frappe.get_doc("Sales Order Item", row.get("sales_order_item"))
				warehouse = row.get("warehouse") or so_item.warehouse
				has_batch_no = frappe.get_cached_value("Item", so_item.item_code, "has_batch_no")
				frappe.flags.stock_reservation_item_ranges[so_item.name] = {
					"max_length": row.get("max_length"),
					"max_section_weight": row.get("max_section_weight"),
				}
				constraints = _get_batch_constraints("Sales Order", so_item.name, so_item.item_code)

				if has_batch_no:
					eligible_stock_qty = _get_filtered_available_qty(
						so_item.item_code, warehouse, constraints
					)
					if eligible_stock_qty <= 0:
						debug_details = _get_batch_debug_details(
							so_item.item_code, warehouse, constraints
						)
						filtered_out_items.append(
							_(
								"Row #{0}: No eligible batch found for Item {1}. Warehouse: {2}. Length Range: {3} to {4}. Section Weight Range: {5} to {6}. Available Batches: {7}. Eligible Batches: {8}."
							).format(
								so_item.idx,
								frappe.bold(so_item.item_code),
								frappe.bold(debug_details.warehouse or "-"),
								frappe.bold(constraints.get("min_length") if constraints.get("min_length") is not None else "-"),
								frappe.bold(constraints.get("max_length") if constraints.get("max_length") is not None else "-"),
								frappe.bold(constraints.get("min_section_weight") if constraints.get("min_section_weight") is not None else "-"),
								frappe.bold(constraints.get("max_section_weight") if constraints.get("max_section_weight") is not None else "-"),
								frappe.bold(", ".join(debug_details.available_batches) or "None"),
								frappe.bold(", ".join(debug_details.eligible_batches) or "None"),
							)
						)
						continue

					conversion_factor = flt(row.get("conversion_factor")) or flt(so_item.conversion_factor) or 1
					requested_qty = flt(row.get("qty_to_reserve"))
					if from_voucher_type not in ["Pick List", "Purchase Receipt"]:
						requested_qty = requested_qty * conversion_factor

					requested_qty = min(requested_qty, eligible_stock_qty)
					if requested_qty <= 0:
						filtered_out_items.append(
							_(
								"Row #{0}: Quantity to reserve for Item {1} becomes 0 after applying the row range."
							).format(
								so_item.idx,
								frappe.bold(so_item.item_code),
							)
						)
						continue

					row.qty_to_reserve = (
						requested_qty
						if from_voucher_type in ["Pick List", "Purchase Receipt"]
						else requested_qty / conversion_factor
					)

				updated_items_details.append(row)

			items_details = updated_items_details
			if filtered_out_items:
				frappe.msgprint(
					"<br>".join(filtered_out_items),
					title=_("Stock Reservation"),
					indicator="orange",
				)

			if not items_details:
				return
		else:
			for so_item in sales_order.get("items") or []:
				if not so_item.get("reserve_stock"):
					continue

				has_batch_no = frappe.get_cached_value("Item", so_item.item_code, "has_batch_no")
				constraints = _get_batch_constraints("Sales Order", so_item.name, so_item.item_code)

				if has_batch_no:
					so_item.qty_to_reserve = _get_filtered_available_qty(
						so_item.item_code, so_item.warehouse, constraints
					)

		return _ORIGINAL_CREATE_STOCK_RESERVATION_ENTRIES_FOR_SO_ITEMS(
			sales_order=sales_order,
			items_details=items_details or None,
			from_voucher_type=from_voucher_type,
			notify=notify,
		)
	finally:
		frappe.flags.stock_reservation_item_ranges = {}


def _update_sb_entries_custom_fields(doc):
	"""Update custom fields in Serial and Batch Entry rows"""

	if doc.voucher_type != "Sales Order" or not doc.voucher_detail_no:
		return

	# get sales order item
	so_item = frappe.get_doc("Sales Order Item", doc.voucher_detail_no)

	# get item weight
	weight_per_meter = flt(
		frappe.db.get_value("Item", so_item.item_code, "weight_per_meter")
	)

	for row in doc.get("sb_entries", []):
		row.peices = flt(so_item.get("pieces"))
		row.length = flt(so_item.get("length_size"))

		# section weight calculation
		row.section_weight = (
			flt(so_item.get("pieces"))
			* flt(so_item.get("length_size"))
			* weight_per_meter
		) / 1000



def auto_reserve_serial_and_batch(self, based_on=None):
	"""Patch ERPNext auto batch selection to keep only eligible batches by row constraints."""
	_ORIGINAL_AUTO_RESERVE_SERIAL_AND_BATCH(self, based_on=based_on)

	constraints = _get_batch_constraints(self.voucher_type, self.voucher_detail_no, self.item_code)
	_filter_sb_entries_by_batch_constraints(self, constraints)

	_update_sb_entries_custom_fields(self)


from erpnext.stock.doctype.stock_reservation_entry import stock_reservation_entry as _sre_module

_ORIGINAL_CREATE_STOCK_RESERVATION_ENTRIES_FOR_SO_ITEMS = (
	_sre_module.create_stock_reservation_entries_for_so_items
)
_ORIGINAL_AUTO_RESERVE_SERIAL_AND_BATCH = _sre_module.StockReservationEntry.auto_reserve_serial_and_batch
