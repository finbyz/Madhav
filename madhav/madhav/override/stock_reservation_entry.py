import frappe
from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import StockReservationEntry as _StockReservationEntry,get_available_qty_to_reserve,get_sre_reserved_qty_for_voucher_detail_no
from frappe import _
from frappe.utils import flt
from erpnext.stock.utils import get_stock_balance

class StockReservationEntry(_StockReservationEntry):
    def update_status(self, status: str | None = None, update_modified: bool = True) -> None:
            """Updates status based on Voucher Qty, Reserved Qty and Delivered Qty."""
            over_reservation_allowance = flt(
                frappe.db.get_single_value(
                    "Stock Settings",
                    "over_reservation_allowance"
                ) or 0
            )
    
            max_voucher_qty = self.voucher_qty * (
                1 + over_reservation_allowance / 100
            )
            if not status:
                if self.docstatus == 2:
                    status = "Cancelled"
                elif self.docstatus == 1:
                    if self.reserved_qty == self.delivered_qty:
                        status = "Delivered"
                    elif self.delivered_qty and self.delivered_qty < self.reserved_qty:
                        status = "Partially Delivered"
                    elif self.reserved_qty >= max_voucher_qty:
                        status = "Reserved"
                    else:
                        status = "Partially Reserved"
                else:
                    status = "Draft"
    
            frappe.db.set_value(self.doctype, self.name, "status", status, update_modified=update_modified)
    def validate_with_allowed_qty(self, qty_to_be_reserved: float) -> None:
            """Validates `Reserved Qty` with `Max Reserved Qty`."""
    
            self.db_set(
                "available_qty",
                get_available_qty_to_reserve(self.item_code, self.warehouse, ignore_sre=self.name),
            )
    
            total_reserved_qty = get_sre_reserved_qty_for_voucher_detail_no(
                self.voucher_type, self.voucher_no, self.voucher_detail_no, ignore_sre=self.name
            )
    
            voucher_delivered_qty = 0
            if self.voucher_type == "Sales Order":
                delivered_qty, conversion_factor = frappe.db.get_value(
                    "Sales Order Item",
                    self.voucher_detail_no,
                    ["delivered_qty", "conversion_factor"],
                )
                voucher_delivered_qty = flt(delivered_qty) * flt(conversion_factor)
    
            over_reservation_allowance = flt(
                frappe.db.get_single_value(
                    "Stock Settings",
                    "over_reservation_allowance"
                ) or 0
            )
    
            max_voucher_qty = self.voucher_qty * (
                1 + over_reservation_allowance / 100
            )
    
            allowed_qty = min(
                self.available_qty,
                (
                    max_voucher_qty
                    - voucher_delivered_qty
                    - total_reserved_qty
                )
            )
            allowed_qty = flt(allowed_qty, self.precision("reserved_qty"))
            qty_to_be_reserved = flt(qty_to_be_reserved, self.precision("reserved_qty"))
    
            if self.get("_action") != "submit" and self.voucher_type == "Sales Order" and allowed_qty <= 0:
                msg = _("Item {0} is already reserved/delivered against Sales Order {1}.").format(
                    frappe.bold(self.item_code), frappe.bold(self.voucher_no)
                )
    
                if self.docstatus == 1:
                    self.cancel()
                    return frappe.msgprint(msg)
                else:
                    frappe.throw(msg)
    
            if qty_to_be_reserved > allowed_qty:
                actual_qty = get_stock_balance(self.item_code, self.warehouse)
                msg = """
                    Cannot reserve more than Allowed Qty {} {} for Item {} against {} {}.<br /><br />
                    The <b>Allowed Qty</b> is calculated as follows:<br />
                    <ul>
                        <li>Actual Qty [Available Qty at Warehouse] = {}</li>
                        <li>Reserved Stock [Ignore current SRE] = {}</li>
                        <li>Available Qty To Reserve [Actual Qty - Reserved Stock] = {}</li>
                        <li>Voucher Qty [Voucher Item Qty] = {}</li>
                        <li>Delivered Qty [Qty delivered against the Voucher Item] = {}</li>
                        <li>Total Reserved Qty [Qty reserved against the Voucher Item] = {}</li>
                        <li>Allowed Qty [Minimum of (Available Qty To Reserve, (Voucher Qty - Delivered Qty - Total Reserved Qty))] = {}</li>
                    </ul>
                """.format(
                    frappe.bold(allowed_qty),
                    self.stock_uom,
                    frappe.bold(self.item_code),
                    self.voucher_type,
                    frappe.bold(self.voucher_no),
                    actual_qty,
                    actual_qty - self.available_qty,
                    self.available_qty,
                    self.voucher_qty,
                    voucher_delivered_qty,
                    total_reserved_qty,
                    allowed_qty,
                )
                frappe.throw(msg)
    
            if qty_to_be_reserved <= self.delivered_qty:
                msg = _("Reserved Qty should be greater than Delivered Qty.")
                frappe.throw(msg)
    