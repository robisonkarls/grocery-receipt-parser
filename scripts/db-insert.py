#!/usr/bin/env python3
"""
Insert parsed receipt data into SQLite database.
Input: Receipt ID and JSON file with structured data
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import uuid

DB_PATH = Path.home() / '.grocery-receipts/db/groceries.db'

def insert_receipt(data, receipt_id, image_path):
    """Insert receipt and items into database."""
    
    structured = data.get('structured', {})
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Insert receipt
        cursor.execute("""
            INSERT INTO receipts (
                id, store_name, store_location, receipt_date, receipt_time,
                total_amount, tax_amount, subtotal, payment_method, transaction_id,
                markdown_path, image_path, ocr_method, ocr_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_id,
            structured.get('store', 'Unknown'),
            structured.get('location', ''),
            structured.get('date'),
            structured.get('time', ''),
            structured.get('total', 0.0),
            structured.get('tax', 0.0),
            structured.get('subtotal', 0.0),
            structured.get('payment_method', ''),
            structured.get('transaction_id', ''),
            f"grocery/receipts/{receipt_id}.md",
            image_path,
            data.get('method', 'unknown'),
            data.get('confidence', 0.0)
        ))
        
        # Insert items
        items = structured.get('items', [])
        for idx, item in enumerate(items):
            item_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO items (
                    id, receipt_id, name, total_price, category, line_number
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                receipt_id,
                item['name'],
                item['price'],
                item.get('category', ''),
                idx + 1
            ))
            
            # Update purchase patterns
            update_purchase_pattern(cursor, item['name'], item['price'], 
                                   structured.get('date'), structured.get('store'),
                                   item.get('category'))
        
        conn.commit()
        print(json.dumps({
            'success': True,
            'receipt_id': receipt_id,
            'items_inserted': len(items)
        }))
        
    except Exception as e:
        conn.rollback()
        print(json.dumps({
            'success': False,
            'error': str(e)
        }), file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

def update_purchase_pattern(cursor, item_name, price, purchase_date, store, category):
    """Update or create purchase pattern for item."""
    
    # Check if pattern exists
    cursor.execute(
        "SELECT purchase_count, avg_price, min_price, max_price, last_purchase_date FROM purchase_patterns WHERE item_name = ?",
        (item_name,)
    )
    row = cursor.fetchone()
    
    if row:
        count, avg_price, min_price, max_price, last_date = row
        new_count = count + 1
        new_avg = ((avg_price * count) + price) / new_count
        new_min = min(min_price, price)
        new_max = max(max_price, price)
        
        # Calculate days between purchases
        if last_date and purchase_date:
            from datetime import datetime
            last_dt = datetime.strptime(last_date, '%Y-%m-%d')
            current_dt = datetime.strptime(purchase_date, '%Y-%m-%d')
            days_diff = (current_dt - last_dt).days
            
            # Update avg days (weighted average)
            cursor.execute(
                "SELECT avg_days_between_purchase FROM purchase_patterns WHERE item_name = ?",
                (item_name,)
            )
            old_avg_days = cursor.fetchone()[0] or 0
            new_avg_days = ((old_avg_days * (count - 1)) + days_diff) / count if count > 1 else days_diff
        else:
            new_avg_days = None
        
        cursor.execute("""
            UPDATE purchase_patterns
            SET purchase_count = ?,
                avg_price = ?,
                min_price = ?,
                max_price = ?,
                last_purchase_date = ?,
                avg_days_between_purchase = ?,
                preferred_store = ?,
                preferred_category = ?
            WHERE item_name = ?
        """, (new_count, new_avg, new_min, new_max, purchase_date, 
              new_avg_days, store, category, item_name))
    else:
        # Create new pattern
        cursor.execute("""
            INSERT INTO purchase_patterns (
                item_name, purchase_count, avg_price, min_price, max_price,
                last_purchase_date, preferred_store, preferred_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (item_name, 1, price, price, price, purchase_date, store, category))

def main():
    if len(sys.argv) < 3:
        print("Usage: db-insert.py <receipt_id> <json_file> [image_path]", file=sys.stderr)
        sys.exit(1)
    
    receipt_id = sys.argv[1]
    json_path = Path(sys.argv[2])
    image_path = sys.argv[3] if len(sys.argv) > 3 else ''
    
    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(json_path) as f:
        data = json.load(f)
    
    insert_receipt(data, receipt_id, image_path)

if __name__ == '__main__':
    main()
