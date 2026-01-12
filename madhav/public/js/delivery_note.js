frappe.ui.form.on("Delivery Note", {
	onload(frm) {
		// When Delivery Note is created from a Sales Order, copy
		// `pieces`, `length_size` and `qty` from Sales Order Item into
		// `lengthpieces_so`, `length_sizeso` and `quantityso` of Delivery Note Item
		// via a server-side method (no direct get_value from JS).
		if (frm.doc.__islocal && Array.isArray(frm.doc.items)) {
			(frm.doc.items || []).forEach((row) => {
				// `so_detail` is the link to the Sales Order Item row
				if (row.so_detail && (!row.lengthpieces_so || !row.length_sizeso)) {
					frappe.call({
						method: "madhav.api.get_so_item_pieces_and_length",
						args: {
							so_detail: row.so_detail,
						},
						callback: (r) => {
							if (!r.message) return;

							frappe.model.set_value(
								row.doctype,
								row.name,
								"lengthpieces_so",
								r.message.pieces
							);
							frappe.model.set_value(
								row.doctype,
								row.name,
								"length_sizeso",
								r.message.length_size
							);
							frappe.model.set_value(
								row.doctype,
								row.name,
								"quantityso",
								r.message.qty
							);
						},
					});
				}
			});
		}
	},
	onload_post_render: function(frm) {
        set_lengthpieces(frm);
    },

    refresh: function(frm) {
        set_lengthpieces(frm);
    }
});
frappe.ui.form.on('Delivery Note Item', {
	batch_no(frm, cdt, cdn) {
		let d = locals[cdt][cdn];

		if (!d.batch_no) return;

		// fetch pieces from Batch only once
		frappe.db.get_value(
			"Batch",
			d.batch_no,
			"pieces",
			function (r) {
				if (r && r.pieces != null) {
					frappe.model.set_value(
						cdt,
						cdn,
						"pieces",
						r.pieces
					);
				}
			}
		);
	},
});
function set_lengthpieces(frm) {
    (frm.doc.items || []).forEach(row => {
        if (row.pieces && !row.lengthpieces_so) {
            row.lengthpieces_so = row.pieces;
			row.average_length = row.length_size
			row.length_sizeso = row.length_size
        }
    });
    frm.refresh_field("items");
}