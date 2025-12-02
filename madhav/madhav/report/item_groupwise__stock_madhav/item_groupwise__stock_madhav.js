frappe.query_reports["Item Groupwise  Stock Madhav"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname":"warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"get_query": function() {
				const company = frappe.query_report.get_filter_value('company');
				return { 
					filters: { 'company': company }
				}
			}
		},
		{
			"fieldname":"show_0_qty_inventory",
			"label": __("Show 0 Qty Inventory"),
			"fieldtype": "Check",				
		},
	],
	"tree": true,
	"name_field": "item_group",
	"parent_field": "parent_item_group",
	"initial_depth": 1,
	"formatter": function(value, row, column, data, default_formatter) {
		if (column.fieldname=="item_group") {
			value = data.item_group || value;

			column.link_onclick =
				"erpnext.financial_statements.open_general_ledger(" + JSON.stringify(data) + ")";
			column.is_tree = true;
		}
		value = default_formatter(value, row, column, data);

		if (!data.parent_item_group) {
			value = $(`<span>${value}</span>`);

			var $value = $(value).css("font-weight", "bold");
			if (data.warn_if_negative && data[column.fieldname] < 0) {
				$value.addClass("text-danger");
			}

			value = $value.wrap("<p></p>").parent().html();
		}
		
		if (column.fieldname == "balance_qty" && data && data.balance_qty < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		}
		if (column.fieldname == "balance_value" && data && data.balance_value < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		}

		return value;
	},
}

// Route to Stock Ledger for Item Group
function route_to_sle(company, warehouse, item_group) {
	const base_url = window.location.origin;
	let url = `${base_url}/app/query-report/Stock Ledger?company=${encodeURIComponent(company)}&item_group=${encodeURIComponent(item_group)}`;
	
	if (warehouse) {
		url += `&warehouse=${encodeURIComponent(warehouse)}`;
	}
	
	window.open(url, "_blank");
}

// Route to Stock Ledger for Item
function route_to_sle_item(company, warehouse, item_name) {
	const base_url = window.location.origin;
	let url = `${base_url}/app/query-report/Stock Ledger?company=${encodeURIComponent(company)}&item_code=${encodeURIComponent(item_name)}`;
	
	if (warehouse) {
		url += `&warehouse=${encodeURIComponent(warehouse)}`;
	}
	
	window.open(url, "_blank");
}

// Route to Stock Balance for Item Group
function route_to_stock_balance(company, warehouse, item_group) {
	const base_url = window.location.origin;
	let url = `${base_url}/app/query-report/Stock Balance?company=${encodeURIComponent(company)}&show_warehouse_wise_balance=1&item_group=${encodeURIComponent(item_group)}`;
	
	if (warehouse) {
		url += `&warehouse=${encodeURIComponent(warehouse)}`;
	}
	
	window.open(url, "_blank");
}

// Route to Stock Balance for Item
function route_to_stock_balance_item(company, warehouse, item_name) {
	const base_url = window.location.origin;
	let url = `${base_url}/app/query-report/Stock Balance?company=${encodeURIComponent(company)}&show_warehouse_wise_balance=1&item_code=${encodeURIComponent(item_name)}`;
	
	if (warehouse) {
		url += `&warehouse=${encodeURIComponent(warehouse)}`;
	}
	
	window.open(url, "_blank");
}

// Route to Monthly Stock Summary for Item Group
function route_to_monthly_stock_balance(company, item_group) {
	const base_url = window.location.origin;
	const url = `${base_url}/app/query-report/Monthly Stock Summary?company=${encodeURIComponent(company)}&item_group=${encodeURIComponent(item_group)}`;
	window.open(url, "_blank");
}

// Route to Monthly Stock Summary for Item
function route_to_monthly_stock_balance_item(company, item_name) {
	const base_url = window.location.origin;
	const url = `${base_url}/app/query-report/Monthly Stock Summary?company=${encodeURIComponent(company)}&item_code=${encodeURIComponent(item_name)}`;
	window.open(url, "_blank");
}