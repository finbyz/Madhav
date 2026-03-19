# Copyright (c) 2026, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from frappe.model.document import Document


class StockTransfer(Document):

    def validate(self):
        self.validate_transfer_item_limits()

    def on_submit(self):
        self.create_stock_entry()

    def validate_transfer_item_limits(self):
        for item in self.transfer_item:
            if not item.batch:
                continue

            batch_values = frappe.db.get_value(
                "Batch", item.batch, ["pieces", "batch_qty"], as_dict=True
            )

            if not batch_values:
                continue

            batch_pieces = flt(batch_values.pieces)
            batch_qty = flt(batch_values.batch_qty)
            item_pieces = flt(item.pieces)
            item_qty = flt(item.qty)

            if item_pieces > batch_pieces:
                frappe.throw(
                    f"Row #{item.idx}: Pieces {item_pieces} cannot exceed Batch Pieces {batch_pieces} for Batch {item.batch}."
                )

            if item_qty > batch_qty:
                frappe.throw(
                    f"Row #{item.idx}: Qty {item_qty} cannot exceed Batch Qty {batch_qty} for Batch {item.batch}."
                )

    def create_stock_entry(self):
        if not self.transfer_item:
            frappe.throw(
                "No items in the Transfer Item table. Please fetch details before submitting."
            )

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.stock_transfer = self.name,
        se.company = self.company
        se.from_warehouse = self.source_warehouse
        se.to_warehouse = self.target_warehouse

        if self.sales_order:
            se.sales_order_no = self.sales_order

        for item in self.transfer_item:
            se.append(
                "items",
                {
                    "item_code": item.item_code,
                    "qty": item.qty,
                    "s_warehouse": item.source_warehouse or self.source_warehouse,
                    "t_warehouse": item.target_warehouse or self.target_warehouse,
                    "batch_no": item.batch,
                    "use_serial_batch_fields": 1,
                    "pieces": item.pieces,
                    "average_length": item.length,
                    "section_weight": item.section_weight,
                },
            )

        se.insert(ignore_permissions=True)
        se.submit()

        frappe.msgprint(
            f"Stock Entry <b><a href='/app/stock-entry/{se.name}'>{se.name}</a></b> created successfully.",
            alert=True,
        )

        frappe.db.set_value("Stock Transfer", self.name, "stock_entry", se.name)


@frappe.whitelist()
def get_batch_stock(
    source_warehouse=None, from_date=None, to_date=None, item_name=None
):

    conditions = ["sbe.warehouse = %(source_warehouse)s"]

    if from_date and to_date:
        conditions.append("sabb.posting_date between %(from_date)s and %(to_date)s")

    if item_name:
        conditions.append("i.item_name LIKE %(item_name)s")

    where_clause = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
		SELECT
			sbe.batch_no,
			sabb.item_code,
			i.item_name,
			b.pieces,
			b.average_length,
			b.section_weight,
            b.batch_qty
		FROM `tabSerial and Batch Entry` sbe

		INNER JOIN `tabSerial and Batch Bundle` sabb
			ON sabb.name = sbe.parent

		LEFT JOIN `tabBatch` b
			ON b.name = sbe.batch_no

		LEFT JOIN `tabItem` i
			ON i.name = sabb.item_code

		WHERE
			{where_clause}
			AND sabb.is_cancelled = 0

		GROUP BY
			sbe.batch_no

		HAVING
			SUM(sbe.qty - IFNULL(sbe.delivered_qty, 0)) > 0

		ORDER BY
			sabb.posting_date ASC

	""",
        {
            "source_warehouse": source_warehouse,
            "from_date": from_date,
            "to_date": to_date,
            "item_name": f"%{item_name}%" if item_name else None,
        },
        as_dict=1,
    )

    return data
