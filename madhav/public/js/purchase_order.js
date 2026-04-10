frappe.ui.form.on("Purchase Order", {
    cost_center: function (frm) {
        update_taxes_fields(frm);
    },
    branch: function (frm) {
        update_taxes_fields(frm);
    },
    validate(frm) {
        update_taxes_fields(frm);
    },
    refresh: function (frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Blanket Order'), function () {
                erpnext.utils.map_current_doc({
                    method: "madhav.doc_events.purchase_order.make_purchase_order_from_blanket",
                    source_doctype: "Blanket Order",
                    target: frm,

                    setters: {
                        supplier: frm.doc.supplier || undefined,
                        company: frm.doc.company
                    },

                    allow_child_item_selection: true,
                    child_fieldname: "items",
                    child_columns: ["item_code", "item_name", "qty", "ordered_qty", "rate"],

                    get_query: function () {
                        
                        return {
                            query: "madhav.doc_events.purchase_order.get_blanket_order_items",
                            filters: {
                                supplier: frm.doc.supplier,
                                company: frm.doc.company
                            }
                        };
                    }
                });
            }, __('Get Items From'));
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
