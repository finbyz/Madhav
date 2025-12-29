frappe.ui.form.on('Purchase Receipt', {
    company: function(frm) {
        set_series(frm);
    },
    is_return: function(frm) {
        set_series(frm);
    },
    onload: function(frm) {
        set_series(frm);
        check_supplier_series_and_toggle_fields(frm);
    },
    supplier: function(frm) {
        check_supplier_series_and_toggle_fields(frm);
    }
});

function check_supplier_series_and_toggle_fields(frm) {
    if (!frm.doc.supplier) return;

    // Take first 3 letters of the supplier ID
    const prefix = frm.doc.supplier.substring(0, 3).toUpperCase();
    console.log("checking supplier prefix...", prefix);

    if (prefix === "RAW") {
        console.log("yes it's RAW");
        frm.set_df_property('weight_demand', 'hidden', 0);
        frm.set_df_property('weight_received', 'hidden', 0);
        frm.set_df_property('total_length_in_meter', 'hidden', 0);
    } else {
        console.log("not RAW");
        frm.set_df_property('weight_demand', 'hidden', 1);
        frm.set_df_property('weight_received', 'hidden', 1);
        frm.set_df_property('total_length_in_meter', 'hidden', 1);
    }

    frm.refresh_fields(['weight_demand', 'weight_received', 'total_length_in_meter']);
}

// function set_series(frm) {
//     if (!frm.is_new()) return; // Don't change if not new

//     if (frm.doc.company === "MADHAV UDYOG PRIVATE LIMITED") {
//         if (frm.doc.is_return) {
//             frm.set_value('naming_series', 'MURPR.YY.-');
//         } else {
//             frm.set_value('naming_series', 'MUPR.YY.-');
//         }
//     } else if (frm.doc.company === "MADHAV STELCO PRIVATE LIMITED") {
//         if (frm.doc.is_return) {
//             frm.set_value('naming_series', 'MSRPR.YY.-');
//         } else {
//             frm.set_value('naming_series', 'MSPR.YY.-');
//         }
//     }
// }

// frappe.ui.form.on('Purchase Receipt Item', {
//     pieces: function (frm, cdt, cdn) {
//         calculate_total_length(frm);
//     },
//     average_length: function (frm, cdt, cdn) {
//         calculate_total_length(frm);
//     },
//     items_remove: function (frm, cdt, cdn) {
//         calculate_total_length(frm);
//     }
// });

// function calculate_total_length(frm) {
//     let total = 0;
//     frm.doc.items.forEach(item => {
//         let pieces = flt(item.pieces);
//         let avg_len = flt(item.average_length);
//         if (pieces && avg_len) {
//             total += pieces * avg_len;
//         }
//     });
//     frm.set_value('total_length_in_meter', total);
// }

frappe.ui.form.on('Purchase Receipt Item', {
    pieces: function (frm, cdt, cdn) {
        update_totals(frm);
    },
    average_length: function (frm, cdt, cdn) {
        update_totals(frm);
    },
    rejected_qty: function (frm, cdt, cdn) {
        update_totals(frm);
    },
    items_remove: function (frm, cdt, cdn) {
        update_totals(frm);
    }
});

frappe.ui.form.on('Purchase Receipt', {
    weight_received: function(frm) {
        update_totals(frm);
    }
});

function update_totals(frm) {
    let total_length = 0;

    // Step 1: Calculate total_length_in_meter
    frm.doc.items.forEach(item => {
        let pieces = flt(item.pieces);
        let avg_len = flt(item.average_length);

        if (pieces && avg_len) {
            total_length += pieces * avg_len;
        }
    });

    frm.set_value("total_length_in_meter", total_length.toFixed(2));

    // Step 2: Calculate section_weight from weight_received (in tonnes → kg)
    let weight_received = flt(frm.doc.weight_received);  // in tonnes
    let weight_received_kg = weight_received * 1000;

    let section_weight = total_length > 0 ? weight_received_kg / total_length : 0;

    // Step 3: Update each row
    frm.doc.items.forEach(item => {
        let pieces = flt(item.pieces);
        let avg_len = flt(item.average_length);

        // Calculate accepted_qty and set values
        item.section_weight = section_weight.toFixed(2);

        let accepted_qty_kg = pieces * avg_len * section_weight;
        item.qty = (accepted_qty_kg / 1000).toFixed(4); // in tonnes

        item.received_qty = flt(item.qty) + flt(item.rejected_qty);
    });

    frm.refresh_field("items");
}


