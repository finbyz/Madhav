import frappe

def calculate_qty_in_tonne(doc,method):
    
    total_length_in_meter = 0
    total_qty = 0
    
    for row in doc.items:

        if row.length_size and row.pieces:  
            
            total_length_in_meter += row.length_size * row.pieces
            item = frappe.get_doc("Item", row.item_code)            
            weight_per_meter = float(item.weight_per_meter) or 0           
            row.qty = (row.length_size * row.pieces * weight_per_meter) / 1000  # assuming 1000 kg = 1 tonne
            
            total_qty += row.qty
    
    doc.total_qty = total_qty
    doc.total_length_in_meter = total_length_in_meter
            