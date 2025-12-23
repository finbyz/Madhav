// Copyright (c) 2025, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Dispatch Details"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "delivery_note",
            label: __("Delivery Note"),
            fieldtype: "Link",
            options: "Delivery Note"
        }
    ]
};
