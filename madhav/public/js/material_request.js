frappe.ui.form.on('Material Request', {
    validate(frm) {
        if (frm.doc.company === "MADHAV UDYOG PRIVATE LIMITED") {
            frm.set_value("naming_series", "MUMR.YY.-");
        } else if (frm.doc.company === "MADHAV STELCO PRIVATE LIMITED") {
            frm.set_value("naming_series", "MSMR.YY.-");
        } 
	},
	cost_center: function (frm) {
        update_items_fields(frm);
    },
    branch: function (frm) {
        update_items_fields(frm);
    },
	validate: function(frm) {
		update_items_fields(frm);
	},
	refresh: function(frm){
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Sales Order"),
				() => frm.events.get_items_from_sales_order(frm),
				__("Get Items From")
			);
		}
	},
	get_items_from_sales_order: function (frm) {
		erpnext.utils.map_current_doc({
			method: "madhav.doc_events.material_request.make_material_request",
			source_doctype: "Sales Order",
			target: frm,
			allow_child_item_selection: 1,
			child_fieldname: "items",
			child_columns: [ "item_code",
                    "item_name",
                    "qty",
                    "uom",
                    "rate",
                    "length_size",
                    "pieces",
                    "assorted_length",
                    "delivery_date"],  // ← was missing
			setters: {
				customer: frm.doc.customer || undefined,
				delivery_date: undefined,
			},
			get_query_filters: {
				docstatus: 1,
				status: ["not in", ["Closed", "On Hold"]],
				per_delivered: ["<", 99.99],
				company: frm.doc.company,
			},
		});
},
})

function update_items_fields(frm) {
    if (!frm.doc.items) return;

    frm.doc.items.forEach(row => {

        if (frm.doc.cost_center) {
            frappe.model.set_value(row.doctype, row.name, "cost_center", frm.doc.cost_center);
        }

        if (frm.doc.branch) {
            frappe.model.set_value(row.doctype, row.name, "branch", frm.doc.branch);
        }

    });

    frm.refresh_field('items');
}

frappe.ui.form.on('Material Request Item', {
	qty: function (frm,cdt,cdn) {
		console.log("chekcing for MR................")
		let d = locals[cdt][cdn];
		frappe.db.get_value("Stock Settings", 'Stock Settings','calculate_conversion_factor_based_on_stock_quantity_and_quantity', function (r) {
			if (cint(r.calculate_conversion_factor_based_on_stock_quantity_and_quantity) == 1) {
				if(d.qty > 0){
					frappe.model.set_value(cdt, cdn, "conversion_factor", flt(d.stock_qty/d.qty));
				}
			}
		});
	},
	stock_qty: function (frm,cdt,cdn) {
		let d = locals[cdt][cdn];
		frappe.db.get_value("Stock Settings", 'Stock Settings','calculate_conversion_factor_based_on_stock_quantity_and_quantity', function (r) {
			if (cint(r.calculate_conversion_factor_based_on_stock_quantity_and_quantity) == 1) {
				if(d.qty > 0){
					frappe.model.set_value(cdt, cdn, "conversion_factor", flt(d.stock_qty/d.qty));
				}
			}
		});
	},
});