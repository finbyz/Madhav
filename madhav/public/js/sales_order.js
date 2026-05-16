frappe.ui.form.on('Sales Order', {
    cost_center: function(frm) {
        update_taxes_fields(frm);
    },
    branch: function(frm) {
        update_taxes_fields(frm);
    },

    refresh(frm) {

        frm.remove_custom_button(__('Material Request'), __('Create'));

        frm.add_custom_button(
            __('Material Request'),
            () => frm.events.make_material_request(frm),
            __('Create')
        );

        frm.remove_custom_button(__('Purchase Order'), __('Create'));
        frm.add_custom_button(
            __("Purchase Order"),
            () => frm.events.make_purchase_order(frm),
            __("Create")
        );

        // Stock Reservation > Reserve button should only be visible if the SO has unreserved stock and no Pick List is created against the SO.
        if (
            frm.doc.docstatus === 1 &&
            frm.doc.__onload &&
            frm.doc.__onload.has_unreserved_stock &&
            flt(frm.doc.per_picked) === 0
        ) {
            frm.remove_custom_button(__("Reserve"), __("Stock Reservation"));
            frm.add_custom_button(
                __("Reserve"),
                () => frm.events.create_stock_reservation_entries(frm),
                __("Stock Reservation")
            );
        }
    },
    make_purchase_order(frm) {

        // ✅ FIX: this.frm → frm
        let pending_items = frm.doc.items.some((item) => {
            const effective_stock_qty =
                flt(item.stock_qty) - flt(item.stock_reserved_qty || 0);

            const pending_qty =
                effective_stock_qty -
                frm.cscript.get_ordered_qty(item, frm.doc);
            return pending_qty > 0;
        });

        if (!pending_items) {
            frappe.throw({
                message: __("Purchase Order already created for all Sales Order items"),
                title: __("Note"),
            });
        }

        var dialog = new frappe.ui.Dialog({
            title: __("Select Items"),
            size: "large",
            fields: [
                {
                    fieldtype: "Check",
                    label: __("Against Default Supplier"),
                    fieldname: "against_default_supplier",
                    default: 0,
                },
                {
                    fieldname: "items_for_po",
                    fieldtype: "Table",
                    label: __("Select Items"),
                    fields: [
                        { fieldtype: "Data", fieldname: "item_code", label: __("Item"), read_only: 1, in_list_view: 1 },
                        { fieldtype: "Data", fieldname: "item_name", label: __("Item name"), read_only: 1, in_list_view: 1 },
                        { fieldtype: "Float", fieldname: "pending_qty", label: __("Pending Qty"), read_only: 1, in_list_view: 1 },
                        { fieldtype: "Link", fieldname: "uom", label: __("UOM"), options: "UOM", read_only: 1, in_list_view: 1 },
                        { fieldtype: "Data", fieldname: "supplier", label: __("Supplier"), read_only: 1, in_list_view: 1 },
                    ],
                },
            ],

            primary_action_label: __("Create Purchase Order"),
            primary_action: (args) => {

                let selected_items = dialog.fields_dict.items_for_po.grid
                    .get_selected_children()
                    .filter(row => {
                        let so_item = frm.doc.items.find(d => d.name === row.name);
                        return so_item && !so_item.is_manufacture;
                    });
                if (!selected_items.length) {
                    frappe.throw({
                        message: "Please select Items from the Table",
                        title: __("Items Required"),
                        indicator: "blue",
                    });
                }

                dialog.hide();

                var method = args.against_default_supplier
                    ? "make_purchase_order_for_default_supplier"
                    : "make_purchase_order";

                return frappe.call({
                    method: "madhav.api." + method,
                    freeze_message: __("Creating Purchase Order ..."),
                    args: {
                        source_name: frm.doc.name,
                        selected_items: selected_items,
                    },
                    freeze: true,
                    callback: function (r) {
                        if (!r.exc) {
                            if (!args.against_default_supplier) {
                                frappe.model.sync(r.message);
                                frappe.set_route("Form", r.message.doctype, r.message.name);
                            } else {
                                frappe.route_options = {
                                    sales_order: frm.doc.name,
                                };
                                frappe.set_route("List", "Purchase Order");
                            }
                        }
                    },
                });
            },
        });

        dialog.fields_dict["against_default_supplier"].df.onchange = () => set_po_items_data();

        const set_po_items_data = () => {

            let against_default_supplier = dialog.get_value("against_default_supplier");

            let po_items = [];

            frm.doc.items.forEach((d) => {

                if (d.is_manufacture) return;

                let ordered_qty =
                    frm.cscript.get_ordered_qty(d, frm.doc);

                let effective_stock_qty =
                    flt(d.stock_qty) - flt(d.stock_reserved_qty || 0);

                let pending_qty =
                    (effective_stock_qty - ordered_qty) /
                    flt(d.conversion_factor);

                if (pending_qty > 0) {
                    po_items.push({
                        name: d.name,
                        item_name: d.item_name,
                        item_code: d.item_code,
                        pending_qty: pending_qty,
                        uom: d.uom,
                        supplier: d.supplier,
                    });
                }
            });

            if (against_default_supplier) {
                po_items = po_items.filter(d => d.supplier);
            }

            // ✅ overwrite grid data completely
            dialog.fields_dict.items_for_po.df.data = po_items;
            dialog.get_field("items_for_po").refresh();

            // ✅ select ONLY visible rows
            dialog.wrapper
                .find(".grid-heading-row .grid-row-check")
                .prop("checked", true)
                .trigger("click");
        };

        set_po_items_data();
        dialog.get_field("items_for_po").grid.only_sortable();
        dialog.get_field("items_for_po").refresh();
        dialog.show();
    },
    
    create_stock_reservation_entries(frm) {
        const dialog = new frappe.ui.Dialog({
            title: __("Stock Reservation"),
            size: "extra-large",
            fields: [
                {
                    fieldname: "set_warehouse",
                    fieldtype: "Link",
                    label: __("Set Warehouse"),
                    options: "Warehouse",
                    default: frm.doc.set_warehouse,
                    get_query: () => {
                        return {
                            filters: [["Warehouse", "is_group", "!=", 1]],
                        };
                    },
                    onchange: () => {
                        if (dialog.get_value("set_warehouse")) {
                            dialog.fields_dict.items.df.data.forEach((row) => {
                                row.warehouse = dialog.get_value("set_warehouse");
                            });
                            dialog.fields_dict.items.grid.refresh();

                        }
                    },
                },
                { fieldtype: "Column Break" },
                {
                    fieldname: "add_item",
                    fieldtype: "Link",
                    label: __("Add Item"),
                    options: "Sales Order Item",
                    get_query: () => {
                        return {
                            query: "erpnext.controllers.queries.get_filtered_child_rows",
                            filters: {
                                parenttype: frm.doc.doctype,
                                parent: frm.doc.name,
                                reserve_stock: 1,
                            },
                        };
                    },
                    onchange: () => {
                        let sales_order_item = dialog.get_value("add_item");

                        if (sales_order_item) {
                            frm.doc.items.forEach((item) => {
                                if (item.name === sales_order_item) {
                                    let unreserved_qty =
                                        (flt(item.stock_qty) -
                                            (item.stock_reserved_qty
                                                ? flt(item.stock_reserved_qty)
                                                : flt(item.delivered_qty) * flt(item.conversion_factor))) /
                                        flt(item.conversion_factor);

                                    if (unreserved_qty > 0) {
                                        dialog.fields_dict.items.df.data.forEach((row) => {
                                            if (row.sales_order_item === sales_order_item) {
                                                unreserved_qty -= row.qty_to_reserve;
                                            }
                                        });
                                    }

                                    frappe.db.get_value("Item", item.item_code, "weight_per_meter").then((r) => {
                                        dialog.fields_dict.items.df.data.push({
                                            __checked: 1,
                                            sales_order_item: item.name,
                                            item_code: item.item_code,
                                            item_name: item.item_name,
                                            warehouse: dialog.get_value("set_warehouse") || item.warehouse,
                                            length_size: item.length_size,
                                            max_length: flt(item.length_size) + 1.5,
                                            pieces: item.pieces,
                                            total_length: flt(item.pieces) * flt(item.length_size),
                                            section_weight: flt(r.message.weight_per_meter),
                                            max_section_weight: null,
                                            qty_to_reserve: Math.max(unreserved_qty, 0),
                                        });
                                        dialog.fields_dict.items.grid.refresh();
                                        dialog.set_value("add_item", undefined);
                                    });
                                }
                            });
                        }
                    },
                },
                {
                    fieldtype: "Section Break",
                    label: __("Selection Details"),
                },

                {
                    fieldtype: "Section Break",
                    label: __("Items to Reserve"),
                },
                {
                    fieldname: "items",
                    fieldtype: "Table",
                    label: __("Items to Reserve"),
                    allow_bulk_edit: false,
                    cannot_add_rows: true,
                    cannot_delete_rows: true,
                    data: [],
                    fields: [

                        {
                            fieldname: "sales_order_item",
                            fieldtype: "Link",
                            label: __("SO Item"),
                            options: "Sales Order Item",
                            read_only: 1,
                            in_list_view: 0,
                        },
                        {
                            fieldname: "item_code",
                            fieldtype: "Link",
                            label: __("Item Code"),
                            options: "Item",
                            read_only: 1,
                            in_list_view: 1,
                            columns: 2
                        },
                        {
                            fieldname: "item_name",
                            fieldtype: "Data",
                            label: __("Item Name"),
                            read_only: 1,
                            in_list_view: 1,
                            columns: 2
                        },
                        {
                            fieldname: "warehouse",
                            fieldtype: "Link",
                            label: __("Warehouse"),
                            options: "Warehouse",
                            in_list_view: 1,
                            columns: 1
                        },
                        {
                            fieldname: "length_size",
                            fieldtype: "Float",
                            label: __("Length"),
                            in_list_view: 1,
                            columns: 1
                        },
                        {
                            fieldname: "max_length",
                            fieldtype: "Float",
                            label: __("Max Length"),
                            in_list_view: 1,
                            columns: 1

                        },
                        {
                            fieldname: "pieces",
                            fieldtype: "Float",
                            label: __("Pieces"),
                            read_only: 1,
                            in_list_view: 1,
                            columns: 1
                        },
                        {
                            fieldname: "section_weight",
                            fieldtype: "Float",
                            label: __("Section Weight"),
                            in_list_view: 1,
                            columns: 1
                        },
                        {
                            fieldname: "qty_to_reserve",
                            fieldtype: "Float",
                            label: __("Qty"),
                            reqd: 1,
                            in_list_view: 1,
                            columns: 1
                        }
                    ]
                }
            ],
            primary_action_label: __("Reserve Stock"),
            primary_action: () => {
                var data = { items: dialog.fields_dict.items.grid.get_selected_children() };

                if (data.items && data.items.length > 0) {
                    frappe.call({
                        method: "madhav.api.create_stock_reservation_entries",
                        args: {     
                            source_name: frm.doc.name,
                            items_details: data.items,
                        },
                        freeze: true,
                        freeze_message: __("Reserving Stock..."),
                        callback: (r) => {
                            dialog.hide();
                            frm.reload_doc();
                        },
                    });

                    
                } else {
                    frappe.msgprint(__("Please select items to reserve."));
                }
            },
        }); // This closes the frappe.ui.Dialog constructor

        // Store all eligible items initially
        const all_eligible_items = [];
        const item_codes = [...new Set(frm.doc.items.filter(i => i.reserve_stock).map((i) => i.item_code))];

        if (item_codes.length === 0) {
            dialog.fields_dict.items.df.data = all_eligible_items;
            dialog.fields_dict.items.grid.refresh();
            dialog.show();
            return;
        }

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Item",
                filters: { name: ["in", item_codes] },
                fields: ["name", "weight_per_meter"],
            },
            callback: (r) => {
                const weights = {};
                (r.message || []).forEach((item) => {
                    weights[item.name] = flt(item.weight_per_meter);
                });

                frm.doc.items.forEach((item) => {
                    if (item.reserve_stock) {
                        let unreserved_qty =
                            (flt(item.stock_qty) -
                                (item.stock_reserved_qty
                                    ? flt(item.stock_reserved_qty)
                                    : flt(item.delivered_qty) * flt(item.conversion_factor))) /
                            flt(item.conversion_factor);

                        if (unreserved_qty > 0) {
                            all_eligible_items.push({
                                __checked: 1,
                                sales_order_item: item.name,
                                item_code: item.item_code,
                                item_name: item.item_name,
                                warehouse: item.warehouse,
                                length_size: item.length_size,
                                max_length: flt(item.length_size) + 1.5,
                                pieces: item.pieces,
                                total_length: flt(item.pieces) * flt(item.length_size),
                                section_weight: flt(weights[item.item_code] || 0),
                                max_section_weight: null,
                                qty_to_reserve: unreserved_qty,
                            });
                        }
                    }
                });

                all_eligible_items.sort((a, b) => {
                    return flt(a.length_size) - flt(b.length_size);
                });
                dialog.fields_dict.items.df.data = all_eligible_items;
                dialog.fields_dict.items.grid.refresh();
                dialog.show();
            },
        });
    },
    make_material_request(frm) {
        frappe.model.open_mapped_doc({
            method: "madhav.api.make_material_request",
            frm: frm,
        });
    },
    validate(frm) {
        update_taxes_fields(frm);
        if (frm.is_new()) {  // Only set if new
            if (frm.doc.company === "MADHAV UDYOG PRIVATE LIMITED") {
                frm.set_value("naming_series", "MU-SO.YY.-");
            } else if (frm.doc.company === "MADHAV STELCO PRIVATE LIMITED") {
                frm.set_value("naming_series", "MS-SO.YY.-");
            }
        }
    },
    make_work_order(frm) {
        frm.call({
            method: "erpnext.selling.doctype.sales_order.sales_order.get_work_order_items",
            args: {
                sales_order: frm.docname,
            },
            freeze: true,
            callback: function (r) {
                if (!r.message) {
                    frappe.msgprint({
                        title: __("Work Order not created"),
                        message: __("No Items with Bill of Materials to Manufacture"),
                        indicator: "orange",
                    });
                    return;
                } else {
                    const fields = [
                        {
                            label: __("Items"),
                            fieldtype: "Table",
                            fieldname: "items",
                            description: __("Select BOM and Qty for Production"),
                            fields: [
                                {
                                    fieldtype: "Read Only",
                                    fieldname: "item_code",
                                    label: __("Item Code"),
                                    in_list_view: 1,
                                },
                                {
                                    fieldtype: "Link",
                                    fieldname: "bom",
                                    options: "BOM",
                                    reqd: 1,
                                    label: __("Select BOM"),
                                    in_list_view: 1,
                                    get_query: function (doc) {
                                        return { filters: { item: doc.item_code } };
                                    },
                                },
                                {
                                    fieldtype: "Float",
                                    fieldname: "pending_qty",
                                    reqd: 1,
                                    label: __("Qty"),
                                    in_list_view: 1,
                                },
                                {
                                    fieldtype: "Data",
                                    fieldname: "sales_order_item",
                                    reqd: 1,
                                    label: __("Sales Order Item"),
                                    hidden: 1,
                                },
                            ],
                            data: r.message,
                            get_data: () => {
                                return r.message;
                            },
                        },
                    ];
                    var d = new frappe.ui.Dialog({
                        title: __("Select Items to Manufacture"),
                        fields: fields,
                        primary_action: function () {
                            var data = { items: d.fields_dict.items.grid.get_selected_children() };
                            if (!data.items.length) {
                                frappe.throw(__("Please select atleast one item to continue"));
                            }
                            frm.call({
                                method: "make_work_orders",
                                args: {
                                    items: data,
                                    company: frm.doc.company,
                                    sales_order: frm.docname,
                                    project: frm.project,
                                },
                                freeze: true,
                                callback: function (r) {
                                    if (r.message) {
                                        frappe.msgprint({
                                            message: __("Work Orders Created: {0}", [
                                                r.message
                                                    .map(function (d) {
                                                        return repl(
                                                            '<a href="/app/work-order/%(name)s">%(name)s</a>',
                                                            { name: d }
                                                        );
                                                    })
                                                    .join(", "),
                                            ]),
                                            indicator: "green",
                                        });
                                        frappe.call({
                                            method: "madhav.api.sync_work_orders_from_sales_order",
                                            args: {
                                                sales_order: frm.doc.name
                                            },
                                            freeze: true,
                                            callback: function (res) {
                                                if (!res.exc) {

                                                }
                                            }
                                        });
                                    }
                                    d.hide();
                                },
                            });
                        },
                        primary_action_label: __("Create"),
                    });
                    d.show();
                }
            },
        });
    }
});

frappe.ui.form.on('Sales Order Item', {
    qty: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_length(frm, cdt, cdn);
    },
    length_size: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_length(frm, cdt, cdn);
    },
    pieces: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_length(frm, cdt, cdn);
    },
    items_remove: function (frm, cdt, cdn) {
        update_total_length(frm, cdt, cdn);
    },

    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.item_code) return;

        frappe.db.get_value(
            "Item",
            row.item_code,
            "is_manufacture"
        ).then(r => {
            if (r && r.message) {
                frappe.model.set_value(
                    cdt,
                    cdn,
                    "is_manufacture",
                    r.message.is_manufacture || 0
                );
            }
        });
    }
});



function calculate_qty(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (row.length_size && row.qty && row.item_code) {
        frappe.db.get_value("Item", row.item_code, "weight_per_meter")
            .then(r => {
                if (r.message && r.message.weight_per_meter) {
                    let weight_per_meter = r.message.weight_per_meter;
                    let pieces = (row.qty * 1000) / (row.length_size * weight_per_meter);
                    // Set lower integer value
                    pieces = Math.floor(pieces);
                    frappe.model.set_value(cdt, cdn, "pieces", pieces);
                } else {
                    frappe.msgprint("Weight per meter not found in Item master.");
                }
            });
    }
    if (row.length_size && row.pieces && row.item_code && !row.qty) {
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