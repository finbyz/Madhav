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



def validate(self, method):
    for row in self.items: 
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
                "docstatus": 1,
            },
            pluck="name",
        )

        for sre_name in sre_list:
            try:
                sre = frappe.get_doc("Stock Reservation Entry", sre_name)

                if sre.docstatus == 1:
                    sre.flags.ignore_permissions = True
                    sre.cancel()

            except Exception:
                frappe.log_error(
                    title="SRE Cancel Error",
                    message=f"{sre_name}\n{frappe.get_traceback()}",
                )


@frappe.whitelist()
def create_sr_from_dn(delivery_note):
    doc = frappe.get_doc("Delivery Note", delivery_note)
    create_stock_reconciliation(doc)
    return "done"


def create_stock_reconciliation(self):
    import frappe
    from frappe.utils import flt, nowtime, get_datetime, add_to_date

    items_with_invoice_qty = [row for row in self.items if flt(row.difference_qty) > 0]

    if not items_with_invoice_qty:
        return

    # ── Remove stale SRs ─────────────────────────────────────────────
    stale_srs = frappe.get_all(
        "Stock Reconciliation Item",
        filters={"delivery_note_ref": self.name},
        pluck="parent",
    )

    for sr_name in set(stale_srs):
        try:
            stale_sr = frappe.get_doc("Stock Reconciliation", sr_name)
            if stale_sr.docstatus == 1:
                stale_sr.flags.ignore_permissions = True
                stale_sr.cancel()

            frappe.delete_doc(
                "Stock Reconciliation",
                sr_name,
                ignore_permissions=True,
                force=True,
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Failed to cancel stale SR {sr_name}"
            )

    # ── Create SR ────────────────────────────────────────────────────
    sr = frappe.new_doc("Stock Reconciliation")
    sr.purpose = "Stock Reconciliation"
    sr.cost_center = self.cost_center
    sr.branch = self.branch

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

    # ── 🔥 Update SBB & DN AFTER SUBMIT ─────────────────────────────
    for dn_row in self.items:
        if not dn_row.serial_and_batch_bundle:
            continue

        sbb = frappe.get_doc("Serial and Batch Bundle", dn_row.serial_and_batch_bundle)

        # Map SR qty by batch
        batch_map = {
            d.batch_no: d.qty
            for d in sr.items
            if d.item_code == dn_row.item_code and d.batch_no
        }

        updated_total = 0

        for entry in sbb.entries:
            if entry.batch_no in batch_map:
                entry.qty = flt(batch_map[entry.batch_no])
                updated_total += entry.qty

        # Save SBB
        sbb.flags.ignore_permissions = True
        sbb.save()

        # Update DN qty
        dn_row.qty = updated_total

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
    # ✅ SAFE KWARGS PARSING (FIXED)
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
        if key in ("dynamic_filters", "project" , "po_no"):
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
        fields=["name", "customer", "transaction_date", "currency", "company","po_no"],
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
        AND sre.status IN ('Reserved', 'Partially Reserved')
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

        # ✅ correct pending logic
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