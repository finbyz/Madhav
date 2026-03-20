import frappe
from frappe import _
from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan as ERPNextProductionPlan
from pypika.terms import ExistsCriterion
from frappe.utils import (
	add_days,
	ceil,
	cint,
	comma_and,
	flt,
	get_link_to_form,
	getdate,
	now_datetime,
	nowdate,
)


INCHES_PER_METER = 39.37

def meters_to_inches(value):
	try:
		return float(value) * INCHES_PER_METER if value not in (None, "") else 0.0
	except Exception:
		return 0.0

class CustomProductionPlan(ERPNextProductionPlan):
    
	def create_work_order(self, item):
		from erpnext.manufacturing.doctype.work_order.work_order import OverProductionError

		if flt(item.get("qty")) <= 0:
			return

		wo = frappe.new_doc("Work Order")
		wo.update(item)
		wo.planned_start_date = item.get("planned_start_date") or item.get("schedule_date")

		if item.get("warehouse"):
			wo.fg_warehouse = item.get("warehouse")

		wo.set_work_order_operations()
		wo.set_required_items()

		try:
			wo.flags.ignore_mandatory = True
			wo.flags.ignore_validate = True
			wo.insert()
			wo.submit()
			return wo.name
		except OverProductionError:
			pass

	def validate(self):
		super().validate()
		self.validate_production_plan()

	def validate_production_plan(self):
		for row in self.get("po_items"):  # check correct child table name
			if isinstance(row.length, str):
				row.length = row.length.strip()
			if row.pieces:
				row.pieces = int(row.pieces)

	@frappe.whitelist()
	def get_items(self):
		super().get_items()

		# after fetching items, also pull custom fields from Sales Order Item and Sales Order
		for row in self.get("po_items"):  # adjust child table name if needed
			if row.sales_order and row.sales_order_item:
				# Get custom fields from Sales Order Item
				so_item = frappe.db.get_value(
					"Sales Order Item",
					row.sales_order_item,
					["pieces", "length_size"],
					as_dict=True,
				)
				if so_item:
					row.section_weight = frappe.db.get_value(
						"Item", row.item_code, "weight_per_meter"
					)
					row.pieces = so_item.pieces or 0
					# Convert and store in inches as required for po_items
					if so_item.length_size:
						row.length = meters_to_inches(so_item.length_size)
						row.length_size_m = so_item.length_size or 0.0

				# Get customer information from Sales Order
				so_details = frappe.db.get_value(
					"Sales Order",
					row.sales_order,
					["customer", "customer_name", "po_no"],
					as_dict=True,
				)
				if so_details:
					row.customer = so_details.customer or ""
					row.customer_name = so_details.customer_name or ""
					row.customers_purchase_order = so_details.po_no or ""

	@frappe.whitelist()
	def get_open_sales_orders(self):
		"""Pull sales orders which are pending to deliver based on criteria selected"""
		open_so = custom_get_sales_orders(self)
		if open_so:
			self.add_so_in_table(open_so)
		else:
			frappe.msgprint(_("Sales orders are not available for production"))

	@frappe.whitelist()
	def get_items(self):
		self.set("po_items", [])
		if self.get_items_from == "Sales Order":
			self.custom_get_so_items()
		elif self.get_items_from == "Material Request":
			self.get_mr_items()

	def custom_get_so_items(self):
	# Check for empty table or empty rows
		if not self.get("sales_orders") or not self.get_so_mr_list(
			"sales_order", "sales_orders"
		):
			frappe.throw(
				_("Please fill the Sales Orders table"),
				title=_("Sales Orders Required"),
			)

		so_list = self.get_so_mr_list("sales_order", "sales_orders")

		bom = frappe.qb.DocType("BOM")
		so_item = frappe.qb.DocType("Sales Order Item")

		items_subquery = (
			frappe.qb.from_(bom)
			.select(bom.name)
			.where(bom.is_active == 1)
		)

		item = frappe.qb.DocType("Item")

		items_query = (
			frappe.qb.from_(so_item)
			.select(
				so_item.parent,
				so_item.item_code,
				so_item.warehouse,
				so_item.qty,
				so_item.work_order_qty,
				so_item.delivered_qty,
				so_item.conversion_factor,
				so_item.description,
				so_item.name,
				so_item.bom_no,
			)
			.distinct()
			.where(
				(so_item.parent.isin(so_list))
				& (so_item.docstatus == 1)
				& (so_item.is_manufacture == 1)
				& (so_item.qty > so_item.work_order_qty)
				& (so_item.item_name.like(f"%{self.item_name}%"))
				# & (so_item.item_name.like(f"%{self.item_name.replace(' ', '%')}%"))
			)
		)

		if self.item_code and frappe.db.exists("Item", self.item_code):
			items_query = items_query.where(
				so_item.item_code == self.item_code
			)
			items_subquery = items_subquery.where(
				self.get_bom_item_condition()
				or bom.item == so_item.item_code
			)

		items_query = items_query.where(
			ExistsCriterion(items_subquery)
		)

		items = items_query.run(as_dict=True)

		for item in items:
			item.pending_qty = (
				flt(item.qty)
				- max(item.work_order_qty, item.delivered_qty, 0)
			) * item.conversion_factor

		pi = frappe.qb.DocType("Packed Item")

		pending_qty = (
			frappe.qb.terms.Case()
			.when(
				(so_item.work_order_qty > so_item.delivered_qty),
				(
					(
						(so_item.qty - so_item.work_order_qty) * pi.qty
					)
					/ so_item.qty
				),
			)
			.else_(
				(
					(
						(so_item.qty - so_item.delivered_qty) * pi.qty
					)
					/ so_item.qty
				)
			)
		)

		packed_items_query = (
			frappe.qb.from_(so_item)
			.from_(pi)
			.select(
				pi.parent,
				pi.item_code,
				pi.warehouse.as_("warehouse"),
				pending_qty.as_("pending_qty"),
				pi.parent_item,
				pi.description,
				so_item.name,
			)
			.distinct()
			.where(
				(so_item.parent == pi.parent)
				& (so_item.docstatus == 1)
				& (pi.parent_item == so_item.item_code)
				& (so_item.parent.isin(so_list))
				& (
					(
						(so_item.work_order_qty > so_item.delivered_qty)
						& (so_item.qty > so_item.work_order_qty)
					)
					| (
						(so_item.work_order_qty <= so_item.delivered_qty)
						& (so_item.qty > so_item.delivered_qty)
					)
				)
				& (
					ExistsCriterion(
						frappe.qb.from_(bom)
						.select(bom.name)
						.where(
							(bom.item == pi.item_code)
							& (bom.is_active == 1)
						)
					)
				)
			)
		)

		if self.item_code:
			packed_items_query = packed_items_query.where(
				so_item.item_code == self.item_code
			)

		packed_items = packed_items_query.run(as_dict=True)

		self.add_items(items + packed_items)
		self.calculate_total_planned_qty()

def custom_get_sales_orders(self):
	bom = frappe.qb.DocType("BOM")
	pi = frappe.qb.DocType("Packed Item")
	so = frappe.qb.DocType("Sales Order")
	so_item = frappe.qb.DocType("Sales Order Item")

	open_so_subquery1 = frappe.qb.from_(bom).select(bom.name).where(bom.is_active == 1)

	open_so_subquery2 = (
		frappe.qb.from_(pi)
		.select(pi.name)
		.where(
			(pi.parent == so.name)
			& (pi.parent_item == so_item.item_code)
			& (
				ExistsCriterion(
					frappe.qb.from_(bom)
					.select(bom.name)
					.where((bom.item == pi.item_code) & (bom.is_active == 1))
				)
			)
		)
	)

	item = frappe.qb.DocType("Item")

	open_so_query = (
		frappe.qb.from_(so)
		.join(so_item).on(so_item.parent == so.name)
		.select(
			so.name,
			so.transaction_date,
			so.customer,
			so.base_grand_total
		)
		.distinct()
		.where(
			(so.docstatus == 1)
			& (so.status.notin(["Stopped", "Closed"]))
			& (so.company == self.company)
			# & (so.is_manufacture == 1)
			& (so_item.qty > so_item.production_plan_qty)
			& (so_item.item_name.like(f"%{self.item_name}%"))   
			# & (so_item.item_name.like(f"%{self.item_name.replace(' ', '%')}%"))
		)
	)

	date_field_mapper = {
		"from_date": so.transaction_date >= self.from_date,
		"to_date": so.transaction_date <= self.to_date,
		"from_delivery_date": so_item.delivery_date >= self.from_delivery_date,
		"to_delivery_date": so_item.delivery_date <= self.to_delivery_date,
	}

	for field, value in date_field_mapper.items():
		if self.get(field):
			open_so_query = open_so_query.where(value)

	for field in ("customer", "project", "sales_order_status"):
		if self.get(field):
			so_field = "status" if field == "sales_order_status" else field
			open_so_query = open_so_query.where(so[so_field] == self.get(field))

	if self.item_code and frappe.db.exists("Item", self.item_code):
		open_so_query = open_so_query.where(so_item.item_code == self.item_code)
		open_so_subquery1 = open_so_subquery1.where(
			self.get_bom_item_condition() or bom.item == so_item.item_code
		)

	open_so_query = open_so_query.where(
		ExistsCriterion(open_so_subquery1) | ExistsCriterion(open_so_subquery2)
	)

	open_so = open_so_query.run(as_dict=True)

	return open_so

