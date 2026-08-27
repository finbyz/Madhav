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


# ---------------------------------------------------------------
# Reservations from this specific warehouse are treated as
# "extra / tolerance" reservations, drawn from a shared pool
# calculated at 20% (Stock Settings.over_reservation_allowance)
# of the TOTAL Sales Order quantity (all lines combined) - not
# per line. A line may only draw from this pool once its own
# base (exact) quantity has been fully reserved.
# ---------------------------------------------------------------

def get_tolerance_warehouse(throw=True):
	"""Returns the configured tolerance warehouse, or None if unset.

	Pass throw=False when the caller only needs it for an equality
	check (e.g. "is this a tolerance row?") - a missing setting there
	just means the answer is "no", not an error. Only throw when the
	code is actually about to perform tolerance-specific logic (i.e.
	we already know we're handling a tolerance row and genuinely need
	the warehouse value to proceed).
	"""
	warehouse = frappe.db.get_single_value("Stock Settings", "batch_reservation_tolerance_warehouse")
	if not warehouse and throw:
		frappe.throw(
			frappe._(
				"Please configure the Batch Reservation Tolerance Warehouse in Stock Settings "
				"before reserving tolerance quantity."
			)
		)
	return warehouse


def get_so_total_qty(sales_order):
	return flt(
		frappe.db.sql(
			"""
			select sum(qty) from `tabSales Order Item`
			where parent = %s and docstatus = 1
			""",
			sales_order,
		)[0][0]
		or 0
	)


def get_tolerance_pool(sales_order):
	total_so_qty = get_so_total_qty(sales_order)
	tolerance_pct = flt(
		frappe.db.get_single_value("Stock Settings", "over_reservation_allowance") or 0
	)
	return flt(total_so_qty * tolerance_pct / 100)


def get_used_tolerance_qty(sales_order):
	"""Tolerance qty already reserved (submitted SREs) against this SO
	from the tolerance warehouse, across ANY document. Returns 0 if
	the tolerance warehouse isn't configured, rather than throwing -
	this is called as part of routine pool bookkeeping, not only when
	a tolerance reservation is actively being made."""
	warehouse = get_tolerance_warehouse(throw=False)
	if not warehouse:
		return 0
	return flt(
		frappe.db.sql(
			"""
			select sum(reserved_qty) from `tabStock Reservation Entry`
			where voucher_type = 'Sales Order'
				and voucher_no = %(so)s
				and warehouse = %(wh)s
				and docstatus = 1
			""",
			{"so": sales_order, "wh": warehouse},
		)[0][0]
		or 0
	)


def validate_tolerance_row(sales_order, sales_order_item, warehouse, reserved_qty, exclude_doc=None):
	"""Re-usable check for a tolerance-warehouse row: base must be
	exhausted, and the SO-wide pool must have room. Called both at
	staging time (add_to_reservation_batches) and again at submit
	time (create_fg_stock_reservation), since a staged row can become
	invalid if other reservations consume the base/pool in between."""
	so_item = frappe.db.get_value(
		"Sales Order Item", sales_order_item, ["qty", "delivered_qty"], as_dict=True
	)
	if not so_item:
		frappe.throw(frappe._("Sales Order Item {0} not found.").format(sales_order_item))

	pending_qty = flt(so_item.qty) - flt(so_item.delivered_qty)

	# We're actively performing tolerance logic here, so a missing
	# configuration is a genuine error - throw.
	tolerance_wh = get_tolerance_warehouse()

	already_reserved_base_qty = flt(
		frappe.db.sql(
			"""
			select sum(reserved_qty) from `tabStock Reservation Entry`
			where voucher_type = 'Sales Order' and voucher_detail_no = %(sod)s
				and docstatus = 1 and warehouse != %(wh)s
				and (%(exclude)s is null or name != %(exclude)s)
			""",
			{"sod": sales_order_item, "wh": tolerance_wh, "exclude": exclude_doc},
		)[0][0]
		or 0
	)

	if pending_qty - already_reserved_base_qty > 0.0001:
		frappe.throw(
			frappe._(
				"Cannot reserve extra (tolerance) quantity for Sales Order Item {0}: "
				"the base quantity ({1} still pending) must be fully reserved first."
			).format(sales_order_item, pending_qty - already_reserved_base_qty)
		)

	tolerance_pool = get_tolerance_pool(sales_order)
	used_tolerance = get_used_tolerance_qty(sales_order)
	remaining_tolerance = tolerance_pool - used_tolerance

	if flt(reserved_qty) > remaining_tolerance:
		frappe.throw(
			frappe._(
				"Cannot reserve {0} as tolerance qty: only {1} of the tolerance pool "
				"remains for Sales Order {2}."
			).format(reserved_qty, remaining_tolerance, sales_order)
		)


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

		# Running total of tolerance pool already consumed for this SO
		# (from previously submitted documents). Incremented in-memory
		# as we process rows below, so multiple lines drawing from the
		# same SO-level pool within this single submission stay in sync.
		self._tolerance_pool_used = get_used_tolerance_qty(self.sales_order) if self.get("sales_order") else 0

		for row in self.reservation_batches:
			self.create_fg_stock_reservation(
				item_code=row.item_code,
				warehouse=row.source_warehouse,
				qty=round(row.reserved_qty, 3),
				so_qty=row.sales_order_item_qty,
				stock_uom=frappe.db.get_value("Item", row.item_code, "stock_uom"),
				sales_order=row.sales_order,
				sales_order_item=row.sales_order_item,
				batch_no=row.batch_no,
				from_voucher_type=self.doctype,
				from_voucher_no=self.name,
				from_voucher_detail_no=row.name
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
		"""Cancel every Stock Reservation Entry created from this
		document. Looked up directly via from_voucher_type/from_voucher_no
		rather than a per-row back-reference field (which is never
		populated by create_fg_stock_reservation), so this reliably
		finds and cancels everything this document created."""
		sre_names = frappe.get_all(
			"Stock Reservation Entry",
			filters={
				"from_voucher_type": self.doctype,
				"from_voucher_no": self.name,
				"docstatus": 1,
			},
			pluck="name",
		)
		for sre_name in sre_names:
			sre = frappe.get_doc("Stock Reservation Entry", sre_name)
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

		is_tolerance_row = (warehouse == get_tolerance_warehouse(throw=False))

		if is_tolerance_row:
			# Re-validate here too - staging only checked this at the
			# time the row was added; other reservations may have
			# consumed the base/pool since then.
			validate_tolerance_row(sales_order, sales_order_item, warehouse, qty)

			# ---------------------------------------------------------
			# draw from the shared SO-level tolerance pool
			# instead of the per-line SO qty cap.
			# ---------------------------------------------------------
			tolerance_pool = get_tolerance_pool(sales_order)
			remaining_tolerance = tolerance_pool - flt(self._tolerance_pool_used)
			so_available_qty = max(0, floor_qty(remaining_tolerance, 3))
		else:
			# Base reservation - strictly against the SO Item qty,
			# no tolerance (subtask 1 behaviour, unchanged).
			so_available_qty = max(
				0,
				floor_qty(
					so_qty
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

		# Defensive: ensure the warnings/pool-tracking state exists even
		# if this method is ever called directly (e.g. from a script)
		# without going through create_stock_reservationentries() first.
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

		if is_tolerance_row:
			self._tolerance_pool_used = flt(getattr(self, "_tolerance_pool_used", 0)) + flt(reserve_qty)

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

	target_warehouse = warehouse or doc.warehouse

	if target_warehouse == get_tolerance_warehouse(throw=False):
		# ---------------------------------------------------------
		# TOLERANCE RESERVATION (Subtask 2)
		# ---------------------------------------------------------
		validate_tolerance_row(sales_order, sales_order_item, target_warehouse, reserved_qty)

		doc.append("reservation_batches", {
			"sales_order":     sales_order,
			"sales_order_item": sales_order_item,
			"sales_order_item_qty": sales_order_item_qty,
			"posting_date":    posting_date or doc.posting_date,
			"item_code":       item_code,
			"item_name":       item_name,
			"batch_no":        batch_no,
			"source_warehouse": target_warehouse,
			"reserved_qty":    flt(reserved_qty),
			"reserved_pieces": flt(pieces),
			"length":          flt(length),
			"section_weight":  flt(section_weight),
		})

		doc.save(ignore_permissions=True)
		new_row = doc.reservation_batches[-1]
		return {
			"sales_order": new_row.sales_order,
			"sales_order_item": new_row.sales_order_item,
			"sales_order_item_qty": new_row.sales_order_item_qty,
			"posting_date": str(new_row.posting_date) if new_row.posting_date else "",
			"item_code": new_row.item_code,
			"item_name": new_row.item_name,
			"batch_no": new_row.batch_no,
			"source_warehouse": new_row.source_warehouse,
			"reserved_qty": flt(new_row.reserved_qty),
			"reserved_pieces": flt(new_row.reserved_pieces),
			"length": flt(new_row.length),
			"section_weight": flt(new_row.section_weight),
		}

	# ---------------------------------------------------------
	# CAP AT SALES ORDER LINE'S PENDING QTY
	# No tolerance considered here - reservation must stay
	# strictly within what's actually pending on the SO line.
	# ---------------------------------------------------------

	so_item = frappe.db.get_value(
		"Sales Order Item",
		sales_order_item,
		["qty", "delivered_qty", "pieces"],
		as_dict=True,
	)

	if not so_item:
		frappe.throw(
			frappe._("Sales Order Item {0} not found.").format(sales_order_item)
		)

	pending_qty = flt(so_item.qty) - flt(so_item.delivered_qty)

	already_staged_qty = flt(sum(
		flt(row.reserved_qty)
		for row in doc.get("reservation_batches")
		if row.sales_order_item == sales_order_item
	))

	remaining_qty = flt(pending_qty - already_staged_qty)

	if remaining_qty <= 0:
		frappe.throw(
			frappe._(
				"Sales Order Item {0} is already fully staged for reservation "
				"({1} of {2} pending qty used). Cannot add Batch {3}."
			).format(sales_order_item, already_staged_qty, pending_qty, batch_no)
		)

	if flt(reserved_qty) > remaining_qty:
		frappe.throw(
			frappe._(
				"Cannot reserve {0} from Batch {1} for Sales Order Item {2}: "
				"only {3} qty is still pending (excluding tolerance)."
			).format(reserved_qty, batch_no, sales_order_item, remaining_qty)
		)

	already_staged_pieces = flt(sum(
		flt(row.reserved_pieces)
		for row in doc.get("reservation_batches")
		if row.sales_order_item == sales_order_item
	))
	remaining_pieces = flt(so_item.pieces) - already_staged_pieces

	# Fixed: previously "remaining_pieces > 0 and pieces > remaining_pieces"
	# silently skipped this check once remaining_pieces was already <= 0,
	# letting any amount of pieces through unchecked exactly when the cap
	# should have been tightest. max(0, remaining_pieces) means a
	# negative/zero remainder still blocks any further pieces.
	if flt(pieces) > max(0, remaining_pieces):
		frappe.throw(
			frappe._(
				"Cannot reserve {0} pieces from Batch {1} for Sales Order Item {2}: "
				"only {3} pieces are still pending."
			).format(pieces, batch_no, sales_order_item, remaining_pieces)
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
				"item_name": frappe.db.get_value("Item", row.item_code, "item_name"),
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

@frappe.whitelist()
def get_reserved_batches(docname):
	"""
	Fetch actual reserved batches from Stock Reservation Entry
	created by this Batch Wise Reservation Tool.
	"""

	stock_reservation_entries = frappe.get_all(
		"Stock Reservation Entry",
		filters={
			"from_voucher_type": "Batch Wise Reservation Tool",
			"from_voucher_no": docname,
			"docstatus": 1,
		},
		fields=[
			"name",
			"item_code",
			"warehouse",
			"voucher_type",
			"voucher_no",
			"voucher_detail_no",
			"reserved_qty",
			"status",
		],
		order_by="creation asc",
	)

	reserved_batches = []

	for sre in stock_reservation_entries:

		sb_entries = frappe.get_all(
			"Serial and Batch Entry",
			filters={
				"parent": sre.name,
				"parenttype": "Stock Reservation Entry",
			},
			fields=[
				"batch_no",
				"qty",
				"warehouse",
			],
			order_by="idx asc",
		)

		for sb in sb_entries:
			reserved_batches.append({
				"sales_order": sre.voucher_no,
				"item_code": sre.item_code,
				"batch_no": sb.batch_no,
				"reserved_qty": sb.qty,
				"warehouse": sb.warehouse or sre.warehouse,
				"status": sre.status,
			})

	return reserved_batches
