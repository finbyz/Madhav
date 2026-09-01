import frappe
import json
from frappe.utils import flt, cint, nowtime, nowdate
from frappe import _

from madhav.madhav.utils.stock_piece_utils import (
	int_pieces_from_qty,
	qty_from_pieces,
	resolve_entry_length,
	resolve_entry_pieces,
	resolve_entry_section_weight,
	resolve_sre_dn_length,
	sync_dn_item_length_from_entries,
)

def on_submit(doc, method=None):
    if not doc.items:
        return

    keys = {
        (d.item_code, d.warehouse, d.batch_no)
        for d in doc.items
        if d.item_code and d.warehouse and d.batch_no
    }

    if not keys:
        return

    item_codes = list({k[0] for k in keys})
    warehouses = list({k[1] for k in keys})
    batch_nos = list({k[2] for k in keys})

    sre_rows = frappe.db.sql(
        """
        SELECT
            parent.item_code,
            parent.warehouse,
            child.batch_no,
            parent.reserved_qty
        FROM `tabStock Reservation Entry` parent
        JOIN `tabSerial and Batch Entry` child
            ON child.parent = parent.name
        WHERE parent.docstatus = 1
          AND parent.item_code IN %(item_codes)s
          AND parent.warehouse IN %(warehouses)s
          AND child.batch_no IN %(batch_nos)s
        """,
        {
            "item_codes": item_codes,
            "warehouses": warehouses,
            "batch_nos": batch_nos,
        },
        as_dict=True,
    )

    reserved_lookup = {}
    for r in sre_rows:
        key = (r.item_code, r.warehouse, r.batch_no)
        reserved_lookup[key] = reserved_lookup.get(key, 0) + flt(r.reserved_qty)

    for row in doc.items:
        if row.invoice_qty != row.qty:
            frappe.msgprint(
                _(
                    "Row {0}: Invoice qty {1} is not equal to Delivery qty {2} "
                    "for Item {3}, Batch {4} in Warehouse {5}"
                ).format(
                    row.idx,
                    row.invoice_qty,
                    row.qty,
                    row.item_code,
                    row.batch_no,
                    row.warehouse,
                ),
                title="Error with Qty",
            )
        # Removed the throw block here.
        # If invoice_qty <= batch_qty, we don't cancel SRE, so qty will naturally be < reserved_qty which is valid.

from frappe.utils import flt, get_datetime, add_to_date, nowtime


def before_insert(self, method):
    change_qty_serial_and_batch(self)


def validate(self, method):

    for row in self.items:
        # ERPNext rebuilds the bundle when both batch_no and
        # serial_and_batch_bundle are set on the same row.
        if row.serial_and_batch_bundle and row.batch_no:
            row.batch_no = None

        if row.against_sales_order:
            deliver_as_qty = frappe.db.get_value(
                "Sales Order", row.against_sales_order, "deliver_as_qty"
            )
            if deliver_as_qty and not row.invoice_qty:
                frappe.throw(f"Invoice Qty is mandatory for row {row.idx}")
            if deliver_as_qty and not row.custom_deliver_as_qty:
                row.custom_deliver_as_qty = deliver_as_qty

    if _has_deliver_as_qty_over_delivery(self):
        for args in self.status_updater:
            if (
                args.get("target_dt") == "Sales Order Item"
                and args.get("overflow_type") == "delivery"
            ):
                args["validate_qty"] = False


def _has_deliver_as_qty_over_delivery(doc):
    for row in doc.items:
        if not cint(row.custom_deliver_as_qty) or not flt(row.invoice_qty):
            continue
        if flt(row.invoice_qty) > flt(row.qty):
            return True
        if row.so_detail:
            so_qty = flt(frappe.db.get_value("Sales Order Item", row.so_detail, "qty"))
            if flt(row.invoice_qty) > so_qty:
                return True
    return False


def get_batch_available_pieces(item_code, warehouse, batch_no):
    """
    Current available pieces for a batch, derived from Piece Stock Ledger
    Entry. batch_no on the PSLE itself isn't reliably populated, so we join
    through the Serial and Batch Bundle's entries (which do carry batch_no).
    """
    result = frappe.db.sql(
        """
        SELECT SUM(psle.actual_qty) as total_pieces
        FROM `tabPiece Stock Ledger Entry` psle
        INNER JOIN `tabSerial and Batch Entry` sbe
            ON sbe.parent = psle.serial_and_batch_bundle
        WHERE psle.item_code = %s
          AND psle.warehouse = %s
          AND sbe.batch_no = %s
          AND psle.is_cancelled = 0
        """,
        (item_code, warehouse, batch_no),
        as_dict=True,
    )
    return flt(result[0].total_pieces) if result and result[0].total_pieces else 0


def get_ssb_bundle_for_voucher_from_sre(sre):
	"""Create a DN Serial/Batch Bundle from SRE with reservation length and integer pieces."""
	sre_row = sre if isinstance(sre, dict) else sre.as_dict()
	sre_name = sre_row.get("name")
	so_detail = sre_row.get("voucher_detail_no")
	item_code = sre_row.get("item_code")

	sb_entries = frappe.db.sql(
		"""
		SELECT
			serial_no,
			batch_no,
			qty,
			delivered_qty,
			pieces,
			length,
			section_weight,
			warehouse
		FROM `tabSerial and Batch Entry`
		WHERE parent = %s
		  AND parenttype = 'Stock Reservation Entry'
		  AND qty > IFNULL(delivered_qty, 0)
		ORDER BY idx
		""",
		sre_name,
		as_dict=True,
	)
	if not sb_entries:
		return None

	bundle = frappe.new_doc("Serial and Batch Bundle")
	bundle.type_of_transaction = "Outward"
	bundle.voucher_type = "Delivery Note"
	bundle.posting_date = nowdate()
	bundle.posting_time = nowtime()

	for field in ("item_code", "warehouse", "has_serial_no", "has_batch_no"):
		setattr(bundle, field, sre_row[field])

	for row in sb_entries:
		avail_qty = flt(row.qty) - flt(row.delivered_qty)
		length = resolve_entry_length(row, row.batch_no, so_detail)
		section_weight = resolve_entry_section_weight(
			row, item_code, length, row.batch_no
		)
		pieces = resolve_entry_pieces(row, avail_qty, length, section_weight)

		bundle.append(
			"entries",
			{
				"serial_no": row.serial_no,
				"batch_no": row.batch_no,
				"qty": avail_qty,
				"pieces": pieces,
				"length": length,
				"section_weight": section_weight,
				"warehouse": row.warehouse or sre_row.get("warehouse"),
			},
		)

	bundle.flags.ignore_permissions = True
	bundle.save(ignore_permissions=True)
	return bundle.name


def _apply_reserved_dims_to_dn_item(dn_item, so_item, sre):
	"""Stamp batch/reservation length and integer pieces on the DN row."""
	from madhav.madhav.utils.stock_piece_utils import int_pieces_from_qty

	reserved_stock_qty = flt(sre.reserved_qty) - flt(sre.delivered_qty)
	so_length = flt(so_item.get("length_size"))
	so_detail = so_item.get("name") or getattr(so_item, "name", None)
	sre_name = sre.name if hasattr(sre, "name") else sre.get("name")

	# SO ordered length is reference only; DN shows actual reserved batch length.
	if so_length and hasattr(dn_item, "length_sizeso"):
		dn_item.length_sizeso = so_length

	reserved_length = resolve_sre_dn_length(sre_name, so_detail)
	if not reserved_length:
		reserved_length = so_length
	if reserved_length and hasattr(dn_item, "length_size"):
		dn_item.length_size = reserved_length

	# Prefer pieces already on this SRE's batch rows (per-batch, not full SO)
	sre_pieces = 0
	if sre_name and frappe.db.has_column("Serial and Batch Entry", "pieces"):
		sre_pieces = cint(
			frappe.db.sql(
				"""
				select coalesce(sum(pieces), 0)
				from `tabSerial and Batch Entry`
				where parent = %s and parenttype = 'Stock Reservation Entry'
				""",
				sre_name,
			)[0][0]
		)

	section_weight = flt(so_item.get("section_weight"))
	if not section_weight and so_item.item_code:
		section_weight = flt(
			frappe.db.get_value("Item", so_item.item_code, "weight_per_meter") or 0
		)

	if sre_pieces > 0:
		scaled_pieces = sre_pieces
	elif reserved_length and section_weight and reserved_stock_qty > 0:
		# Single ceil from reserved weight using batch length, not SO ordered length
		scaled_pieces = int_pieces_from_qty(
			reserved_stock_qty, reserved_length, section_weight
		)
	else:
		so_pieces = cint(so_item.get("pieces"))
		so_stock_qty = flt(so_item.stock_qty) or (
			flt(so_item.qty) * flt(so_item.conversion_factor or 1)
		)
		if so_pieces and so_stock_qty > 0 and reserved_stock_qty > 0:
			# Already-integer SO pieces: round proportionally (no second ceil)
			scaled_pieces = max(
				0, int(round(so_pieces * reserved_stock_qty / so_stock_qty))
			)
		else:
			scaled_pieces = so_pieces

	if hasattr(dn_item, "lengthpieces_so") and scaled_pieces:
		dn_item.lengthpieces_so = scaled_pieces
	if hasattr(dn_item, "pieces") and scaled_pieces:
		dn_item.pieces = scaled_pieces

	if hasattr(dn_item, "section_weight"):
		if section_weight:
			dn_item.section_weight = section_weight
		elif reserved_length and scaled_pieces and reserved_stock_qty:
			dn_item.section_weight = (reserved_stock_qty * 1000) / (
				scaled_pieces * reserved_length
			)


def change_qty_serial_and_batch(self):
    for item in self.items:
        if not item.against_sales_order:
            continue

        deliver_as_qty = frappe.db.get_value(
            "Sales Order",
            item.against_sales_order,
            "deliver_as_qty",
        )

        if not item.serial_and_batch_bundle:
            continue

        bundle = frappe.get_doc(
            "Serial and Batch Bundle",
            item.serial_and_batch_bundle,
        )
        bundle.reload()

        # IMPORTANT: Use item.qty here, NOT invoice_qty.
        target_qty = flt(item.qty)

        batch_entries = [e for e in bundle.entries if e.batch_no]
        if not batch_entries:
            continue

        total_original_qty = sum(abs(flt(e.qty)) for e in batch_entries)
        if not total_original_qty:
            continue

        # Plain batch items (no length/section_weight) must not go through the
        # steel piece conversion — that path forces qty to 0 when dims are missing.
        # Also do NOT cap by Batch.batch_qty: that field is not available stock and
        # incorrectly shrinks deliver-as-qty / SR-adjusted bundles on cancel/submit.
        has_piece_dims = any(
            flt(e.length) and flt(e.section_weight) for e in batch_entries
        )
        if not has_piece_dims:
            desired_qty = []
            for entry in batch_entries:
                original = abs(flt(entry.qty))
                ratio = (original / total_original_qty) if total_original_qty else 0
                desired_qty.append(target_qty * ratio)
            allocated_total_qty = sum(desired_qty)
            for i, entry in enumerate(batch_entries):
                entry.qty = -desired_qty[i]
                if hasattr(entry, "pieces"):
                    entry.pieces = 0
            item.qty = allocated_total_qty
            item.stock_qty = allocated_total_qty
            item.amount = flt(item.rate) * allocated_total_qty
            item.base_amount = item.amount * flt(self.conversion_rate or 1)
            if hasattr(item, "pieces"):
                item.pieces = 0
            bundle.total_qty = -allocated_total_qty
            bundle.flags.ignore_validate = True
            bundle.flags.ignore_links = True
            bundle.save(ignore_permissions=True)
            bundle.reload()
            continue

        # ── Step 1 (steel): Proportional QTY from reserved/fetched weight ──
        # Do NOT cap by Batch.batch_qty — that field is receipt size, not
        # available stock, and was shrinking reserved qty on DN save
        # (e.g. 0.445 → 0.443).
        desired_qty = []
        for entry in batch_entries:
            original = abs(flt(entry.qty))
            ratio = original / total_original_qty
            desired_qty.append(target_qty * ratio)

        # Absorb floating remainder on the first entry
        leftover_qty = target_qty - sum(desired_qty)
        if abs(leftover_qty) > 0.0000001 and desired_qty:
            desired_qty[0] += leftover_qty

        # ── Step 2: Integer pieces for display / piece ledger (do NOT rewrite weight) ──
        # Reserved/fetched qty is the physical weight from stock reservation.
        # Converting qty → ceil(pieces) → qty_from_pieces drifts weight
        # (e.g. 0.445 → 0.443) and breaks Deliver-as-Qty vs Invoice Qty.
        desired_pieces = []
        for i, entry in enumerate(batch_entries):
            entry_length = resolve_entry_length(
                entry, entry.batch_no, item.so_detail
            )
            entry_section_weight = resolve_entry_section_weight(
                entry, item.item_code, entry_length, entry.batch_no
            )
            if entry_length and not flt(entry.length):
                entry.length = entry_length
            if entry_section_weight and not flt(entry.section_weight):
                entry.section_weight = entry_section_weight

            # Prefer pieces already on the reservation/bundle for this row.
            # Recalculate only when missing — avoids ceil(SO pieces) again (+1 PC).
            existing_pieces = cint(flt(entry.pieces))
            if existing_pieces > 0:
                pieces = existing_pieces
            else:
                pieces = int_pieces_from_qty(
                    desired_qty[i], entry_length, entry_section_weight
                )
            desired_pieces.append(pieces)

        target_total_pieces = sum(desired_pieces)

        # ── Step 3: Cap integer pieces against batch availability, spill leftover ──
        available_pieces_cache = {
            entry.batch_no: int(round(get_batch_available_pieces(
                item.item_code, entry.warehouse or item.warehouse, entry.batch_no
            )))
            for entry in batch_entries
        }

        for i, entry in enumerate(batch_entries):
            available = available_pieces_cache.get(entry.batch_no, 0)
            if available and desired_pieces[i] > available:
                desired_pieces[i] = available

        actual_total_pieces = sum(desired_pieces)
        leftover_pieces = target_total_pieces - actual_total_pieces

        for i, entry in enumerate(batch_entries):
            if leftover_pieces <= 0:
                break
            available = available_pieces_cache.get(entry.batch_no, 0)
            if not available:
                continue
            room = available - desired_pieces[i]
            if room > 0:
                take = min(room, leftover_pieces)
                desired_pieces[i] += int(take)
                leftover_pieces -= int(take)

        if leftover_pieces > 0:
            frappe.msgprint(
                f"Not enough available pieces for {item.item_code} in "
                f"{item.warehouse}: short by {leftover_pieces} pieces.",
                indicator="orange",
                alert=True,
            )

        # ── Step 4: Keep reserved weight; only stamp integer pieces ──
        total_allocated_pieces = 0
        last_section_weight = 0
        for i, entry in enumerate(batch_entries):
            pieces = int(desired_pieces[i])
            entry.qty = -desired_qty[i]
            entry.pieces = pieces
            total_allocated_pieces += pieces
            last_section_weight = flt(entry.section_weight)

        allocated_total_qty = sum(desired_qty)

        item.qty = allocated_total_qty
        item.stock_qty = allocated_total_qty * flt(item.conversion_factor or 1)
        item.amount = flt(item.rate) * allocated_total_qty
        item.base_amount = item.amount * flt(self.conversion_rate or 1)
        item.pieces = int(total_allocated_pieces)
        if last_section_weight:
            item.section_weight = last_section_weight
        sync_dn_item_length_from_entries(item, batch_entries, item.so_detail)
        bundle.total_qty = -allocated_total_qty
        bundle.flags.ignore_validate = True
        bundle.flags.ignore_links = True
        bundle.save(ignore_permissions=True)
        bundle.reload()

        frappe.logger().info(
            f"Updated Bundle {bundle.name}: Total Qty={bundle.total_qty}, "
            f"Total Pieces={total_allocated_pieces}, "
            f"Entries={[{'batch': d.batch_no, 'qty': d.qty, 'pieces': d.pieces} for d in bundle.entries]}"
        )

def get_available_qty_for_item(row):
    # Prefer this DN row's bundle. Multi-batch DNs use one SRE/bundle per row;
    # summing all SO-line reservations would understate difference_qty on the
    # over-invoiced row and can pull stock from sibling batches on submit.
    if row.serial_and_batch_bundle:
        sbb = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)
        bundle_qty = sum(abs(flt(e.qty)) for e in sbb.entries if e.batch_no)
        if bundle_qty:
            return bundle_qty

    if row.against_sales_order and row.so_detail:
        sre_rows = frappe.get_all(
            "Stock Reservation Entry",
            filters={
                "voucher_type": "Sales Order",
                "voucher_no": row.against_sales_order,
                "voucher_detail_no": row.so_detail,
                "docstatus": 1,
            },
            fields=["reserved_qty", "delivered_qty"],
        )
        if sre_rows:
            return sum(flt(d.reserved_qty) - flt(d.delivered_qty) for d in sre_rows)

    return 0



def update_bundle_to_invoice_qty(item, invoice_qty, qty, deliver_as_qty):
    if not deliver_as_qty:
        return
    if not item.serial_and_batch_bundle:
        return

    bundle = frappe.get_doc("Serial and Batch Bundle", item.serial_and_batch_bundle)
    bundle.reload()

    batch_entries = [e for e in bundle.entries if e.batch_no]
    if not batch_entries:
        return

    total_original_qty = sum(abs(flt(e.qty)) for e in batch_entries)
    if not total_original_qty:
        return

    target_qty = flt(invoice_qty)

    # No change needed
    if abs(target_qty - total_original_qty) < 0.0001:
        return

    # ── Proportional distribution ──
    # When expanding to invoice_qty (deliver-as-qty overage), do NOT cap by
    # Batch.batch_qty — that field is often the original receipt size, and
    # Stock Reconciliation creates the missing stock before DN submit.
    # Cap only when shrinking (or holding) so we never invent qty above the
    # batch master without an intentional over-delivery.
    expanding = target_qty > total_original_qty + 0.0001
    desired = []
    for entry in batch_entries:
        original = abs(flt(entry.qty))
        ratio = original / total_original_qty
        desired_qty = target_qty * ratio

        if not expanding:
            batch_qty = flt(
                frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
            )
            # batch_qty 0 means unset / unknown — do not cap to zero
            if batch_qty > 0:
                desired_qty = min(desired_qty, batch_qty)
        desired.append(desired_qty)

    # Spill leftover (from capped batches) to batches with remaining room
    actual_total = sum(desired)
    leftover = target_qty - actual_total

    if not expanding:
        for i, entry in enumerate(batch_entries):
            if abs(leftover) < 0.0001:
                break
            batch_qty = flt(
                frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
            )
            if batch_qty <= 0:
                desired[i] += leftover
                leftover = 0
                break
            room = batch_qty - desired[i]
            if room > 0:
                take = min(room, leftover)
                desired[i] += take
                leftover -= take
    elif abs(leftover) > 0.0001:
        # Expanding: put any floating remainder on the first batch entry
        desired[0] += leftover
        leftover = 0

    # ── Apply per-entry reservation length; integer pieces ──
    total_pieces = 0

    for i, entry in enumerate(batch_entries):
        entry_length = resolve_entry_length(
            entry, entry.batch_no, item.so_detail
        )
        entry_section_weight = resolve_entry_section_weight(
            entry, item.item_code, entry_length, entry.batch_no
        )
        if entry_length and not flt(entry.length):
            entry.length = entry_length
        if entry_section_weight and not flt(entry.section_weight):
            entry.section_weight = entry_section_weight

        pieces = int_pieces_from_qty(desired[i], entry_length, entry_section_weight)
        entry.qty = -desired[i]
        entry.pieces = pieces
        total_pieces += pieces

    if hasattr(item, "pieces"):
        item.pieces = int(total_pieces)

    sync_dn_item_length_from_entries(item, batch_entries, item.so_detail)

    bundle.total_qty = -target_qty
    bundle.flags.ignore_validate = True
    bundle.flags.ignore_links = True
    bundle.save(ignore_permissions=True)

from frappe.utils import get_datetime, add_to_date, nowtime


def before_submit(self, method):
    # For each row, work out how much qty is available "for free" (from the
    # existing reservation / batch / bundle) before we'd need to cancel the
    # SRE and create a Stock Reconciliation to cover the excess.
    for i in self.items:
        available_qty = get_available_qty_for_item(i)

        if flt(i.invoice_qty) > available_qty:
            i.difference_qty = flt(i.invoice_qty) - available_qty
        else:
            i.difference_qty = 0

        # No overage: nothing to reconcile.
        # Only auto-sync qty/bundle to invoice_qty when there is an actual
        # bundle to rebalance. For plain SO-reserved (non-batch, non-bundle)
        # items, leave `qty` exactly as entered — it represents the physical
        # delivery qty, not the billed qty.
        if flt(i.difference_qty) <= 0 and flt(i.invoice_qty) > 0 and i.serial_and_batch_bundle and i.custom_deliver_as_qty:
            i.qty = flt(i.invoice_qty)
            i.stock_qty = flt(i.invoice_qty) * flt(i.conversion_factor or 1)
            update_bundle_to_invoice_qty(i, flt(i.invoice_qty),flt(i.qty),flt(i.custom_deliver_as_qty))

    cancel_stock_reservations_from_so(self)

    # Step 3: Create Stock Reconciliation (this will handle updating SBB & DN qty ONLY for items with difference > 0)
    create_stock_reconciliation(self)

    # Ensure totals are recalculated even if SR function skipped everything
    self.calculate_taxes_and_totals()


CANCELLED_SRE_COMMENT_PREFIX = "MADHAV_DN_CANCELLED_SRE::"


def cancel_stock_reservations_from_so(doc):
    """
    Snapshot active SO reservations linked to this DN, then cancel only those
    needed for Deliver-as-Qty overage (difference_qty > 0).

    Snapshot is always stored for reserved DNs so cancel can restore if an SRE
    was cancelled during submit. Unreserved DNs have no SREs → no snapshot →
    cancel will not invent a reservation (PR review).
    """
    snapshots = []
    seen_sre = set()
    cancel_errors = []
    so_details_needing_cancel = {
        row.so_detail
        for row in doc.items
        if row.so_detail and flt(row.difference_qty) > 0
    }

    for row in doc.items:
        if not row.against_sales_order or not row.so_detail:
            continue

        sre_list = frappe.get_all(
            "Stock Reservation Entry",
            filters={
                "voucher_type": "Sales Order",
                "voucher_no": row.against_sales_order,
                "voucher_detail_no": row.so_detail,
                "docstatus": 1,
            },
            pluck="name",
        )

        for sre_name in sre_list:
            if sre_name in seen_sre:
                continue
            seen_sre.add(sre_name)
            try:
                sre = frappe.get_doc("Stock Reservation Entry", sre_name)
                if sre.docstatus != 1:
                    continue
                snapshots.append(_snapshot_sre(sre))

                if row.so_detail in so_details_needing_cancel:
                    sre.flags.ignore_permissions = True
                    sre.cancel()
            except Exception:
                frappe.log_error(
                    title="SRE Snapshot/Cancel Error",
                    message=f"{sre_name}\n{frappe.get_traceback()}",
                )
                cancel_errors.append(sre_name)

    if snapshots and doc.name:
        _store_cancelled_sre_snapshot(doc.name, snapshots)

    if cancel_errors:
        frappe.throw(
            _(
                "Failed to snapshot/cancel Stock Reservation Entry(ies) for Delivery Note {0}:<br>{1}"
            ).format(frappe.bold(doc.name), "<br>".join(frappe.bold(e) for e in cancel_errors)),
            title=_("Stock Reservation Error"),
        )


def _snapshot_sre(sre):
	"""Capture fields needed to recreate a Stock Reservation Entry."""
	return {
		"name": sre.name,
		"item_code": sre.item_code,
		"warehouse": sre.warehouse,
		"company": sre.company,
		"stock_uom": sre.stock_uom,
		"voucher_type": sre.voucher_type,
		"voucher_no": sre.voucher_no,
		"voucher_detail_no": sre.voucher_detail_no,
		"voucher_qty": flt(sre.voucher_qty),
		"reserved_qty": flt(sre.reserved_qty),
		"delivered_qty": flt(sre.delivered_qty),
		"available_qty": flt(sre.available_qty),
		"reservation_based_on": sre.reservation_based_on,
		"has_batch_no": cint(sre.has_batch_no),
		"has_serial_no": cint(sre.has_serial_no),
		"from_voucher_type": sre.from_voucher_type,
		"from_voucher_no": sre.from_voucher_no,
		"from_voucher_detail_no": sre.from_voucher_detail_no,
		"sb_entries": [
			{
				"batch_no": e.batch_no,
				"serial_no": e.serial_no,
				"qty": flt(e.qty),
				"delivered_qty": flt(e.get("delivered_qty")),
				"warehouse": e.warehouse,
				"pieces": flt(e.get("pieces")),
				"length": flt(e.get("length")),
				"section_weight": flt(e.get("section_weight")),
			}
			for e in (sre.get("sb_entries") or [])
		],
	}


def _store_cancelled_sre_snapshot(delivery_note, snapshots):
    """Persist SRE snapshots on the DN for restore-on-cancel."""
    existing = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Delivery Note",
            "reference_name": delivery_note,
            "comment_type": "Info",
        },
        fields=["name", "content"],
    )
    for row in existing:
        content = row.content or ""
        if content.startswith(CANCELLED_SRE_COMMENT_PREFIX) or content.startswith(
            "MADHAV_DN_CANCELLED_SRE::"
        ):
            frappe.delete_doc("Comment", row.name, ignore_permissions=True, force=True)

    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Delivery Note",
            "reference_name": delivery_note,
            "content": CANCELLED_SRE_COMMENT_PREFIX + json.dumps(snapshots),
        }
    ).insert(ignore_permissions=True)


def _load_cancelled_sre_snapshot(delivery_note):
	"""Load SRE snapshot stored on the DN.

	Raises if a snapshot comment exists but cannot be parsed — cancel must not
	silently continue without restoring reservations.
	"""
	prefixes = (CANCELLED_SRE_COMMENT_PREFIX, "MADHAV_DN_CANCELLED_SRE::")
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Delivery Note",
			"reference_name": delivery_note,
			"comment_type": "Info",
		},
		fields=["name", "content"],
		order_by="creation desc",
		limit=20,
	)
	for comment in comments:
		content = comment.content or ""
		for prefix in prefixes:
			if not content.startswith(prefix):
				continue
			payload = content[len(prefix) :]
			try:
				snapshots = json.loads(payload)
			except Exception:
				frappe.log_error(
					title="DN Cancel - Invalid SRE Snapshot",
					message=f"{delivery_note}\n{content}",
				)
				frappe.throw(
					_(
						"Could not read stock reservation snapshot for Delivery Note {0}. "
						"Cancellation aborted so reservations are not left inconsistent."
					).format(frappe.bold(delivery_note)),
					title=_("Invalid Reservation Snapshot"),
				)
			if not isinstance(snapshots, list):
				frappe.throw(
					_(
						"Stock reservation snapshot for Delivery Note {0} is invalid "
						"(expected a list of reservations)."
					).format(frappe.bold(delivery_note)),
					title=_("Invalid Reservation Snapshot"),
				)
			return snapshots, comment.name
	return [], None


def on_cancel(doc, method=None):
	"""Release stock adjustments, restore reserved qty, re-sync SO on DN cancel."""
	if getattr(doc, "is_return", 0):
		return

	release_stock_used_by_delivery_note(doc)
	# Only undeliver the residual this DN still holds on SREs (do not reduce
	# earlier Delivery Notes' delivered qty a second time).
	reverse_sre_delivery_for_dn(doc)
	# Restore every cancelled reservation from the submit-time snapshot.
	restore_stock_reservations_after_cancel(doc)
	update_sales_order_quantities_on_cancel(doc)


def release_stock_used_by_delivery_note(doc):
	"""Cancel Stock Reconciliations created for this DN (keep cancelled docs for audit)."""
	cancel_stock_reconciliations_for_delivery_note(doc.name, delete=False)


def reverse_sre_delivery_for_dn(doc):
	"""Reduce SRE delivered_qty only by what this DN still accounts for.

	ERPNext may already have undelivered on cancel. Re-running a full
	``stock_qty`` undeliver would eat previously delivered qty from earlier
	DNs. We only undeliver the excess above deliveries from other submitted DNs.
	"""
	if not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
		return

	# Aggregate this DN's stock qty per SO line
	dn_qty_by_detail = {}
	for item in doc.items:
		if not item.against_sales_order or not item.so_detail:
			continue
		dn_qty_by_detail.setdefault(
			item.so_detail,
			frappe._dict(
				sales_order=item.against_sales_order,
				qty=0,
				dn_items=[],
			),
		)
		dn_qty_by_detail[item.so_detail].qty += flt(item.stock_qty)
		dn_qty_by_detail[item.so_detail].dn_items.append(item)

	for so_detail, info in dn_qty_by_detail.items():
		other_delivered = _delivered_qty_excluding_dn(so_detail, doc.name)
		# Newest first so we peel this DN's delivery before earlier DNs'.
		sre_names = frappe.get_all(
			"Stock Reservation Entry",
			filters={
				"docstatus": 1,
				"voucher_type": "Sales Order",
				"voucher_no": info.sales_order,
				"voucher_detail_no": so_detail,
				"status": ["in", ["Partially Delivered", "Delivered"]],
			},
			pluck="name",
			order_by="creation desc",
		)
		if not sre_names:
			continue

		sres = [frappe.get_doc("Stock Reservation Entry", n) for n in sre_names]
		current_delivered = sum(flt(s.delivered_qty) for s in sres)
		# Anything above other DNs' delivered is residual from this DN (or a
		# failed ERPNext undeliver). Never undeliver below other_delivered.
		excess = current_delivered - other_delivered
		if excess <= 0:
			continue

		qty_to_undeliver = min(excess, flt(info.qty))
		if qty_to_undeliver <= 0:
			continue

		# Prefer undelivering against batches used on this DN's rows
		batch_qty = {}
		for item in info.dn_items:
			for batch_no, qty in _dn_item_batch_qty_map(item).items():
				batch_qty[batch_no] = batch_qty.get(batch_no, 0) + qty

		for sre in sres:
			if qty_to_undeliver <= 0:
				break
			can = min(flt(sre.delivered_qty), qty_to_undeliver)
			if can <= 0:
				continue
			undelivered = _undeliver_sre_qty(sre, can, batch_qty)
			if undelivered <= 0:
				continue
			sre.db_set("delivered_qty", flt(sre.delivered_qty) - undelivered, update_modified=False)
			sre.reload()
			sre.update_status()
			sre.update_reserved_stock_in_bin()
			qty_to_undeliver -= undelivered


def _dn_item_batch_qty_map(item):
	batch_qty = {}
	if not item.serial_and_batch_bundle:
		return batch_qty
	try:
		sbb = frappe.get_doc("Serial and Batch Bundle", item.serial_and_batch_bundle)
	except Exception:
		return batch_qty
	for entry in sbb.entries or []:
		if entry.batch_no:
			batch_qty[entry.batch_no] = batch_qty.get(entry.batch_no, 0) + abs(flt(entry.qty))
	return batch_qty


def _undeliver_sre_qty(sre, qty, batch_qty=None):
	"""Reduce sb_entry delivered_qty then return how much header delivered can fall."""
	if qty <= 0:
		return 0

	if sre.reservation_based_on != "Serial and Batch" or not sre.get("sb_entries"):
		return qty

	remaining = qty
	batch_qty = dict(batch_qty or {})

	def _undo_from_entries(prefer_batches):
		nonlocal remaining
		for entry in sre.sb_entries:
			if remaining <= 0:
				break
			if prefer_batches and entry.batch_no not in batch_qty:
				continue
			limit = batch_qty.get(entry.batch_no, remaining) if prefer_batches else remaining
			undo = min(flt(entry.delivered_qty), remaining, limit)
			if undo <= 0:
				continue
			entry.db_set("delivered_qty", flt(entry.delivered_qty) - undo, update_modified=False)
			remaining -= undo
			if prefer_batches and entry.batch_no in batch_qty:
				batch_qty[entry.batch_no] = max(batch_qty[entry.batch_no] - undo, 0)

	if batch_qty:
		_undo_from_entries(prefer_batches=True)
	if remaining > 0:
		_undo_from_entries(prefer_batches=False)

	return qty - remaining


def update_sales_order_quantities_on_cancel(doc):
	"""Re-sync SO delivered_qty / per_delivered after DN cancel cleanup (Manjot task 3).

	ERPNext runs update_prevdoc_status in DeliveryNote.on_cancel before this hook.
	Re-run after Madhav SR/SRE cleanup and refresh bin reserved qty for affected lines.
	"""
	so_item_rows = [
		row.so_detail for row in doc.items if row.against_sales_order and row.so_detail
	]
	if not so_item_rows:
		return

	doc.update_prevdoc_status()

	so_names = {row.against_sales_order for row in doc.items if row.against_sales_order}
	for so_name in so_names:
		affected = [
			row.so_detail
			for row in doc.items
			if row.against_sales_order == so_name and row.so_detail
		]
		so = frappe.get_doc("Sales Order", so_name)
		so.update_reserved_qty(affected)


def _distribute_delivered_across_snapshots(snapshots, exclude_dn):
	"""Assign delivered_qty per restored SRE without double-counting SO deliveries.

	Each snapshot keeps its own pre-cancel delivered_qty. Any extra delivered
	qty from other submitted DNs (beyond the sum of snapshot delivered) is
	spread across reservations by remaining capacity (reserved - own delivered).
	"""
	from collections import defaultdict

	prepared = [dict(s) for s in snapshots]
	by_detail = defaultdict(list)
	for snap in prepared:
		by_detail[snap.get("voucher_detail_no")].append(snap)

	for so_detail, group in by_detail.items():
		if not so_detail:
			continue
		other_dn_delivered = _delivered_qty_excluding_dn(so_detail, exclude_dn)
		own_total = sum(flt(s.get("delivered_qty")) for s in group)
		extra = max(other_dn_delivered - own_total, 0)

		for snap in group:
			own = flt(snap.get("delivered_qty"))
			reserved = flt(snap.get("reserved_qty"))
			# Never invent delivered above this reservation's size
			snap["delivered_qty"] = min(own, reserved)
			for entry in snap.get("sb_entries") or []:
				entry["delivered_qty"] = min(
					flt(entry.get("delivered_qty")),
					flt(entry.get("qty")),
				)

		if extra <= 0:
			continue

		for snap in group:
			if extra <= 0:
				break
			reserved = flt(snap.get("reserved_qty"))
			room = max(reserved - flt(snap.get("delivered_qty")), 0)
			if room <= 0:
				continue
			add = min(room, extra)
			snap["delivered_qty"] = flt(snap.get("delivered_qty")) + add
			extra -= add
			# Mirror extra onto batch rows with remaining capacity
			remaining_add = add
			for entry in snap.get("sb_entries") or []:
				if remaining_add <= 0:
					break
				entry_room = max(flt(entry.get("qty")) - flt(entry.get("delivered_qty")), 0)
				if entry_room <= 0:
					continue
				entry_add = min(entry_room, remaining_add)
				entry["delivered_qty"] = flt(entry.get("delivered_qty")) + entry_add
				remaining_add -= entry_add

	return prepared


def restore_stock_reservations_after_cancel(doc):
	"""
	Restore Stock Reservation Entries from the submit-time snapshot.

	Restores every snapshot row (all batches). Unreserved DNs have no snapshot
	and must not get a new reservation invented on cancel.
	"""
	if not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
		return

	snapshots, comment_name = _load_cancelled_sre_snapshot(doc.name)
	if not snapshots:
		return

	prepared = _distribute_delivered_across_snapshots(snapshots, doc.name)

	errors = []
	for snapshot in prepared:
		try:
			# Skip only when THIS reservation is still submitted. Do not skip
			# other batches just because another SRE on the SO line is active.
			if _snapshot_sre_still_active(snapshot):
				continue
			_recreate_stock_reservation_from_snapshot(snapshot)
		except Exception:
			frappe.log_error(
				title="DN Cancel - SRE Restore Error",
				message=f"{doc.name}\n{frappe.as_json(snapshot)}\n{frappe.get_traceback()}",
			)
			errors.append(
				f"{snapshot.get('item_code') or ''} / "
				f"{snapshot.get('voucher_no') or ''} / "
				f"reserved {flt(snapshot.get('reserved_qty'))}"
			)

	if comment_name:
		frappe.delete_doc("Comment", comment_name, ignore_permissions=True, force=True)

	if errors:
		frappe.throw(
			_(
				"Failed to restore stock reservation(s) while cancelling Delivery Note {0}:<br>{1}"
			).format(frappe.bold(doc.name), "<br>".join(frappe.bold(e) for e in errors)),
			title=_("Stock Reservation Restore Failed"),
		)


def _snapshot_sre_still_active(snapshot):
	"""True when the snapshotted SRE was never cancelled and is still submitted."""
	sre_name = snapshot.get("name")
	if not sre_name or not frappe.db.exists("Stock Reservation Entry", sre_name):
		return False
	return cint(frappe.db.get_value("Stock Reservation Entry", sre_name, "docstatus")) == 1


def _delivered_qty_excluding_dn(so_detail, exclude_dn):
	"""Stock qty still delivered against SO item from other submitted DNs."""
	if not so_detail:
		return 0
	return flt(
		frappe.db.sql(
			"""
			select coalesce(sum(dni.stock_qty), 0)
			from `tabDelivery Note Item` dni
			join `tabDelivery Note` dn on dn.name = dni.parent
			where dni.so_detail = %s
			  and dn.docstatus = 1
			  and ifnull(dn.is_return, 0) = 0
			  and dn.name != %s
			""",
			(so_detail, exclude_dn or ""),
		)[0][0]
	)


def _get_active_reserved_qty(sales_order, so_detail, warehouse=None):
	"""Net reserved qty still available to deliver (reserved - delivered)."""
	filters = {
		"voucher_type": "Sales Order",
		"voucher_no": sales_order,
		"voucher_detail_no": so_detail,
		"docstatus": 1,
		"status": ["in", ["Reserved", "Partially Reserved", "Partially Delivered"]],
	}
	if warehouse:
		filters["warehouse"] = warehouse

	rows = frappe.get_all(
		"Stock Reservation Entry",
		filters=filters,
		fields=["reserved_qty", "delivered_qty"],
	)
	return sum(flt(r.reserved_qty) - flt(r.delivered_qty) for r in rows)


def _get_active_reserved_stock_qty(sales_order, so_detail, warehouse=None):
	"""Gross reserved qty on active SREs (do not subtract delivered)."""
	filters = {
		"voucher_type": "Sales Order",
		"voucher_no": sales_order,
		"voucher_detail_no": so_detail,
		"docstatus": 1,
		"status": ["in", ["Reserved", "Partially Reserved", "Partially Delivered", "Delivered"]],
	}
	if warehouse:
		filters["warehouse"] = warehouse

	rows = frappe.get_all(
		"Stock Reservation Entry",
		filters=filters,
		fields=["reserved_qty"],
	)
	return sum(flt(r.reserved_qty) for r in rows)


def _recreate_stock_reservation_from_snapshot(snapshot):
	reserved_qty = flt(snapshot.get("reserved_qty"))
	if reserved_qty <= 0:
		return

	sales_order = snapshot.get("voucher_no")
	so_detail = snapshot.get("voucher_detail_no")
	warehouse = snapshot.get("warehouse")
	delivered_qty = flt(snapshot.get("delivered_qty"))
	voucher_qty = flt(snapshot.get("voucher_qty") or reserved_qty)

	# Prefer live SO line qty — snapshot voucher_qty may be a partial reserve size.
	if so_detail and frappe.db.exists("Sales Order Item", so_detail):
		soi = frappe.db.get_value(
			"Sales Order Item",
			so_detail,
			["qty", "stock_qty", "conversion_factor"],
			as_dict=True,
		)
		if soi:
			voucher_qty = flt(soi.stock_qty) or (
				flt(soi.qty) * flt(soi.conversion_factor or 1)
			)

	# Headroom is based on gross reserved vs voucher only. Do not subtract
	# delivered_qty here — that belongs on the SRE after submit and would
	# incorrectly shrink later batches in a multi-batch restore.
	active_qty = _get_active_reserved_stock_qty(sales_order, so_detail, warehouse)
	remaining_capacity = max(voucher_qty - active_qty, 0)
	if remaining_capacity <= 0:
		return

	if reserved_qty > remaining_capacity:
		reserved_qty = remaining_capacity

	# Keep prior delivered on this reservation; clamp to what we can restore.
	delivered_qty = min(delivered_qty, reserved_qty)

	sre = frappe.new_doc("Stock Reservation Entry")
	sre.item_code = snapshot.get("item_code")
	sre.warehouse = warehouse
	sre.company = snapshot.get("company")
	sre.stock_uom = snapshot.get("stock_uom")
	sre.voucher_type = snapshot.get("voucher_type") or "Sales Order"
	sre.voucher_no = sales_order
	sre.voucher_detail_no = so_detail
	sre.voucher_qty = voucher_qty
	sre.reserved_qty = reserved_qty
	sre.available_qty = flt(snapshot.get("available_qty") or reserved_qty)
	sre.available_qty_to_reserve = reserved_qty
	from_voucher_type = snapshot.get("from_voucher_type")
	from_voucher_no = snapshot.get("from_voucher_no")
	from_voucher_detail_no = snapshot.get("from_voucher_detail_no")
	# DN-cancel restore runs after the DN is cancelled — linking from_voucher
	# to that DN raises CancelledLinkError.
	if from_voucher_type and from_voucher_no:
		if cint(frappe.db.get_value(from_voucher_type, from_voucher_no, "docstatus")) == 2:
			from_voucher_type = from_voucher_no = from_voucher_detail_no = None
	sre.from_voucher_type = from_voucher_type
	sre.from_voucher_no = from_voucher_no
	sre.from_voucher_detail_no = from_voucher_detail_no

	reservation_based_on = snapshot.get("reservation_based_on") or "Qty"
	sb_entries = snapshot.get("sb_entries") or []

	if reservation_based_on == "Serial and Batch" and sb_entries:
		sre.has_batch_no = 1
		sre.has_serial_no = cint(snapshot.get("has_serial_no"))
		sre.reservation_based_on = "Serial and Batch"
		sre.use_serial_batch_fields = 1

		# Keep all batches from the snapshot at original qty when possible.
		# Only scale if we had to cap reserved_qty for voucher headroom.
		total_sb_qty = sum(
			flt(e.get("qty")) for e in sb_entries if e.get("batch_no") or e.get("serial_no")
		)
		scale = (
			(reserved_qty / total_sb_qty)
			if total_sb_qty > 0 and abs(total_sb_qty - reserved_qty) > 0.0001
			else 1.0
		)

		# Preserve snapshot length/pieces on restore — these reflect the
		# reservation state at DN submit/cancel, not a fresh batch pick.
		for entry in sb_entries:
			if not entry.get("batch_no") and not entry.get("serial_no"):
				continue
			entry_qty = flt(entry.get("qty")) * scale
			if entry_qty <= 0:
				continue
			entry_delivered = min(flt(entry.get("delivered_qty")) * scale, entry_qty)
			sre.append(
				"sb_entries",
				{
					"batch_no": entry.get("batch_no"),
					"serial_no": entry.get("serial_no"),
					"qty": entry_qty,
					"delivered_qty": entry_delivered,
					"warehouse": entry.get("warehouse") or warehouse,
					"pieces": flt(entry.get("pieces")),
					"length": flt(entry.get("length")),
					"section_weight": flt(entry.get("section_weight")),
				},
			)

		if not sre.sb_entries:
			return

		reserved_qty = sum(flt(e.qty) for e in sre.sb_entries)
		sre.reserved_qty = reserved_qty
		sre.available_qty_to_reserve = reserved_qty
		delivered_qty = min(delivered_qty, reserved_qty)

		# Keep explicit batches from snapshot; do not auto-pick
		sre.auto_reserve_serial_and_batch = lambda *args, **kwargs: None
	else:
		sre.reservation_based_on = "Qty"
		sre.has_batch_no = 0
		sre.has_serial_no = 0

	sre.flags.ignore_permissions = True
	sre.insert()
	sre.submit()

	# Preserve this reservation's delivered qty after submit (earlier DNs /
	# prior history on this SRE only — already distributed per snapshot).
	if delivered_qty > 0:
		sre.db_set("delivered_qty", delivered_qty, update_modified=False)
		if sre.reservation_based_on == "Serial and Batch":
			# Prefer entry-level delivered from snapshot; if header has delivered
			# but entries were zero, leave entries as stored on insert.
			for entry in sre.sb_entries:
				if flt(entry.delivered_qty) > 0:
					frappe.db.set_value(
						"Serial and Batch Entry",
						entry.name,
						"delivered_qty",
						flt(entry.delivered_qty),
						update_modified=False,
					)
		sre.reload()
		sre.update_status()
		sre.update_reserved_qty_in_voucher()
		sre.update_reserved_stock_in_bin()


def cancel_stock_reconciliations_for_delivery_note(delivery_note, delete=False):
    """Cancel Stock Reconciliations created for a DN.

    By default only cancels (docstatus=2) so the audit trail is retained.
    Force-delete is opt-in and should not be used on DN cancel.
    """
    sr_names = frappe.get_all(
        "Stock Reconciliation Item",
        filters={"delivery_note_ref": delivery_note},
        pluck="parent",
    )

    errors = []
    for sr_name in set(sr_names):
        try:
            sr = frappe.get_doc("Stock Reconciliation", sr_name)
            if sr.docstatus == 1:
                sr.flags.ignore_permissions = True
                sr.cancel()

            if delete and frappe.db.exists("Stock Reconciliation", sr_name):
                # Soft cleanup only when explicitly requested (e.g. replace stale
                # draft/cancelled SR before recreating on DN submit). Prefer
                # cancel-only on DN cancel so audit history remains.
                if cint(frappe.db.get_value("Stock Reconciliation", sr_name, "docstatus")) == 2:
                    frappe.delete_doc(
                        "Stock Reconciliation",
                        sr_name,
                        ignore_permissions=True,
                        force=True,
                    )
        except Exception:
            frappe.log_error(
                title="DN Cancel - Stock Reconciliation Release Error",
                message=f"{sr_name}\n{frappe.get_traceback()}",
            )
            errors.append(sr_name)

    if errors and not delete:
        # On DN cancel, surface SR release failures instead of swallowing them
        frappe.throw(
            _(
                "Failed to cancel Stock Reconciliation(s) linked to Delivery Note {0}:<br>{1}"
            ).format(frappe.bold(delivery_note), "<br>".join(frappe.bold(e) for e in errors)),
            title=_("Stock Reconciliation Cancel Failed"),
        )


@frappe.whitelist()
def create_sr_from_dn(delivery_note):
    doc = frappe.get_doc("Delivery Note", delivery_note)
    create_stock_reconciliation(doc)
    return "done"


def create_stock_reconciliation(self):
    import frappe
    from frappe.utils import flt, nowtime, get_datetime, add_to_date

    items_with_invoice_qty = [row for row in self.items if flt(row.difference_qty) > 0 and row.custom_deliver_as_qty]
    if not items_with_invoice_qty:
        return

    # ── Remove stale SRs linked to this DN ───────────────────────────
    # ── Remove stale SRs linked to this DN (cancel only — keep audit trail) ──
    cancel_stock_reconciliations_for_delivery_note(self.name, delete=False)

    # ── Create SR ────────────────────────────────────────────────────
    sr = frappe.new_doc("Stock Reconciliation")
    sr.purpose = "Stock Reconciliation"
    # Only set optional dims when both DN and SR expose the field (sites differ).
    if sr.meta.has_field("cost_center") and self.meta.has_field("cost_center"):
        sr.cost_center = self.get("cost_center")
    if sr.meta.has_field("branch") and self.meta.has_field("branch"):
        sr.branch = self.get("branch")

    db_posting = frappe.db.get_value(
        "Delivery Note", self.name, ["posting_date", "posting_time"], as_dict=True
    )

    dn_posting_date = db_posting.posting_date if db_posting else self.posting_date
    dn_posting_time = (
        db_posting.posting_time if db_posting else (self.posting_time or nowtime())
    )

    dt = get_datetime(f"{dn_posting_date} {dn_posting_time}")
    before_dt = add_to_date(dt, seconds=-10)

    sr.set_posting_time = 1
    sr.posting_date = before_dt.date()
    sr.posting_time = before_dt.strftime('%H:%M:%S')
    sr.company = self.company

    if self.set_warehouse:
        sr.set_warehouse = self.set_warehouse

    # ── Add Items ────────────────────────────────────────────────────
    for row in items_with_invoice_qty:
        total_qty = flt(row.qty) + flt(row.difference_qty)

        valuation_rate = 0
        if total_qty and flt(row.amount):
            valuation_rate = flt(row.amount) / total_qty
        if not valuation_rate:
            valuation_rate = (
                flt(row.incoming_rate)
                or flt(row.rate)
                or flt(frappe.get_cached_value("Item", row.item_code, "valuation_rate"))
                or 1
            )

        # ── CASE 1: Bundle ───────────────────────────────────────────
        if row.serial_and_batch_bundle:
            sbb = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)

            batch_entries = [e for e in sbb.entries if e.batch_no]
            batch_count = len(batch_entries)

            if batch_count > 0:
                total_bundle_qty = sum(abs(flt(e.qty)) for e in batch_entries)

                for entry in batch_entries:
                    batch_qty = abs(flt(entry.qty))

                    ratio = (
                        batch_qty / total_bundle_qty
                        if total_bundle_qty
                        else 1.0 / batch_count
                    )

                    entry_invoice_qty = flt(row.invoice_qty) * ratio
                    entry_diff_qty = entry_invoice_qty - batch_qty
                    entry_dn_qty = batch_qty

                    sr.append(
                        "items",
                        {
                            "item_code": row.item_code,
                            "warehouse": row.warehouse or self.set_warehouse,
                            "use_serial_batch_fields": 1,
                            "batch_no": entry.batch_no,
                            "qty": entry_invoice_qty,
                            "difference_qty": entry_diff_qty,
                            "reconcile_all_serial_batch": 0,
                            "delivery_note_qty": entry_dn_qty,
                            "valuation_rate": valuation_rate,
                            "current_rate": flt(row.incoming_rate),
                            "pieces": (
                                flt(row.get("pieces")) * ratio
                                if row.get("pieces")
                                else 0
                            ),
                            "length": flt(row.get("length")),
                            "average_length": flt(row.get("average_length")),
                            "section_weight": flt(row.get("section_weight")),
                            "delivery_note_ref": self.name,
                            "serial_and_batch_bundle": None,
                        },
                    )
                continue

        # ── CASE 2: Normal ───────────────────────────────────────────
        sr.append(
            "items",
            {
                "item_code": row.item_code,
                "warehouse": row.warehouse or self.set_warehouse,
                "batch_no": row.batch_no or None,
                "use_serial_batch_fields": 1 if row.batch_no else 0,
                "qty": row.invoice_qty,
                "difference_qty": flt(row.difference_qty),
                "reconcile_all_serial_batch": 0,
                "delivery_note_qty": flt(row.qty),
                "amount": flt(row.amount),
                "valuation_rate": valuation_rate,
                "current_rate": flt(row.incoming_rate),
                "pieces": flt(row.get("pieces")),
                "length": flt(row.get("length")),
                "average_length": flt(row.get("average_length")),
                "section_weight": flt(row.get("section_weight")),
                "delivery_note_ref": self.name,
                "serial_and_batch_bundle": None,
            },
        )

    # ── Insert SR ───────────────────────────────────────────────────
    sr.flags.ignore_permissions = True
    sr.insert(ignore_permissions=True)

    # ── Adjust valuation ─────────────────────────────────────────────
    for sr_item in sr.items:
        if (
            flt(sr_item.qty)
            and flt(sr_item.current_qty)
            and flt(sr_item.current_valuation_rate)
        ):
            new_rate = flt(
                flt(sr_item.current_qty)
                * flt(sr_item.current_valuation_rate)
                / flt(sr_item.qty)
            )
            # Do not clobber a positive rate with a computed zero.
            if new_rate:
                sr_item.valuation_rate = new_rate
                sr_item.amount = flt(sr_item.qty) * flt(sr_item.valuation_rate)
        # Never submit with a zero valuation rate (ERPNext throws).
        if flt(sr_item.qty) and not flt(sr_item.valuation_rate):
            sr_item.valuation_rate = (
                flt(sr_item.current_valuation_rate)
                or flt(sr_item.current_rate)
                or flt(frappe.db.get_value("Item", sr_item.item_code, "valuation_rate"))
                or flt(
                    frappe.db.get_value(
                        "Bin",
                        {"item_code": sr_item.item_code, "warehouse": sr_item.warehouse},
                        "valuation_rate",
                    )
                )
                or 1
            )
            sr_item.amount = flt(sr_item.qty) * flt(sr_item.valuation_rate)

    sr.save(ignore_permissions=True)

    # Final guard after validate/save may reset rates from empty SLE history.
    for sr_item in sr.items:
        if flt(sr_item.qty) and not flt(sr_item.valuation_rate):
            sr_item.valuation_rate = (
                flt(frappe.db.get_value("Item", sr_item.item_code, "valuation_rate")) or 1
            )
            sr_item.amount = flt(sr_item.qty) * flt(sr_item.valuation_rate)
            sr_item.db_set("valuation_rate", sr_item.valuation_rate, update_modified=False)
            sr_item.db_set("amount", sr_item.amount, update_modified=False)

    # ── Submit SR ───────────────────────────────────────────────────
    sr.submit()

    # ── Update SBB & DN AFTER SUBMIT ─────────────────────────────
    for dn_row in self.items:
        # Skip items without difference (they were already updated safely in before_submit)
        if flt(dn_row.difference_qty) <= 0:
            continue

        if dn_row.serial_and_batch_bundle:
            update_bundle_to_invoice_qty(dn_row, flt(dn_row.invoice_qty),flt(dn_row.qty),flt(dn_row.custom_deliver_as_qty))

        dn_row.qty = flt(dn_row.invoice_qty)
        dn_row.stock_qty = flt(dn_row.invoice_qty) * flt(dn_row.conversion_factor or 1)

    # ── Recalculate DN ──────────────────────────────────────────────
    for row in self.items:
        row.amount = 0
        row.base_amount = 0
        row.net_amount = 0
        row.base_net_amount = 0

    self.set_missing_values()

    if hasattr(self, "apply_pricing_rule"):
        self.apply_pricing_rule()

    for row in self.items:
        row.amount = flt(row.qty) * flt(row.rate)
        row.base_amount = flt(row.amount) * flt(self.conversion_rate or 1)

    self.calculate_taxes_and_totals()

    self.run_method("validate")

    if hasattr(self, "validate_stock"):
        self.validate_stock()

    if hasattr(self, "validate_with_previous_doc"):
        self.validate_with_previous_doc()

    if hasattr(self, "recalculate_rate_and_amount"):
        self.recalculate_rate_and_amount()

    frappe.msgprint(
        f"Stock Reconciliation <b>{sr.name}</b> created and submitted for Delivery Note <b>{self.name}</b>.",
        alert=True,
    )

import frappe
import json
from frappe.utils import flt
from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
    get_sre_details_for_voucher,
)
from erpnext.stock.doctype.packed_item.packed_item import make_packing_list
from frappe.model.mapper import get_mapped_doc


@frappe.whitelist()
def make_delivery_note_custom(source_name, target_doc=None, kwargs=None):

    # =====================================================
    # SAFE KWARGS PARSING
    # =====================================================
    if not kwargs:
        kwargs = frappe.flags.args or {}

    # if string → parse JSON
    if isinstance(kwargs, str):
        try:
            kwargs = json.loads(kwargs)
        except Exception:
            kwargs = {}

    # if list → merge dicts
    if isinstance(kwargs, list):
        temp = {}
        for k in kwargs:
            if isinstance(k, dict):
                temp.update(k)
        kwargs = temp

    # final safety
    if not isinstance(kwargs, dict):
        kwargs = {}

    kwargs = frappe._dict(kwargs)

    # =====================================================
    selected_sre = kwargs.get("selected_sre", [])
    for_reserved_stock = kwargs.get("for_reserved_stock")

    so = frappe.get_doc("Sales Order", source_name)

    def set_missing_values(source, target):
        target.run_method("set_missing_values")
        target.run_method("calculate_taxes_and_totals")
        target.run_method("set_use_serial_batch_fields")
        make_packing_list(target)

    def update_item(source, target, source_parent):
        target.qty = flt(source.qty) - flt(source.delivered_qty)
        target.amount = target.qty * flt(source.rate)
        target.base_amount = target.qty * flt(source.base_rate)
        target.deliver_as_qty = source_parent.deliver_as_qty

    # =====================================================
    # STEP 1: MAP BASIC DOC
    # =====================================================
    target_doc = get_mapped_doc(
        "Sales Order",
        so.name,
        {
            "Sales Order": {
                "doctype": "Delivery Note",
                "validation": {"docstatus": ["=", 1]},
            },
            "Sales Order Item": {
                "doctype": "Delivery Note Item",
                "field_map": {
                    "name": "so_detail",
                    "parent": "against_sales_order",
                    "rate": "rate",
                },
                "postprocess": update_item,
            },
        },
        target_doc,
    )

    # remove default mapped items
    target_doc.items = []

    # =====================================================
    # STEP 2: SRE LOGIC (reserved stock only — client requirement)
    # =====================================================
    if for_reserved_stock:
        sre_list = get_sre_details_for_voucher("Sales Order", source_name)

        so_items = {d.name: d for d in so.items}

        for sre in sre_list:

            # filter selected SRE / SO item rows
            if selected_sre and sre.voucher_detail_no not in selected_sre:
                continue

            so_item = so_items.get(sre.voucher_detail_no)
            if not so_item:
                continue

            dn_item = get_mapped_doc(
                "Sales Order Item",
                so_item.name,
                {
                    "Sales Order Item": {
                        "doctype": "Delivery Note Item",
                        "field_map": {
                            "name": "so_detail",
                            "parent": "against_sales_order",
                            "rate": "rate",
                        },
                    }
                },
                ignore_permissions=True,
            )

            # qty from reserved (full available reserved qty for this SRE)
            dn_item.qty = flt(sre.reserved_qty) / flt(dn_item.conversion_factor or 1)
            dn_item.warehouse = sre.warehouse
            dn_item.custom_deliver_as_qty = so.deliver_as_qty
            _apply_reserved_dims_to_dn_item(dn_item, so_item, sre)
            # batch / serial handling — copy reservation length/pieces into bundle
            if sre.reservation_based_on == "Serial and Batch":
                dn_item.serial_and_batch_bundle = get_ssb_bundle_for_voucher_from_sre(sre)
                if dn_item.serial_and_batch_bundle:
                    # Do not stamp batch_no when a bundle is present — ERPNext
                    # treats batch_no + serial_and_batch_bundle as conflicting
                    # and may rebuild the bundle on submit.
                    if hasattr(dn_item, "batch_no"):
                        dn_item.batch_no = None
                    bundle_entries = frappe.get_all(
                        "Serial and Batch Entry",
                        filters={
                            "parent": dn_item.serial_and_batch_bundle,
                            "parenttype": "Serial and Batch Bundle",
                        },
                        fields=["batch_no", "qty", "length"],
                    )
                    sync_dn_item_length_from_entries(
                        dn_item, bundle_entries, dn_item.so_detail
                    )

            if frappe.get_meta("Delivery Note Item").has_field("custom_sre"):
                dn_item.custom_sre = sre.name

            target_doc.append("items", dn_item)

    # =====================================================
    # FINALIZE
    # =====================================================
    set_missing_values(so, target_doc)

    return target_doc

import frappe
import json
from frappe.utils import flt, cstr


@frappe.whitelist()
def get_sales_order_items_for_selector(filters=None):

    # -----------------------------
    # Parse filters safely
    # -----------------------------
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    so_filters = [["docstatus", "=", 1]]

    # -----------------------------
    # Static Filters (from frontend)
    # -----------------------------
    for key, val in filters.items():
        if key in ("dynamic_filters", "project", "po_no"):
            continue

        if val:
            if isinstance(val, list) and len(val) == 2:
                so_filters.append([key, val[0], val[1]])
            else:
                so_filters.append([key, "=", val])

    # Project filter
    if filters.get("project"):
        so_filters.append(["project", "=", filters.get("project")])

    if filters.get("po_no"):
        so_filters.append(["po_no", "like", f"%{filters['po_no']}%"])

    # -----------------------------
    # Dynamic Filters (FilterGroup)
    # -----------------------------
    dynamic_filters = filters.get("dynamic_filters")

    if dynamic_filters:
        if isinstance(dynamic_filters, str):
            dynamic_filters = json.loads(dynamic_filters)

        for df in dynamic_filters:
            if len(df) >= 4:
                fieldname = df[1]
                operator = df[2]
                value = df[3]

                if operator == "Between" and isinstance(value, str) and " to " in value:
                    value = value.split(" to ")

                so_filters.append([fieldname, operator, value])

    # -----------------------------
    # Fetch Sales Orders
    # -----------------------------
    sales_orders = frappe.get_all(
        "Sales Order",
        fields=["name", "customer", "transaction_date", "currency", "company", "po_no"],
        filters=so_filters,
        order_by="transaction_date desc",
    )

    if not sales_orders:
        return []

    so_names = [d.name for d in sales_orders]
    so_map = {d.name: d for d in sales_orders}

    # -----------------------------
    # Fetch SO Items (Optimized)
    # -----------------------------
    optional_soi_cols = []
    for col in ("pieces", "length_size", "assorted_length", "description"):
        if frappe.db.has_column("Sales Order Item", col):
            optional_soi_cols.append(f"soi.{col}")
        else:
            optional_soi_cols.append(f"NULL AS {col}")

    section_weight_sel = (
        "item.weight_per_meter AS section_weight"
        if frappe.db.has_column("Item", "weight_per_meter")
        else "0 AS section_weight"
    )

    items = frappe.db.sql(
        f"""
        SELECT
            soi.name,
            soi.parent,
            soi.item_code,
            soi.item_name,
            soi.qty,
            soi.delivered_qty,
            soi.rate,
            soi.amount,
            soi.uom,
            {", ".join(optional_soi_cols)},
            {section_weight_sel}
        FROM `tabSales Order Item` soi
        LEFT JOIN `tabItem` item
            ON item.name = soi.item_code
        WHERE soi.parent IN %(so_names)s
        ORDER BY soi.parent ASC, soi.idx ASC
        """,
        {"so_names": so_names},
        as_dict=True,
    )

    # -----------------------------
    # Fetch Reservation (Optimized)
    # -----------------------------
    reservation_rows = frappe.db.sql(
        """
        SELECT
            sre.voucher_detail_no,
            SUM(sre.reserved_qty - sre.delivered_qty) AS reserved_qty
        FROM `tabStock Reservation Entry` sre
        WHERE sre.docstatus = 1
        AND sre.voucher_type = 'Sales Order'
        AND sre.status IN ('Reserved', 'Partially Reserved','Partially Delivered')
        AND (%(company)s IS NULL OR sre.company = %(company)s)
        GROUP BY sre.voucher_detail_no
        """,
        {"company": filters.get("company")},
        as_dict=True,
    )

    reservation_map = {
        r.voucher_detail_no: flt(r.reserved_qty) for r in reservation_rows
    }

    # -----------------------------
    # Build Final Rows
    # -----------------------------
    rows = []

    for row in items:

        # correct pending logic
        pending_qty = flt(row.qty) - flt(row.delivered_qty)

        if pending_qty <= 0:
            continue

        so = so_map.get(row.parent) or {}

        reserved_qty = flt(reservation_map.get(row.name, 0))
        # Client: only reserved SO qty should appear for Delivery Note fetch
        if reserved_qty <= 0:
            continue

        rows.append(
            {
                "name": row.name,
                "parent": row.parent,
                "customer": so.get("customer"),
                "transaction_date": so.get("transaction_date"),
                "company": so.get("company"),
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": flt(row.qty),
                "pending_qty": pending_qty,
                "reserved_qty": reserved_qty,
                "uom": row.uom,
                "pieces": row.pieces,
                "length": row.length_size,
                "section_weight": flt(row.section_weight),
                "po_no": so.get("po_no"),
                "assorted_length": row.assorted_length,
                "description": row.description,
            }
        )

    return rows