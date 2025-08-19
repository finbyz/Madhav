frappe.ui.form.on('Work Order', {
    refresh: function(frm) {
        frm.add_custom_button('Create Cutting Plan', function() {
            let source_warehouse = frm.doc.source_warehouse;
            
            frappe.new_doc("Cutting Plan", {
                work_order: frm.doc.name,
                company: frm.doc.company,
                target_qty: frm.doc.qty,
                default_source_warehouse: source_warehouse,
                date: frappe.datetime.now_datetime(),
            });
            
            // Wait for form to load, then add child row
            setTimeout(function() {
                let cutting_plan_form = cur_frm;
                if (cutting_plan_form && cutting_plan_form.doctype === 'Cutting Plan') {
                    if (!cutting_plan_form.doc.cut_plan_detail || cutting_plan_form.doc.cut_plan_detail.length === 0) {
                        let row = cutting_plan_form.add_child('cut_plan_detail');
                        row.source_warehouse = source_warehouse;
                        cutting_plan_form.refresh_field('cut_plan_detail');
                    }
                }
            }, 1000);
        });
    }
});