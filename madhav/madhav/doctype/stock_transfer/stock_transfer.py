# Copyright (c) 2026, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from frappe.model.document import Document


class StockTransfer(Document):
    
    def on_cancel(self):
        for row in self.transfer_item:

            sre_name = frappe.db.get_value(
                "Stock Reservation Entry",
                {
                    "from_voucher_type": self.doctype,
                    "from_voucher_no": self.name,
                    "from_voucher_detail_no": row.name,
                    "docstatus": 1
                }
            )

            if sre_name:
                sre = frappe.get_doc("Stock Reservation Entry", sre_name)
                sre.cancel()

        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)

            if se.docstatus == 1:
                se.cancel()

        self.db_set("stock_entry", "")     

    def validate(self):
        self.validate_transfer_item_limits()
        self.add_customer_and_po_no()
        
    def add_customer_and_po_no(self):
        for row in self.transfer_item:
            if row.source_document_type == "Stock Entry":
                work_order = frappe.db.get_value(
                    "Stock Entry",
                    row.source_document_name,
                    "work_order"
                )

                if work_order:
                    wo = frappe.get_doc("Work Order", work_order)
                    row.customer = wo.customer
                    row.customer_name = frappe.db.get_value(
                        "Customer", wo.customer, "customer_name"
                    )
                    row.customer_po_no = wo.po_no

            elif row.source_document_type == "Purchase Receipt":
                # Fetch Sales Order from Purchase Receipt Item
                pr_item = frappe.db.get_value(
                    "Purchase Receipt Item",
                    {
                        "parent": row.source_document_name,
                        "item_code": row.item_code, 
                        "batch_no": row.batch
                    },
                    ["sales_order", "sales_order_item"],
                    as_dict=True,
                )

                if pr_item and pr_item.sales_order:
                    so = frappe.db.get_value(
                        "Sales Order",
                        pr_item.sales_order,
                        ["customer", "po_no"],
                        as_dict=True,
                    )

                    if so:
                        row.customer = so.customer
                        row.customer_name = frappe.db.get_value(
                            "Customer",
                            so.customer,
                            "customer_name",
                        )
                        row.customer_po_no = so.po_no

    def on_submit(self):
        self.create_stock_entry()
        
        for row in self.transfer_item:
            if not row.source_document_type:
                continue
            
            # Get work order name from the source document
            if row.source_document_type == "Stock Entry":
                wo_name = frappe.db.get_value(
                    row.source_document_type,
                    row.source_document_name,
                    "work_order"
                )
                if not wo_name:
                    continue
                
                # Fetch the Work Order doc to get sales_order and sales_order_item
                wor = frappe.get_doc("Work Order", wo_name)
                
                if not wor.sales_order or not wor.sales_order_item:
                    continue
                
                # Get the qty from the specific Sales Order Item linked to this WO
                so_qty = frappe.db.get_value(
                    "Sales Order Item",
                    wor.sales_order_item,   # this is the SO Item row name stored on WO
                    "qty"
                )
                
                if not so_qty:
                    continue
                if wor.fg_warehouse == self.target_warehouse:
                    self.create_fg_stock_reservation(
                        item_code=row.item_code,
                        warehouse=self.target_warehouse,
                        qty=row.qty,
                        so_qty=so_qty,
                        name=self.name,
                        stock_uom=frappe.db.get_value("Item", row.item_code, "stock_uom"),
                        work_order=wo_name,
                        sales_order=wor.sales_order,
                        sales_order_item = wor.sales_order_item,
                        batch_no=row.batch,
                        quality_required=0,
                        from_voucher_type = self.doctype,
                        from_voucher_no = self.name,
                        from_voucher_detail_no = row.name
                    )
            elif row.source_document_type == "Purchase Receipt":
                pr_item = frappe.db.get_value(
                    "Purchase Receipt Item",
                    {
                        "parent": row.source_document_name,
                        "item_code": row.item_code,
                    },
                    ["sales_order", "sales_order_item"],
                    as_dict=True,
                )

                if not pr_item or not pr_item.sales_order or not pr_item.sales_order_item:
                    continue

                so_qty = frappe.db.get_value(
                    "Sales Order Item",
                    pr_item.sales_order_item,
                    "qty"
                )

                if not so_qty:
                    continue

                self.create_fg_stock_reservation(
                    item_code=row.item_code,
                    warehouse=self.target_warehouse,
                    qty=row.qty,
                    so_qty=so_qty,
                    name=self.name,
                    stock_uom=frappe.db.get_value("Item", row.item_code, "stock_uom"),
                    work_order=None,
                    sales_order=pr_item.sales_order,
                    sales_order_item=pr_item.sales_order_item,
                    batch_no=row.batch,
                    quality_required=0,
                    from_voucher_type=self.doctype,
                    from_voucher_no=self.name,
                    from_voucher_detail_no=row.name,
                )

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
        # se.stock_transfer = self.name,
        se.set_posting_time = 1
        se.posting_date = self.posting_date
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
                    "cost_center": self.cost_center,
                    "branch": self.branch,
                },
            )

        se.insert(ignore_permissions=True)
        se.submit()

        frappe.msgprint(
            f"Stock Entry <b><a href='/app/stock-entry/{se.name}'>{se.name}</a></b> created successfully.",
            alert=True,
        )

        frappe.db.set_value("Stock Transfer", self.name, "stock_entry", se.name)
    def create_fg_stock_reservation(
        self,
        item_code,
        warehouse,
        qty,
        so_qty,
        name,
        stock_uom,
        work_order,
        sales_order=None,
        sales_order_item=None,
        batch_no=None,
        quality_required=False,
        from_voucher_type = None,
        from_voucher_no = None,
        from_voucher_detail_no = None
    ):
        # ==============================
        # DEBUG INFORMATION
        # ==============================


        if not sales_order:
            return
        if quality_required:
            frappe.log_error(
                title="Quality Inspection Required - Skipping Stock Reservation",
                message=f"Skipping stock reservation for {item_code} in WO {work_order} linked to SO {sales_order} because quality inspection is required."
            )
            return

        # ==============================
        # GET SO ITEM
        # ==============================
        so_items = frappe.get_all(
            "Sales Order Item",
            filters={
                "parent": sales_order,
                "item_code": item_code,
                "name": sales_order_item,
                "docstatus": 1
            },
            fields=["name", "qty", "stock_reserved_qty"]
        )
        
        if not so_items:
            frappe.throw(f"❌ SO Item not found for {item_code} in {sales_order}")
        
        # Find the SO item with available quantity
        so_detail = None
        available_qty = 0
        
        for item in so_items:
            available = flt(item.qty) - flt(item.stock_reserved_qty or 0)
            if available > 0:
                so_detail = item.name
                available_qty = available
                break

        if not so_detail:
            frappe.throw(f"❌ No available quantity in {sales_order} for {item_code}")

        # ==============================
        # RESERVED QTY CHECK
        # ==============================
        already_reserved_qty = frappe.db.sql("""
            SELECT COALESCE(SUM(reserved_qty), 0)
            FROM `tabStock Reservation Entry`
            WHERE
                voucher_type = 'Sales Order'
                AND voucher_no = %s
                AND voucher_detail_no = %s
                AND docstatus = 1
                AND item_code = %s
        """, (sales_order, so_detail, item_code))[0][0] or 0

        available_qty_to_reserve = flt(so_qty) - flt(already_reserved_qty)
        frappe.log_error(
            title="Stock Reservation Debug",
            message=(f"SO: {sales_order}, Item: {item_code}, SO Qty: {so_qty}, Already Reserved: {already_reserved_qty}, Available to Reserve: {available_qty_to_reserve}") 
        )

        if available_qty_to_reserve <= 0:
            return

        reserve_qty = min(qty, available_qty_to_reserve)

        # ==============================
        # CREATE STOCK RESERVATION ENTRY
        # ==============================
        sre = frappe.new_doc("Stock Reservation Entry")

        sre.item_code = item_code
        sre.warehouse = warehouse
        sre.company = self.company
        sre.stock_uom = stock_uom

        sre.voucher_type = "Sales Order"
        sre.voucher_no = sales_order
        sre.voucher_detail_no = so_detail
        sre.from_voucher_type = from_voucher_type
        sre.from_voucher_no = from_voucher_no
        sre.from_voucher_detail_no = from_voucher_detail_no
        sre.reserved_qty = reserve_qty
        sre.voucher_qty = so_qty
        sre.available_qty = available_qty
        sre.available_qty_to_reserve = reserve_qty
        
        # Check if item actually has batch tracking
        has_batch_no = frappe.get_cached_value("Item", item_code, "has_batch_no")

        # ==============================
        # HANDLE BATCH NO
        # ==============================
        if batch_no and has_batch_no and reserve_qty > 0:
            sre.has_batch_no = 1
            sre.has_serial_no = 0
            sre.reservation_based_on = "Serial and Batch"
            sre.use_serial_batch_fields = 1
            
            so_item_data = frappe.db.get_value(
                "Sales Order Item", 
                so_detail, 
                ["pieces", "length_size"], 
                as_dict=True
            )
            weight_per_meter = frappe.db.get_value("Item", item_code, "weight_per_meter") or 0.0

            sb_entry = sre.append("sb_entries", {
                "batch_no": batch_no,
                "qty": reserve_qty,
                "warehouse": warehouse
            })
            
            if so_item_data:
                # Assuming custom fields peices (typo intended, matching original), length, section_weight
                sb_entry.pieces = flt(so_item_data.get("pieces"))
                sb_entry.length = flt(so_item_data.get("length_size"))
                sb_entry.section_weight = (
                    flt(so_item_data.get("pieces")) 
                    * flt(so_item_data.get("length_size")) 
                    * flt(weight_per_meter)
                ) / 1000.0

            
            # Monkey-patch instance to bypass auto reservation clearing our explicit batch
            sre.auto_reserve_serial_and_batch = lambda *args, **kwargs: None
        else:
            sre.reservation_based_on = "Qty"

        # Save and submit the SRE
        sre.flags.ignore_permissions = True
        sre.insert()
        sre.submit()
        if sre:
            frappe.log_error(
                title="Stock Reserved",
                message=f"Reserved {reserve_qty} of {item_code} in {warehouse} for SO {sales_order} (Batch: {batch_no})"
            )


@frappe.whitelist()
def get_batch_stock(
    source_warehouse=None,
    from_date=None,
    to_date=None,
    item_name=None
):
    conditions = [
    "sabb.warehouse = %(source_warehouse)s",
    "sbe.warehouse = %(source_warehouse)s"
    ]

    if from_date and to_date:
        conditions.append(
            "sabb.posting_date BETWEEN %(from_date)s AND %(to_date)s"
        )

    if item_name:
        conditions.append(
            "i.item_name LIKE %(item_name)s"
        )

    where_clause = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            sbe.batch_no,
            MAX(sabb.item_code) AS item_code,
            MAX(i.item_name) AS item_name,

            SUM(
                sbe.qty - IFNULL(sbe.delivered_qty, 0)
            ) AS qty,

            IFNULL(MAX(p.pieces), 0) AS pieces,

            MAX(b.average_length) AS average_length,
            MAX(b.section_weight) AS section_weight,
            MAX(b.reference_doctype) AS reference_doctype,
            MAX(b.reference_name) AS reference_name

        FROM `tabSerial and Batch Entry` sbe

        INNER JOIN `tabSerial and Batch Bundle` sabb
            ON sabb.name = sbe.parent

        LEFT JOIN `tabBatch` b
            ON b.name = sbe.batch_no

        LEFT JOIN `tabItem` i
            ON i.name = sabb.item_code

        LEFT JOIN (
            SELECT
                sbe2.batch_no,
                psle.warehouse,
                SUM(psle.actual_qty) AS pieces
            FROM `tabPiece Stock Ledger Entry` psle
            INNER JOIN `tabSerial and Batch Entry` sbe2
                ON sbe2.parent = psle.serial_and_batch_bundle
            WHERE IFNULL(psle.is_cancelled, 0) = 0
            GROUP BY
                sbe2.batch_no,
                psle.warehouse
        ) p
            ON p.batch_no = sbe.batch_no
            AND p.warehouse = sbe.warehouse

        WHERE
            {where_clause}
            AND sabb.is_cancelled = 0
            And sabb.docstatus = 1

        GROUP BY
            sbe.batch_no

        HAVING
            SUM(
                sbe.qty - IFNULL(sbe.delivered_qty, 0)
            ) > 0

        ORDER BY
            MAX(sabb.posting_date) ASC
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