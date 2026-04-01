frappe.ui.form.on("Purchase Invoice", {
   cost_center: function(frm) {
        update_taxes_fields(frm);
    },
    branch: function(frm) {
        update_taxes_fields(frm);
    }
});
function update_taxes_fields(frm) {
    if (!frm.doc.taxes) return;

    frm.doc.taxes.forEach(row => {
        if (frm.doc.cost_center) {
            row.cost_center = frm.doc.cost_center;
        }

        // If you have branch field in taxes table
        if (frm.doc.branch && row.branch !== undefined) {
            row.branch = frm.doc.branch;
        }
    });

    frm.refresh_field('taxes');
}