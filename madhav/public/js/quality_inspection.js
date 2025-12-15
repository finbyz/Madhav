frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		// Set inspected_by once when creating a new Quality Inspection
		if(!frm.doc.inspected_by) {
			frm.set_value("inspected_by", frappe.session.user);
		}
	},

	rejected_qty(frm) {
	update_accepted_qty(frm);
	},

	sample_size(frm) {
		update_accepted_qty(frm);
	},
});

const update_accepted_qty = (frm) => {
	console.log("checking for update_accepted_qty");
	const sample_size = parseFloat(frm.doc.sample_size) || 0;
	const rejected_qty = parseFloat(frm.doc.rejected_qty) || 0;

	// accepted_qty = sample_size - rejected_qty (never below zero)
	const accepted_qty = Math.max(sample_size - rejected_qty, 0);
	frm.set_value("accepted_qty", accepted_qty);
};

