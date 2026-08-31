"""Helpers for integer PC pieces and reservation length/weight on bundle rows."""
from __future__ import annotations

import math

import frappe
from frappe.utils import flt


def int_pieces_from_qty(qty, length, section_weight):
	"""Whole PC count from weight — ceil of theoretical pieces (SO behaviour).

	Example: 30.458 → 31.

	Also guards float noise so values like 31.0000000002 do not become 32.
	"""
	length = flt(length)
	section_weight = flt(section_weight)
	qty = flt(qty)
	if not length or not section_weight or qty <= 0:
		return 0

	raw = (qty * 1000) / (length * section_weight)
	# Near-exact integers: trust round (float dust), do not ceil up by 1
	near = round(raw)
	if abs(raw - near) < 1e-6:
		return max(0, int(near))
	# Tiny epsilon so ceil(N) is not ceil(N + 1e-15)
	return max(0, int(math.ceil(raw - 1e-9)))


def resolve_entry_length(entry, batch_no=None, so_detail=None):
	"""Prefer reservation length, then SO line, then batch average."""
	if isinstance(entry, dict):
		length = flt(entry.get("length"))
		batch_no = batch_no or entry.get("batch_no")
	else:
		length = flt(getattr(entry, "length", 0))
		batch_no = batch_no or getattr(entry, "batch_no", None)

	if length:
		return length

	if so_detail:
		length = flt(frappe.db.get_value("Sales Order Item", so_detail, "length_size"))
		if length:
			return length

	if batch_no:
		return flt(frappe.db.get_value("Batch", batch_no, "average_length") or 0)

	return 0


def resolve_entry_section_weight(entry, item_code, length, batch_no=None):
	if isinstance(entry, dict):
		section_weight = flt(entry.get("section_weight"))
		batch_no = batch_no or entry.get("batch_no")
		qty = flt(entry.get("qty")) - flt(entry.get("delivered_qty"))
		pieces = flt(entry.get("pieces"))
	else:
		section_weight = flt(getattr(entry, "section_weight", 0))
		batch_no = batch_no or getattr(entry, "batch_no", None)
		qty = flt(getattr(entry, "qty", 0)) - flt(getattr(entry, "delivered_qty", 0))
		pieces = flt(getattr(entry, "pieces", 0))

	if section_weight:
		return section_weight

	if batch_no:
		section_weight = flt(frappe.db.get_value("Batch", batch_no, "section_weight") or 0)
		if section_weight:
			return section_weight

	if item_code:
		section_weight = flt(frappe.db.get_value("Item", item_code, "weight_per_meter") or 0)
		if section_weight:
			return section_weight

	if pieces and length and qty:
		return (qty * 1000) / (pieces * flt(length))

	return 0


def resolve_entry_pieces(entry, avail_qty, length, section_weight):
	"""Integer pieces for a reservation row from reserved weight (single ceil).

	Do not re-ceil already-rounded SO pieces — that adds a spurious +1 PC.
	"""
	avail_qty = flt(avail_qty)
	length = flt(length)
	section_weight = flt(section_weight)

	# Primary: derive once from this row's reserved weight
	if avail_qty > 0 and length and section_weight:
		return int_pieces_from_qty(avail_qty, length, section_weight)

	if isinstance(entry, dict):
		stored = flt(entry.get("pieces"))
		total_qty = flt(entry.get("qty"))
		delivered = flt(entry.get("delivered_qty"))
	else:
		stored = flt(getattr(entry, "pieces", 0))
		total_qty = flt(getattr(entry, "qty", 0))
		delivered = flt(getattr(entry, "delivered_qty", 0))

	if stored <= 0:
		return 0

	orig_avail = total_qty - delivered
	if orig_avail > 0 and abs(orig_avail - avail_qty) > 0.0001 and avail_qty > 0:
		# Proportional share of already-integer pieces — round, do not ceil again
		return max(0, int(round(stored * (avail_qty / orig_avail))))

	return max(0, int(round(stored)))


def qty_from_pieces(pieces, length, section_weight):
	pieces = flt(pieces)
	length = flt(length)
	section_weight = flt(section_weight)
	if not pieces or not length or not section_weight:
		return 0
	return (pieces * length * section_weight) / 1000
