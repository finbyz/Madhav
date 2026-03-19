# Copyright (c) 2026, Finbyz pvt. ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now
from frappe.utils import flt

class FinishWorkOrder(Document):

    def on_update(self):
        self.create_unplanned_work_orders()
        
    def after_insert(self):
        for row in self.pending_work_orders:
            if row.sales_order:
                doc = frappe.get_doc("Sales Order",row.sales_order)
                if doc.quality_required and not row.make_it_unplanned:
                    row.target_warehouse = frappe.db.get_value("Company",self.company,"default_quality_inspection_warehouse")

    def validate(self):
        self.update_totals()

    def update_totals(self):
        total_wo_qty = 0
        total_wo_pieces = 0
        total_rm_qty = 0
        total_rm_pieces = 0
        total_scrap_qty = 0
        
        for row in self.pending_work_orders:
            total_wo_qty += row.qty or 0
            total_wo_pieces += row.pieces or 0
            
        for row in self.raw_materials:
            total_rm_qty += row.qty or 0
            total_rm_pieces += row.pieces or 0
            
        for row in self.scrap_items:
            total_scrap_qty += row.qty or 0
            
        self.total_work_order_qty = total_wo_qty
        self.total_work_order_pieces = total_wo_pieces
        self.total_raw_material_qty = total_rm_qty
        self.total_raw_material_pieces = total_rm_pieces
        self.scrap_qty = total_scrap_qty
        
        # ✅ Prevent division by zero
        if total_wo_qty:
            self.scrap_ratio = total_scrap_qty / total_wo_qty
        else:
            self.scrap_ratio = 0

        if (total_wo_qty + total_scrap_qty):
            self.consumption_ratio = total_rm_qty / (total_wo_qty + total_scrap_qty)
        else:
            self.consumption_ratio = 0

        # ✅ Update child table fields
        for row in self.pending_work_orders:
            ready_qty = row.ready_qty or 0

            row.consumption = ready_qty * self.consumption_ratio
            row.scrap_qty = ready_qty * self.scrap_ratio

    def create_unplanned_work_orders(self):

        for row in self.pending_work_orders:

            if row.make_it_unplanned and not row.work_order:

                new_wo = self.create_new_work_order(row)
                row.work_order = new_wo
            # else:
            #     frappe.db.set_value("Work Order", row.work_order, "finish_work_order", self.name)

    def create_new_work_order(self, row):

        wo = frappe.new_doc("Work Order")

        # ---- Core Fields ----
        wo.production_item = row.item
        wo.qty = row.ready_qty
        wo.stock_uom = row.stock_uom
        wo.company = "MADHAV STELCO PRIVATE LIMITED"
        wo.fg_warehouse = row.target_warehouse
        wo.finish_work_order = row.parent
        bom = frappe.get_value("BOM", {"item": row.item, "is_default": 1}, "name")
        wo.bom_no = bom

        # ---- Custom / Extended Fields ----
        wo.length = row.length_size
        wo.pieces = row.ready_pieces

        # ---- Optional Clean Defaults ----
        wo.skip_transfer = 1

        # ---- Reference Tracking ----
        wo.custom_reference_wo = row.old_work_order
        wo.custom_finish_doc = self.name

        wo.insert(ignore_permissions=True)
        wo.submit()

        frappe.msgprint(f"Created Unplanned Work Order <b>{wo.name}</b>")

        return wo.name

    def create_fg_stock_reservation(self, item_code, warehouse, qty, so_qty, name, stock_uom, work_order, sales_order=None):
        """Create Stock Reservation Entry for Finished Good"""

        if not item_code or not warehouse or not qty:
            return
        
        try:
            sre = frappe.new_doc("Stock Reservation Entry")
            sre.item_code = item_code
            sre.warehouse = warehouse
            sre.reserved_qty = qty
            sre.voucher_qty = so_qty
            available_qty = so_qty - qty
            sre.available_qty = available_qty
            so_detail = frappe.db.get_value(
                "Work Order",
                {"name": work_order},
                "sales_order_item"
            )
            # Optional but recommended links
            if sales_order:
                sre.voucher_type = "Sales Order"
                sre.voucher_no = sales_order
                sre.voucher_detail_no = so_detail
            else:
                return
            
            if not available_qty:
                return

            sre.company = self.company
            sre.stock_uom = stock_uom
            sre.flags.ignore_permissions = True
            sre.insert()
            sre.submit()

        except Exception:
            frappe.log_error(
                title=f"Stock Reservation Failed: {item_code}",
                message=frappe.get_traceback()
            )
            frappe.throw(
                f"Failed to create Stock Reservation Entry for Item <b>{item_code}</b>"
            )
            
    def on_submit(self):

        # ==============================
        # BUILD FIFO RAW MATERIAL POOL
        # ==============================
        rm_pool = []
        for rm in self.raw_materials:
            if rm.qty and rm.qty > 0:
                rm_pool.append({
                    "item_code": rm.item_code,
                    "warehouse": rm.source_warehouse,
                    "remaining_qty": rm.qty,
                    "batch_no": rm.batch_no,
                    "pieces": rm.pieces,
                    "length": rm.length,
                    "section_weight": rm.section_weight
                })

        rm_index = 0

        # ==============================
        # BUILD FIFO SCRAP POOL
        # ==============================
        scrap_pool = []
        for sc in self.scrap_items:
            if sc.qty and sc.qty > 0:
                scrap_pool.append({
                    "item_code": sc.item,
                    "remaining_qty": sc.qty,
                })

        scrap_index = 0

        # ==============================
        # ITERATE PENDING WORK ORDERS
        # ==============================
        for pwo in self.pending_work_orders:

            precision = frappe.get_precision("Stock Entry Detail", "qty")

            fg_qty = flt(pwo.consumption or 0, precision)
            scrap_required = flt(pwo.scrap_qty or 0, precision)

            if fg_qty <= 0:
                continue

            if not pwo.work_order:
                frappe.throw(
                    f"Row {pwo.idx}: Work Order is not set for item <b>{pwo.item}</b>. "
                    f"Please save the document first to generate unplanned work orders."
                )

            # ==============================
            # CREATE STOCK ENTRY
            # ==============================
            try:
                se = frappe.new_doc("Stock Entry")
                se.stock_entry_type = "Manufacture"
                se.company = self.company
                se.to_warehouse = pwo.target_warehouse
                se.work_order = pwo.work_order
                se.from_bom = 1

                se.flags.ignore_permissions = True
                se.flags.ignore_mandatory = True
                se.flags.ignore_bom_validation = True
                se.flags.ignore_work_order_validation = True

                remaining_fg_qty = fg_qty

                # ==============================
                # FIFO RAW MATERIAL CONSUMPTION
                # ==============================
                while remaining_fg_qty > 0.0001 and rm_index < len(rm_pool):
                    rm_row = rm_pool[rm_index]

                    if rm_row["remaining_qty"] <= 0:
                        rm_index += 1
                        continue

                    consume = flt(min(remaining_fg_qty, rm_row["remaining_qty"]), precision)

                    # ✅ Only carry pieces & length when this consume exhausts the batch row
                    is_last_consume = (consume >= rm_row["remaining_qty"] - 0.0001)

                    se.append("items", {
                        "item_code": rm_row["item_code"],
                        "s_warehouse": rm_row["warehouse"],
                        "qty": consume,
                        "pieces": rm_row["pieces"] if is_last_consume else 0,
                        "average_length": rm_row["length"] if is_last_consume else 0,
                        "section_weight": rm_row["section_weight"],
                        "batch_no": rm_row["batch_no"],
                        "required_stock_in_pieces": 1,
                        "use_serial_batch_fields": 1
                    })

                    rm_row["remaining_qty"] = flt(rm_row["remaining_qty"] - consume, precision)
                    remaining_fg_qty = flt(remaining_fg_qty - consume, precision)

                    if rm_row["remaining_qty"] <= 0.0001:
                        rm_row["remaining_qty"] = 0
                        rm_index += 1

                # Guard: warn if RM pool ran out before filling this work order
                if remaining_fg_qty > 0.0001:
                    frappe.throw(
                        f"Row {pwo.idx}: Raw material pool exhausted. "
                        f"Still need <b>{remaining_fg_qty}</b> tonnes for Work Order "
                        f"<b>{pwo.work_order}</b> (Item: {pwo.item}). "
                        f"Please add more raw materials."
                    )

                # ==============================
                # FIFO SCRAP CONSUMPTION
                # ==============================
                remaining_scrap = scrap_required

                while remaining_scrap > 0.0001 and scrap_index < len(scrap_pool):
                    sc_row = scrap_pool[scrap_index]

                    if sc_row["remaining_qty"] <= 0:
                        scrap_index += 1
                        continue

                    consume_scrap = flt(min(remaining_scrap, sc_row["remaining_qty"]), precision)

                    se.append("items", {
                        "item_code": sc_row["item_code"],
                        "t_warehouse": "Cutting Scrap - MS",
                        "qty": consume_scrap,
                        "is_scrap_item": 1,
                        "required_stock_in_pieces": 1
                    })

                    sc_row["remaining_qty"] = flt(sc_row["remaining_qty"] - consume_scrap, precision)
                    remaining_scrap = flt(remaining_scrap - consume_scrap, precision)

                    if sc_row["remaining_qty"] <= 0.0001:
                        sc_row["remaining_qty"] = 0
                        scrap_index += 1

                # ==============================
                # FINISHED GOOD ENTRY
                # ==============================
                se.append("items", {
                    "item_code": pwo.item,
                    "t_warehouse": pwo.target_warehouse,
                    "qty": pwo.ready_qty,
                    "pieces": pwo.ready_pieces,
                    "average_length": pwo.length_size,
                    "section_weight": pwo.standard_weight,
                    "is_finished_item": 1,
                    "required_stock_in_pieces": 1
                })

                se.fg_completed_qty = pwo.ready_qty

                se.insert()
                se.submit()
                self.create_fg_stock_reservation(
                    item_code=pwo.item,
                    warehouse=pwo.target_warehouse,
                    qty=pwo.ready_qty,
                    so_qty=pwo.qty,
                    name=pwo.name,
                    stock_uom=pwo.stock_uom,
                    work_order=pwo.work_order,
                    sales_order=pwo.sales_order,
                )

            except Exception as e:
                frappe.log_error(
                    title=f"Stock Entry Failed for WO {pwo.work_order}",
                    message=frappe.get_traceback()
                )
                frappe.throw(
                    f"Failed to create Stock Entry for Work Order <b>{pwo.work_order}</b> "
                    f"(Row {pwo.idx}, Item: {pwo.item}).<br><br>"
                    f"Error: {str(e)}<br><br>"
                    f"Check <b>Error Log</b> for full traceback."
                )

            # ==============================
            # UPDATE WORK ORDER PIECES
            # ==============================
            try:
                doc = frappe.get_doc("Work Order", pwo.work_order)
                completed_pcs = flt(doc.completed_pcs or 0)
                total_pcs = flt(doc.pieces or 0)
                pwo_pcs = flt(pwo.pieces or 0)

                doc.db_set("completed_pcs", completed_pcs + pwo_pcs)
                doc.db_set("pending_pcs", total_pcs - (completed_pcs + pwo_pcs))

            except Exception as e:
                frappe.log_error(
                    title=f"Work Order Update Failed for {pwo.work_order}",
                    message=frappe.get_traceback()
                )
                frappe.throw(
                    f"Stock Entry was created but failed to update Work Order <b>{pwo.work_order}</b>.<br><br>"
                    f"Error: {str(e)}"
                )

        # ==============================
        # REMAINING RM → EXCESS FIELD
        # ==============================
        excess = 0
        for rm in rm_pool:
            if rm["remaining_qty"] > 0:
                excess += rm["remaining_qty"]

        self.db_set("excess_rm_qty", flt(excess, precision))
        
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_available_batches(doctype, txt, searchfield, start, page_len, filters):

    item_code = filters.get("item_code")
    warehouse = filters.get("warehouse")

    if not item_code or not warehouse:
        return []

    return frappe.db.sql("""
    SELECT
        sbe.batch_no,
        CONCAT(
            ROUND(SUM(sbe.qty - IFNULL(sbe.delivered_qty, 0)), 3),
            ', ',
            sabb.posting_date,
            ', ',
            sabb.voucher_no
        ) as description
    FROM
        `tabSerial and Batch Entry` sbe
    INNER JOIN
        `tabSerial and Batch Bundle` sabb
            ON sabb.name = sbe.parent
    WHERE
        sabb.item_code = %(item_code)s
        AND sbe.warehouse = %(warehouse)s
        AND sabb.is_cancelled = 0
        AND sbe.batch_no LIKE %(txt)s
    GROUP BY
        sbe.batch_no
    HAVING
        SUM(sbe.qty - IFNULL(sbe.delivered_qty, 0)) > 0
    ORDER BY
        sabb.posting_date ASC
    LIMIT %(start)s, %(page_len)s
""", {
    "item_code": item_code,
    "warehouse": warehouse,
    "txt": f"%{txt}%",
    "start": start,
    "page_len": page_len
})
