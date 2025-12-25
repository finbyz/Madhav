frappe.query_reports["Production Plan"] = {
    filters: [
        {
            fieldname: "production_plan",
            label: "Production Plan",
            fieldtype: "Link",
            options: "Production Plan",
            reqd: 1
        }
    ]
};
