#!/usr/bin/env python3
"""
Scrape Costco CA coupons page and cross-reference against recent purchases.
Outputs JSON with potential refund opportunities.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path.home() / '.grocery-receipts' / 'db' / 'groceries.db'
DAYS_WINDOW = 30  # Costco price adjustment window


def get_recent_purchases(days=DAYS_WINDOW):
    """Get items purchased within the refund window."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT 
            i.name,
            i.total_price,
            r.receipt_date,
            r.store_name,
            r.store_location,
            r.id as receipt_id
        FROM items i
        JOIN receipts r ON i.receipt_id = r.id
        WHERE r.receipt_date >= ?
          AND i.total_price > 0
          AND i.category != 'fuel'
        ORDER BY r.receipt_date DESC
    """, (cutoff,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'name': r[0],
            'price_paid': r[1],
            'date': r[2],
            'store': r[3],
            'location': r[4],
            'receipt_id': r[5]
        }
        for r in rows
    ]


def normalize(text):
    """Lowercase, strip punctuation for fuzzy matching."""
    import re
    return re.sub(r'[^a-z0-9 ]', '', text.lower())


def keyword_match(purchased_name, coupon_name, threshold=2):
    """Return True if enough keywords overlap between two product names."""
    p_words = set(normalize(purchased_name).split()) - {'ks', 'the', 'a', 'and', 'of', 'in', 'g', 'kg', 'ml', 'pk'}
    c_words = set(normalize(coupon_name).split()) - {'ks', 'the', 'a', 'and', 'of', 'in', 'g', 'kg', 'ml', 'pk'}
    overlap = p_words & c_words
    return len(overlap) >= threshold


def main():
    if len(sys.argv) < 2:
        print("Usage: coupon-check.py <coupons_json_file>")
        sys.exit(1)

    coupons_path = Path(sys.argv[1])
    with open(coupons_path) as f:
        coupons = json.load(f)

    purchases = get_recent_purchases()
    matches = []

    for coupon in coupons:
        for purchase in purchases:
            if keyword_match(purchase['name'], coupon['name']):
                days_since = (datetime.now() - datetime.strptime(purchase['date'], '%Y-%m-%d')).days
                refund_potential = round(purchase['price_paid'] - coupon['sale_price'], 2)
                if refund_potential > 0 and days_since <= DAYS_WINDOW:
                    matches.append({
                        'purchased_item': purchase['name'],
                        'coupon_item': coupon['name'],
                        'price_paid': purchase['price_paid'],
                        'sale_price': coupon['sale_price'],
                        'savings': coupon['savings'],
                        'refund_potential': refund_potential,
                        'purchase_date': purchase['date'],
                        'days_since_purchase': days_since,
                        'days_left_in_window': DAYS_WINDOW - days_since,
                        'receipt_id': purchase['receipt_id'],
                        'coupon_valid_until': coupon.get('valid_until', '')
                    })

    print(json.dumps({'matches': matches, 'total': len(matches)}, indent=2))


if __name__ == '__main__':
    main()
