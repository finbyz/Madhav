import frappe
from frappe.utils import cint, flt
from erpnext.controllers.sales_and_purchase_return import get_rate_for_return

def update_stock_ledger(self, allow_negative_stock=False, via_landed_cost_voucher=False):
    self.update_ordered_and_reserved_qty()

    sl_entries = []
    stock_items = self.get_stock_items()

    for d in self.get("items"):
        if d.item_code not in stock_items:
            continue

        if d.warehouse:
            pr_qty = flt(flt(d.qty) * flt(d.conversion_factor), d.precision("stock_qty"))
            pieces_qty = flt(d.pieces)
            
            if pr_qty:
                if d.from_warehouse and (
                    (not cint(self.is_return) and self.docstatus == 1)
                    or (cint(self.is_return) and self.docstatus == 2)
                ):
                    serial_and_batch_bundle = d.get("serial_and_batch_bundle")
                    if self.is_internal_transfer() and self.is_return and self.docstatus == 2:
                        serial_and_batch_bundle = frappe.db.get_value(
                            "Stock Ledger Entry",
                            {"voucher_detail_no": d.name, "warehouse": d.from_warehouse},
                            "serial_and_batch_bundle",
                        )

                    from_warehouse_sle = self.get_sl_entries(
                        d,
                        {
                            "actual_qty": -1 * pr_qty,
                            "pieces_qty": -1 * pieces_qty,
                            "warehouse": d.from_warehouse,
                            "outgoing_rate": d.rate,
                            "recalculate_rate": 1,
                            "dependant_sle_voucher_detail_no": d.name,
                            "serial_and_batch_bundle": serial_and_batch_bundle,
                        },
                    )

                    sl_entries.append(from_warehouse_sle)

                type_of_transaction = "Inward"
                if self.docstatus == 2:
                    type_of_transaction = "Outward"

                inward_qty = pr_qty
                inward_pieces = pieces_qty

                sle = self.get_sl_entries(
                    d,
                    {
                        "actual_qty": inward_qty,
                        "pieces_qty": inward_pieces,
                        "serial_and_batch_bundle": (
                            d.serial_and_batch_bundle
                            if not self.is_internal_transfer()
                            or self.is_return
                            or (self.is_internal_transfer() and self.docstatus == 2)
                            else self.get_package_for_target_warehouse(
                                d, type_of_transaction=type_of_transaction
                            )
                        ),
                    },
                )

                if self.is_return:
                    outgoing_rate = get_rate_for_return(
                        self.doctype, self.name, d.item_code, self.return_against, item_row=d
                    )

                    sle.update(
                        {
                            "outgoing_rate": outgoing_rate,
                            "recalculate_rate": 1,
                            "serial_and_batch_bundle": d.serial_and_batch_bundle,
                        }
                    )
                    if d.from_warehouse:
                        sle.dependant_sle_voucher_detail_no = d.name
                else:
                    sle.update(
                        {
                            "incoming_rate": d.valuation_rate,
                            "recalculate_rate": 1
                            if (self.is_subcontracted and (d.bom or d.get("fg_item"))) or d.from_warehouse
                            else 0,
                        }
                    )
                sl_entries.append(sle)

                if d.from_warehouse and (
                    (not cint(self.is_return) and self.docstatus == 2)
                    or (cint(self.is_return) and self.docstatus == 1)
                ):
                    serial_and_batch_bundle = None
                    if self.is_internal_transfer() and self.docstatus == 2:
                        serial_and_batch_bundle = frappe.db.get_value(
                            "Stock Ledger Entry",
                            {"voucher_detail_no": d.name, "warehouse": d.warehouse},
                            "serial_and_batch_bundle",
                        )

                    from_warehouse_sle = self.get_sl_entries(
                        d,
                        {
                            "actual_qty": -1 * pr_qty,
                            "pieces_qty": -1 * pieces_qty,
                            "warehouse": d.from_warehouse,
                            "recalculate_rate": 1,
                            "serial_and_batch_bundle": (
                                self.get_package_for_target_warehouse(d, d.from_warehouse, "Inward")
                                if self.is_internal_transfer() and self.is_return
                                else serial_and_batch_bundle
                            ),
                        },
                    )

                    sl_entries.append(from_warehouse_sle)

        if flt(d.rejected_qty) != 0:
            sl_entries.append(
                self.get_sl_entries(
                    d,
                    {
                        "warehouse": d.rejected_warehouse,
                        "actual_qty": flt(flt(d.rejected_qty) * flt(d.conversion_factor), d.precision("stock_qty")),
                        "pieces_qty": flt(d.rejected_pieces) if hasattr(d, "rejected_pieces") else 0.0,
                        "incoming_rate": 0.0,
                        "serial_and_batch_bundle": d.rejected_serial_and_batch_bundle,
                    },
                )
            )

    if self.get("is_old_subcontracting_flow"):
        self.make_sl_entries_for_supplier_warehouse(sl_entries)

    self.make_sl_entries(
        sl_entries,
        allow_negative_stock=allow_negative_stock,
        via_landed_cost_voucher=via_landed_cost_voucher,
    )
