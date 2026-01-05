// Copyright (c) 2026, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["PO Sheet"] = {
    "filters": [
        {
            fieldname: "sales_order",
            label: __("Sales Order"),
            fieldtype: "Link",
            options: "Sales Order"
        },

        {
            fieldname: "from_date",
            label: __("From Delivery Date"),
            fieldtype: "Date"
        },

        {
            fieldname: "to_date",
            label: __("To Delivery Date"),
            fieldtype: "Date"
        },

        {
            fieldname: "party_name",
            label: __("Party Name"),
            fieldtype: "Link",
            options: "Customer"
        }
    ]
};
