// Copyright (c) 2026, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Batch Wise Reservation Tool", {
	fetch_sales_order(frm) {
		if (frm.doc.docstatus == 0) {
			frm.trigger("fetch_sales_order_details");
		}
	},

	fetch_sales_order_details(frm) {
		// Collect filter values from the form
		const filters = {
			customer: frm.doc.customer,
			sales_order: frm.doc.sales_order,
			item_name: frm.doc.item_name,
			customer_po_no: frm.doc.customer_po_no,
			sales_order_date: frm.doc.sales_order_date,
		};

		// Check if at least one filter is provided
		const has_filters = Object.values(filters).some(val => val);
		if (!has_filters) {
			frappe.msgprint(__("Please provide at least one filter to fetch Sales Order items."));
			return;
		}

		frappe.call({
			method: "madhav.madhav.doctype.batch_wise_reservation_tool.batch_wise_reservation_tool.fetch_sales_order_items",
			args: {
				filters: filters
			},
			freeze: true,
			freeze_message: __("Fetching Sales Order items..."),
			callback: function (r) {
				if (r.message) {
					if (r.message.length === 0) {
						frappe.msgprint(__("No pending Sales Order items found matching the filters."));
						return;
					}

					// Clear existing rows
					frm.clear_table("pending_line_items");

					// Add fetched items to the child table
					r.message.forEach(item => {
						let row = frm.add_child("pending_line_items");
						row.sales_order = item.sales_order;
						row.sales_order_item = item.sales_order_item;
						row.item_code = item.item_code;
						row.item_name = item.item_name;
						row.qty = item.qty;
						row.pending_qty = item.pending_qty;
						row.pieces = item.pieces;
						row.length = item.length;
						row.section_weight = item.section_weight;
						row.reserve_qty = item.reserve_qty;
					});

					frm.refresh_field("pending_line_items");
					frappe.show_alert({
						message: __("{0} Sales Order items fetched successfully.", [r.message.length]),
						indicator: "green"
					});
				}
			}
		});
	},
});

frappe.ui.form.on("Sales Order Pending Line Items", {
	fetch_batch(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.item_code) {
			frappe.msgprint(__("Please select an Item Code first."));
			return;
		}

		const parent = frm.doc;
		const warehouse = parent.warehouse;

		if (!warehouse) {
			frappe.msgprint(__("Please select a Warehouse in the main form."));
			return;
		}

		frappe.call({
			method: "madhav.madhav.doctype.batch_wise_reservation_tool.batch_wise_reservation_tool.fetch_available_batches",
			args: {
				item_code: row.item_code,
				warehouse: warehouse,
				pending_qty: row.pending_qty || row.qty,
				reserve_qty: row.reserve_qty || 0
			},
			freeze: true,
			freeze_message: __("Fetching available batches..."),
			callback: function (r) {
				if (!r.message || !r.message.length) {
					frappe.msgprint(
						__("No available batches found for {0} in warehouse {1}.", [row.item_code, warehouse])
					);
					return;
				}

				frm.clear_table("available_batches");

				r.message.forEach(batch => {
					let d = frm.add_child("available_batches");

					d.batch = batch.batch;
					d.item_code = batch.item_code;
					d.pieces = batch.pieces;
					d.length = batch.length;
					d.section_weight = batch.section_weight;
					d.available_qty = batch.available_qty;
					// store the pending row reference for exact matching in Reserve
					d.sales_order_item = row.sales_order_item;
				});

				frm.refresh_field("available_batches");

				frappe.show_alert({
					message: __("{0} available batches fetched successfully.", [r.message.length]),
					indicator: "green"
				});
			}
		});
	}
});

frappe.ui.form.on("Available Stock Batches", {
	reserve(frm, cdt, cdn) {
		let batch = locals[cdt][cdn];

		if (!frm.doc.pending_line_items || !frm.doc.pending_line_items.length) {
			frappe.msgprint(__("No pending line items found. Please fetch Sales Order items first."));
			return;
		}

		// Match pending line by sales_order_item (exact), fallback to item_code
		let pending = frm.doc.pending_line_items.find(r =>
			batch.sales_order_item
				? r.sales_order_item == batch.sales_order_item
				: r.item_code == batch.item_code
		);

		if (!pending) {
			frappe.msgprint(__("No matching pending line found for item {0}.", [batch.item_code]));
			return;
		}

		if (!frm.doc.warehouse) {
			frappe.msgprint(__("Please select a Warehouse in the main form before reserving."));
			return;
		}

		frappe.call({
			method: "madhav.madhav.doctype.batch_wise_reservation_tool.batch_wise_reservation_tool.add_to_reservation_batches",
			args: {
				docname: frm.doc.name,
				// from pending_line_items
				sales_order: pending.sales_order || frm.doc.sales_order || "",
				sales_order_item: pending.sales_order_item,
				sales_order_item_qty: pending.qty,
				item_code: pending.item_code,
				item_name: pending.item_name,
				// from available_batches
				batch_no: batch.batch,
				reserved_qty: batch.available_qty,
				length: batch.length,
				pieces: batch.pieces,
				section_weight: batch.section_weight,
				// from form header
				warehouse: frm.doc.warehouse,
				posting_date: frm.doc.posting_date,
			},
			freeze: true,
			freeze_message: __("Adding batch to reservations..."),
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({
						message: __("Batch {0} added to reservations.", [batch.batch]),
						indicator: "green"
					});
					frm.reload_doc();
				}
			}
		});
	}
});