import json
import csv
import os

# File paths
backend_path = os.path.join(os.path.dirname(__file__), 'backend_costprice.backend.json')
sales_path = os.path.join(os.path.dirname(__file__), 'Revel_data.revel_stripped_data.json')
output_path = os.path.join(os.path.dirname(__file__), 'joined_sales_purchases.csv')

# Load backend (purchase) data
with open(backend_path, 'r', encoding='utf-8') as f:
    backend_data = json.load(f)

# Build a lookup by barcode
purchase_lookup = {}
for item in backend_data:
    barcode = item.get('Cleaned Barcode')
    if barcode:
        purchase_lookup[barcode] = item

# Load sales data
with open(sales_path, 'r', encoding='utf-8') as f:
    sales_data = json.load(f)

# Prepare output rows
rows = []
for sale in sales_data:
    barcode = sale.get('product_barcode')
    purchase = purchase_lookup.get(barcode, {})
    row = {
        'Date': sale.get('date', ''),
        'Barcode': barcode or '',
        'Product': purchase.get('Item Name', ''),
        'Purchase Qty': purchase.get('Quantity', ''),
        'Purchase Price': purchase.get('Unit Price', ''),
        'Sales Qty': sale.get('n_items', ''),
        'Sales Price': sale.get('price', '')
    }
    rows.append(row)

# Write to CSV
with open(output_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'Date', 'Barcode', 'Product', 'Purchase Qty', 'Purchase Price', 'Sales Qty', 'Sales Price'
    ])
    writer.writeheader()
    writer.writerows(rows)

print(f"Output written to {output_path}")
