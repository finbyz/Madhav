import frappe
from frappe import _


def duplicate_po_items_to_assembly_items_without_consolidate(doc, method):
    """Duplicate current po_items rows to assembly_items_without_consolidate without altering po_items."""
    # Reset target table to avoid duplication on subsequent saves
    doc.set("assembly_items_without_consolidate", [])

    if not getattr(doc, "po_items", None):
        return

    fields_to_copy = [
        "item_code",
        "bom_no",
        "planned_qty",
        "pending_qty",
        "pieces",
        "length",
        "length_size_m",
        "stock_uom",
        "warehouse",
        "planned_start_date",
        "product_bundle_item",
        "sales_order",
        "sales_order_item",
        "description",
        "customer",
        "customer_name",
    ]

    for row in doc.get("po_items"):
        new_row = {key: getattr(row, key, None) for key in fields_to_copy}
        doc.append("assembly_items_without_consolidate", new_row)

def consolidate_assembly_items(doc, method):

    if not doc.po_items:
        return
    
    consolidated_items = {}
    
    for item in doc.po_items:
        item_code = item.item_code
        
        if item_code in consolidated_items:
            
            consolidated_items[item_code]['planned_qty'] += item.planned_qty or 0
            consolidated_items[item_code]['pieces'] += item.pieces or 0
            consolidated_items[item_code]['length'] += item.length or 0
            
            if item.bom_no and not consolidated_items[item_code]['bom_no']:
                consolidated_items[item_code]['bom_no'] = item.bom_no
                
        else:
            
            consolidated_items[item_code] = {
                'item_code': item_code,
                'bom_no': item.bom_no,
                'planned_qty': item.planned_qty or 0,
                'pieces': item.pieces or 0,
                'length': item.length or 0,
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
            'pieces': consolidated_item['pieces'],
            'length': consolidated_item['length'],
            'stock_uom': consolidated_item['stock_uom'],
            'warehouse': consolidated_item['warehouse'],
            'planned_start_date': consolidated_item['planned_start_date']            
        })

