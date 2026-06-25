frappe.ui.form.on('Material Request', {
    validate(frm) {
        if (frm.doc.company === "MADHAV UDYOG PRIVATE LIMITED") {
            frm.set_value("naming_series", "MUMR.YY.-");
        } else if (frm.doc.company === "MADHAV STELCO PRIVATE LIMITED") {
            frm.set_value("naming_series", "MSMR.YY.-");
        } 
	},
	cost_center: function (frm) {
        update_items_fields(frm);
    },
    branch: function (frm) {
        update_items_fields(frm);
    },
	validate: function(frm) {
		update_items_fields(frm);
	},
	refresh: function(frm){
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Sales Order"),
				() => frm.events.get_items_from_sales_order(frm),
				__("Get Items From")
			);
		}
	},
	get_items_from_sales_order: function (frm) {
		let opts = {
			method: "madhav.doc_events.material_request.make_material_request",
			source_doctype: "Sales Order",
			target: frm,
			allow_child_item_selection: 1,
			child_fieldname: "items",
			child_columns: [
				"item_code",
				"item_name",
				"qty",
				"uom",
				"rate",
				"length_size",
				"pieces",
				"assorted_length",
				"delivery_date"
			],
			setters: {
				customer: frm.doc.customer || undefined,
				delivery_date: undefined,
			},
			get_query_filters: {
				docstatus: 1,
				status: ["not in", ["Closed", "On Hold"]],
				per_delivered: ["<", 99.99],
				company: frm.doc.company,
			},
		};

		// Build the query args same as standard map_current_doc
		let query_args = {};
		if (opts.get_query_filters) {
			query_args.filters = opts.get_query_filters;
		}
		if (opts.get_query_method) {
			query_args.query = opts.get_query_method;
		}
		if (query_args.filters || query_args.query) {
			opts.get_query = () => query_args;
		}

		// Create the dialog manually so we can override the action
		const d = new frappe.ui.form.MultiSelectDialog({
			doctype: opts.source_doctype,
			target: opts.target,
			date_field: opts.date_field || undefined,
			setters: opts.setters,
			get_query: opts.get_query,
			add_filters_group: 1,
			allow_child_item_selection: opts.allow_child_item_selection,
			child_fieldname: opts.child_fieldname,
			child_columns: opts.child_columns,
			size: opts.size,
			action: function(selections, args) {
				let values = selections;
				if (values.length === 0) {
					frappe.msgprint(__("Please select {0}", [opts.source_doctype]));
					return;
				}

				// Capture filter criteria from the dialog's filter area
				let filter_criteria = {};
				if (d.filter_area && d.filter_area.filter_list) {
					d.filter_area.filter_list.get_filters().forEach(f => {
						// f = [fieldname, condition, value, doctype]
						if (f[0] && f[2] !== undefined && f[2] !== "") {
							filter_criteria[f[0]] = {
								condition: f[1],
								value: f[2]
							};
						}
					});
				}

				// Build args to pass to server
				let call_args = {
					"method": opts.method,
					"source_names": values,
					"target_doc": cur_frm.doc,
					"args": {
						filtered_children: args ? args.filtered_children : [],
						filter_criteria: filter_criteria
					}
				};

				d.dialog.hide();

				// Call the mapper directly (same as _map in standard code)
				frappe.call({
					type: "POST",
					method: 'frappe.model.mapper.map_docs',
					args: call_args,
					callback: function(r) {
						if (!r.exc) {
							frappe.model.sync(r.message);
							cur_frm.dirty();
							cur_frm.refresh();
						}
					}
				});
			},
		});

		return d;
	},
})

function update_items_fields(frm) {
    if (!frm.doc.items) return;

    frm.doc.items.forEach(row => {

        if (frm.doc.cost_center) {
            frappe.model.set_value(row.doctype, row.name, "cost_center", frm.doc.cost_center);
        }

        if (frm.doc.branch) {
            frappe.model.set_value(row.doctype, row.name, "branch", frm.doc.branch);
        }

    });

    frm.refresh_field('items');
}

frappe.ui.form.on('Material Request Item', {
	qty: function (frm,cdt,cdn) {
		console.log("chekcing for MR................")
		let d = locals[cdt][cdn];
		frappe.db.get_value("Stock Settings", 'Stock Settings','calculate_conversion_factor_based_on_stock_quantity_and_quantity', function (r) {
			if (cint(r.calculate_conversion_factor_based_on_stock_quantity_and_quantity) == 1) {
				if(d.qty > 0){
					frappe.model.set_value(cdt, cdn, "conversion_factor", flt(d.stock_qty/d.qty));
				}
			}
		});
	},
	stock_qty: function (frm,cdt,cdn) {
		let d = locals[cdt][cdn];
		frappe.db.get_value("Stock Settings", 'Stock Settings','calculate_conversion_factor_based_on_stock_quantity_and_quantity', function (r) {
			if (cint(r.calculate_conversion_factor_based_on_stock_quantity_and_quantity) == 1) {
				if(d.qty > 0){
					frappe.model.set_value(cdt, cdn, "conversion_factor", flt(d.stock_qty/d.qty));
				}
			}
		});
	},
});