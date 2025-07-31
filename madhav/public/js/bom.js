frappe.ui.form.on('BOM', {
    length: function(frm) {
        calculate_qty(frm);
    },
    pieces: function(frm) {
        calculate_qty(frm);
    }
});

function calculate_qty(frm) {
    if (frm.doc.length && frm.doc.pieces && frm.doc.item) {
        frappe.db.get_value("Item", frm.doc.item, "weight_per_meter")
            .then(r => {
                if (r.message && r.message.weight_per_meter) {
                    let weight_per_meter = r.message.weight_per_meter;
                    let qty = (weight_per_meter * frm.doc.length * frm.doc.pieces) / 1000;
                    frm.set_value("quantity", qty);
                } else {
                    frappe.msgprint("Weight per meter not found in Item master.");
                }
            });
    }
}""