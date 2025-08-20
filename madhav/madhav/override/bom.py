import frappe
from erpnext.manufacturing.doctype.bom.bom import BOM as _BOM

class BOM(_BOM):
	def autoname(self):
		# ignore amended documents while calculating current index

		if self.bom_creator:
			search_key = f"{self.bom_creator}"
		else:
			search_key = f"{self.doctype}-{self.item}%"
		existing_boms = frappe.get_all(
			"BOM", filters={"name": search_key, "amended_from": ["is", "not set"]}, pluck="name"
		)

		index = self.get_index_for_bom(existing_boms)

		prefix = self.doctype
		suffix = "%.2i" % index  # convert index to string (1 -> "001")
		if self.bom_creator:
			prefix = self.bom_creator
			bom_name = f"{prefix}-{suffix}"
		else:
			bom_name = f"{prefix}-{self.item}-{suffix}"

		if len(bom_name) <= 140:
			name = bom_name
		else:
			# since max characters for name is 140, remove enough characters from the
			# item name to fit the prefix, suffix and the separators
			truncated_length = 140 - (len(prefix) + len(suffix) + 2)
			truncated_item_name = self.item[:truncated_length]
			# if a partial word is found after truncate, remove the extra characters
			truncated_item_name = truncated_item_name.rsplit(" ", 1)[0]
			name = f"{prefix}-{truncated_item_name}-{suffix}"

		if frappe.db.exists("BOM", name):
			existing_boms = frappe.get_all(
				"BOM", filters={"name": ("like", search_key), "amended_from": ["is", "not set"]}, pluck="name"
			)

			index = self.get_index_for_bom(existing_boms)
			suffix = "%.2i" % index
			name = f"{prefix}-{self.item}-{suffix}"

		self.name = name