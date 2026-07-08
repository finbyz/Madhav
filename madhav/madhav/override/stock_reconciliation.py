from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation as _StockReconciliation
from frappe import bold,_
import frappe
class StockReconciliation(_StockReconciliation):
    def validate_reserved_stock(self) -> None:
            from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
                get_sre_reserved_qty_for_items_and_warehouses as get_sre_reserved_qty_details,
            )

            item_code_list, warehouse_list, batch_list = [], [], []

            for item in self.items:
                item_code_list.append(item.item_code)
                warehouse_list.append(item.warehouse)
                batch_list.append(item.batch_no)

            sre_reserved_qty_details = get_sre_reserved_qty_details(
                item_code_list, warehouse_list, batch_list
            )

            if not sre_reserved_qty_details:
                return

            # ✅ Only consider exact batch matches
            reco_keys = {
                (item.item_code, item.warehouse, item.batch_no)
                for item in self.items if item.batch_no
            }

            data = []

            for (item_code, warehouse, batch_no), reserved_qty in sre_reserved_qty_details.items():
                if (item_code, warehouse, batch_no) in reco_keys and reserved_qty > 0:
                    data.append([item_code, warehouse, batch_no, reserved_qty])

            if not data:
                return  # ✅ allow submission

            # ❌ Block only for exact batch match
            if len(data) == 1:
                d = data[0]
                msg = _(
                    "{0} units are reserved for Item {1}, Batch {2} in Warehouse {3}, please un-reserve to {4}."
                ).format(bold(d[3]), bold(d[0]), bold(d[2]), bold(d[1]), self._action)
            else:
                items_html = ""
                for d in data:
                    items_html += "<li>{} units of Item {} Batch {} in Warehouse {}</li>".format(
                        bold(d[3]), bold(d[0]), bold(d[2]), bold(d[1])
                    )

                msg = _(
                    "Reserved stock found for following Item-Batch combinations. Un-reserve to {0}:<br><br>{1}"
                ).format(self._action, items_html)

            frappe.throw(msg, title=_("Stock Reservation"))