frappe.ui.form.on("Purchase Invoice", {
   cost_center: function(frm) {
        update_taxes_fields(frm);
    },
    branch: function(frm) {
        update_taxes_fields(frm);
    },
    validate(frm){
        update_taxes_fields(frm);
    },
     naming_series: function(frm) {
        if (frm.doc.naming_series == "RDP/26-27-.#####.") {
            frm.set_value("branch", "Rolling Division");
        }
        else if (frm.doc.naming_series == "MUP/26-27-.#####.") {
            frm.set_value("branch", "Fabrication/Galvanization");
        }
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