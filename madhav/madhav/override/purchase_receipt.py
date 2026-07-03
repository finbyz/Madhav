from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt as _PurchaseReceipt
import frappe
from frappe.utils import cint, flt,get_datetime
from erpnext.stock.get_item_details import get_conversion_factor


class PurchaseReceipt(_PurchaseReceipt):

    def validate(self):
        """Allow UOM different from Purchase Order by auto-setting conversion_factor/stock_qty."""
        super().validate()
        # Allow using the same supplier_delivery_note if any previous PRs with that note are cancelled
        if getattr(self, "supplier_delivery_note", None):
            
            existing = frappe.get_all(
                "Purchase Receipt",
                filters={
                    "supplier_delivery_note": self.supplier_delivery_note,
                    "supplier": self.supplier,
                    "docstatus": ["in", [0, 1]],  # Draft or Submitted block reuse
                    "name": ["!=", self.name],
                },
                limit=1,
            )
            if existing:
                frappe.throw(
                    frappe._("Supplier Delivery Note {0} is already used in PR: {1} and cannot be reused.").format(
                        self.supplier_delivery_note, existing[0].name
                    )
                )


    def validate_with_previous_doc(self):
        """Run core previous doc validation but neutralize UOM equality by temporarily aligning UOMs."""
        # Save original UOMs and replace with PO Item UOMs (if any) to bypass strict UOM compare
        original_uoms = {}
        try:
            for row in self.items or []:
                original_uoms[row.name] = row.uom
                if getattr(row, "purchase_order_item", None):
                    po_uom = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "uom")
                    if po_uom:
                        row.uom = po_uom
            # Call core validation which will now pass UOM equality
            super().validate_with_previous_doc()
        finally:
            # Restore original UOMs
            for row in self.items or []:
                if row.name in original_uoms:
                    row.uom = original_uoms[row.name]

    def validate_rate_with_reference_doc(self, args=None):
        """Override to skip strict rate equality with reference documents.

        This avoids errors like 'Rate must be same as Purchase Order' when UOM differs
        or negotiated rates change. All other validations remain intact.
        """
        return

        if (
            cint(frappe.db.get_single_value("Buying Settings", "maintain_same_rate"))
            and not self.is_return
            and not self.is_internal_supplier
        ):
            self.validate_rate_with_reference_doc(
                [["Purchase Order", "purchase_order", "purchase_order_item"]]
            )
    def reserve_stock_for_sales_order(self):
        if (
            self.is_return
            or not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation")
            or not frappe.db.get_single_value(
                "Stock Settings", "auto_reserve_stock_for_sales_order_on_purchase"
            )
        ):
            return

        self.reload()  # reload to get the Serial and Batch Bundle Details

        so_items_details_map = {}
        for item in self.items:
            if item.sales_order and item.sales_order_item:
                soi = frappe.db.get_value(
                    "Sales Order Item",
                    item.sales_order_item,
                    ["warehouse", "item_code"],
                    as_dict=True,
                )

                if not soi:
                    continue

                if soi.item_code != item.item_code:
                    continue

                if soi.warehouse != item.warehouse:
                    continue

                item_details = {
                    "sales_order_item": item.sales_order_item,
                    "item_code": item.item_code,
                    "warehouse": item.warehouse,
                    "qty_to_reserve": item.stock_qty,
                    "from_voucher_no": item.parent,
                    "from_voucher_detail_no": item.name,
                    "serial_and_batch_bundle": item.serial_and_batch_bundle,
                }
                so_items_details_map.setdefault(item.sales_order, []).append(item_details)

        if so_items_details_map:
            if get_datetime(f"{self.posting_date} {self.posting_time}") > get_datetime():
                return frappe.msgprint(
                    _("Cannot create Stock Reservation Entries for future dated Purchase Receipts.")
                )

            for so, items_details in so_items_details_map.items():
                so_doc = frappe.get_doc("Sales Order", so)
                so_doc.create_stock_reservation_entries(
                    items_details=items_details,
                    from_voucher_type="Purchase Receipt",
                    notify=True,
                )

