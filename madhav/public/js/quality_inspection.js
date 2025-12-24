frappe.ui.form.on("Quality Inspection", {
	validate: function(frm) {
		// Ensure accepted_qty is correctly calculated before saving
		update_accepted_qty(frm);
	},
	refresh(frm) {
		// Set inspected_by once when creating a new Quality Inspection
		if(!frm.doc.inspected_by) {
			frm.set_value("inspected_by", frappe.session.user);
		}

		// Store original sample size from PR to enforce max limit
		if (frm.is_new() && frm.doc.sample_size) {
			frm._max_sample_size_from_pr = frm.doc.sample_size;
		} else if (!frm._max_sample_size_from_pr && frm.doc.sample_size) {
			// Fallback: first time we see a value on existing doc
			frm._max_sample_size_from_pr = frm.doc.sample_size;
		}
	},

	rejected_qty(frm) {
	update_accepted_qty(frm);
	},

	sample_size(frm) {
		const entered = parseFloat(frm.doc.sample_size) || 0;
		const max_allowed = parseFloat(frm._max_sample_size_from_pr) || 0;

		if (max_allowed && entered > max_allowed) {
			frappe.msgprint({
				message: __("You are not allowed to set Sample Size more than {0}.", [max_allowed]),
				indicator: "red",
			});
			frm.set_value("sample_size", max_allowed);
		}

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

