import frappe
from frappe import _

def consolidate_assembly_items(doc, method):

    if not doc.po_items:
        return
    
    consolidated_items = {}
    
    for item in doc.po_items:
        item_code = item.item_code
        
        if item_code in consolidated_items:
            
            consolidated_items[item_code]['planned_qty'] += item.planned_qty or 0
            
            if item.bom_no and not consolidated_items[item_code]['bom_no']:
                consolidated_items[item_code]['bom_no'] = item.bom_no
                
        else:
            
            consolidated_items[item_code] = {
                'item_code': item_code,
                'bom_no': item.bom_no,
                'planned_qty': item.planned_qty or 0,
                'stock_uom': item.stock_uom,
                'warehouse': item.warehouse,
                'planned_start_date': item.planned_start_date                
            }
    
    # Clear existing assembly items
    doc.po_items = []    
    
    for item_code, consolidated_item in consolidated_items.items():
        doc.append('po_items', {
            'item_code': consolidated_item['item_code'],
            'bom_no': consolidated_item['bom_no'],
            'planned_qty': consolidated_item['planned_qty'],
            'stock_uom': consolidated_item['stock_uom'],
            'warehouse': consolidated_item['warehouse'],
            'planned_start_date': consolidated_item['planned_start_date']            
        })
