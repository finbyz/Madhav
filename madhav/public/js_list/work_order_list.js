frappe.listview_settings["Work Order"] = {
	add_fields: [
		"bom_no",
		"status",
		"sales_order",
		"qty",
		"produced_qty",
		"expected_delivery_date",
		"planned_start_date",
		"planned_end_date",
	],

	filters: [["status", "!=", "Stopped"]],

	get_indicator: function (doc) {
		if (doc.status === "Submitted") {
			return [__("Not Started"), "orange", "status,=,Submitted"];
		}

		return [
			__(doc.status),
			{
				Draft: "red",
				Stopped: "red",
				"Not Started": "red",
				"In Process": "orange",
				Completed: "green",
				Closed: "gray",
				Cancelled: "gray",
			}[doc.status],
			"status,=," + doc.status,
		];
	},

	refresh(listview) {
		// Prevent duplicate action on every refresh
		if (listview.close_action_added) return;
		listview.close_action_added = true;

		listview.page.add_action_item(__("Close"), () => {
			const selected = listview.get_checked_items();

			if (!selected.length) {
				frappe.msgprint(__("Please select at least one Work Order."));
				return;
			}

			frappe.confirm(
				__("Once the Work Order is Closed. It can't be resumed."),
				async () => {
					for (const row of selected) {
						await frappe.call({
							method: "erpnext.manufacturing.doctype.work_order.work_order.stop_unstop",
							args: {
								work_order: row.name,
                                "status": "Closed"
							},
							freeze: true,
							freeze_message: __("Updating Work Order status"),
						});
					}

					frappe.show_alert({
						message: __("Selected Work Orders have been closed."),
						indicator: "green",
					});

					listview.refresh();
				}
			);
		});
	},
};