#!/usr/bin/env python3
"""
Insert parsed receipt data into SQLite database.
Resolves DB path from: GROCERY_DATA_DIR env > config.json > default ~/.grocery-receipts
"""

import sys
import json
import sqlite3
import os
from pathlib import Path
import uuid
import hashlib

def resolve_data_dir():
    """Resolve the data directory from env, config, or default."""
    # 1. Env var
    if os.environ.get('GROCERY_DATA_DIR'):
        return Path(os.environ['GROCERY_DATA_DIR'])
    
    # 2. config.json in default location
    config_path = Path.home() / '.grocery-receipts' / 'config.json'
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
            if 'dataDir' in config:
                return Path(config['dataDir'])
    
    # 3. Default
    return Path.home() / '.grocery-receipts'

DATA_DIR = resolve_data_dir()
DB_PATH = DATA_DIR / 'db' / 'groceries.db'

def compute_file_hash(path):
    """Return sha256 hex digest of a file, or None if path is empty/missing."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def insert_receipt(data, receipt_id, image_path):
    """Insert receipt and items into database."""
    structured = data.get('structured', {})

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Dedup check 1: source file hash (same file submitted twice)
    source_hash = compute_file_hash(image_path)
    if source_hash:
        cursor.execute("SELECT id FROM receipts WHERE source_file_hash = ?", (source_hash,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            print(json.dumps({
                'success': False,
                'duplicate': True,
                'duplicate_reason': 'source_file_hash',
                'existing_id': existing[0],
                'error': f'Receipt already in database (id={existing[0]})'
            }))
            sys.exit(0)

    # Dedup check 2: transaction_id (same receipt from different file/scan)
    transaction_id = structured.get('transaction_id', '').strip()
    if transaction_id:
        cursor.execute("SELECT id FROM receipts WHERE transaction_id = ?", (transaction_id,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            print(json.dumps({
                'success': False,
                'duplicate': True,
                'duplicate_reason': 'transaction_id',
                'existing_id': existing[0],
                'error': f'Receipt with transaction_id={transaction_id} already in database (id={existing[0]})'
            }))
            sys.exit(0)

    try:
        cursor.execute("""
            INSERT INTO receipts (
                id, store_name, store_location, receipt_date, receipt_time,
                total_amount, tax_amount, subtotal, payment_method, transaction_id,
                markdown_path, image_path, ocr_method, ocr_confidence, source_file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_id,
            structured.get('store') or 'Unknown',
            structured.get('location', ''),
            structured.get('date'),
            structured.get('time', ''),
            structured.get('total', 0.0),
            structured.get('tax', 0.0),
            structured.get('subtotal', 0.0),
            structured.get('payment_method', ''),
            transaction_id,
            f"receipts/{receipt_id}.md",
            image_path,
            data.get('method', 'unknown'),
            data.get('confidence', 0.0),
            source_hash
        ))

        items = structured.get('items', [])
        for idx, item in enumerate(items):
            cursor.execute("""
                INSERT INTO items (id, receipt_id, name, total_price, category, line_number)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), receipt_id,
                item['name'], item['price'],
                item.get('category', ''), idx + 1
            ))
            update_purchase_pattern(cursor, item['name'], item['price'],
                                    structured.get('date'), structured.get('store'),
                                    item.get('category'))

        conn.commit()
        print(json.dumps({'success': True, 'receipt_id': receipt_id, 'items_inserted': len(items)}))

    except Exception as e:
        conn.rollback()
        print(json.dumps({'success': False, 'error': str(e)}), file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

def update_purchase_pattern(cursor, item_name, price, purchase_date, store, category):
    cursor.execute(
        "SELECT purchase_count, avg_price, min_price, max_price, last_purchase_date, avg_days_between_purchase FROM purchase_patterns WHERE item_name = ?",
        (item_name,)
    )
    row = cursor.fetchone()

    if row:
        count, avg_price, min_price, max_price, last_date, old_avg_days = row
        new_count = count + 1
        new_avg = ((avg_price * count) + price) / new_count
        new_min = min(min_price, price)
        new_max = max(max_price, price)
        new_avg_days = old_avg_days

        if last_date and purchase_date:
            from datetime import datetime
            days_diff = (datetime.strptime(purchase_date, '%Y-%m-%d') - datetime.strptime(last_date, '%Y-%m-%d')).days
            new_avg_days = (((old_avg_days or 0) * (count - 1)) + days_diff) / count

        cursor.execute("""
            UPDATE purchase_patterns
            SET purchase_count=?, avg_price=?, min_price=?, max_price=?,
                last_purchase_date=?, avg_days_between_purchase=?,
                preferred_store=?, preferred_category=?
            WHERE item_name=?
        """, (new_count, new_avg, new_min, new_max, purchase_date, new_avg_days, store, category, item_name))
    else:
        cursor.execute("""
            INSERT INTO purchase_patterns
                (item_name, purchase_count, avg_price, min_price, max_price, last_purchase_date, preferred_store, preferred_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
