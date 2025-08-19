import frappe


def create_batch(self):

	from erpnext.stock.doctype.batch.batch import make_batch
	dct = {}

	if hasattr(self, 'voucher_detail_no'):
		if self.voucher_type == "Stock Entry":
			data = frappe.get_doc("Stock Entry Detail", self.voucher_detail_no)
		else:
			data = frappe.get_doc(f"{self.voucher_type} Item", self.voucher_detail_no)
			
		dct.update({
			"pieces": data.get("pieces"),
			"weight_received": data.get("qty"),
			"average_length":data.get("average_length"),
			# "length_weight_in_kg": data.get("length_weight_in_kg"),
			"section_weight": data.get("section_weight"),
			# "no_of_packages": data.get("no_of_packages"),
			# "batch_yield": data.get("batch_yield"),
			# "concentration": data.get("concentration")
			"reference_detail_no": self.voucher_detail_no
		})
		# if data.get("quality_inspection"):
		# 	quality_inspection = frappe.get_doc("Quality Inspection", data.get("quality_inspection"))
		# 	retest_date = quality_inspection.retest_date
		# 	expiry_date = quality_inspection.expiry_date
		# 	manufacturing_date = quality_inspection.manufacturing_date
		# 	dct.update({
		# 	"retest_date": retest_date,
		# 	"expiry_date":expiry_date,
		# 	"manufacturing_date":manufacturing_date,
		# })
	
	
	dct.update({
		"item": self.get("item_code"),
		"reference_doctype": self.get("voucher_type"),
		"reference_name": self.get("voucher_no"),
	})
	
	return make_batch(frappe._dict(dct))