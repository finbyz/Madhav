frappe.query_reports["Batch Wise Stock Balance"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
			get_query: function () {
				return {
					filters: {
						has_batch_no: 1,
					},
				};
			},
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},		
		{
			fieldname: "warehouse_type",
			label: __("Warehouse Type"),
			fieldtype: "Link",
			width: "80",
			options: "Warehouse Type",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				let warehouse_type = frappe.query_report.get_filter_value("warehouse_type");
				let company = frappe.query_report.get_filter_value("company");
				return {
					filters: {
						...(warehouse_type && { warehouse_type }),
						...(company && { company }),
					},
				};
			},
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
			get_query: function () {
				let item_code = frappe.query_report.get_filter_value("item_code");
				return {
					filters: {
						item: item_code,
					},
				};
			},
		},
		{
			"fieldname": "batch_group",
			"label": __("Batch Group"),
			"fieldtype": "Link",
			"options": "Batch Group", // Replace with your actual Batch Group doctype name
			
		},
	],
	set_batch_route_to_stock_ledger: function (data) {
		frappe.route_options = {
			batch_no: data["Batch"],
		};
		frappe.set_route("query-report", "Stock Ledger Madhav");
	},
};
function view_stock_ledger_report(item_code, filter_company, from_date, to_date, batch_no) {
	let fiscal_year = erpnext.utils.get_fiscal_year(frappe.datetime.get_today());

	frappe.db.get_value("Fiscal Year", { "name": fiscal_year }, "year_start_date", function (value) {
		const base_url = window.location.origin;
		const query_string = 
			`company=${encodeURIComponent(filter_company)}` +
			`&from_date=${value.year_start_date}` +
			`&to_date=${to_date}` +
			`&item_code=${encodeURIComponent(item_code)}` +
			`&batch_no=${encodeURIComponent(batch_no)}`+
			`&segregate_serial_batch_bundle=0`;

		const url = `${base_url}/app/query-report/Stock Ledger Madhav?${query_string}`;
		window.open(url, "_blank");
	});
}
