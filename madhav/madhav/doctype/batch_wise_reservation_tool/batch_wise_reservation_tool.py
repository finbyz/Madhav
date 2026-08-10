# Copyright (c) 2026, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
import json
import math
from frappe.model.document import Document
from frappe.utils import flt, nowdate


def floor_qty(value, precision=3):
	"""
	Rounds `value` DOWN to `precision` decimals (never up).

	A tiny epsilon is added before flooring to guard against binary
	float representation errors (e.g. 0.464 sometimes being stored
	internally as 0.46399999999998), which would otherwise cause a
	valid quantity to be floored down to the next lower value.
	"""
	factor = 10 ** precision
	return math.floor((flt(value) * factor) + 1e-6) / factor


class BatchWiseReservationTool(Document):
	def on_submit(self):
		self.create_stock_reservationentries()

	def on_cancel(self):
		self.cancel_stock_reservation_entries()

	def create_stock_reservationentries(self):
		
		if not self.reservation_batches:
			frappe.throw(frappe._("No reservation batches found. Please add batch reservations before submitting."))

		# Collects a summary of rows that were capped (partially reserved)
		# or skipped (nothing available) so we can inform the user once,
		# after all rows have been processed, instead of aborting the
		# whole submission on the first shortfall.
		self._reservation_warnings = []

		# Validate all rows firstcreate_stock_reservation_entries_for_so_items
		for row in self.reservation_batches:
			self.create_fg_stock_reservation(
			item_code=row.item_code,
			warehouse = row.source_warehouse,
			qty = round(row.reserved_qty,3),
			so_qty = row.sales_order_item_qty,
			stock_uom = frappe.db.get_value("Item",row.item_code,"stock_uom"),
			sales_order=row.sales_order,
			sales_order_item=row.sales_order_item,
			batch_no=row.batch_no,
			from_voucher_type = self.doctype,
			from_voucher_no = self.name,
			from_voucher_detail_no = row.name
		)

		if self._reservation_warnings:
			lines = "<br>".join(self._reservation_warnings)
			frappe.msgprint(
				frappe._(
					"Some rows could not be fully reserved due to limited "
					"available stock:<br><br>{0}"
				).format(lines),
				title=frappe._("Partial / Skipped Reservations"),
				indicator="orange",
			)

	def cancel_stock_reservation_entries(self):
		for row in self.reservation_batches:
			sre_name = frappe.db.get_value(
				"Staged Batch Reservations Verification",
				row.name,
				"stock_reservation_entry",
			)
			if sre_name:
				sre = frappe.get_doc("Stock Reservation Entry", sre_name)
				if sre.docstatus == 1:
					sre.cancel()

	def create_fg_stock_reservation(
		self,
		item_code,
		warehouse,
		qty,
		so_qty,
		stock_uom,
		sales_order=None,
		sales_order_item=None,
		batch_no=None,
		from_voucher_type=None,
		from_voucher_no=None,
		from_voucher_detail_no=None,
	):
		from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
			get_available_qty_to_reserve,
		)

		if not sales_order:
			return

		qty = floor_qty(qty, 3)
		so_qty = floor_qty(so_qty, 3)

		if qty <= 0:
			frappe.throw(
				frappe._("Reservation quantity must be greater than zero.")
			)

		# ---------------------------------------------------------
		# BATCH GUARD
		# If a batch was explicitly selected, fail loudly here if the
		# item isn't actually batch-tracked, instead of silently
		# falling through to a qty-only reservation later (which
		# looks like a batch reservation in the UI but isn't one).
		# ---------------------------------------------------------

		if batch_no:
			item_has_batch_no = frappe.get_cached_value(
				"Item", item_code, "has_batch_no"
			)
			if not item_has_batch_no:
				frappe.throw(
					frappe._(
						"Batch {0} was selected for Item {1}, but this Item "
						"does not have 'Has Batch No' enabled. Enable batch "
						"tracking on the Item, or remove the batch selection "
						"for this row."
					).format(
						frappe.bold(batch_no),
						frappe.bold(item_code),
					)
				)

		# ---------------------------------------------------------
		# GET SALES ORDER ITEM
		# ---------------------------------------------------------

		item = frappe.db.get_value(
			"Sales Order Item",
			{
				"parent": sales_order,
				"name": sales_order_item,
				"item_code": item_code,
				"docstatus": 1,
			},
			[
				"name",
				"qty",
				"delivered_qty",
				"stock_reserved_qty",
			],
			as_dict=True,
		)

		if not item:
			frappe.throw(
				frappe._(
					"SO Item {0} not found for Item {1} in Sales Order {2}."
				).format(
					sales_order_item,
					item_code,
					sales_order,
				)
			)

		so_detail = item.name

		# ---------------------------------------------------------
		# ALREADY RESERVED AGAINST THIS SO ITEM
		# ---------------------------------------------------------

		already_reserved_qty = flt(
			frappe.db.sql(
				"""
				SELECT COALESCE(SUM(reserved_qty), 0)
				FROM `tabStock Reservation Entry`
				WHERE
					voucher_type = 'Sales Order'
					AND voucher_no = %s
					AND voucher_detail_no = %s
					AND docstatus = 1
					AND item_code = %s
				""",
				(
					sales_order,
					so_detail,
					item_code,
				),
			)[0][0]
			or 0
		)

		# ---------------------------------------------------------
		# SO AVAILABLE QTY
		# ---------------------------------------------------------

		delivered_qty = flt(item.delivered_qty)

		over_reservation_allowance = flt(
			frappe.db.get_single_value(
				"Stock Settings",
				"over_reservation_allowance",
			)
			or 0
		)

		allowed_so_qty = so_qty * (
			1 + over_reservation_allowance / 100
		)

		so_available_qty = max(
			0,
			floor_qty(
				allowed_so_qty
				- delivered_qty
				- already_reserved_qty,
				3,
			),
		)

		# ---------------------------------------------------------
		# BATCH AVAILABLE QTY
		# ---------------------------------------------------------

		batch_available_qty = None

		if batch_no:
			batch_stock = frappe.db.sql(
				"""
				SELECT
					COALESCE(SUM(sle.actual_qty), 0) AS actual_qty
				FROM `tabStock Ledger Entry` sle
				INNER JOIN `tabSerial and Batch Entry` sbe
					ON sbe.parent = sle.serial_and_batch_bundle
				WHERE
					sle.item_code = %(item_code)s
					AND sle.warehouse = %(warehouse)s
					AND sle.is_cancelled = 0
					AND sbe.batch_no = %(batch_no)s
				""",
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"batch_no": batch_no,
				},
				as_dict=True,
			)

			actual_batch_qty = flt(
				batch_stock[0].actual_qty
				if batch_stock
				else 0
			)

			# -----------------------------------------------------
			# RESERVED QTY FOR THIS BATCH
			# -----------------------------------------------------

			reserved_batch_qty = flt(
				frappe.db.sql(
					"""
					SELECT
						COALESCE(SUM(sbe.qty), 0)
					FROM `tabStock Reservation Entry` sre
					INNER JOIN `tabSerial and Batch Entry` sbe
						ON sbe.parent = sre.name
					WHERE
						sre.docstatus = 1
						AND sre.status IN (
							'Reserved',
							'Partially Reserved',
							'Partially Delivered'
						)
						AND sre.item_code = %(item_code)s
						AND sre.warehouse = %(warehouse)s
						AND sbe.batch_no = %(batch_no)s
					""",
					{
						"item_code": item_code,
						"warehouse": warehouse,
						"batch_no": batch_no,
					},
				)[0][0]
				or 0
			)

			batch_available_qty = max(
				0,
				floor_qty(actual_batch_qty - reserved_batch_qty, 3),
			)

		# ---------------------------------------------------------
		# ITEM + WAREHOUSE LEVEL AVAILABLE QTY (mirrors what core's
		# Stock Reservation Entry.validate_with_allowed_qty() will
		# independently check on submit)
		# ---------------------------------------------------------

		item_level_available_qty = floor_qty(
			get_available_qty_to_reserve(item_code, warehouse), 3
		)

		# ---------------------------------------------------------
		# FINAL AVAILABLE QTY
		# All values are already floored to 3 decimals above, so the
		# minimum of them is guaranteed to be <= the true available
		# qty at every level - no separate safety buffer needed.
		# ---------------------------------------------------------

		candidates = [so_available_qty, item_level_available_qty]

		if batch_available_qty is not None:
			candidates.append(batch_available_qty)

		available_qty_to_reserve = min(candidates)
		usable_qty_to_reserve = max(0, floor_qty(available_qty_to_reserve, 3))

		# ---------------------------------------------------------
		# DEBUG
		# ---------------------------------------------------------

		frappe.log_error(
			title="Stock Reservation Debug",
			message=frappe.as_json(
				{
					"sales_order": sales_order,
					"sales_order_item": so_detail,
					"item_code": item_code,
					"warehouse": warehouse,
					"batch_no": batch_no,
					"requested_qty": qty,
					"so_qty": so_qty,
					"delivered_qty": delivered_qty,
					"already_reserved_qty": already_reserved_qty,
					"over_reservation_allowance": over_reservation_allowance,
					"allowed_so_qty": allowed_so_qty,
					"so_available_qty": so_available_qty,
					"batch_available_qty": batch_available_qty,
					"item_level_available_qty": item_level_available_qty,
					"final_available_qty": available_qty_to_reserve,
					"usable_qty_to_reserve": usable_qty_to_reserve,
				},
				indent=2,
			),
		)

		# ---------------------------------------------------------
		# VALIDATE / AUTO-CAP TO AVAILABLE QTY
		#
		# Instead of hard-failing the entire submission on the first
		# row that exceeds availability, we cap the reservation to
		# whatever is genuinely available and continue. If nothing
		# at all is available, we skip this row (no SRE created) and
		# continue with the rest, rather than aborting the whole
		# document. Every capped/skipped row is collected and shown
		# to the user as a single summary at the end of the submit.
		# ---------------------------------------------------------

		requested_qty = qty

		# Defensive: ensure the warnings list exists even if this method
		# is ever called directly (e.g. from a script) without going
		# through create_stock_reservationentries() first.
		if not hasattr(self, "_reservation_warnings"):
			self._reservation_warnings = []

		if usable_qty_to_reserve <= 0:
			self._reservation_warnings.append(
				frappe._(
					"Row skipped - Item {0} from Batch {1} against Sales Order "
					"{2}: requested {3} {4}, but nothing is currently "
					"available to reserve."
				).format(
					frappe.bold(item_code),
					frappe.bold(batch_no or "-"),
					frappe.bold(sales_order),
					requested_qty,
					stock_uom,
				)
			)
			return

		reserve_qty = requested_qty

		if floor_qty(requested_qty, 3) > usable_qty_to_reserve:
			reserve_qty = usable_qty_to_reserve
			self._reservation_warnings.append(
				frappe._(
					"Row capped - Item {0} from Batch {1} against Sales Order "
					"{2}: requested {3} {4}, only {5} {4} was available and "
					"has been reserved instead."
				).format(
					frappe.bold(item_code),
					frappe.bold(batch_no or "-"),
					frappe.bold(sales_order),
					requested_qty,
					stock_uom,
					reserve_qty,
				)
			)

		if reserve_qty <= 0:
			# Shouldn't happen given the usable_qty_to_reserve <= 0 check
			# above, but guard defensively against a zero/negative
			# reservation ever being created.
			return

		# ---------------------------------------------------------
		# CREATE STOCK RESERVATION ENTRY
		# ---------------------------------------------------------

		sre = frappe.new_doc("Stock Reservation Entry")

		sre.item_code = item_code
		sre.warehouse = warehouse
		sre.company = self.company
		sre.stock_uom = stock_uom

		sre.voucher_type = "Sales Order"
		sre.voucher_no = sales_order
		sre.voucher_detail_no = so_detail

		sre.from_voucher_type = from_voucher_type
		sre.from_voucher_no = from_voucher_no
		sre.from_voucher_detail_no = from_voucher_detail_no

		sre.reserved_qty = flt(reserve_qty, 3)
		sre.voucher_qty = flt(so_qty, 3)
		sre.available_qty = flt(
			available_qty_to_reserve,
			3,
		)
		sre.available_qty_to_reserve = flt(
			reserve_qty,
			3,
		)

		# ---------------------------------------------------------
		# BATCH
		# ---------------------------------------------------------

		has_batch_no = frappe.get_cached_value(
			"Item",
			item_code,
			"has_batch_no",
		)

		if batch_no and has_batch_no and reserve_qty > 0:

			sre.has_batch_no = 1
			sre.has_serial_no = 0
			sre.reservation_based_on = "Serial and Batch"
			sre.use_serial_batch_fields = 1

			sre.append(
				"sb_entries",
				{
					"batch_no": batch_no,
					"qty": reserve_qty,
					"warehouse": warehouse,
					"pieces": frappe.db.get_value(
						"Batch",
						batch_no,
						"pieces",
					) or 0,
					"length": frappe.db.get_value(
						"Batch",
						batch_no,
						"average_length",
					) or 0,
					"section_weight": frappe.db.get_value(
						"Batch",
						batch_no,
						"section_weight",
					) or 0,
				},
			)

			# Keep explicitly selected batch
			sre.auto_reserve_serial_and_batch = (
				lambda *args, **kwargs: None
			)

		else:
			sre.reservation_based_on = "Qty"

		# ---------------------------------------------------------
		# INSERT + SUBMIT
		# ---------------------------------------------------------

		sre.flags.ignore_permissions = True
		sre.insert()
		sre.submit()

		frappe.log_error(
			title="Stock Reserved",
			message=(
				f"Reserved {reserve_qty} of {item_code} "
				f"in {warehouse} for SO {sales_order} "
				f"(Batch: {batch_no})"
			),
		)

@frappe.whitelist()
def fetch_sales_order_items(filters):
	"""
	Fetch Sales Order Items based on filter criteria.
	Filters can include:
	customer, sales_order, item_name, customer_po_no, sales_order_date
	"""

	if isinstance(filters, str):
		filters = json.loads(filters)

	filters = filters or {}

	# Sales Order Filters
	so_filters = [["docstatus", "=", 1]]

	if filters.get("customer"):
		so_filters.append(["customer", "=", filters.get("customer")])

	if filters.get("sales_order"):
		so_filters.append(["name", "=", filters.get("sales_order")])

	if filters.get("customer_po_no"):
		so_filters.append(
			["po_no", "like", f"%{filters.get('customer_po_no')}%"]
		)

	if filters.get("sales_order_date"):
		so_filters.append(
			["transaction_date", "=", filters.get("sales_order_date")]
		)

	# Fetch Sales Orders
	sales_orders = frappe.get_all(
		"Sales Order",
		filters=so_filters,
		fields=[
			"name",
			"customer",
			"transaction_date",
			"po_no",
			"company",
		],
		order_by="transaction_date desc",
	)

	if not sales_orders:
		return []

	so_names = [d.name for d in sales_orders]
	so_map = {d.name: d for d in sales_orders}

	# Sales Order Item Filters
	item_filters = {
		"parent": ["in", so_names]
	}

	if filters.get("item_name"):
		item_filters["item_name"] = [
			"like",
			f"%{filters.get('item_name')}%",
		]

	# Fetch Sales Order Items
	items = frappe.get_all(
		"Sales Order Item",
		filters=item_filters,
		fields=[
			"name",
			"parent",
			"item_code",
			"item_name",
			"qty",
			"delivered_qty",
			"pieces",
			"length_size",
			"description",
			"assorted_length",
			"warehouse",
			"uom",
			"stock_uom",
			"rate",
			"amount",
			"conversion_factor",
		],
		order_by="parent asc, idx asc",
	)

	if not items:
		return []

	# Fetch Section Weight from Item
	item_codes = list({d.item_code for d in items if d.item_code})

	item_details = frappe.get_all(
		"Item",
		filters={"name": ["in", item_codes]},
		fields=[
			"name",
			"weight_per_meter",  # Change to custom_section_weight if required
		],
	)

	weight_map = {
		d.name: flt(d.weight_per_meter)
		for d in item_details
	}

	# Fetch Reserved Qty
	reservation_rows = frappe.db.sql(
		"""
		SELECT
			voucher_detail_no,
			SUM(reserved_qty) AS reserved_qty
		FROM `tabStock Reservation Entry`
		WHERE docstatus = 1
			AND voucher_type = 'Sales Order'
			AND status IN (
				'Reserved',
				'Partially Reserved',
				'Partially Delivered'
			)
			AND voucher_detail_no IN %(items)s
		GROUP BY voucher_detail_no
		""",
		{"items": [d.name for d in items]},
		as_dict=True,
	)

	reservation_map = {
		d.voucher_detail_no: flt(d.reserved_qty)
		for d in reservation_rows
	}

	rows = []

	for row in items:
		pending_qty = flt(row.qty) - flt(row.delivered_qty)

		if pending_qty <= 0:
			continue

		so = so_map.get(row.parent)

		reserved_qty = min(
			flt(reservation_map.get(row.name, 0)),
			pending_qty,
		)

		reserve_qty = reserved_qty

		rows.append({
			"sales_order": row.parent,
			"sales_order_item": row.name,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"qty": flt(row.qty),
			"pending_qty": pending_qty,
			"reserve_qty": reserve_qty,
			"pieces": row.pieces,
			"length": row.length_size,
			"section_weight": weight_map.get(row.item_code, 0),
		})

	return rows

@frappe.whitelist()
def add_to_reservation_batches(
	docname,
	# --- from pending_line_items ---
	sales_order,
	sales_order_item,
	item_code,
	item_name,
	# --- from available_batches ---
	batch_no,
	reserved_qty,
	# --- optional / defaulted args must come last ---
	sales_order_item_qty=0,
	length=0,
	pieces=0,
	section_weight=0,
	# --- from form header ---
	warehouse=None,
	posting_date=None,
):
	"""
	Merge one available_batches row + one pending_line_items row into
	reservation_batches, then save the parent document.
	"""
	doc = frappe.get_doc("Batch Wise Reservation Tool", docname)

	if doc.docstatus != 0:
		frappe.throw(frappe._("Cannot modify a submitted or cancelled document."))

	# Duplicate guard
	for row in doc.get("reservation_batches"):
		if row.batch_no == batch_no and row.sales_order_item == sales_order_item:
			frappe.throw(
				frappe._("Batch {0} is already reserved for Sales Order Item {1}.").format(
					batch_no, sales_order_item
				)
			)

	doc.append("reservation_batches", {
		"sales_order":     sales_order,
		"sales_order_item": sales_order_item,
		"sales_order_item_qty": sales_order_item_qty,
		"posting_date":    posting_date or doc.posting_date,
		"item_code":       item_code,
		"item_name":       item_name,
		"batch_no":        batch_no,
		"source_warehouse": warehouse or doc.warehouse,
		"reserved_qty":    flt(reserved_qty),
		"reserved_pieces": flt(pieces),
		"length":          flt(length),
		"section_weight":  flt(section_weight),
	})

	doc.save(ignore_permissions=True)

	# Return the last appended row so JS can display it
	new_row = doc.reservation_batches[-1]
	return {
		"sales_order":      new_row.sales_order,
		"sales_order_item": new_row.sales_order_item,
		"sales_order_item_qty": new_row.sales_order_item_qty,
		"posting_date":     str(new_row.posting_date) if new_row.posting_date else "",
		"item_code":        new_row.item_code,
		"item_name":        new_row.item_name,
		"batch_no":         new_row.batch_no,
		"source_warehouse": new_row.source_warehouse,
		"reserved_qty":     flt(new_row.reserved_qty),
		"reserved_pieces":  flt(new_row.reserved_pieces),
		"length":           flt(new_row.length),
		"section_weight":   flt(new_row.section_weight),
	}


@frappe.whitelist()
def fetch_available_batches(item_code, warehouse, pending_qty=0, reserve_qty=0):
	"""
	Fetch available batches for an item in a warehouse.

	Available Qty =
		Inward Qty
		- Outward Qty
		- Reserved Qty
	"""

	pending_qty = flt(pending_qty)
	reserve_qty = flt(reserve_qty)

	required_qty = pending_qty - reserve_qty

	if required_qty <= 0:
		return []

	# -----------------------------------------
	# Get actual batch-wise stock from
	# Stock Ledger Entry + Serial and Batch Entry
	# -----------------------------------------

	batch_stock = frappe.db.sql(
		"""
		SELECT
			sbe.batch_no AS batch,
			sle.item_code,
			SUM(sle.actual_qty) AS actual_qty
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabSerial and Batch Entry` sbe
			ON sbe.parent = sle.serial_and_batch_bundle
		WHERE
			sle.item_code = %(item_code)s
			AND sle.warehouse = %(warehouse)s
			AND sle.is_cancelled = 0
			AND sbe.batch_no IS NOT NULL
		GROUP BY sbe.batch_no, sle.item_code
		HAVING SUM(sle.actual_qty) > 0
		""",
		{
			"item_code": item_code,
			"warehouse": warehouse,
		},
		as_dict=True,
	)

	if not batch_stock:
		return []

	batch_names = [d.batch for d in batch_stock]

	# -----------------------------------------
	# Batch Details
	# -----------------------------------------

	batch_details = frappe.db.get_all(
		"Batch",
		filters={
			"name": ["in", batch_names],
			"disabled": 0,
		},
		fields=[
			"name",
			"pieces",
			"average_length",
		],
	)

	batch_map = {d.name: d for d in batch_details}

	# -----------------------------------------
	# Reserved Qty
	# -----------------------------------------

	reserved_qty_map = frappe.db.sql("""
		SELECT
			sbe.batch_no,
			SUM(sbe.qty) AS reserved_qty
		FROM `tabStock Reservation Entry` sre
		INNER JOIN `tabSerial and Batch Entry` sbe
			ON sbe.parent = sre.name
		WHERE
			sre.docstatus = 1
			AND sre.status IN ('Reserved', 'Partially Reserved', 'Partially Delivered')
			AND sbe.batch_no IN %(batch_names)s
		GROUP BY sbe.batch_no
	""", {
		"batch_names": tuple(batch_names),
	}, as_dict=True)

	reserved_map = {
		d.batch_no: flt(d.reserved_qty)
		for d in reserved_qty_map
	}


	result = []

	for row in batch_stock:

		actual_qty = flt(row.actual_qty)
		reserved_qty = flt(reserved_map.get(row.batch, 0))
		available_qty = actual_qty - reserved_qty

		if available_qty <= 0:
			continue

		batch = batch_map.get(row.batch)

		result.append(
			{
				"batch": row.batch,
				"item_code": row.item_code,
				"pieces": batch.pieces if batch else 0,
				"length": batch.average_length if batch else 0,
				"section_weight": batch.average_length if batch else 0,
				"actual_qty": actual_qty,
				"reserved_qty": reserved_qty,
				"available_qty": available_qty,
			}
		)

	result.sort(key=lambda d: d["available_qty"], reverse=True)

	return result