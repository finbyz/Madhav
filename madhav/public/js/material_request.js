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
	}
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