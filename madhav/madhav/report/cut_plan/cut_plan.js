// Copyright (c) 2025, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Cut Plan"] = {
	"filters":  [
        {
            fieldname: "date",
            label: __("Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "cutting_plan",
            label: __("Cutting Plan"),
            fieldtype: "Link",
            options: "Cutting Plan"
        }
    ]
};
