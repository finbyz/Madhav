frappe.ui.form.on('Cutting Plan', {
    refresh: function(frm) {

        // Disable add/remove rows in scrap_transfer child table
        frm.fields_dict["cutting_plan_scrap_transfer"].grid.cannot_add_rows = true;
        frm.fields_dict["cutting_plan_scrap_transfer"].grid.only_sortable = true;
        frm.fields_dict["cutting_plan_scrap_transfer"].refresh();

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
                    filters: {
                        'item': row.item_code,
                        'disabled': 0
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

        // Add button to auto-fill scrap transfer table
        if (!frm.is_new()) {
            frm.add_custom_button(__('Auto Fill Scrap Transfer'), function() {
                auto_fill_scrap_transfer_table(frm);
            }, __('Actions'));
        }
    }
});

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
        update_scrap_qty_for_all_batches(frm);  
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

    // Step 1: Calculate total_length_in_meter
    frm.doc.cut_plan_detail.forEach(item => {
        let qty = flt(item.qty);
        let basic_amount = flt(item.basic_amount);

        if (qty) {
            total_qty += qty;
        }
        if (basic_amount) {
            total_amount += basic_amount;
        }

    });

    frm.set_value("total_qty", total_qty.toFixed(2));
    frm.set_value("amount", total_amount.toFixed(2));

}

frappe.ui.form.on('Cutting Plan Finish', {
    pieces: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Validate batch quantity after qty calculation
        validate_batch_qty_consumption(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    length_size: function (frm, cdt, cdn) {
        calculate_qty(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Validate batch quantity after qty calculation
        validate_batch_qty_consumption(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    cutting_plan_finish_remove: function(frm, cdt, cdn) {
        update_total_cut_plan_qty(frm, cdt, cdn);    
        // Update scrap quantity in RM Plan Detail
        update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },
    qty: function(frm, cdt, cdn) {
        // Validate batch quantity when qty is directly changed
        validate_batch_qty_consumption(frm, cdt, cdn);
        update_total_cut_plan_qty(frm, cdt, cdn);
        // Update scrap quantity in RM Plan Detail
        update_scrap_qty_for_all_batches(frm);
        // Auto-fill scrap transfer table
        auto_fill_scrap_transfer_table(frm);
    },

    // Add validation for RM reference batch
    rm_reference_batch: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let available_batches = [];
        
        // Get all batches from cut_plan_detail
        if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
            frm.doc.cut_plan_detail.forEach(function(detail_row) {
                if (detail_row.batch) {
                    available_batches.push(detail_row.batch);
                }
            });
        }
        
        // Validate if selected batch exists in cut_plan_detail
        if (row.rm_reference_batch && !available_batches.includes(row.rm_reference_batch)) {
            frappe.msgprint('Selected batch is not available in RM Detail For Cut Plan section');
            frappe.model.set_value(cdt, cdn, 'rm_reference_batch', '');
        } else if (row.rm_reference_batch) {
            // Auto-fill pieces and length_size from cut_plan_detail table
            if (frm.doc.cut_plan_detail && frm.doc.cut_plan_detail.length > 0) {
                frm.doc.cut_plan_detail.forEach(function(detail_row) {
                    if (detail_row.batch === row.rm_reference_batch) {
                        // Auto-fill pieces and length_size if they exist in cut_plan_detail
                        if (detail_row.pieces) {
                            frappe.model.set_value(cdt, cdn, 'pieces', detail_row.pieces);
                        }
                        if (detail_row.length_size) {
                            frappe.model.set_value(cdt, cdn, 'length_size', detail_row.length_size);
                        }
                        // If both pieces and length_size are available, calculate qty
                        if (detail_row.pieces && detail_row.length_size) {
                            // Let the calculate_qty function handle the calculation
                            // It will be triggered by the pieces and length_size field updates above
                        }
                        return false; // Break the loop once we find the matching batch
                    }
                });
            }
            
            // Validate quantity if qty is available after auto-fill
            if (row.qty) {
                validate_batch_qty_consumption(frm, cdt, cdn);
                // Update scrap quantity in RM Plan Detail
                update_scrap_qty_for_all_batches(frm);
                // Auto-fill scrap transfer table
                auto_fill_scrap_transfer_table(frm);
            }
        }
    }
});

function calculate_qty(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.pieces || !row.length_size){
          return;
    }
     let qty = row.pieces * row.length_size *row.section_weight;
     let qty_in_tonne = (qty/1000).toFixed(2);
     frappe.model.set_value(cdt, cdn, 'qty', qty_in_tonne);
}

function update_total_cut_plan_qty(frm, cdt, cdn){
    let total_cut_plan_qty = 0;

    frm.doc.cutting_plan_finish.forEach(item => {
        let qty = flt(item.qty);

        if (qty) {
            total_cut_plan_qty += qty;
        }
    });

    frm.set_value("cut_plan_total_qty", total_cut_plan_qty.toFixed(2));
}

// Function to validate batch quantity consumption
function validate_batch_qty_consumption(frm, cdt, cdn) {
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
    
    // Check if total quantity exceeds available quantity
    if (total_with_current > available_qty) {
        let remaining_qty = (available_qty - consumed_qty).toFixed(2);
        
        frappe.msgprint({
            title: 'Quantity Validation Error',
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

// Function to update scrap quantity for a specific batch
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

// Function to auto-fill scrap transfer table
function auto_fill_scrap_transfer_table(frm) {
    if (!frm.doc.cut_plan_detail || frm.doc.cut_plan_detail.length === 0) {
        return;
    }
    
    // Clear existing scrap transfer rows
    frm.clear_table('cutting_plan_scrap_transfer');
    
    // Get scrap items from RM Plan Detail
    frm.doc.cut_plan_detail.forEach(function(detail_row) {
        if (detail_row.item_code && detail_row.scrap_qty && flt(detail_row.scrap_qty) > 0) {
            // Add scrap transfer row
            let scrap_row = frm.add_child('cutting_plan_scrap_transfer');
            scrap_row.item_code = detail_row.item_code;
            scrap_row.scrap_qty = detail_row.scrap_qty;
            scrap_row.batch = detail_row.batch;
            
            // Get UOM from item or use the one from detail row
            if (detail_row.uom) {
                scrap_row.uom = detail_row.uom;
            } else {
                // Fetch UOM from Item master
                frappe.db.get_value('Item', detail_row.item_code, 'stock_uom')
                    .then(r => {
                        if (r.message && r.message.stock_uom) {
                            frappe.model.set_value('Cutting Plan Scrap Transfer', scrap_row.name, 'uom', r.message.stock_uom);
                        }
                    });
            }
            
            // Set basic rate if available
            if (detail_row.basic_rate) {
                scrap_row.basic_rate = detail_row.basic_rate;
            }
            
            // Set default scrap warehouse if available in form
            if (frm.doc.default_scrap_warehouse) {
                scrap_row.target_scrap_warehouse = frm.doc.default_scrap_warehouse;
            }
        }
    });
    
    // Refresh the scrap transfer table
    frm.refresh_field('cutting_plan_scrap_transfer');
}