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
});
