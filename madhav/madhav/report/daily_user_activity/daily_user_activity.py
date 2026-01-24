import json
import frappe
from frappe.utils import escape_html

def execute(filters=None):
    filters = filters or {}

    target_user = filters.get("user")
    target_date = filters.get("to_date")

    data = []

    doctypes = frappe.get_all(
        "DocType",
        filters={
            "issingle": 0,
            "istable": 0   # skip child tables
        },
        pluck="name"
    )
    
    if target_date:
        start = f"{target_date} 00:00:00"
        end = f"{target_date} 23:59:59"

    for dt in doctypes:
        table = f"`tab{dt}`"

        conditions = []
        values = {}

        if target_user:
            conditions.append("owner = %(user)s")
            values["user"] = target_user

        if target_date:
            conditions.append("creation BETWEEN %(start)s AND %(end)s")
            values["start"] = start
            values["end"] = end

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        try:
            rows = frappe.db.sql(
                f"""
                SELECT
                    '{dt}' AS ref_doctype,
                    name AS docname,
                    owner,
                    creation
                FROM {table}
                {where_clause}
                ORDER BY creation DESC
                """,
                values,
                as_dict=True
            )

            for row in rows:
                row["open_doc"] = f"""
                <a class="btn btn-xs btn-primary"
                   href="/app/{frappe.scrub(row['ref_doctype'])}/{row['docname']}"
                   target="_blank"
                   style="padding:1px 6px;font-size:13px;line-height:20px;height:20px;">
                   Open
                </a>
                """
                if row["ref_doctype"] == "Version":
                    row["activity_type"] = "Modified"
                else:
                    row["activity_type"] = "Created"

            data.extend(rows)

        except Exception:
            # Skip system/virtual tables
            pass

    columns = [
        {
            "label": "User",
            "fieldname": "owner",
            "fieldtype": "Link",
            "options": "User",
            "width": 150,
        },
        {
            "label": "DocType",
            "fieldname": "ref_doctype",
            "fieldtype": "Link",
            "options": "DocType",
            "width": 250,
        },
        {
            "label": "Document",
            "fieldname": "docname",
            "fieldtype": "Dynamic Link",
            "options": "ref_doctype",
            "width": 250,
        },
        {
            "label": "Activity",
            "fieldname": "activity_type",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": "Creation",
            "fieldname": "creation",
            "fieldtype": "Datetime",
            "width": 150,
        },
        # {
        #     "label": "View",
        #     "fieldname": "open_doc",
        #     "fieldtype": "HTML",
        #     "width": 100,
        # },
    ]

    return columns, data


import json

def get_non_empty_list_names(data):
    if not data:
        return ""

    # Version.data comes as JSON string → convert
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return ""

    if not isinstance(data, dict):
        return ""

    result = []
    for key, value in data.items():
        if isinstance(value, list) and value:
            result.append(key)

    return ", ".join(result)


import frappe
import json
from frappe.utils import escape_html

def render_version_data(data):
    """
    Render version JSON data into an HTML table for the Timeline.
    """
    if not data:
        return ""

    # Parse JSON if it is a string
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return ""

    html = []
    
    # Map DocStatus for readability
    docstatus_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    # ---------------------------------------
    # 1. Main Field Changes
    # ---------------------------------------
    if data.get("changed"):
        html.append("""
            <h6 class="uppercase mb-2 text-muted">Changed Values</h6>
            <table class="table table-bordered table-sm table-condensed">
                <thead>
                    <tr class="active">
                        <th width="30%">Field</th>
                        <th width="35%">Old Value</th>
                        <th width="35%">New Value</th>
                    </tr>
                </thead>
                <tbody>
        """)

        for field, old_val, new_val in data["changed"]:
            # Handle Docstatus integers
            if field == "docstatus":
                old_val = docstatus_map.get(old_val, old_val)
                new_val = docstatus_map.get(new_val, new_val)

            html.append(f"""
                <tr>
                    <td>{escape_html(str(field))}</td>
                    <td class="text-danger">{escape_html(str(old_val)) if old_val is not None else ""}</td>
                    <td class="text-success">{escape_html(str(new_val)) if new_val is not None else ""}</td>
                </tr>
            """)
        
        html.append("</tbody></table>")

    # ---------------------------------------
    # 2. Rows Added
    # ---------------------------------------
    if data.get("added"):
        # FIXED: Used single quotes for the string wrapper to allow double quotes for HTML classes
        html.append('<h6 class="uppercase mt-3 mb-2 text-muted">Rows Added</h6>')
        
        for table_field, row in data["added"]:
            html.append(f"""
                <div class="border rounded p-2 mb-2 bg-light">
                    <strong>{escape_html(table_field)}</strong>
                    <table class="table table-sm mt-1 mb-0">
            """)
            for k, v in row.items():
                if k not in ("name", "owner", "creation", "modified", "docstatus", "parent", "parenttype", "parentfield", "doctype"):
                    html.append(f"<tr><td width='40%'>{escape_html(k)}</td><td>{escape_html(str(v))}</td></tr>")
            html.append("</table></div>")

    # ---------------------------------------
    # 3. Rows Removed
    # ---------------------------------------
    if data.get("removed"):
        # FIXED: Used single quotes
        html.append('<h6 class="uppercase mt-3 mb-2 text-muted">Rows Removed</h6>')
        
        for table_field, row in data["removed"]:
            html.append(f"""
                <div class="border rounded p-2 mb-2 bg-light">
                    <strong>{escape_html(table_field)}</strong>
                    <table class="table table-sm mt-1 mb-0">
            """)
            for k, v in row.items():
                if k not in ("name", "owner", "creation", "modified", "docstatus", "parent", "parenttype", "parentfield", "doctype"):
                    html.append(f"<tr><td width='40%'>{escape_html(k)}</td><td>{escape_html(str(v))}</td></tr>")
            html.append("</table></div>")

   # ---------------------------------------
    # 4. Rows Changed (Edits inside tables)
    # ---------------------------------------
    if data.get("row_changed"):
        html.append('<h6 class="uppercase mt-3 mb-2 text-muted">Rows Updated</h6>')
        
        # FIXED: Iterate over 'item' and extract indices manually to avoid unpacking errors
        for item in data["row_changed"]:
            # Ensure we have at least 3 elements
            if len(item) < 3:
                continue
                
            table_field = item[0]
            row_name = item[1]
            changes = item[2]
            
            html.append(f"""
                <div class="border rounded p-2 mb-2 bg-light">
                    <strong>{escape_html(table_field)}</strong> <span class="text-muted">({row_name})</span>
                    <table class="table table-bordered table-sm mt-1 mb-0 bg-white">
                        <thead><tr class="active"><th>Field</th><th>Old</th><th>New</th></tr></thead>
                        <tbody>
            """)
            
            for change_row in changes:
                # Ensure change_row also has 3 elements [field, old, new]
                if len(change_row) < 3:
                    continue
                    
                field, old_val, new_val = change_row[0], change_row[1], change_row[2]

                html.append(f"""
                    <tr>
                        <td>{escape_html(str(field))}</td>
                        <td class="text-danger">{escape_html(str(old_val)) if old_val is not None else ""}</td>
                        <td class="text-success">{escape_html(str(new_val)) if new_val is not None else ""}</td>
                    </tr>
                """)
            html.append("</tbody></table></div>")

    return "".join(html)