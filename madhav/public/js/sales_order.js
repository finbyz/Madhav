frappe.ui.form.on('Sales Order Item', {
    length_size: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_length(frm, cdt, cdn);
    },
    pieces: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_length(frm, cdt, cdn);
    },
    items_remove: function (frm, cdt, cdn){
        update_total_length(frm, cdt, cdn);
    }
});

function calculate_qty(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (row.length_size && row.pieces && row.item_code) {
        frappe.db.get_value("Item", row.item_code, "weight_per_meter")
            .then(r => {
                if (r.message && r.message.weight_per_meter) {
                    let weight_per_meter = r.message.weight_per_meter;
                    let qty = (weight_per_meter * row.length_size * row.pieces) / 1000;
                    frappe.model.set_value(cdt, cdn, "qty", qty);
                } else {
                    frappe.msgprint("Weight per meter not found in Item master.");
                }
            });
    }
}

function update_total_length(frm, cdt, cdn) {
    let total_length = 0;

    // Step 1: Calculate total_length_in_meter
    frm.doc.items.forEach(item => {
        let pieces = flt(item.pieces);
        let avg_len = flt(item.length_size);

        if (pieces && avg_len) {
            total_length += pieces * avg_len;
        }
    });

    frm.set_value("total_length_in_meter", total_length.toFixed(2));
}