import frappe
import json
from frappe.utils import flt, cint, nowtime
from frappe import _
from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import get_stock_reservation_entries_for_voucher

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
        if not row.batch_no:
            continue

        key = (row.item_code, row.warehouse, row.batch_no)
        reserved_qty = flt(reserved_lookup.get(key))

        if reserved_qty and flt(row.qty) < reserved_qty:
            frappe.throw(
                _(
                    "Row {0}: Delivery qty {1} is less than reserved qty {2} "
                    "for Item {3}, Batch {4} in Warehouse {5}"
                ).format(
                    row.idx,
                    row.qty,
                    reserved_qty,
                    row.item_code,
                    row.batch_no,
                    row.warehouse,
                )
            )


@frappe.whitelist()
def get_sales_order_items_for_selector(filters=None):

    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    so_filters = [
        ["docstatus", "=", 1],
    ]

    # Handle filters from frontend (status, per_delivered, company, customer, project)
    for key, val in filters.items():
        if key in ("dynamic_filters", "project"):
            continue

        if val:
            if isinstance(val, list) and len(val) == 2:
                # Array format like ["not in", [...]] or ["<", 99.99]
                so_filters.append([key, val[0], val[1]])
            else:
                so_filters.append([key, "=", val])

    if filters.get("project"):
        so_filters.append(["project", "=", filters.get("project")])

    # Handle dynamic filters from FilterGroup
    if filters.get("dynamic_filters"):
        dynamic_filters = filters.get("dynamic_filters")
        if isinstance(dynamic_filters, str):
            dynamic_filters = json.loads(dynamic_filters)

        for df in dynamic_filters:
            if len(df) >= 4:
                # df format: [doctype, fieldname, operator, value]
                fieldname = df[1]
                operator = df[2]
                value = df[3]

                if operator == "Between" and isinstance(value, str) and " to " in value:
                    value = value.split(" to ")

                so_filters.append([fieldname, operator, value])

    sales_orders = frappe.get_all(
        "Sales Order",
        fields=["name", "customer", "transaction_date", "currency"],
        filters=so_filters,
        order_by="transaction_date desc",
    )

    if not sales_orders:
        return []

    so_names = [d.name for d in sales_orders]
    so_map = {d.name: d for d in sales_orders}

    # -------------------------
    # Fetch Sales Order Items + Item section weight
    # -------------------------

    items = frappe.db.sql(
        """
        SELECT
            soi.name,
            soi.parent,
            soi.item_code,
            soi.item_name,
            soi.qty,
            soi.rate,
            soi.amount,
            soi.billed_amt,
            soi.uom,
            soi.pieces,
            soi.length_size,
            soi.description,
            item.weight_per_meter as section_weight
        FROM `tabSales Order Item` soi
        LEFT JOIN `tabItem` item
            ON item.name = soi.item_code
        WHERE soi.parent IN %(so_names)s
        ORDER BY soi.parent asc, soi.idx asc
        """,
        {"so_names": so_names},
        as_dict=True,
    )

    # -----------------------------
    # Fetch reserved quantities
    # -----------------------------

    reservation_rows = frappe.db.sql(
        """
        SELECT
            sre.voucher_detail_no,
            SUM(sre.reserved_qty) AS reserved_qty,
            SUM(sbe.peices) AS reserved_pieces
        FROM `tabStock Reservation Entry` sre
        LEFT JOIN `tabSerial and Batch Entry` sbe
            ON sbe.parent = sre.name
        WHERE sre.docstatus = 1
        AND sre.voucher_type = 'Sales Order'
        GROUP BY sre.voucher_detail_no
        """,
        as_dict=True,
    )

    reservation_map = {r.voucher_detail_no: r for r in reservation_rows}

    rows = []

    for row in items:

        billed_qty = flt(row.billed_amt) / flt(row.rate) if flt(row.rate) else 0
        pending_qty = flt(row.qty) - billed_qty

        if pending_qty <= 0:
            continue

        so = so_map.get(row.parent) or {}

        reservation = reservation_map.get(row.name, {})

        rows.append(
            {
                "name": row.name,
                "parent": row.parent,
                "customer": so.get("customer"),
                "transaction_date": so.get("transaction_date"),
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": flt(row.qty),
                "pending_qty": pending_qty,
                "uom": row.uom,
                "pieces": row.pieces,
                "length": row.length_size,
                # section weight from Item
                "section_weight": flt(row.section_weight),
                # reservation data
                "reserved_qty": flt(reservation.get("reserved_qty")),
                "reserved_pieces": flt(reservation.get("reserved_pieces")),
            }
        )

    return rows


def validate(self, method):
    for row in self.items:
        if row.serial_and_batch_bundle:
            data = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)
            if len(data.entries) == 1:
                for doc in data.entries:
                    if not row.batch_no:
                        row.batch_no = doc.batch_no
                        if row.serial_and_batch_bundle:
                            try:
                                sbb = frappe.get_doc("Serial and Batch Bundle", row.serial_and_batch_bundle)

                                # If submitted → cancel first
                                if sbb.docstatus == 1:
                                    sbb.cancel()

                                # Delete document
                                frappe.delete_doc("Serial and Batch Bundle", sbb.name, force=1)

                                # Clear reference
                                row.serial_and_batch_bundle = ""

                            except Exception:
                                frappe.log_error(
                                    title="SBB Delete Error",
                                    message=frappe.get_traceback()
                                )
        if row.against_sales_order:
            deliver_as_qty = frappe.db.get_value(
                "Sales Order", row.against_sales_order, "deliver_as_qty"
            )
            if deliver_as_qty and not row.invoice_qty:
                frappe.throw(f"Invoice Qty is mandatory for row {row.idx}")


from frappe.utils import get_datetime, add_to_date, nowtime


def before_submit(self, method):
    # Step 1: Set difference qty
    for i in self.items:
        i.difference_qty = i.invoice_qty - i.qty

    # Step 2: Cancel Stock Reservation linked with Sales Order
    cancel_stock_reservations_from_so(self)

    # Step 3: Create Stock Reconciliation
    create_stock_reconciliation(self)


def cancel_stock_reservations_from_so(doc):
    """
    Cancel Stock Reservation Entries created against Sales Order
    using DN item references
    """

    for row in doc.items:
        if not row.against_sales_order or not row.so_detail:
            continue

        sre_list = frappe.get_all(
            "Stock Reservation Entry",
            filters={
                "voucher_type": "Sales Order",
                "voucher_no": row.against_sales_order,
                "voucher_detail_no": row.so_detail,
                "docstatus": 1
            },
            pluck="name"
        )

        for sre_name in sre_list:
            try:
                sre = frappe.get_doc("Stock Reservation Entry", sre_name)

                if sre.docstatus == 1:
                    sre.cancel()

            except Exception:
                frappe.log_error(
                    title="SRE Cancel Error",
                    message=f"{sre_name}\n{frappe.get_traceback()}"
                )


@frappe.whitelist()
def create_sr_from_dn(delivery_note):
    doc = frappe.get_doc("Delivery Note", delivery_note)
    create_stock_reconciliation(doc)
    return "done"


def create_stock_reconciliation(self):
    """
    Before DN submits:
    1. Collect all items with invoice_qty > 0 into ONE Stock Reconciliation.
    2. For each item: qty = invoice_qty, valuation_rate = amount / invoice_qty (amount unchanged).
    3. Insert + submit the SR (triggers SR on_submit which updates DN item rows in DB).
    4. Reload updated qty/valuation_rate back into in-memory doc items so DN submits with correct values.
    """

    items_with_invoice_qty = [row for row in self.items if flt(row.invoice_qty) > 0]

    if not items_with_invoice_qty:
        return

    # ── Cancel & delete any stale SRs from previous failed DN submit attempts ──
    # If DN submission failed before, the SR it created is still submitted.
    # That leftover SR blocks the next attempt with a "future transaction" error.
    stale_srs = frappe.get_all(
        "Stock Reconciliation Item",
        filters={"delivery_note_ref": self.name},
        fields=["parent"],
        pluck="parent",
    )
    for sr_name in set(stale_srs):
        try:
            stale_sr = frappe.get_doc("Stock Reconciliation", sr_name)
            if stale_sr.docstatus == 1:
                stale_sr.flags.ignore_permissions = True
                stale_sr.cancel()
            frappe.delete_doc(
                "Stock Reconciliation", sr_name, ignore_permissions=True, force=True
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Failed to cancel stale SR {sr_name}"
            )

    sr = frappe.new_doc("Stock Reconciliation")
    sr.purpose = "Stock Reconciliation"
    from frappe.utils import add_to_date

    # IMPORTANT: During before_submit, self.posting_time may already be overridden
    # to the current time by the Frappe submit flow. Read from DB to get the actual
    # saved posting_date/time, then post SR 1 second BEFORE it so it is never
    # a "future" entry relative to the DN's Serial and Batch Bundle.
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

    sr.posting_time = before_dt.time()
    sr.company = self.company
    if self.set_warehouse:
        sr.set_warehouse = self.set_warehouse

    for row in items_with_invoice_qty:
        total_qty = flt(row.qty) + flt(row.difference_qty)

        valuation_rate = 0
        if total_qty:
            valuation_rate = flt(row.amount) / total_qty

        sr.append(
            "items",
            {
                "item_code": row.item_code,
                "warehouse": row.warehouse or self.set_warehouse,
                "batch_no": row.batch_no or None,
                "use_serial_batch_fields": cint(row.get("use_serial_batch_fields")),
                "serial_and_batch_bundle":(
                     row.serial_and_batch_bundle if not row.use_serial_batch_fields else ""
                ),
                "qty": row.invoice_qty,
                "difference_qty": flt(row.difference_qty),
                "reconcile_all_serial_batch": (
                    1 if not row.use_serial_batch_fields else 0
                ),
                "delivery_note_qty": flt(row.qty),
                "amount": flt(row.amount),
                "current_rate": flt(row.incoming_rate),
                "pieces": flt(row.get("pieces")),
                "length": flt(row.get("length")),
                "average_length": flt(row.get("average_length")),
                "section_weight": flt(row.get("section_weight")),
                "delivery_note_ref": self.name,
            },
        )

    sr.flags.ignore_permissions = True
    # sr.flags.ignore_validate_serial_batch = True

    # ── Manually trigger current stock calculations ──────────────────────────
    # SR's validate() skips these if use_serial_batch_fields=True and save=False.
    # Calling it with save=True here ensures current_qty/valuation_rate are set.
    sr.set_current_serial_and_batch_bundle(save=True)
    sr.insert(ignore_permissions=True)
    sr.save(ignore_permissions=True)

    # Set a process-level flag so check_future_entries_exists skips this specific SR
    # for BOTH the SR bundle validation AND the subsequent DN bundle validation.
    # frappe.flags is reset automatically between requests — no manual cleanup needed.
    # frappe.flags.skip_future_check_for_sr = sr.name
    updated_map = {
        sr_row.item_code + "|" + (sr_row.batch_no or ""): sr_row for sr_row in sr.items
    }

    for dn_row in self.items:
        key = dn_row.item_code + "|" + (dn_row.batch_no or "")
        sr_row = updated_map.get(key)

        if sr_row:
            dn_row.qty = sr_row.delivery_note_qty + sr_row.difference_qty
            dn_row.incoming_rate = sr_row.valuation_rate

    # Reset dependent fields
    for row in self.items:
        row.amount = 0
        row.base_amount = 0
        row.net_amount = 0
        row.base_net_amount = 0

    # Recalculate base values
    self.set_missing_values()

    # Apply pricing rules (if exists)
    if hasattr(self, "apply_pricing_rule"):
        self.apply_pricing_rule()

    # Recalculate item amounts
    for row in self.items:
        row.amount = flt(row.qty) * flt(row.rate)
        row.base_amount = flt(row.amount) * flt(self.conversion_rate or 1)

    # Taxes & totals
    self.calculate_taxes_and_totals()

    # 🔥 Re-run full validation
    self.run_method("validate")

    # Stock validations
    if hasattr(self, "validate_stock"):
        self.validate_stock()

    if hasattr(self, "validate_with_previous_doc"):
        self.validate_with_previous_doc()

    # Optional (version dependent)
    if hasattr(self, "recalculate_rate_and_amount"):
        self.recalculate_rate_and_amount()

    sr.submit()

    frappe.msgprint(
        f"Stock Reconciliation <b>{sr.name}</b> created and submitted for Delivery Note <b>{self.name}</b>.",
        alert=True,
    )

    # ── Reload updated values back into in-memory doc items ──────────────────
    # SR on_submit already updated DN Item rows in DB; reflect those changes
    # in the in-memory doc so the DN stock ledger uses invoice_qty as qty.
