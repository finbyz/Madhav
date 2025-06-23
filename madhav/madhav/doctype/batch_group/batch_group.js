// Copyright (c) 2025, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Batch Group", {
	refresh(frm) {
        frm.add_custom_button("Batch Wise Stock Balance Report", function () {
            frappe.set_route("query-report", "Batch Wise Stock Balance", {
                batch_group: frm.doc.name
            });
        }, "Reports");
	},
});
