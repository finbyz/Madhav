import frappe
import json
from frappe.utils import flt, cint, nowtime
from frappe import _

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
    fix_group_cost_center(self)
    populate_missing_batch_bundle(self)
    change_qty_serial_and_batch(self)


def fix_group_cost_center(self):
    """
    Delivery Notes made via the standard "Create > Delivery Note" button
    run core ERPNext's get_mapped_doc + set_missing_values(), which can
    overwrite a row's cost_center with the company's group/root cost
    center even when the source Sales Order Item already had a valid
    leaf-level cost center set. ERPNext refuses to submit against a group
    cost center ("... is a group cost center and group cost centers
    cannot be used in transactions"), so this silently blocks submit
    despite the correct value being available one hop away on the SO.

    Re-sync from the SO Item whenever the DN row ended up on a group
    cost center (or with none at all) but the SO row has a valid leaf
    cost center to fall back to.
    """
    for item in self.items:
        if not item.so_detail:
            continue

        current = item.get("cost_center")
        if current and not frappe.db.get_value("Cost Center", current, "is_group"):
            # Already a valid leaf cost center — leave it alone.
            continue

        so_cost_center = frappe.db.get_value("Sales Order Item", item.so_detail, "cost_center")
        if not so_cost_center:
            continue

        if frappe.db.get_value("Cost Center", so_cost_center, "is_group"):
            # SO row itself only has a group center — nothing safe to copy.
            continue

        item.cost_center = so_cost_center


def populate_missing_batch_bundle(self):
    """
    Delivery Notes made via the standard "Create > Delivery Note" button
    (core get_mapped_doc) never run our SRE/batch-bundle logic — that only
    happens in make_delivery_note_custom (the "Get Items From > Sales
    Order" dialog). Rows can end up with neither batch_no nor
    serial_and_batch_bundle set, even though the SO has active,
    batch-tracked Stock Reservation Entries backing the row.

    Attach the correct Serial and Batch Bundle here so both creation paths
    converge on the same data shape before any invoice_qty /
    reconciliation logic runs.
    """
    from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
        get_ssb_bundle_for_voucher,
    )

    for item in self.items:
        if not item.against_sales_order or not item.so_detail:
            continue
        if item.serial_and_batch_bundle or item.batch_no:
            continue

        sre_list = frappe.get_all(
            "Stock Reservation Entry",
            filters={
                "voucher_type": "Sales Order",
                "voucher_no": item.against_sales_order,
                "voucher_detail_no": item.so_detail,
                "docstatus": 1,
            },
            # get_ssb_bundle_for_voucher (erpnext core) reads item_code,
            # warehouse, has_serial_no and has_batch_no directly off this
            # dict via sre["field"] — fetching only name/reservation_based_on
            # caused a KeyError there, which silently prevented the bundle
            # from ever being attached.
            fields=[
                "name",
                "reservation_based_on",
                "item_code",
                "warehouse",
                "has_serial_no",
                "has_batch_no",
            ],
        )

        batch_sres = [s for s in sre_list if s.reservation_based_on == "Serial and Batch"]
        if not batch_sres:
            continue

        if len(batch_sres) == 1:
            bundle_name = get_ssb_bundle_for_voucher(batch_sres[0])
            if bundle_name:
                item.serial_and_batch_bundle = bundle_name
        else:
            # SO item was reserved across more than one SRE — merge their
            # batch entries into a single bundle so this DN row still
            # represents the full reserved quantity.
            item.serial_and_batch_bundle = _build_merged_batch_bundle(item, batch_sres)


def _build_merged_batch_bundle(item, sre_rows):
    from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
        get_ssb_bundle_for_voucher,
    )

    merged_entries = []
    for sre in sre_rows:
        bundle_name = get_ssb_bundle_for_voucher(sre)
        if not bundle_name:
            continue
        src_bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
        merged_entries.extend(e for e in src_bundle.entries if e.batch_no)

    if not merged_entries:
        return None

    new_bundle = frappe.new_doc("Serial and Batch Bundle")
    new_bundle.item_code = item.item_code
    new_bundle.warehouse = item.warehouse
    new_bundle.voucher_type = "Delivery Note"
    new_bundle.type_of_transaction = "Outward"

    for e in merged_entries:
        new_bundle.append(
            "entries",
            {
                "batch_no": e.batch_no,
                "qty": -abs(flt(e.qty)),
                "warehouse": e.warehouse or item.warehouse,
                "pieces": flt(e.get("pieces")),
                "length": flt(e.get("length")),
                "section_weight": flt(e.get("section_weight")),
            },
        )

    new_bundle.total_qty = -sum(abs(flt(e.qty)) for e in merged_entries)
    new_bundle.flags.ignore_validate = True
    new_bundle.flags.ignore_links = True
    new_bundle.insert(ignore_permissions=True)
    return new_bundle.name

def validate(self, method):

    for row in self.items:
        if row.against_sales_order:
            deliver_as_qty = frappe.db.get_value(
                "Sales Order", row.against_sales_order, "deliver_as_qty"
            )

            # Sync the row-level flag from the Sales Order regardless of
            # how this row was created (standard "Create > Delivery Note"
            # mapping vs. the custom reserved-stock selector). The
            # quantity-difference handling in before_submit relies on
            # this row-level field, so without this sync it silently
            # never runs for Delivery Notes made via the standard path.
            if deliver_as_qty and not row.custom_deliver_as_qty:
                row.custom_deliver_as_qty = 1

            if deliver_as_qty and not row.invoice_qty:
                frappe.throw(f"Invoice Qty is mandatory for row {row.idx}")

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


def change_qty_serial_and_batch(self):
    for item in self.items:
        #print("DEBUG entry:", item.item_code, item.against_sales_order, item.serial_and_batch_bundle, flush=True)

        if not item.against_sales_order:
            #print("DEBUG skip - no against_sales_order:", item.item_code, flush=True)
            continue

        deliver_as_qty = frappe.db.get_value(
            "Sales Order",
            item.against_sales_order,
            "deliver_as_qty",
        )

        if not item.serial_and_batch_bundle:
            #print("DEBUG skip - no serial_and_batch_bundle:", item.item_code, flush=True)
            continue

        bundle = frappe.get_doc(
            "Serial and Batch Bundle",
            item.serial_and_batch_bundle,
        )
        bundle.reload()

        # IMPORTANT: Use item.qty here, NOT invoice_qty.
        target_qty = flt(item.qty)

        batch_entries = [e for e in bundle.entries if e.batch_no]
        #print("DEBUG batch_entries count:", len(batch_entries), flush=True)
        if not batch_entries:
            #print("DEBUG skip - no batch_entries", flush=True)
            continue

        #print("DEBUG bundle entries:", [(e.batch_no, e.length, e.section_weight, e.qty) for e in batch_entries], flush=True)
        total_original_qty = sum(abs(flt(e.qty)) for e in batch_entries)
        if not total_original_qty:
            continue

        # ── Step 1: Proportional distribution of QTY, capped by batch_qty ──
        desired_qty = []
        for entry in batch_entries:
            original = abs(flt(entry.qty))
            ratio = original / total_original_qty
            dq = target_qty * ratio

            batch_qty = flt(
                frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
            )
            dq = min(dq, batch_qty)
            desired_qty.append(dq)

        actual_total_qty = sum(desired_qty)
        leftover_qty = target_qty - actual_total_qty

        for i, entry in enumerate(batch_entries):
            if abs(leftover_qty) < 0.0001:
                break
            batch_qty = flt(
                frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
            )
            room = batch_qty - desired_qty[i]
            if room > 0:
                take = min(room, leftover_qty)
                desired_qty[i] += take
                leftover_qty -= take

        # ── Step 2: Convert each entry's qty → pieces using ITS OWN length/section_weight ──
        # qty = (pieces * length * section_weight) / 1000
        # => pieces = (qty * 1000) / (length * section_weight)
        raw_pieces = []
        for i, entry in enumerate(batch_entries):
            entry_length = flt(entry.length)
            entry_section_weight = flt(entry.section_weight)
            if entry_length and entry_section_weight:
                pieces = (desired_qty[i] * 1000) / (entry_length * entry_section_weight)
            else:
                pieces = 0
            raw_pieces.append(pieces)

        target_total_pieces = sum(raw_pieces)

        # ── Step 3: Cap pieces against what's actually available in the batch, spill leftover ──
        available_pieces_cache = {
            entry.batch_no: get_batch_available_pieces(
                item.item_code, entry.warehouse or item.warehouse, entry.batch_no
            )
            for entry in batch_entries
        }

        desired_pieces = []
        for i, entry in enumerate(batch_entries):
            available = available_pieces_cache.get(entry.batch_no, 0)
            dp = raw_pieces[i]
            if available and available > 0:
                dp = min(dp, available)
            desired_pieces.append(dp)

        actual_total_pieces = sum(desired_pieces)
        leftover_pieces = target_total_pieces - actual_total_pieces

        for i, entry in enumerate(batch_entries):
            if abs(leftover_pieces) < 0.0001:
                break
            available = available_pieces_cache.get(entry.batch_no, 0)
            if not available:
                continue
            room = available - desired_pieces[i]
            if room > 0:
                take = min(room, leftover_pieces)
                desired_pieces[i] += take
                leftover_pieces -= take

        # If total available pieces across all batches is less than what's
        # needed, leftover_pieces stays > 0 here — meaning we physically
        # can't fulfil target_qty in full. Flag it rather than silently
        # under-delivering.
        if leftover_pieces > 0.0001:
            frappe.msgprint(
                f"Not enough available pieces for {item.item_code} in "
                f"{item.warehouse}: short by {leftover_pieces:.2f} pieces.",
                indicator="orange",
                alert=True,
            )

        # ── Step 4: Recompute qty from FINAL pieces so qty & pieces stay in sync ──
        final_qty = []
        total_allocated_pieces = 0
        for i, entry in enumerate(batch_entries):
            entry_length = flt(entry.length)
            entry_section_weight = flt(entry.section_weight)
            pieces = desired_pieces[i]

            if entry_length and entry_section_weight:
                qty = (pieces * entry_length * entry_section_weight) / 1000
            else:
                qty = 0

            final_qty.append(qty)
            total_allocated_pieces += pieces
        allocated_total_qty = sum(final_qty)

        # ── Write everything back ──
        for i, entry in enumerate(batch_entries):
            # Outward transaction stores negative qty
                pieces = desired_pieces[i]
                length = flt(entry.length)

                # Calculate section weight from final qty, pieces and length
                if pieces and length:
                    section_weight = (final_qty[i] * 1000) / (pieces * length)
                else:
                    section_weight = 0

                # Update bundle entry
                entry.section_weight = section_weight
                entry.qty = -final_qty[i]        # Outward transaction stores negative qty
                entry.pieces = pieces

        item.qty = allocated_total_qty
        item.stock_qty = allocated_total_qty
        item.amount = flt(item.rate) * allocated_total_qty
        item.base_amount = item.amount * flt(self.conversion_rate or 1)
        item.pieces = max(0, total_allocated_pieces)
        item.section_weight = section_weight
        bundle.total_qty = -allocated_total_qty
        bundle.flags.ignore_validate = True
        bundle.flags.ignore_links = True
        #print("DEBUG final item.qty:", item.qty, "item.amount:", item.amount, flush=True)
        bundle.save(ignore_permissions=True)
        bundle.reload()

        frappe.logger().info(
            f"Updated Bundle {bundle.name}: Total Qty={bundle.total_qty}, "
            f"Total Pieces={total_allocated_pieces}, "
            f"Entries={[{'batch': d.batch_no, 'qty': d.qty, 'pieces': d.pieces} for d in bundle.entries]}"
        )

def get_available_qty_for_item(row):

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

    # Not tied to an active SO reservation — fall back to whatever batch
    # qty is actually represented in the bundle (batch_no is not a
    # reliable single-batch source of truth, see note above).
    if row.serial_and_batch_bundle:
        sbb = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)
        return sum(abs(flt(e.qty)) for e in sbb.entries if e.batch_no)

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

    # ── Proportional distribution with batch_qty caps & spillover ──
    desired = []
    for entry in batch_entries:
        original = abs(flt(entry.qty))
        ratio = original / total_original_qty
        desired_qty = target_qty * ratio

        batch_qty = flt(
            frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
        )
        desired_qty = min(desired_qty, batch_qty)
        desired.append(desired_qty)

    # Spill leftover (from capped batches) to batches with remaining room
    actual_total = sum(desired)
    leftover = target_qty - actual_total

    for i, entry in enumerate(batch_entries):
        if abs(leftover) < 0.0001:
            break
        batch_qty = flt(
            frappe.db.get_value("Batch", entry.batch_no, "batch_qty") or 0
        )
        room = batch_qty - desired[i]
        if room > 0:
            take = min(room, leftover)
            desired[i] += take
            leftover -= take

    # ── Apply ──
    length = flt(item.length)
    section_weight = flt(item.section_weight)
    total_pieces = 0

    for i, entry in enumerate(batch_entries):
        entry.qty = -desired[i]

        # Calculate pieces from qty using formula:
        # qty = (pieces * length * section_weight) / 1000
        # => pieces = (qty * 1000) / (length * section_weight)
        if length and section_weight:
            entry.pieces = (desired[i] * 1000) / (length * section_weight)
        else:
            entry.pieces = 0

        total_pieces += entry.pieces

    bundle.total_qty = -target_qty
    bundle.flags.ignore_validate = True
    bundle.flags.ignore_links = True
    bundle.save(ignore_permissions=True)

from frappe.utils import get_datetime, add_to_date, nowtime


def before_submit(self, method):
    # For each row, work out how much qty is available "for free" (from the
    # existing reservation / batch / bundle) before we'd need to cancel the
    # SRE and create a Stock Reconciliation to cover the excess.
    #
    # FIX: gate difference_qty on custom_deliver_as_qty. Previously this was
    # computed unconditionally for every row, which meant rows NOT flagged
    # for "deliver as qty" could still end up with a difference_qty > 0.
    # That leaked downstream into cancel_stock_reservations_from_so and the
    # final loop in create_stock_reconciliation (both of which only check
    # difference_qty > 0, not the ticked flag), letting mixed ticked/unticked
    # rows on one DN cross-contaminate. Fixing it here, at the source, closes
    # that gap for every consumer at once.
    for i in self.items:
        if not i.custom_deliver_as_qty:
            i.difference_qty = 0
            continue

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
    Cancel Stock Reservation Entries created against Sales Order
    using DN item references.

    Snapshots cancelled SRE details on the Delivery Note so they can be
    restored when the Delivery Note is cancelled (Manjot task 2).
    """
    cancelled_snapshots = []

    for row in doc.items:
        if not row.against_sales_order or not row.so_detail:
            continue

        # Skip if no difference qty (invoice_qty within remaining reserved qty)
        if flt(row.difference_qty) <= 0:
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
            try:
                sre = frappe.get_doc("Stock Reservation Entry", sre_name)

                if sre.docstatus == 1:
                    cancelled_snapshots.append(_snapshot_sre(sre))
                    sre.flags.ignore_permissions = True
                    sre.cancel()

            except Exception:
                frappe.log_error(
                    title="SRE Cancel Error",
                    message=f"{sre_name}\n{frappe.get_traceback()}",
                )

    if cancelled_snapshots and doc.name:
        _store_cancelled_sre_snapshot(doc.name, cancelled_snapshots)


def _snapshot_sre(sre):
    """Capture fields needed to recreate a Stock Reservation Entry."""
    return {
        "item_code": sre.item_code,
        "warehouse": sre.warehouse,
        "company": sre.company,
        "stock_uom": sre.stock_uom,
        "voucher_type": sre.voucher_type,
        "voucher_no": sre.voucher_no,
        "voucher_detail_no": sre.voucher_detail_no,
        "voucher_qty": flt(sre.voucher_qty),
        "reserved_qty": flt(sre.reserved_qty),
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
                "warehouse": e.warehouse,
                "pieces": flt(e.get("pieces")),
                "length": flt(e.get("length")),
                "section_weight": flt(e.get("section_weight")),
            }
            for e in (sre.get("sb_entries") or [])
        ],
    }


def _store_cancelled_sre_snapshot(delivery_note, snapshots):
    """Persist cancelled SRE snapshots on the DN for restore-on-cancel."""
    # Replace any previous snapshot for this DN
    existing = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Delivery Note",
            "reference_name": delivery_note,
            "comment_type": "Info",
            "content": ("like", f"{CANCELLED_SRE_COMMENT_PREFIX}%"),
        },
        pluck="name",
    )
    for name in existing:
        frappe.delete_doc("Comment", name, ignore_permissions=True, force=True)

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
    comments = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Delivery Note",
            "reference_name": delivery_note,
            "comment_type": "Info",
            "content": ("like", f"{CANCELLED_SRE_COMMENT_PREFIX}%"),
        },
        fields=["name", "content"],
        order_by="creation desc",
        limit=1,
    )
    if not comments:
        return [], None

    content = comments[0].content or ""
    if not content.startswith(CANCELLED_SRE_COMMENT_PREFIX):
        return [], comments[0].name

    try:
        return json.loads(content[len(CANCELLED_SRE_COMMENT_PREFIX) :]), comments[0].name
    except Exception:
        frappe.log_error(
            title="DN Cancel - Invalid SRE Snapshot",
            message=f"{delivery_note}\n{content}",
        )
        return [], comments[0].name


def on_cancel(doc, method=None):
    """Manjot Issue 1: release stock, then restore reservations on DN cancel."""
    if getattr(doc, "is_return", 0):
        return

    release_stock_used_by_delivery_note(doc)
    restore_stock_reservations_after_cancel(doc)


def release_stock_used_by_delivery_note(doc):
    """Cancel Stock Reconciliations created for this DN (delivery_note_ref)."""
    cancel_stock_reconciliations_for_delivery_note(doc.name, delete=True)


def restore_stock_reservations_after_cancel(doc):
    """
    Restore Stock Reservation Entries cancelled during DN submit.

    ERPNext already reverses delivered_qty on SREs that remain submitted.
    This restores SREs that Madhav fully cancelled (difference_qty / Deliver as Qty).
    """
    if not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
        return

    snapshots, comment_name = _load_cancelled_sre_snapshot(doc.name)
    if not snapshots:
        # Fallback: rebuild from DN item batches when no snapshot exists
        snapshots = _build_sre_snapshots_from_dn_items(doc)

    if not snapshots:
        return

    for snapshot in snapshots:
        try:
            _recreate_stock_reservation_from_snapshot(snapshot)
        except Exception:
            frappe.log_error(
                title="DN Cancel - SRE Restore Error",
                message=f"{doc.name}\n{frappe.as_json(snapshot)}\n{frappe.get_traceback()}",
            )

    if comment_name:
        frappe.delete_doc("Comment", comment_name, ignore_permissions=True, force=True)


def _build_sre_snapshots_from_dn_items(doc):
    """Build reservation snapshots from DN rows when no submit-time snapshot exists."""
    snapshots = []

    for row in doc.items:
        if not row.against_sales_order or not row.so_detail:
            continue

        # Skip if an active reservation already covers this SO item
        active_qty = _get_active_reserved_qty(
            row.against_sales_order, row.so_detail, row.warehouse
        )
        qty_to_restore = flt(row.stock_qty)
        if qty_to_restore <= 0 or active_qty >= qty_to_restore:
            continue

        so_qty = flt(
            frappe.db.get_value("Sales Order Item", row.so_detail, "qty") or qty_to_restore
        )
        stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
        batches = _get_batch_qtys_from_dn_item(row)

        if batches:
            for batch_no, batch_qty in batches:
                if batch_qty <= 0:
                    continue
                snapshots.append(
                    {
                        "item_code": row.item_code,
                        "warehouse": row.warehouse,
                        "company": doc.company,
                        "stock_uom": stock_uom,
                        "voucher_type": "Sales Order",
                        "voucher_no": row.against_sales_order,
                        "voucher_detail_no": row.so_detail,
                        "voucher_qty": so_qty,
                        "reserved_qty": batch_qty,
                        "available_qty": batch_qty,
                        "reservation_based_on": "Serial and Batch",
                        "has_batch_no": 1,
                        "has_serial_no": 0,
                        "from_voucher_type": "Delivery Note",
                        "from_voucher_no": doc.name,
                        "from_voucher_detail_no": row.name,
                        "sb_entries": [
                            {
                                "batch_no": batch_no,
                                "qty": batch_qty,
                                "warehouse": row.warehouse,
                                "pieces": flt(row.get("pieces")),
                                "length": flt(row.get("length")),
                                "section_weight": flt(row.get("section_weight")),
                            }
                        ],
                    }
                )
        else:
            snapshots.append(
                {
                    "item_code": row.item_code,
                    "warehouse": row.warehouse,
                    "company": doc.company,
                    "stock_uom": stock_uom,
                    "voucher_type": "Sales Order",
                    "voucher_no": row.against_sales_order,
                    "voucher_detail_no": row.so_detail,
                    "voucher_qty": so_qty,
                    "reserved_qty": qty_to_restore,
                    "available_qty": qty_to_restore,
                    "reservation_based_on": "Qty",
                    "has_batch_no": 0,
                    "has_serial_no": 0,
                    "from_voucher_type": "Delivery Note",
                    "from_voucher_no": doc.name,
                    "from_voucher_detail_no": row.name,
                    "sb_entries": [],
                }
            )

    return snapshots


def _get_batch_qtys_from_dn_item(row):
    batches = []
    if row.serial_and_batch_bundle:
        entries = frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": row.serial_and_batch_bundle},
            fields=["batch_no", "qty"],
        )
        for e in entries:
            if e.batch_no:
                batches.append((e.batch_no, abs(flt(e.qty))))
    elif row.batch_no:
        batches.append((row.batch_no, flt(row.stock_qty)))
    return batches


def _get_active_reserved_qty(sales_order, so_detail, warehouse=None):
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


def _recreate_stock_reservation_from_snapshot(snapshot):
    reserved_qty = flt(snapshot.get("reserved_qty"))
    if reserved_qty <= 0:
        return

    sales_order = snapshot.get("voucher_no")
    so_detail = snapshot.get("voucher_detail_no")
    warehouse = snapshot.get("warehouse")

    # Avoid duplicate reservation if ERPNext already restored delivered_qty
    if _get_active_reserved_qty(sales_order, so_detail, warehouse) >= reserved_qty:
        return

    sre = frappe.new_doc("Stock Reservation Entry")
    sre.item_code = snapshot.get("item_code")
    sre.warehouse = warehouse
    sre.company = snapshot.get("company")
    sre.stock_uom = snapshot.get("stock_uom")
    sre.voucher_type = snapshot.get("voucher_type") or "Sales Order"
    sre.voucher_no = sales_order
    sre.voucher_detail_no = so_detail
    sre.voucher_qty = flt(snapshot.get("voucher_qty") or reserved_qty)
    sre.reserved_qty = reserved_qty
    sre.available_qty = flt(snapshot.get("available_qty") or reserved_qty)
    sre.available_qty_to_reserve = reserved_qty
    sre.from_voucher_type = snapshot.get("from_voucher_type")
    sre.from_voucher_no = snapshot.get("from_voucher_no")
    sre.from_voucher_detail_no = snapshot.get("from_voucher_detail_no")

    reservation_based_on = snapshot.get("reservation_based_on") or "Qty"
    sb_entries = snapshot.get("sb_entries") or []

    if reservation_based_on == "Serial and Batch" and sb_entries:
        sre.has_batch_no = 1
        sre.has_serial_no = cint(snapshot.get("has_serial_no"))
        sre.reservation_based_on = "Serial and Batch"
        sre.use_serial_batch_fields = 1

        for entry in sb_entries:
            if not entry.get("batch_no") and not entry.get("serial_no"):
                continue
            sre.append(
                "sb_entries",
                {
                    "batch_no": entry.get("batch_no"),
                    "serial_no": entry.get("serial_no"),
                    "qty": flt(entry.get("qty")),
                    "warehouse": entry.get("warehouse") or warehouse,
                    "pieces": flt(entry.get("pieces")),
                    "length": flt(entry.get("length")),
                    "section_weight": flt(entry.get("section_weight")),
                },
            )

        # Keep explicit batches from snapshot; do not auto-pick
        sre.auto_reserve_serial_and_batch = lambda *args, **kwargs: None
    else:
        sre.reservation_based_on = "Qty"
        sre.has_batch_no = 0
        sre.has_serial_no = 0

    sre.flags.ignore_permissions = True
    sre.insert()
    sre.submit()


def cancel_stock_reconciliations_for_delivery_note(delivery_note, delete=False):
    """Cancel (and optionally delete) Stock Reconciliations created for a DN."""
    sr_names = frappe.get_all(
        "Stock Reconciliation Item",
        filters={"delivery_note_ref": delivery_note},
        pluck="parent",
    )

    for sr_name in set(sr_names):
        try:
            sr = frappe.get_doc("Stock Reconciliation", sr_name)
            if sr.docstatus == 1:
                sr.flags.ignore_permissions = True
                sr.cancel()

            if delete and frappe.db.exists("Stock Reconciliation", sr_name):
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
    cancel_stock_reconciliations_for_delivery_note(self.name, delete=True)

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
        if total_qty:
            valuation_rate = flt(row.amount) / total_qty

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
                "use_serial_batch_fields": 1,
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
        if flt(sr_item.qty) and flt(sr_item.current_qty):
            sr_item.valuation_rate = flt(
                flt(sr_item.current_qty)
                * flt(sr_item.current_valuation_rate)
                / flt(sr_item.qty)
            )
            sr_item.amount = flt(sr_item.qty) * flt(sr_item.valuation_rate)

    sr.save(ignore_permissions=True)

    # ── Submit SR ───────────────────────────────────────────────────
    sr.submit()

    # ── Sync batch details (ported from "Update Batch details" Server Script) ──
    for row in sr.items:
        if row.batch_no:
            frappe.db.set_value(
                "Batch",
                row.batch_no,
                {
                    "pieces": row.pieces,
                    "assorted_length": row.assorted_length,
                    "average_length": row.average_length,
                },
            )

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
    get_ssb_bundle_for_voucher,
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
    # STEP 2: SRE LOGIC
    # =====================================================
    if for_reserved_stock:
        sre_list = get_sre_details_for_voucher("Sales Order", source_name)

        so_items = {d.name: d for d in so.items}

        for sre in sre_list:

            # filter selected SRE
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

            # qty from reserved
            dn_item.qty = flt(sre.reserved_qty) / flt(dn_item.conversion_factor or 1)
            dn_item.custom_deliver_as_qty = so.deliver_as_qty
            # batch / serial handling
            if sre.reservation_based_on == "Serial and Batch":
                dn_item.serial_and_batch_bundle = get_ssb_bundle_for_voucher(sre)

            # set custom field (no db_set!)
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
    items = frappe.db.sql(
        """
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
            soi.pieces,
            soi.length_size,
            soi.assorted_length,
            soi.description,
            item.weight_per_meter AS section_weight
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
            SUM(sre.reserved_qty) AS reserved_qty
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

        reserved_qty = reservation_map.get(row.name, 0)

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