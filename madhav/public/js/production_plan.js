frappe.ui.form.on('Production Plan', {
    refresh: function(frm) {
        // Show button only if Production Plan is submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button('Create Cutting Plan', function() {
                let source_warehouse = frm.doc.source_warehouse;
                let target_warehouse = frm.doc.fg_warehouse;

                frappe.new_doc("Cutting Plan", {
                    production_plan: frm.doc.name,  // link back to Production Plan
                    company: frm.doc.company,
                    target_qty: frm.doc.total_planned_qty,  // use Production Plan qty field
                    default_source_warehouse: source_warehouse,
                    default_finished_goods_warehouse: target_warehouse,
                    date: frappe.datetime.now_datetime(),
                });

                // Wait for Cutting Plan form to open
                setTimeout(function() {
                    let cutting_plan_form = cur_frm;
                    if (cutting_plan_form && cutting_plan_form.doctype === 'Cutting Plan') {
                        cutting_plan_form.set_value('default_source_warehouse', source_warehouse);

                        // Map items from Production Plan child table
                        let production_plan_items = frm.doc.po_items || [];

                        production_plan_items.forEach(d => {
                            let row = cutting_plan_form.add_child('cut_plan_detail');
                            row.item_code = d.item_code;
                            row.source_warehouse = d.warehouse || source_warehouse;
                            row.qty = d.planned_qty || d.qty;
                        });

                        cutting_plan_form.refresh_field('cut_plan_detail');
                    }
                }, 1000);
            });
        }
    },
    get_sales_orders(frm) {
        // Delay required because rows are added asynchronously
        setTimeout(() => {
            populate_customer_names(frm);
        }, 500);
    },
});

function populate_customer_names(frm) {
    (frm.doc.sales_orders || []).forEach(row => {
        if (row.sales_order && !row.customer_name) {
            frappe.db.get_value(
                "Sales Order",
                row.sales_order,
                ["customer", "customer_name"],
                (r) => {
                    if (r) {
                        row.customer = r.customer;
                        row.customer_name = r.customer_name;
                        frm.refresh_field("sales_orders");
                    }
                }
            );
        }
    });
}

frappe.ui.form.on("Production Plan Sales Order", {
    sales_order(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.sales_order) {
            row.customer_name = "";
            frm.refresh_field("sales_orders");
            return;
        }

        frappe.db.get_value(
            "Sales Order",
            row.sales_order,
            ["customer", "customer_name"],
            (r) => {
                if (r) {
                    row.customer = r.customer;
                    row.customer_name = r.customer_name;
                    frm.refresh_field("sales_orders");
                }
            }
        );
    }
});
