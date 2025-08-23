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

            // Wait for Cutting Plan form to open
            setTimeout(function() {
                let cutting_plan_form = cur_frm;
                if (cutting_plan_form && cutting_plan_form.doctype === 'Cutting Plan') {
                    
                    // Pick whichever child table exists (items OR required_items)
                    let work_order_items = frm.doc.required_items || frm.doc.items || [];

                    work_order_items.forEach(d => {
                        let row = cutting_plan_form.add_child('cut_plan_detail');
                        row.item_code = d.item_code;
                        row.source_warehouse = d.source_warehouse || source_warehouse;
                        row.qty = d.required_qty || d.qty;  // some versions use required_qty
                        row.uom = d.uom;  // optional, if Cutting Plan has uom field
                    });

                    cutting_plan_form.refresh_field('cut_plan_detail');
                }
            }, 1000);
        });
    }
});
