frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		// Set inspected_by once when creating a new Quality Inspection
		if(!frm.doc.inspected_by) {
			frm.set_value("inspected_by", frappe.session.user);
		}
	},
});

