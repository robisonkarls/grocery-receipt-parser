#!/usr/bin/env python3
"""
Generate Markdown receipt file from parsed OCR JSON.
Input: JSON with structured receipt data
Output: Markdown file with YAML frontmatter (for QMD indexing)
"""

import sys
import json
from pathlib import Path
from datetime import datetime

def generate_markdown(data):
    """Convert structured receipt JSON to Markdown with YAML frontmatter."""
    
    structured = data.get('structured', {})
    
    # Extract metadata
    store = structured.get('store') or 'Unknown Store'
    location = structured.get('location', '')
    date = structured.get('date', datetime.now().strftime('%Y-%m-%d'))
    time = structured.get('time', '')
    total = structured.get('total', 0.0)
    tax = structured.get('tax', 0.0)
    payment = structured.get('payment_method', '')
    transaction_id = structured.get('transaction_id', '')
    items = structured.get('items', [])
    
    # Generate receipt ID
    receipt_id = f"{date}-{store.lower().replace(' ', '-')}-{transaction_id}"
    
    # Group items by category
    categorized_items = {}
    for item in items:
        category = item.get('category', 'other').title()
        if category not in categorized_items:
            categorized_items[category] = []
        categorized_items[category].append(item)
    
    # Build Markdown
    md = f"""---
receipt_id: {receipt_id}
store: {store}
location: {location}
date: {date}
time: {time}
total: {total}
tax: {tax}
payment: {payment}
transaction_id: {transaction_id}
items_count: {len(items)}
---

# {store} Receipt

**Store**: {store}{' ' + location if location else ''}  
**Date**: {date} {time}  
**Total**: ${total:.2f} (Tax: ${tax:.2f})  
**Payment**: {payment}  

## Items Purchased

"""
    
    # Add items by category
    for category, category_items in sorted(categorized_items.items()):
        md += f"### {category}\n"
        category_total = sum(item['price'] for item in category_items)
        for item in category_items:
            md += f"- **{item['name']}** - ${item['price']:.2f}\\n"
        md += f"\\n*{category} subtotal: ${category_total:.2f}*\\n\\n"
    
    # Add summary
    md += f"""## Summary

Total items: {len(items)}  
Subtotal: ${structured.get('subtotal', total - tax):.2f}  
Tax ({int(tax / (total - tax) * 100) if total > tax else 5}%): ${tax:.2f}  
**Total**: ${total:.2f}

Transaction ID: {transaction_id}
"""
    
    return receipt_id, md

def main():
    if len(sys.argv) < 2:
        print("Usage: generate-markdown.py <json_file>", file=sys.stderr)
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    
    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(json_path) as f:
        data = json.load(f)
    
    receipt_id, markdown = generate_markdown(data)
    
    # Output to stdout (caller will redirect to file)
    print(markdown)
    
    # Also print receipt_id to stderr for caller to capture
    print(f"RECEIPT_ID:{receipt_id}", file=sys.stderr)

if __name__ == '__main__':
    main()
