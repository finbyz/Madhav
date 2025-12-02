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