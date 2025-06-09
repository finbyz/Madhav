import frappe
from frappe.utils import cint, flt
from erpnext.stock.get_item_details import get_conversion_factor
from erpnext.controllers.selling_controller import get_serial_and_batch_bundle
from erpnext.controllers.selling_controller import SellingController
from frappe import _

def update_stock_ledger(self, allow_negative_stock=False):
            self.update_reserved_qty()
                    
            sl_entries = []
            # Loop over items and packed items table
            for d in self.get_item_list():
                if frappe.get_cached_value("Item", d.item_code, "is_stock_item") == 1 and flt(d.qty):
                    if flt(d.conversion_factor) == 0.0:
                        d.conversion_factor = (
                            get_conversion_factor(d.item_code, d.uom).get("conversion_factor") or 1.0
                        )
                    
                    # On cancellation or return entry submission, make stock ledger entry for
                    # target warehouse first, to update serial no values properly
                    
                    if d.warehouse and (
                        (not cint(self.is_return) and self.docstatus == 1)
                        or (cint(self.is_return) and self.docstatus == 2)
                    ):
                        sl_entries.append(self.get_sle_for_source_warehouse(d))
                    
                    if d.target_warehouse:
                        sl_entries.append(self.get_sle_for_target_warehouse(d))

                    if d.warehouse and (
                        (not cint(self.is_return) and self.docstatus == 2)
                        or (cint(self.is_return) and self.docstatus == 1)
                    ):
                        sl_entries.append(self.get_sle_for_source_warehouse(d))

            self.make_sl_entries(sl_entries, allow_negative_stock=allow_negative_stock)

def get_sle_for_source_warehouse(self, item_row):
    
    serial_and_batch_bundle = (
        item_row.serial_and_batch_bundle
        if not self.is_internal_transfer() or self.docstatus == 1
        else None
    )

    if self.is_internal_transfer():
        if serial_and_batch_bundle and self.docstatus == 1 and self.is_return:
            serial_and_batch_bundle = self.make_package_for_transfer(
                serial_and_batch_bundle, item_row.warehouse, type_of_transaction="Inward"
            )
        elif not serial_and_batch_bundle:
            serial_and_batch_bundle = frappe.db.get_value(
                "Stock Ledger Entry",
                {"voucher_detail_no": item_row.name, "warehouse": item_row.warehouse},
                "serial_and_batch_bundle",
            )

    sle = self.get_sl_entries(
        item_row,
        {
            "actual_qty": -1 * flt(item_row.qty),
            "incoming_rate": item_row.incoming_rate,
            "recalculate_rate": cint(self.is_return),
            "serial_and_batch_bundle": serial_and_batch_bundle,
            "pieces_qty": -1 * flt(item_row.pieces),  # ← your custom field
        },
    )

    if item_row.target_warehouse and not cint(self.is_return):
        sle.dependant_sle_voucher_detail_no = item_row.name

    return sle

def get_sle_for_target_warehouse(self, item_row):
    sle = self.get_sl_entries(
        item_row,
        {
            "actual_qty": flt(item_row.qty),
            "warehouse": item_row.target_warehouse,
            "pieces_qty": flt(item_row.pieces),  # ← your custom field
        },
    )

    if self.docstatus == 1:
        if not cint(self.is_return):
            sle.update({"incoming_rate": item_row.incoming_rate, "recalculate_rate": 1})
        else:
            sle.update({"outgoing_rate": item_row.incoming_rate})
            if item_row.warehouse:
                sle.dependant_sle_voucher_detail_no = item_row.name

        if item_row.serial_and_batch_bundle and not cint(self.is_return):
            type_of_transaction = "Inward"
            if cint(self.is_return):
                type_of_transaction = "Outward"

            sle["serial_and_batch_bundle"] = self.make_package_for_transfer(
                item_row.serial_and_batch_bundle,
                item_row.target_warehouse,
                type_of_transaction=type_of_transaction,
            )

    return sle

def get_item_list(self):
	il = []
	for d in self.get("items"):
		if d.qty is None:
			frappe.throw(_("Row {0}: Qty is mandatory").format(d.idx))

		if self.has_product_bundle(d.item_code):
			for p in self.get("packed_items"):
				if p.parent_detail_docname == d.name and p.parent_item == d.item_code:
					il.append(
						frappe._dict(
							{
								"warehouse": p.warehouse or d.warehouse,
								"item_code": p.item_code,
								"qty": flt(p.qty),
								"serial_no": p.serial_no if self.docstatus == 2 else None,
								"batch_no": p.batch_no if self.docstatus == 2 else None,
								"uom": p.uom,
								"serial_and_batch_bundle": p.serial_and_batch_bundle
								or get_serial_and_batch_bundle(p, self, d),
								"name": d.name,
								"target_warehouse": p.target_warehouse,
								"company": self.company,
								"voucher_type": self.doctype,
								"allow_zero_valuation": d.allow_zero_valuation_rate,
								"sales_invoice_item": d.get("sales_invoice_item"),
								"dn_detail": d.get("dn_detail"),
								"incoming_rate": p.get("incoming_rate"),
								"item_row": p,
								"pieces": p.get("pieces"),  # ✅ Add this
							}
						)
					)
		else:
			il.append(
				frappe._dict(
					{
						"warehouse": d.warehouse,
						"item_code": d.item_code,
						"qty": d.stock_qty,
						"serial_no": d.serial_no if self.docstatus == 2 else None,
						"batch_no": d.batch_no if self.docstatus == 2 else None,
						"uom": d.uom,
						"stock_uom": d.stock_uom,
						"conversion_factor": d.conversion_factor,
						"serial_and_batch_bundle": d.serial_and_batch_bundle,
						"name": d.name,
						"target_warehouse": d.target_warehouse,
						"company": self.company,
						"voucher_type": self.doctype,
						"allow_zero_valuation": d.allow_zero_valuation_rate,
						"sales_invoice_item": d.get("sales_invoice_item"),
						"dn_detail": d.get("dn_detail"),
						"incoming_rate": d.get("incoming_rate"),
						"item_row": d,
						"pieces": d.get("pieces"),  # ✅ Add this
					}
				)
			)

	return il
