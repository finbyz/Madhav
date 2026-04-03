frappe.ui.form.on("Journal Entry", {
   cost_center: function(frm) {
        update_account_fields(frm);
    },
    branch: function(frm) {
        update_account_fields(frm);
    },
    validate(frm){
        update_account_fields(frm);
    },
    naming_series: function(frm) {
        if (frm.doc.naming_series == "RDJV/26-27-.#####.") {
            frm.set_value("voucher_type", "Journal Entry"); 
            frm.set_value("branch", "Rolling Division");
        }
        else if (frm.doc.naming_series == "RDCA/26-27-.#####.") {
            frm.set_value("voucher_type", "Cash Entry"); 
            frm.set_value("branch", "Rolling Division");
        }
        else if (frm.doc.naming_series == "MUJV/26-27-.#####.") {
            frm.set_value("voucher_type", "Journal Entry"); 
            frm.set_value("branch", "Fabrication/Galvanization");
        }
        else if (frm.doc.naming_series == "MUCA/26-27-.#####.") {
            frm.set_value("voucher_type", "Cash Entry"); 
            frm.set_value("branch", "Fabrication/Galvanization");
        }
        else if (frm.doc.naming_series == "MUBA/26-27-.#####.") {
            frm.set_value("voucher_type", "Bank Entry"); 
        }
    }
});
function update_account_fields(frm) {
    if (!frm.doc.accounts) return;

    frm.doc.accounts.forEach(row => {
        if (frm.doc.cost_center) {
            row.cost_center = frm.doc.cost_center;
        }

        // If you have branch field in taxes table
        if (frm.doc.branch && row.branch !== undefined) {
            row.branch = frm.doc.branch;
        }
    });

    frm.refresh_field('accounts');
}