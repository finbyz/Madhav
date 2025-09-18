frappe.ui.form.on('Work Order', {
    refresh: function(frm) {
        // Show button only if Work Order is submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button('Create Cutting Plan', function() {
                let source_warehouse = frm.doc.source_warehouse;
                let target_warehouse = frm.doc.fg_warehouse;

                frappe.new_doc("Cutting Plan", {
                    work_order: frm.doc.name,
                    company: frm.doc.company,
                    target_qty: frm.doc.qty,
                    default_source_warehouse: source_warehouse,
                    default_finished_goods_warehouse: target_warehouse,
                    date: frappe.datetime.now_datetime(),
                });

                // Wait for Cutting Plan form to open
                setTimeout(function() {
                    let cutting_plan_form = cur_frm;
                    if (cutting_plan_form && cutting_plan_form.doctype === 'Cutting Plan') {
                        cutting_plan_form.set_value('default_source_warehouse', source_warehouse);

                        let work_order_items = frm.doc.required_items || frm.doc.items || [];

                        work_order_items.forEach(d => {
                            let row = cutting_plan_form.add_child('cut_plan_detail');
                            row.item_code = d.item_code;
                            row.source_warehouse = d.source_warehouse || source_warehouse;
                            row.wo_qty = d.required_qty || d.qty;
                            row.work_order_reference = frm.doc.name;
                        });

                        cutting_plan_form.refresh_field('cut_plan_detail');
                    }
                }, 1000);
            });
        }
    }
});
