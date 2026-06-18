// Copyright (c) 2026, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["PO Sheet"] = {
    "filters": [
        {   fieldname: "type",
            "label": __("Type"),
            "fieldtype": "Select",
            "options": ["", "Trading", "Manufacturing"],
            "default": "Manufacturing",
        },
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
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Customer", txt);
            }
        },

        {
            fieldname: "item_code",
            label: __("Item"),
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Item", txt);
            }
        },
        {
            fieldname: "po_no",
            label: __("PO No"),
            fieldtype: "Data"
        }
    ]
};