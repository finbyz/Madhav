frappe.query_reports["Production Plan"] = {
    filters: [
        {
            fieldname: "production_plan",
            label: "Production Plan",
            fieldtype: "Link",
            options: "Production Plan"
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date"
        }
    ]
};
