import frappe
from frappe import _
from frappe.utils import get_url_to_form
from frappe.utils import flt
from erpnext.controllers.status_updater import OverAllowanceError


def validate_limit_on_save(self, method):
    """
    Ensure 'Limit Crossed' validation triggers on Save for Purchase Receipts.
    """
    if hasattr(self, "validate_qty"):
        try:
            self.validate_qty()
        except Exception:
            # If standard path raises, rethrow; otherwise continue to our explicit check.
            raise

    # Explicit PR-based check to ensure early error on Save
    # Use standard Stock Settings allowance for over receipt/delivery
    pr_qty_allowance = flt(frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance")) or 0.0

    for d in self.get("items") or []:
        pr_item = d.get("purchase_order_item")
        if not pr_item:
            continue

        # Fetch PR stock_qty reference
        pr_row = frappe.db.get_value(
            "Purchase Order Item",
            pr_item,
            ["parent", "item_code", "stock_qty"],
            as_dict=True,
        )
        if not pr_row:
            continue

        pr_stock_qty = flt(pr_row.get("stock_qty") or 0.0, d.precision("stock_qty"))
        if pr_stock_qty <= 0:
            continue

        # Sum already received qty across other PRs (draft + submitted), exclude this row
        already_received = frappe.db.sql(
            """
            select coalesce(sum(pri.stock_qty), 0)
            from `tabPurchase Receipt Item` pri
            join `tabPurchase Receipt` pr on pr.name = pri.parent
            where pri.purchase_order_item = %s
              and pr.docstatus < 2
              and not (pri.parent = %s)
            """,
            (pr_item, self.name or ""),
        )[0][0]

        # Proposed total including current row's qty
        proposed_total = flt(already_received) + flt(d.get("stock_qty") or 0.0)

        # Allowed with tolerance
        max_allowed = pr_stock_qty * (100.0 + pr_qty_allowance) / 100.0

        if proposed_total > max_allowed + 1e-9:
            reduce_by = proposed_total - max_allowed
            msg = _(
                "This document is over limit by {0} for item {1}. Are you making another {2} against the same {3}?"
            ).format(
                frappe.bold(flt(reduce_by, d.precision("stock_qty"))),
                frappe.bold(d.get("item_code")),
                frappe.bold(_("Purchase Receipt")),
                frappe.bold(_("Purchase Order")),
            )
            action_msg = _(
                'To allow over receipt / delivery, update "Over Receipt/Delivery Allowance" in Stock Settings or the Item.'
            )
            frappe.throw(msg + "<br><br>" + action_msg, OverAllowanceError, title=_("Limit Crossed"))

def round_off_stock_qty(self,method):
    return
    for item in self.items:
        if item.stock_qty:
            item.db_set("stock_qty", round(item.stock_qty))
            item.db_set("received_stock_qty", round(item.received_stock_qty))
            

def set_actual_rate_per_kg(self, method):
    """
    Set actual_rate_per_kg on Purchase Receipt Item 
    from its linked Purchase Order Item (before save).
    """
    for row in self.items:
        if row.purchase_order_item:
            rate_data = frappe.db.get_value(
                "Purchase Order Item",
                row.purchase_order_item,
                "actual_rate_per_kg",
                as_dict=True,
                # ignore_permissions ensures no permission error
            )

            if rate_data and rate_data.get("actual_rate_per_kg") is not None:
                row.rate_per_kg = rate_data.get("actual_rate_per_kg")

def create_qi(self,method):
    
    created_quality_inspections = []
    for row in self.items:
        
        # Skip if already linked
        if row.quality_inspection:
            continue
        
        if frappe.db.get_value("Item",row.item_code,"inspection_required_before_purchase") == 1:
            if self.company and not self.is_return and frappe.db.get_value("Item",row.item_code,"is_stock_item") == 1 and frappe.db.get_value("Item",row.item_code,"inspection_required_before_purchase") == 1:
                default_quality_inspection_warehouse=frappe.db.get_value("Company",self.company,"default_quality_inspection_warehouse")
                if default_quality_inspection_warehouse:
                    row.warehouse = default_quality_inspection_warehouse
                    
                    row.quality_inspection = make_quality_inspection(self,row)
                    created_quality_inspections.append(row.quality_inspection)
                 
    if created_quality_inspections:
        links = ''.join(
			f'<a href="/app/quality-inspection/{name}" target="_blank">{name}</a>,'
			for name in created_quality_inspections
		)
        
        frappe.msgprint(f"<b>Quality Inspections created:</b>{links}", title="Quality Inspections", indicator="green")

def prevent_edit_after_quality_inspection(doc, method):
    """
    Once at least one valid Quality Inspection exists against this Purchase Receipt,
    disallow further edits while the document is in Draft.
    """
    if doc.docstatus != 0 or doc.is_new() or getattr(doc, "_action", None) == "submit":
        return

    linked_qis = []
    for d in doc.items:
        qi = d.quality_inspection
        
        if not qi:
            continue

        qi_status = frappe.db.get_value("Quality Inspection", qi, "docstatus")
        # Skip references to deleted / cancelled QIs (docstatus None or 2)
        if qi_status in (None, 2):
            continue

        linked_qis.append(qi)

    if len(linked_qis) == 0:
        return
    
    frappe.throw(
        _("Purchase Receipt {0} is locked because Quality Inspection {1} already exists. Submit the Quality Inspections to proceed.")
        .format(doc.name, ", ".join(linked_qis))
    )

def ensure_quality_inspections_submitted(doc, method):
    """
    Reject submission unless every linked Quality Inspection is submitted.
    """
    pending = []

    for d in doc.items or []:
        if not d.quality_inspection:
            continue
        qi_status = frappe.db.get_value("Quality Inspection", d.quality_inspection, "docstatus")
        if qi_status != 1:
            pending.append(d.quality_inspection)

    if pending:
        frappe.throw(
            _("Submit Quality Inspection(s) {0} before submitting this Purchase Receipt.")
            .format(", ".join(pending))
        )


def make_quality_inspection(se_doc, item):
    
    doc = frappe.new_doc("Quality Inspection")
    doc.update({
        "inspection_type": "Incoming",
        "reference_type": se_doc.doctype,
        "reference_name": se_doc.name,
        "item_code": item.item_code,
        # "item_name": item.item_name,
        "ref_item": item.name,
        "description": item.description,
        "batch_no": item.batch_no,
        # "lot_no": item.lot_no,
        # "ar_no": item.ar_no,
        "sample_size": item.qty
    })

    doc.flags.ignore_mandatory = True
    doc.flags.ignore_permissions = True
    doc.flags.ignore_links = True

    doc.save()
    
    return doc.name


def after_submit(doc,method):
    create_batch_group(doc)

def create_batch_group(purchase_receipt):
    # Find all batches linked to this PR
    batch_list = frappe.get_all(
        "Batch",
        filters={
            "reference_doctype": "Purchase Receipt",
            "reference_name": purchase_receipt.name
        },
        fields=["name","pieces","weight_received","average_length","section_weight"]
    )
    
    if not batch_list:        
        return
        
    for batch in batch_list:
        if batch.pieces == 0 or batch.average_length == 0.0 or batch.section_weight == 0.0:            
            return

    # Create Batch Group
    batch_group = frappe.new_doc("Batch Group")
    batch_group.reference_doctype = "Purchase Receipt"
    batch_group.reference_document_name = purchase_receipt.name
    batch_group.total_length_in_meter = purchase_receipt.total_length_in_meter

    weight_received_kg = purchase_receipt.weight_received * 1000 if purchase_receipt.weight_received else 0

    # Check if weight is zero or invalid
    if weight_received_kg == 0:
        return
    
    batch_group.section_weight = round(weight_received_kg/purchase_receipt.total_length_in_meter, 2)
    batch_group.section_weight = round(batch_group.section_weight/39.37, 2)

    for batch in batch_list:
        batch_group.append("batch_details", {
            "batch": batch.name,
            "lengthpieces": batch.pieces,
            "weight_received": batch.weight_received,
            "length_size": batch.average_length,    
            "section_weight": batch.section_weight,
        })

    batch_group.save()
    for batch in batch_list:
        frappe.db.set_value("Batch", batch.name, "batch_group_reference", batch_group.name)

    
    frappe.msgprint(f"✅ Batch Group <a href='/app/batch-group/{batch_group.name}' target='_blank'><b>{batch_group.name}</b></a> created with {len(batch_list)} batches.")
    
def auto_calculation(doc, method):
    total_length_qty = 0
    
    for item in doc.items:
        if item.item_code and item.pieces and item.average_length:
            # Step 1: qty × length
            try:
                qty = float(item.pieces)
                average_length = float(item.average_length)
            except (TypeError, ValueError):
                frappe.throw(f"Invalid qty or length for item {item.item_code}: qty={item.qty}, length={item.length}")

            total_length_qty += qty * average_length
            
    
    # Step 2: Get weight_per_meter from Item master (use first item)
    if doc.items:
        first_item_code = doc.items[0].item_code
        weight_str = frappe.db.get_value("Item", first_item_code, "weight_per_meter") or "0"
        try:
            weight_per_meter = float(weight_str)*39.37
        except ValueError:
            frappe.throw(f"Invalid weight_per_meter for item {first_item_code}: '{weight_str}'")

        # Step 3: total × weight_per_meter → in kg
        weight_in_kg = total_length_qty * weight_per_meter

        # Convert to tonnes
        doc.weight_demand = round(weight_in_kg / 1000, 4)  # 4 decimals for tonne accuracy
    else:
        doc.weight_demand = 0

def validation_section_weight(doc, method):
    if not doc.items or not doc.weight_received or not doc.total_length_in_meter:
        return

    try:
        # Convert total received weight from tons to grams (if needed)
        weight_received_kg = float(doc.weight_received) * 1000
        # Compute section weight in grams per meter, then convert to kg/inch if required
        received_section_weight = round(weight_received_kg / doc.total_length_in_meter, 2)
        received_section_weight = round(received_section_weight / 39.37, 2)
    except ZeroDivisionError:
        frappe.throw(_("Total Length in Meter cannot be zero."))

    violations = []
    missing_standard = []

    for d in doc.items:
        if not d.item_code:
            continue

        standard_section_weight = frappe.db.get_value("Item", d.item_code, "weight_per_meter")
        if not standard_section_weight:
            missing_standard.append(d.item_code)
            continue

        tolerance_pct = frappe.db.get_value("Item", d.item_code, "section_weight_tolerance")
        try:
            tolerance_pct = float(tolerance_pct) if tolerance_pct is not None else 1.5
        except (TypeError, ValueError):
            tolerance_pct = 1.5

        # ✅ Calculate tolerance based on STANDARD section weight
        lower_bound = round(float(standard_section_weight) * (1 - tolerance_pct / 100.0), 2)
        upper_bound = round(float(standard_section_weight) * (1 + tolerance_pct / 100.0), 2)

        # ✅ Compare RECEIVED section weight against STANDARD tolerance range
        if received_section_weight < lower_bound or received_section_weight > upper_bound:
            violations.append({
                "item_code": d.item_code,
                "tolerance": tolerance_pct,
                "received_section_weight": received_section_weight,
                "standard_section_weight": float(standard_section_weight),
                "lower_bound": lower_bound,
                "upper_bound": upper_bound
            })

    if missing_standard:
        frappe.throw(_("Standard section weight not found for items: {0}").format(", ".join(missing_standard)))

    if violations:
        lines = []
        for v in violations:
            lines.append(_(
                "Item {0}: Received weight {1} is outside ±{2}% tolerance range ({3} - {4}) of standard {5}.<br>"
            ).format(
                v["item_code"], v["received_section_weight"], round(v["tolerance"], 2),
                v["lower_bound"], v["upper_bound"], v["standard_section_weight"]
            ))
        message = "\n".join(lines)
        frappe.throw(message)
