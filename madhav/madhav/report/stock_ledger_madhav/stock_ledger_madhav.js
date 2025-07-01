frappe.query_reports["Stock Ledger Madhav"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return {
					filters: { company: company },
				};
			},
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: function () {
				return {
					query: "erpnext.controllers.queries.item_query",
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
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
			on_change() {
				const batch_no = frappe.query_report.get_filter_value("batch_no");
				if (batch_no) {
					frappe.query_report.set_filter_value("segregate_serial_batch_bundle", 1);
				} else {
					frappe.query_report.set_filter_value("segregate_serial_batch_bundle", 0);
				}
			},
		},
		{
			"fieldname": "batch_group",
			"label": __("Batch Group"),
			"fieldtype": "Link",
			"options": "Batch Group", // Replace with your actual Batch Group doctype name
			
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher #"),
			fieldtype: "Data",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "include_uom",
			label: __("Include UOM"),
			fieldtype: "Link",
			options: "UOM",
		},
		{
			fieldname: "valuation_field_type",
			label: __("Valuation Field Type"),
			fieldtype: "Select",
			width: "80",
			options: "Currency\nFloat",
			default: "Currency",
		},
		{
			fieldname: "segregate_serial_batch_bundle",
			label: __("Segregate Serial / Batch Bundle"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname == "out_qty" && data && data.out_qty < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		} else if (column.fieldname == "in_qty" && data && data.in_qty > 0) {
			value = "<span style='color:green'>" + value + "</span>";
		}else if (column.fieldname == "out_qty_pieces" && data && data.out_qty_pieces < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		}else if (column.fieldname == "in_qty_pieces" && data && data.in_qty_pieces > 0) {
			value = "<span style='color:green'>" + value + "</span>";
		}

		return value;
	},
};

function view_batchwise_report(item_code, filter_company, from_date, to_date, batch_no) {
	let fiscal_year = erpnext.utils.get_fiscal_year(frappe.datetime.get_today());

	frappe.db.get_value("Fiscal Year", { "name": fiscal_year }, "year_start_date", function (value) {
		const base_url = window.location.origin;
		const query_string = 
			`company=${encodeURIComponent(filter_company)}` +
			`&from_date=${value.year_start_date}` +
			`&to_date=${to_date}` +
			`&item_code=${encodeURIComponent(item_code)}` +
			`&batch_no=${encodeURIComponent(batch_no)}`;

		const url = `${base_url}/app/query-report/Batch Wise Stock Balance?${query_string}`;
		window.open(url, "_blank");
	});
}

erpnext.utils.add_inventory_dimensions("Stock Stock Ledger Madhav", 10);
