frappe.ui.form.on('Cutting Plan', {
    refresh: function(frm) {

        // Add the "Get Items From" button
        if (frm.doc.docstatus !== 1) {
            frm.add_custom_button(__('Get Items From'), function() {
                show_work_order_dialog(frm);
            });
        }

        // Disable add/remove rows in scrap_transfer child table
        // frm.fields_dict["cutting_plan_scrap_transfer"].grid.cannot_add_rows = true;
        // frm.fields_dict["cutting_plan_scrap_transfer"].grid.only_sortable = true;
        // frm.fields_dict["cutting_plan_scrap_transfer"].refresh();

        // Check if we have a source warehouse stored and this is a new doc
        if (frm.is_new() && window.source_warehouse_for_cutting_plan) {
            // Only add if child table is empty
            if (!frm.doc.cut_plan_detail || frm.doc.cut_plan_detail.length === 0) {
                // Add a new row to child table
                let row = frm.add_child('cut_plan_detail');
                row.source_warehouse = window.source_warehouse_for_cutting_plan;
                
                // Refresh the child table
                frm.refresh_field('cut_plan_detail');
                
                // Clear the global variable
                window.source_warehouse_for_cutting_plan = null;
            }
        }
        
        // Set batch filter for all existing rows and new rows
        frm.set_query('batch', 'cut_plan_detail', function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (row.item_code) {
                return {
                    query: "madhav.api.get_cutting_plan_batches",
                    filters: {
                        item_code: row.item_code,
                        warehouse: row.source_warehouse,
                        include_expired: 1,
                        supplier_name: row.supplier_name
                    }
                };
            } else {
                // Show message if no item selected
                frappe.msgprint('Please select Item Code first');
                return {
                    filters: {
                        'item': 'dummy_item_that_does_not_exist'
                    }
                };
            }
        });

        // Set RM reference batch filter for cutting_plan_finish child table
        // This will show only batches that are present in cut_plan_detail table
        frm.set_query('rm_reference_batch', 'cutting_plan_finish', function(doc, cdt, cdn) {
            // Get all batches from cut_plan_detail table
            let available_batches = [];
            if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
                frm.doc.cut_plan_detail.forEach(function(row) {
                    if (row.batch) {
                        available_batches.push(row.batch);
                    }
                });
            }
            
            if (available_batches.length > 0) {
                return {
                    filters: {
                        'name': ['in', available_batches]
                    }
                };
            } else {
                // If no batches in cut_plan_detail, show message and return empty filter
                frappe.msgprint('Please add batches in RM Detail section first');
                return {
                    filters: {
                        'name': 'no_batch_available'
                    }
                };
            }
        });

        // Set FG item filter for cutting_plan_finish child table
        // This will show only production items from work orders in cut_plan_detail
        setup_fg_item_filter(frm);
    },
    
    cut_plan_type: function(frm) {
        // When cut_plan_type changes, refresh the form to update any cached data
        frm.refresh();
    }
});

function show_work_order_dialog(frm) {
    // Get the cut_plan_type from the current form
    let cut_plan_type = frm.doc.cut_plan_type || '';
    
    let dialog = new frappe.ui.Dialog({
        title: __('Select Work Orders'),
        fields: [
            {
                fieldtype: 'Link',
                fieldname: 'item_to_manufacture',
                label: __('Item to Manufacture'),
                options: 'Item',
                get_query: function() {
                    return {
                        filters: {
                            'is_stock_item': 1
                        }
                    };
                },
                onchange: function() {
                    // When item is selected, update Work Order filter
                    let item = dialog.get_value('item_to_manufacture');
                    dialog.fields_dict.work_order_name.get_query = function() {
                        // Use the cut_plan_type passed from the parent function
                        
                        let filters = {
                            'docstatus': 1
                        };
                        
                        // Set status filter based on cut_plan_type
                        if (cut_plan_type === 'Finished Cut Plan') {
                            filters['status'] = 'Completed';
                        } else {
                            filters['status'] = ['not in', ['Completed', 'Stopped', 'Cancelled']];
                        }
                        
                        if (item) {
                            filters.production_item = item;
                        }
                        return { filters: filters };
                    };
                    // Reload work orders when item changes
                    load_work_orders(dialog, cut_plan_type);
                }
            },  
            {
                fieldtype: 'Link',
                fieldname: 'rm_used',
                label: __('Work Orders Raw Material'),
                options: 'Item',
                description: __('Filter work orders by raw material used'),
                get_query: function() {
                    return {
                        filters: {
                            'is_stock_item': 1
                        }
                    };
                },
                onchange: function() {
                    // Disable work order if RM is selected
                    if (dialog.get_value('rm_used')) {
                        dialog.set_df_property('work_order_name', 'read_only', 1);
                        dialog.set_value('work_order_name', ''); // Clear work order value if any
                    } else {
                        dialog.set_df_property('work_order_name', 'read_only', 0);
                    }
                    // Reload work orders when RM changes
                    load_work_orders(dialog, cut_plan_type);
                }
            },          
            {
                fieldtype: 'Link',
                fieldname: 'work_order_name',
                label: __('Work Order Name'),
                options: 'Work Order',
                description: __('Enter partial name to filter work orders'),
                get_query: function() {
                    let item = dialog.get_value('item_to_manufacture');
                    // Use the cut_plan_type passed from the parent function
                    
                    let filters = {
                        'docstatus': 1
                    };
                    
                    // Set status filter based on cut_plan_type
                    if (cut_plan_type === 'Finished Cut Plan') {
                        filters['status'] = 'Completed';
                    } else {
                        filters['status'] = ['not in', ['Completed', 'Stopped', 'Cancelled']];
                    }
                    
                    if (item) {
                        filters.production_item = item;
                    }
                    return { filters: filters };
                },
                onchange: function() {
                    // Load work orders when work order name changes
                    load_work_orders(dialog, cut_plan_type);
                }
            },
            {
                fieldtype: 'HTML',
                fieldname: 'work_orders_html',
                options: '<div id="work_orders_container"></div>'
            }
        ],
        primary_action_label: __('Get Selected Items'),
        primary_action: function(values) {
            get_selected_work_orders(frm, dialog, cut_plan_type);
        }
    });

    // Add search functionality
    dialog.fields_dict.item_to_manufacture.$input.on('change', function() {
        load_work_orders(dialog, cut_plan_type);
    });

    dialog.fields_dict.work_order_name.$input.on('input', function() {
        load_work_orders(dialog, cut_plan_type);
    });

    // Also handle the awesomplete selection event
    dialog.fields_dict.work_order_name.$input.on('awesomplete-selectcomplete', function() {
        setTimeout(() => {
            load_work_orders(dialog, cut_plan_type);
        }, 100);
    });

    dialog.show();
    
    // Load work orders initially
    setTimeout(() => {
        load_work_orders(dialog, cut_plan_type);
    }, 100);
}

function load_work_orders(dialog, cut_plan_type) {
    let item_to_manufacture = dialog.get_value('item_to_manufacture');
    let work_order_name = dialog.get_value('work_order_name');
    let rm_used = dialog.get_value('rm_used');
    
    console.log('load_work_orders called with cut_plan_type:', cut_plan_type);
    
    let filters = {
        'docstatus': 1
    };
    
    // Set status filter based on cut_plan_type
    if (cut_plan_type === 'Finished Cut Plan') {
        // For Finished Cut Plan, show only completed work orders
        filters['status'] = 'Completed';
        console.log('Filtering for Completed work orders (Finished Cut Plan)');
    } else {
        // For Raw Material Cut Plan, show non-completed work orders
        filters['status'] = ['not in', ['Completed', 'Stopped', 'Cancelled']];
        console.log('Filtering for non-completed work orders (Raw Material Cut Plan)');
    }
    
    if (item_to_manufacture) {
        filters['production_item'] = item_to_manufacture;
    }
    
    if (work_order_name) {
        filters['name'] = ['like', '%' + work_order_name + '%'];
    }

    // If RM is selected, we need to use a server method to filter work orders
    if (rm_used) {
        frappe.call({
            method: 'madhav.api.get_work_orders_by_rm', // You'll need to create this method
            args: {
                rm_item: rm_used,
                filters: filters
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    render_work_orders_table(dialog, r.message, cut_plan_type);
                } else {
                    dialog.fields_dict.work_orders_html.$wrapper.html('<p>No Work Orders Found with selected Raw Material</p>');
                }
            }
        });
        return;
    }

    // Regular call when no RM filter
    get_filtered_work_orders(dialog, filters, cut_plan_type);
}

function get_filtered_work_orders(dialog, filters, cut_plan_type) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Work Order',
            filters: filters,
            fields: ['name','production_item', 'status'],
            order_by: 'creation desc',
            limit_page_length: 20
        },
        callback: function(r) {
            if (r.message) {
                render_work_orders_table(dialog, r.message, cut_plan_type);
            }else {
                // Clear HTML if no records found
                dialog.fields_dict.work_orders_html.$wrapper.html('<p>No Work Orders Found</p>');
            }
        }
    });
}

function render_work_orders_table(dialog, work_orders, cut_plan_type) {
    let html = `
        <div class="table-responsive">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th><input type="checkbox" id="select_all_wo"></th>
                        <th>Work Order</th>
                        <th>Production Item</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
    `;

    work_orders.forEach(function(wo) {
        let pending_qty = wo.qty - (wo.produced_qty || 0);
        html += `
            <tr>
                <td><input type="checkbox" class="work-order-checkbox" data-name="${wo.name}" data-item="${wo.production_item}" data-qty="${pending_qty}"></td>
                <td>${wo.name}</td>
                <td>${wo.production_item}</td>
                <td><span class="badge badge-${wo.status === 'Completed' ? 'success' : 'warning'}">${wo.status}</span></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    dialog.fields_dict.work_orders_html.$wrapper.html(html);

    // Add select all functionality
    $('#select_all_wo').on('change', function() {
        $('.work-order-checkbox').prop('checked', this.checked);
    });
}

function get_selected_work_orders(frm, dialog, cut_plan_type) {
    let selected_work_orders = [];
    
    $('.work-order-checkbox:checked').each(function() {
        selected_work_orders.push({
            work_order: $(this).data('name'),
            item_code: $(this).data('item'),
            qty: $(this).data('qty')
        });
    });

    if (selected_work_orders.length === 0) {
        frappe.msgprint(__('Please select at least one Work Order'));
        return;
    }

    // Process selected work orders and add to cutting plan
    process_selected_work_orders(frm, selected_work_orders, cut_plan_type);
    dialog.hide();
}

function process_selected_work_orders(frm, selected_work_orders, cut_plan_type) {
    if (cut_plan_type === 'Finished Cut Plan') {
        // Build list of work order names
        const wo_names = (selected_work_orders || []).map(w => w.work_order).filter(Boolean);
        if (wo_names.length === 0) {
            frappe.msgprint(__('Please select at least one Work Order'));
            return;
        }
        frappe.call({
            method: 'madhav.api.get_finished_cut_plan_from_mtm',
            args: { work_orders: wo_names },
            callback: function(r) {
                if (!r.message) return;
                const detail_rows = r.message.detail_rows || [];
                const finish_rows = r.message.finish_rows || [];

                // Append consolidated rows to cut_plan_detail
                detail_rows.forEach(function(d) {
                    let row = frm.add_child('cut_plan_detail');
                    row.item_code = d.item_code;
                    row.item_name = d.item_name;
                    row.source_warehouse = d.source_warehouse;
                    row.qty = d.qty;
                    // row.pieces = d.pieces;
                    // row.length_size_inch = d.length_size;
                    // row.length_size = d.length_size/39.37;
                    row.section_weight = d.section_weight;
                    row.batch = d.batch;
                    row.work_order_reference = d.work_order_reference;
                });

                //Append non-consolidated rows to cutting_plan_finish
                finish_rows.forEach(function(f) {
                    let row = frm.add_child('cutting_plan_finish');
                    row.item = f.item;
                    row.batch = f.batch;
                    row.qty = f.qty;
                    row.pieces = f.pieces;
                    row.length_size = f.length_size;
                    row.section_weight = f.section_weight;
                    row.lot_no = f.lot_no;
                    row.rm_reference_batch = f.rm_reference_batch;
                    row.work_order_reference = f.work_order_reference;
                    row.fg_item = f.fg_item;
                });

                frm.refresh_field('cut_plan_detail');
                frm.refresh_field('cutting_plan_finish');
                setup_fg_item_filter(frm);

                frappe.show_alert({
                    message: __('MTM items pulled into Cutting Plan'),
                    indicator: 'green'
                });
            }
        });
    } else {
        // Raw Material Cut Plan: existing behavior via WO required items
        frappe.call({
            method: 'madhav.api.get_work_order_details',
            args: {
                work_orders: selected_work_orders
            },
            callback: function(r) {
                if (r.message) {
                    r.message.forEach(function(item) {
                        let child = frm.add_child('cut_plan_detail');
                        child.item_code = item.item_code;
                        child.item_name = item.item_name;
                        child.source_warehouse = item.source_warehouse;
                        child.wo_qty = item.qty;
                        child.basic_rate = item.basic_rate;
                        child.work_order_reference =  item.work_order_reference;
                        child.sales_order =  item.sales_order
                    });
                    frm.refresh_field('cut_plan_detail');
                    setup_fg_item_filter(frm);
                    frappe.show_alert({
                        message: __('Items added successfully'),
                        indicator: 'green'
                    });
                }
            }
        });
    }
}

// Child table events for cut_plan_detail
frappe.ui.form.on('Cut Plan Detail', {
    cut_plan_detail_add: function(frm, cdt, cdn) {
        // Auto-fill source warehouse when new row is added
        let row = locals[cdt][cdn];
        if (frm.doc.default_source_warehouse && !row.source_warehouse) {
            frappe.model.set_value(cdt, cdn, 'source_warehouse', frm.doc.default_source_warehouse);
        }
        update_total_qty_and_amount(frm, cdt, cdn);
    },

    cut_plan_detail_remove: function(frm, cdt, cdn) {
        update_total_qty_and_amount(frm, cdt, cdn);    
        // Refresh cutting_plan_finish table to update RM reference batch options
        frm.refresh_field('cutting_plan_finish');
        // Update scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    
    item_code: function(frm, cdt, cdn) {
        // Clear batch when item code changes
        let row = locals[cdt][cdn];
        if (row.batch) {
            frappe.model.set_value(cdt, cdn, 'batch', '');
        }

        // Set batch filter when item code changes
        setTimeout(() => {
            set_batch_filter_for_cutting_plan(frm, cdt, cdn);
        }, 100);

        frappe.db.get_value('Item Price', {
            item_code: row.item_code,
            uom: row.uom
        }, 'price_list_rate').then(price_res => {
            console.log("check for item list",price_res.message.price_list_rate);
            if (!price_res || !price_res.message || !price_res.message.price_list_rate) return;

            frappe.model.set_value(cdt, cdn, 'basic_rate', price_res.message.price_list_rate);
        });
        
        // Refresh the batch field to apply the new filter
        frm.refresh_field('cut_plan_detail');
    },
    
    batch: function(frm, cdt, cdn) {
        // Validate that item code is selected before batch
        let row = locals[cdt][cdn];
        if (!row.item_code && row.batch) {
            frappe.msgprint('Please select Item Code first');
            frappe.model.set_value(cdt, cdn, 'batch', '');
            return;
        }

        if (row.batch) {
        frappe.db.get_value("Batch", row.batch, "batch_qty")
            .then(r => {
                if (r.message && r.message.batch_qty !== undefined) {
                    frappe.model.set_value(cdt, cdn, 'qty', r.message.batch_qty);
                }
            });
        }
        // Refresh cutting_plan_finish table to update RM reference batch options
        frm.refresh_field('cutting_plan_finish');        
    },
    pieces: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
    },
    length_size: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
    },
    qty: function(frm, cdt, cdn) {
        // Recalculate basic amount when quantity changes
        let row = locals[cdt][cdn];
        if (row.basic_rate && row.qty) {
            let basic_amount = row.basic_rate * row.qty;
            frappe.model.set_value(cdt, cdn, 'basic_amount', basic_amount);
        }
        update_total_qty_and_amount(frm, cdt, cdn);

        // Update scrap quantity when qty changes in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);  
        // Auto-fill scrap transfer table when qty changes
        auto_fill_scrap_transfer_table(frm);
    },
    
    basic_rate: function(frm, cdt, cdn) {
        // Recalculate basic amount when basic rate changes
        let row = locals[cdt][cdn];
        if (row.basic_rate && row.qty) {
            let basic_amount = row.basic_rate * row.qty;
            frappe.model.set_value(cdt, cdn, 'basic_amount', basic_amount);
        }
    }
});

function update_total_qty_and_amount(frm, cdt, cdn) {
    console.log("update_total_qty_and_amount");
    let total_qty = 0;
    let total_amount = 0;

	// Step 1: Calculate totals and set inch conversions on each RM row
	const METER_TO_INCH = 39.37;
	frm.doc.cut_plan_detail.forEach(item => {
        let qty = flt(item.qty);
        let basic_amount = flt(item.basic_amount);

		// Derive and set inch-based fields for Cut Plan Detail
		let length_size = flt(item.length_size_inch) ? flt(item.length_size_inch) / METER_TO_INCH : 0;
		let section_weight = flt(item.section_weight_inch) ? flt(item.section_weight_inch) *  METER_TO_INCH : 0;
		let total_length_in_meter = flt(item.total_length_in_meter);
		if (!total_length_in_meter && flt(item.pieces) && flt(item.length_size)) {
			total_length_in_meter = flt(item.pieces) * flt(item.length_size);
			frappe.model.set_value('Cut Plan Detail', item.name, 'total_length_in_meter', flt(total_length_in_meter, 3));
		}
		let total_length_in_inch = total_length_in_meter ? total_length_in_meter * METER_TO_INCH : 0;

		frappe.model.set_value('Cut Plan Detail', item.name, 'length_size', flt(length_size, 3));
		frappe.model.set_value('Cut Plan Detail', item.name, 'section_weight', flt(section_weight, 3));
		frappe.model.set_value('Cut Plan Detail', item.name, 'total_length_in_inch', flt(total_length_in_inch, 3));

        if (qty) {
            total_qty += qty;
        }
        if (basic_amount) {
            total_amount += basic_amount;
        }

    });

    frm.set_value("total_qty", total_qty.toFixed(3));
    // frm.set_value("amount", total_amount.toFixed(2));

}

frappe.ui.form.on('Cutting Plan Finish', {
    cutting_plan_finish_add: function(frm, cdt, cdn) {
        // Auto-fill FG item if there's only one production item available
        if (frm.doc.available_fg_items && frm.doc.available_fg_items.length === 1) {
            frappe.model.set_value(cdt, cdn, 'fg_item', frm.doc.available_fg_items[0]);
            // also set work_order_reference when map is available
            const map = frm.__fg_item_to_wo || {};
            const wo = map[frm.doc.available_fg_items[0]];
            if (wo) {
                frappe.model.set_value(cdt, cdn, 'work_order_reference', wo);
            }
        }
    },
    pieces: function (frm, cdt, cdn) {
        calculate_qty_from_inch(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Validate batch quantity after qty calculation
        validate_batch_qty_consumption(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    length_size: function (frm, cdt, cdn) {
        calculate_qty_from_inch(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Validate batch quantity after qty calculation
        validate_batch_qty_consumption(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
        let row = locals[cdt][cdn];
        if (row.length_size_inch && row.section_weight) {
                frappe.model.set_value(cdt, cdn, 'weight_per_length', row.section_weight * row.length_size_inch);
        }
        // Validate finish row constraints in real-time
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_inch: function (frm, cdt, cdn) {
        calculate_qty_from_inch(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Validate batch quantity after qty calculation
        validate_batch_qty_consumption(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
        let row = locals[cdt][cdn];
        if (row.length_size_inch && row.section_weight) {
                frappe.model.set_value(cdt, cdn, 'weight_per_length', row.section_weight * row.length_size_inch);
            }
        // Validate finish row constraints in real-time
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    weight_per_length: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.weight_per_length && row.process_loss){
            // remaining_weight = weight_per_length - (process_loss% of weight_per_length)
            let remaining = row.weight_per_length - (row.weight_per_length * row.process_loss / 100);
            frappe.model.set_value(cdt, cdn, 'remaining_weight', remaining);
        }
    },
    process_loss: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.weight_per_length && row.process_loss){
            // remaining_weight = weight_per_length - (process_loss% of weight_per_length)
            let remaining = row.weight_per_length - (row.weight_per_length * row.process_loss / 100);
            frappe.model.set_value(cdt, cdn, 'remaining_weight', remaining);
        }
    },
    remaining_weight: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.remaining_weight && row.fg_item) {
            frappe.db.get_value("Item", row.fg_item, "weight_per_meter")
                .then(r => {
                    if (r && r.message && r.message.weight_per_meter) {
                        let wpm = r.message.weight_per_meter;
                        let semi_length = row.remaining_weight / wpm;
                        frappe.model.set_value(cdt, cdn, 'semi_fg_length', semi_length);
                    }
                });
        }
    },
    fg_item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log("FG Item changed:", row.fg_item);
        // Set work_order_reference from fg -> wo map if present
        const fgToWo = frm.__fg_item_to_wo || {};
        if (row.fg_item && fgToWo[row.fg_item]) {
            frappe.model.set_value(cdt, cdn, 'work_order_reference', fgToWo[row.fg_item]);
        }

        if (row.remaining_weight && row.fg_item) {
            frappe.db.get_value("Item", row.fg_item, "weight_per_meter")
                .then(r => {
                    if (r && r.message && r.message.weight_per_meter) {
                        let wpm = r.message.weight_per_meter;
                        let semi_length = row.remaining_weight / wpm;
                        frappe.model.set_value(cdt, cdn, 'semi_fg_length', semi_length);
                    }
                });
        }
        if (frm.doc.cut_plan_type == "Finished Cut Plan"){
            frappe.db.get_value("Item", row.fg_item, "weight_per_meter")
                .then(r => {
                    if (r && r.message && r.message.weight_per_meter) {
                        let wpm = r.message.weight_per_meter;
                        frappe.model.set_value(cdt, cdn, 'section_weight', wpm);
                    }
                });
        }
    },
    cutting_plan_finish_remove: function(frm, cdt, cdn) {
        update_total_cut_plan_qty(frm, cdt, cdn);    
        // Update scrap quantity in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    qty: function(frm, cdt, cdn) {
        if(frm.doc.cut_plan_type == "Finished Cut Plan"){
            let row = locals[cdt][cdn];
            if (row.qty){
                frappe.model.set_value(cdt, cdn, 'manual_qty', row.qty);
            }            
        }
        // Validate batch quantity when qty is directly changed
        validate_batch_qty_consumption(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        // update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    section_weight: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // if (row.length_size && row.section_weight) {
        //     frappe.model.set_value(cdt, cdn, 'weight_per_length', row.section_weight*39.37 * row.length_size/39.37);
        // }
    },
        //  
    // Add validation for RM reference batch
    rm_reference_batch: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let available_batches = [];     
        
        // Get all unique batches from cut_plan_detail
        if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
            frm.doc.cut_plan_detail.forEach(function(detail_row) {
                if (detail_row.batch && !available_batches.includes(detail_row.batch)) {
                    available_batches.push(detail_row.batch);
                }
            });
        }
        
        // Validate if selected batch exists in cut_plan_detail
        if (row.rm_reference_batch && !available_batches.includes(row.rm_reference_batch)) {
            frappe.msgprint('Selected batch is not available in RM Detail For Cut Plan section');
            frappe.model.set_value(cdt, cdn, 'rm_reference_batch', '');
        } 
        if (row.rm_reference_batch) {
            let batch_totals = calculate_batch_totals(frm, row.rm_reference_batch);
            if (frm.doc.cut_plan_type == "Finished Cut Plan"){
                row.pieces = batch_totals.total_pieces || 0;
                row.length_size = batch_totals.total_length || 0;
                frappe.db.get_value("Item", row.fg_item, "weight_per_meter").then(r => {
                    if (r && r.message) {
                        console.log("checking for section weight for FG..........",r.message)
                        frappe.model.set_value(cdt, cdn, "section_weight", r.message.weight_per_meter || 0);
                    }
                });
            } else{
                row.pieces = batch_totals.total_pieces || 0;
                row.length_size_inch = batch_totals.total_length || 0;
            }
            
            // Check first occurrence logic only if both values exist
            if (batch_totals.total_pieces && batch_totals.total_length) {
            console.log("Checking if this is first occurrence of batch:", row.rm_reference_batch);

            let current_table = frm.doc.cutting_plan_finish || [];

            // Find if there are any existing rows with the same batch (excluding current row)
            let existing_batch_rows = current_table.filter(table_row =>
                table_row.rm_reference_batch === row.rm_reference_batch &&
                table_row.name !== cdn
            );

            console.log("Existing rows with same batch:", existing_batch_rows.length);

            if (existing_batch_rows.length === 0) {
                // This is the first occurrence of this batch
                console.log("First occurrence of batch - setting full length");
                let total_meter_length = batch_totals.total_pieces * batch_totals.total_length;
                if (frm.doc.cut_plan_type == "Finished Cut Plan"){
                    frappe.model.set_value(cdt, cdn, 'total_length_in_meter', total_meter_length);
                }else{
                    frappe.model.set_value(cdt, cdn, 'total_length_in_meter_inch', total_meter_length);
                }
            } else {
                // This batch already exists, calculate remaining length
                console.log("Batch already exists - calculating remaining length");
                auto_fill_remaining_length(frm, cdt, cdn);
            }
        }
        }
    },
    // Real-time field handlers for finish constraints
    semi_fg_length: function(frm, cdt, cdn) {
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    no_of_length_sizes: function(frm, cdt, cdn) {
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_1: function(frm, cdt, cdn) {
        frm.__last_edited_length_field = 'length_size_1';
        frm.__last_edited_length_row = cdn;
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_2: function(frm, cdt, cdn) {
        frm.__last_edited_length_field = 'length_size_2';
        frm.__last_edited_length_row = cdn;
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_3: function(frm, cdt, cdn) {
        frm.__last_edited_length_field = 'length_size_3';
        frm.__last_edited_length_row = cdn;
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_4: function(frm, cdt, cdn) {
        frm.__last_edited_length_field = 'length_size_4';
        frm.__last_edited_length_row = cdn;
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    length_size_5: function(frm, cdt, cdn) {
        frm.__last_edited_length_field = 'length_size_5';
        frm.__last_edited_length_row = cdn;
        validate_cutting_plan_finish_row_constraints(frm, cdt, cdn);
    },
    lot_no_type: function(frm, cdt, cdn) {
        update_lot_no_from_parts(frm, cdt, cdn);
    },
    lot_number: function(frm, cdt, cdn) {
        update_lot_no_from_parts(frm, cdt, cdn);
    }
});

function update_lot_no_from_parts(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    const typePart = (row.lot_no_type || '').trim();
    const numberPart = (row.lot_number || '').trim();
    const combined = [typePart, numberPart].filter(Boolean).join('-');
    console.log("checking for combined lot_no", combined);
    if (combined) {
        frappe.model.set_value(cdt, cdn, 'lot_no', combined);
    } else {
        // Clear when both empty
        frappe.model.set_value(cdt, cdn, 'lot_no', '');
    }
}

// Updated helper function to auto-fill remaining length
function auto_fill_remaining_length(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
            
    let batch_totals = calculate_batch_totals(frm, row.rm_reference_batch);
    let batch_total_length = batch_totals.total_length;

    // Calculate total consumed length from all previous rows with the same batch
    let total_consumed_length = 0;
    console.log("Checking cutting_plan_finish for consumed length...");
    if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
        frm.doc.cutting_plan_finish.forEach(function(finish_row, index) {
            console.log(`finish_row[${index}]:`, finish_row.name, "batch:", finish_row.rm_reference_batch, "total_length_in_meter:", finish_row.total_length_in_meter);
            // Skip the current row being added/modified
            if (finish_row.name !== row.name && 
                finish_row.rm_reference_batch === row.rm_reference_batch && 
                finish_row.total_length_in_meter) {
                total_consumed_length += finish_row.total_length_in_meter;
                console.log("Added to consumed length:", finish_row.total_length_in_meter, "Total consumed now:", total_consumed_length);
            }
        });
    }
    
        
    // Calculate remaining length
    let remaining_length = batch_total_length - total_consumed_length;
    console.log("remaining_length:", remaining_length);
    
    // Set length_size with remaining length (ensure it's not negative)
    if (remaining_length > 0) {
        console.log("Setting length_size to:", remaining_length);
        
        // Use setTimeout to ensure this runs after other field triggers
        setTimeout(() => {
            frappe.model.set_value(cdt, cdn, 'total_length_in_meter_inch', remaining_length);
            console.log("frappe.model.set_value called with delay");
        }, 100);
        
    } else {
        console.log("Setting length_size to 0 (remaining_length <= 0)");
        setTimeout(() => {
            frappe.model.set_value(cdt, cdn, 'length_size_inch', 0);
        }, 100);
        if (remaining_length < 0) {
            frappe.msgprint(`Warning: No remaining length available for batch ${row.rm_reference_batch}`);
        }
    }
    console.log("=== AUTO_FILL_REMAINING_LENGTH FUNCTION ENDED ===");
}

function calculate_batch_totals(frm, selected_batch) {
    let total_pieces = 0;
    let matching_rows = 0;
    let batch_length_size = 0;

    if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
        frm.doc.cut_plan_detail.forEach(function(detail_row) {
            if (detail_row.batch === selected_batch) {
                total_pieces += flt(detail_row.pieces) || 0;
                batch_length_size = detail_row.length_size_inch || 0; // fixed length size
                matching_rows++;
            }
        });
    }

    let total_length = total_pieces * batch_length_size;

    console.log(`Batch ${selected_batch} found in ${matching_rows} rows:`, {
        total_pieces: total_pieces,
        length_size: batch_length_size,
        total_length: total_length
    });

    return {
        total_pieces: total_pieces,
        length_size: batch_length_size,
        total_length: total_length,
        matching_rows: matching_rows
    };
}

function calculate_qty(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.pieces || !row.length_size){
          return;
    }
     let qty = row.pieces * row.length_size *row.section_weight;
     let qty_in_tonne = (qty/1000).toFixed(3);
     let total_length = row.pieces * row.length_size
     frappe.model.set_value(cdt, cdn, 'qty', qty_in_tonne);
     frappe.model.set_value(cdt, cdn, 'total_length_in_meter',total_length)
}

function calculate_qty_from_inch(frm, cdt, cdn) {
    console.log("now in ...........")
    let row = locals[cdt][cdn];

    if (frm.doc.cut_plan_type == "Finished Cut Plan") {
        if (!row.pieces || !row.length_size){
            return;
        }
        let qty = row.pieces * row.length_size *row.section_weight;
        let qty_in_tonne = (qty/1000).toFixed(3);
        let total_length = row.pieces * row.length_size
        frappe.model.set_value(cdt, cdn, 'qty', qty_in_tonne);
        frappe.model.set_value(cdt, cdn, 'manual_qty', qty_in_tonne);
        frappe.model.set_value(cdt, cdn, 'total_length_in_meter',total_length)
    } 
    if (frm.doc.cut_plan_type == "Raw Material Cut Plan"){
        if (!row.pieces || !row.length_size_inch){
            return;
         }
        console.log("please check raw cut plan................")
        let qty = row.pieces * row.length_size_inch/39.37 *row.section_weight*39.37;
        let qty_in_tonne = (qty/1000).toFixed(3);
        let total_length = row.pieces * row.length_size_inch
        frappe.model.set_value(cdt, cdn, 'qty', qty_in_tonne);
        frappe.model.set_value(cdt, cdn, 'total_length_in_meter_inch',total_length) 
    }
}

// Qty auto-calculation for Cut Plan Finish (second) table
frappe.ui.form.on('Cutting plan Finish Second', {
    pieces: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
    },
    length_size: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
    },
    section_weight: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
    }
});

function update_total_cut_plan_qty(frm, cdt, cdn){
    let total_cut_plan_qty = 0;
    let qty = 0;

    frm.doc.cutting_plan_finish.forEach(item => {
        if(frm.doc.cut_plan_type == "Finished Cut Plan"){
            qty = flt(item.manual_qty);    
        }
        if(frm.doc.cut_plan_type == "Raw Material Cut Plan"){
            qty = flt(item.qty);
        }

        if (qty) {
            total_cut_plan_qty += qty;
        }
    });

    frm.set_value("cut_plan_total_qty", total_cut_plan_qty.toFixed(3));
}

// Function to validate batch quantity consumption
function validate_batch_qty_consumption(frm, cdt, cdn) {
    if (frm.doc.cut_plan_type == "Finished Cut Plan"){
        return;
    }
    console.log("yesy we are cekin gfor quality validation............")
    let current_row = locals[cdt][cdn];
    
    // Only validate if both rm_reference_batch and qty are present
    if (!current_row.rm_reference_batch || !current_row.qty) {
        return;
    }
    
    let batch_to_validate = current_row.rm_reference_batch;
    let current_row_name = current_row.name;
    
    // Get available quantity for this batch from RM Plan Detail
    let available_qty = 0;
    if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
        frm.doc.cut_plan_detail.forEach(function(detail_row) {
            if (detail_row.batch === batch_to_validate) {
                available_qty += flt(detail_row.qty);
            }
        });
    }
    console.log("Batch total availble qttttttttttttttttttty",available_qty)
    // Calculate total consumed quantity for this batch from Cut Plan Finish (excluding current row)
    let consumed_qty = 0;
    if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
        frm.doc.cutting_plan_finish.forEach(function(finish_row) {
            // Exclude current row from total consumed calculation
            if (finish_row.rm_reference_batch === batch_to_validate && 
                finish_row.name !== current_row_name && 
                flt(finish_row.qty)) {
                consumed_qty += flt(finish_row.qty);
            }
        });
    }
    
    // Calculate total after adding current row quantity
    let total_with_current = consumed_qty + flt(current_row.qty);
    console.log("currrrrrrrrrrrrrrrrrrrent qty",total_with_current)
    console.log("Available qqqqqqqqqqqqqqqty",available_qty)
    // Check if total quantity exceeds available quantity
    if (total_with_current > available_qty) {
        let remaining_qty = (available_qty - consumed_qty).toFixed(2);
        
        frappe.msgprint({
            title: 'Quantity Validation',
            message: `<p><strong>Batch:</strong> ${batch_to_validate}</p>
                     <p><strong>Available Quantity:</strong> ${available_qty.toFixed(2)}</p>
                     <p><strong>Already Consumed:</strong> ${consumed_qty.toFixed(2)}</p>
                     <p><strong>Remaining Quantity:</strong> ${remaining_qty}</p>
                     <p><strong>Entered quantity exceeds available quantity. Row will be cleared.</strong></p>`,
            indicator: 'red'
        });
        
        // Clear the row completely
        frappe.model.set_value(cdt, cdn, 'qty', '');
        frappe.model.set_value(cdt, cdn, 'pieces', '');
        frappe.model.set_value(cdt, cdn, 'length_size', '');
        frappe.model.set_value(cdt, cdn, 'total_length_in_meter', '');
        
        return false;
    }
    
    return true;
}

// Function to get batch consumption summary (useful for debugging)
function get_batch_consumption_summary(frm, batch_name) {
    let summary = {
        batch: batch_name,
        available_qty: 0,
        consumed_qty: 0,
        remaining_qty: 0
    };
    
    // Get available quantity
    if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
        frm.doc.cut_plan_detail.forEach(function(detail_row) {
            if (detail_row.batch === batch_name) {
                summary.available_qty += flt(detail_row.qty);
            }
        });
    }
    
    // Get consumed quantity
    if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
        frm.doc.cutting_plan_finish.forEach(function(finish_row) {
            if (finish_row.rm_reference_batch === batch_name && flt(finish_row.qty)) {
                summary.consumed_qty += flt(finish_row.qty);
            }
        });
    }
    
    summary.remaining_qty = summary.available_qty - summary.consumed_qty;
    
    return summary;
}

// Function to update scrap quantity for all batches in RM Plan Detail
function update_scrap_qty_for_all_batches(frm) {
    if (!frm.doc.cut_plan_detail || frm.doc.cut_plan_detail.length === 0) {
        return;
    }
    
    // Loop through each row in RM Plan Detail
    frm.doc.cut_plan_detail.forEach(function(detail_row, index) {
        if (detail_row.batch && flt(detail_row.qty)) {
            let batch_name = detail_row.batch;
            let available_qty = flt(detail_row.qty);
            
            // Calculate total consumed quantity for this batch from Cut Plan Finish
            let consumed_qty = 0;
            if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
                frm.doc.cutting_plan_finish.forEach(function(finish_row) {
                    if (finish_row.rm_reference_batch === batch_name && flt(finish_row.qty)) {
                        consumed_qty += flt(finish_row.qty);
                    }
                });
            }
            
            // Calculate scrap quantity = Available - Consumed
            let scrap_qty = (available_qty - consumed_qty).toFixed(2);
            
            // Update scrap_qty field in the RM Plan Detail row
            frappe.model.set_value('Cut Plan Detail', detail_row.name, 'scrap_qty', parseFloat(scrap_qty));
        }
    });
    
    // Refresh the RM Plan Detail table to show updated values
    frm.refresh_field('cut_plan_detail');
}

// Function to update scrap quantity for a specific batch - currently not using**
function update_scrap_qty_for_batch(frm, batch_name) {
    if (!frm.doc.cut_plan_detail || frm.doc.cut_plan_detail.length === 0) {
        return;
    }
    
    // Find the row with the specific batch
    frm.doc.cut_plan_detail.forEach(function(detail_row) {
        if (detail_row.batch === batch_name && flt(detail_row.qty)) {
            let available_qty = flt(detail_row.qty);
            
            // Calculate total consumed quantity for this batch from Cut Plan Finish
            let consumed_qty = 0;
            if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
                frm.doc.cutting_plan_finish.forEach(function(finish_row) {
                    if (finish_row.rm_reference_batch === batch_name && flt(finish_row.qty)) {
                        consumed_qty += flt(finish_row.qty);
                    }
                });
            }
            
            // Calculate scrap quantity = Available - Consumed
            let scrap_qty = (available_qty - consumed_qty).toFixed(2);
            
            // Update scrap_qty field in the RM Plan Detail row
            frappe.model.set_value('Cut Plan Detail', detail_row.name, 'scrap_qty', parseFloat(scrap_qty));
        }
    });
    
    // Refresh the RM Plan Detail table to show updated values
    frm.refresh_field('cut_plan_detail');
}

// // Function to auto-fill scrap transfer table for batch wise maintainnace
// function auto_fill_scrap_transfer_table(frm) {
//     if (!frm.doc.cut_plan_detail || frm.doc.cut_plan_detail.length === 0) {
//         return;
//     }
    
//     // Clear existing scrap transfer rows
//     frm.clear_table('cutting_plan_scrap_transfer');
    
//     // Get scrap items from RM Plan Detail
//     frm.doc.cut_plan_detail.forEach(function(detail_row) {
//         if (detail_row.item_code && detail_row.scrap_qty && flt(detail_row.scrap_qty) > 0) {
//             // Add scrap transfer row
//             let scrap_row = frm.add_child('cutting_plan_scrap_transfer');
//             scrap_row.item_code = detail_row.item_code;
//             scrap_row.scrap_qty = detail_row.scrap_qty;
//             scrap_row.batch = detail_row.batch;
            
//             // Get UOM from item or use the one from detail row
//             if (detail_row.uom) {
//                 scrap_row.uom = detail_row.uom;
//             } else {
//                 // Fetch UOM from Item master
//                 frappe.db.get_value('Item', detail_row.item_code, 'stock_uom')
//                     .then(r => {
//                         if (r.message && r.message.stock_uom) {
//                             frappe.model.set_value('Cutting Plan Scrap Transfer', scrap_row.name, 'uom', r.message.stock_uom);
//                         }
//                     });
//             }
            
//             // Set basic rate if available
//             if (detail_row.basic_rate) {
//                 scrap_row.basic_rate = detail_row.basic_rate;
//             }
            
//             // Set default scrap warehouse if available in form
//             if (frm.doc.default_scrap_warehouse) {
//                 scrap_row.target_scrap_warehouse = frm.doc.default_scrap_warehouse;
//             }
//         }
//     });
    
//     // Refresh the scrap transfer table
//     frm.refresh_field('cutting_plan_scrap_transfer');
// }

// Function to auto-fill scrap transfer table - without batchwise
function auto_fill_scrap_transfer_table(frm) {
    let scrap_qty = flt(frm.doc.total_qty) - flt(frm.doc.cut_plan_total_qty);
    
    // If table exists and has data
    if (frm.doc.cutting_plan_scrap_transfer && frm.doc.cutting_plan_scrap_transfer.length > 0) {
        // Check if user has entered item_code or target_warehouse
        let first_row = frm.doc.cutting_plan_scrap_transfer[0];
        let has_user_data = first_row.item_code || first_row.target_warehouse;
        
        if (has_user_data) {
            // PRESERVE user data, only update scrap_qty
            first_row.scrap_qty = scrap_qty;
            frm.refresh_field('cutting_plan_scrap_transfer');
            console.log("Updated scrap_qty to:", scrap_qty, "while preserving user data");
            return;
        } else {
            // No user data, safe to recreate
            frm.clear_table('cutting_plan_scrap_transfer');
        }
    } else {
        // Table is empty, clear it anyway (safety)
        frm.clear_table('cutting_plan_scrap_transfer');
    }
    
    // Create new row only if scrap_qty > 0
    if (scrap_qty > 0) {
        let scrap_row = frm.add_child('cutting_plan_scrap_transfer');
        scrap_row.scrap_qty = scrap_qty;
        console.log("Created new scrap row with qty:", scrap_qty);
    }
    
    frm.refresh_field('cutting_plan_scrap_transfer');
}

// Function to set batch filter for cutting plan detail table
function set_batch_filter_for_cutting_plan(frm, cdt, cdn) {
    // Set the query filter for batch field
    console.log("Setting batch filter for cutting plan detail...");
    frm.set_query('batch', 'cut_plan_detail', function(doc, cdt, cdn) {
        const child = locals[cdt][cdn];
        
        return {
            query: "madhav.api.get_cutting_plan_batches",
            filters: {
                item_code: child.item_code,
                warehouse: child.source_warehouse,
                include_expired: 1,
                supplier_name: child.supplier_name
            }
        };
    });
}

// Function to setup FG item filter for cutting plan finish table
function setup_fg_item_filter(frm) {
    // Get all work order references from cut_plan_detail
    let work_order_references = [];
    if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
        frm.doc.cut_plan_detail.forEach(function(row) {
            if (row.work_order_reference && !work_order_references.includes(row.work_order_reference)) {
                work_order_references.push(row.work_order_reference);
            }
        });
    }
    
    if (work_order_references.length > 0) {
        // Get production items from these work orders
        frappe.call({
            method: 'madhav.api.get_production_items_from_work_orders',
            args: {
                work_orders: work_order_references
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    // r.message is a list of { fg_item, work_order_reference }
                    const pairs = r.message || [];
                    const fgItems = pairs.map(p => p.fg_item).filter(Boolean);
                    const map = {};
                    pairs.forEach(p => { if (p.fg_item) { map[p.fg_item] = p.work_order_reference; } });

                    // Store available items and mapping for use in other handlers
                    frm.doc.available_fg_items = fgItems;
                    frm.__fg_item_to_wo = map;
                    
                    // Set FG item filter
                    frm.set_query('fg_item', 'cutting_plan_finish', function(doc, cdt, cdn) {
                        return {
                            filters: {
                                'name': ['in', fgItems]
                            }
                        };
                    });
                    
                    // Auto-fill if only one production item
                    if (fgItems.length === 1) {
                        // Auto-fill existing rows
                        if (frm.doc.cutting_plan_finish && frm.doc.cutting_plan_finish.length > 0) {
                            frm.doc.cutting_plan_finish.forEach(function(row) {
                                if (!row.fg_item) {
                                    frappe.model.set_value('Cutting Plan Finish', row.name, 'fg_item', fgItems[0]);
                                    const wo = map[fgItems[0]];
                                    if (wo) {
                                        frappe.model.set_value('Cutting Plan Finish', row.name, 'work_order_reference', wo);
                                    }
                                }
                            });
                        }
                        
                        // Set default for new rows
                        frm.set_df_property('fg_item', 'cutting_plan_finish', 'default', fgItems[0]);
                        
                        frappe.show_alert({
                            message: __('FG Item auto-filled: ' + fgItems[0]),
                            indicator: 'blue'
                        });
                    }
                    
                    frm.refresh_field('cutting_plan_finish');
                }
            }
        });
    } else {
        // If no work orders in cut_plan_detail, show message
        frm.set_query('fg_item', 'cutting_plan_finish', function(doc, cdt, cdn) {
            frappe.msgprint('Please add work orders in RM Detail section first');
            return {
                filters: {
                    'name': 'no_work_orders_available'
                }
            };
        });
    }
}

// Real-time validation for Cutting Plan Finish constraints
function validate_cutting_plan_finish_row_constraints(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let semi = flt(row.semi_fg_length);
    let count = cint(row.no_of_length_sizes);
    if (!semi || !count) {
        return;
    }

    // Constraint 1: semi_fg_length <= 27
    if (semi > 27) {
        frappe.msgprint(__('Semi-FG Length must be less than or equal to 27.'));
        // frappe.model.set_value(cdt, cdn, 'semi_fg_length', '');
        return;
    }

    // Constraint 2: sum(length_size_1..n) < semi_fg_length
    let total = 0.0;
    for (let i = 1; i <= Math.min(count, 5); i++) {
        let val = flt(row['length_size_' + i] || 0);
        total += val;
    }
	// Allow equality; only error when total is strictly greater than semi (rounded to 3 dp)
	const precision = 3;
	const totalRounded = flt(total, precision);
	const semiRounded = flt(semi, precision);
	if (totalRounded > semiRounded) {
		frappe.msgprint(__('Sum of Length Sizes must be less than Semi-FG Length.'));
        // Try to clear the last edited length_size if possible
        if (frm.__last_edited_length_field && frm.__last_edited_length_row === row.name) {
            frappe.model.set_value(cdt, cdn, frm.__last_edited_length_field, '');
        } else {
            // fallback: clear length_size_1
            frappe.model.set_value(cdt, cdn, 'length_size_1', '');
        }
    }
}
