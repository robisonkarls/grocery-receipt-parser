#!/usr/bin/env python3
"""
Smart restock alert: cross-reference purchase patterns with current Costco coupons.
Identifies items Robison is due to buy that are currently on sale.

Usage:
  python3 restock-check.py
  python3 restock-check.py --coupons /tmp/costco-coupons.json   # use cached coupons
  python3 restock-check.py --due-window 30                      # days overdue to flag (default 14)
  python3 restock-check.py --min-purchases 2                    # min purchase history (default 2)
"""

import json
import sys
import os
import argparse
import subprocess
from datetime import datetime, date
from pathlib import Path
import sqlite3

DB_PATH = Path.home() / '.grocery-receipts' / 'db' / 'groceries.db'
FETCH_SCRIPT = Path.home() / '.openclaw' / 'skills' / 'costco-coupons' / 'scripts' / 'fetch-coupons.py'
COUPON_CACHE = Path('/tmp/costco-coupons.json')

# Fuzzy match: map common DB item name fragments to coupon keyword lists
# Add more as patterns are discovered
MATCH_HINTS = {
    'bacon':            ['bacon'],
    'butter':           ['butter'],
    'rotisserie':       ['rotisserie chicken'],
    'roti chicken':     ['rotisserie chicken'],
    'sour cream':       ['sour cream'],
    'sour crm':         ['sour cream'],
    'spinach':          ['spinach dip', 'spinach'],
    'cucumber':         ['cucumber', 'cuke'],
    'mini cuke':        ['cucumber', 'cuke'],
    'towel':            ['paper towel', 'bounty', 'kirkland towel'],
    'ks towel':         ['paper towel', 'bounty'],
    'dove':             ['dove body wash', 'dove soap'],
    'detergent':        ['laundry detergent', 'tide', 'pods'],
    'pods downy':       ['tide pods', 'laundry detergent'],
    'cat litter':       ['cat litter', 'litter'],
    'cottage cheese':   ['cottage cheese'],
    'grape tomato':     ['grape tomato', 'tomato'],
    'roma tomato':      ['roma tomato', 'tomato'],
    'salad kit':        ['salad', 'kale'],
    'sweet kale':       ['salad', 'kale'],
    'coffee':           ['coffee', 'cold brew'],
    'tissue':           ['facial tissue', 'scotties', 'kleenex'],
    'toilet':           ['bathroom tissue', 'charmin', 'toilet paper'],
    'shrimp':           ['shrimp'],
    'yogurt':           ['yogurt', 'activia'],
    'parmesan':         ['parmesan', 'grated parmesan'],
    'mustard':          ['mustard'],
    'energy drink':     ['energy drink', 'zoa'],
    'water':            ['water'],
    'milk':             ['milk'],
    'eggs':             ['eggs'],
    'ks bacon':         ['bacon'],
    'b/s breast':       ['chicken breast'],
    'chicken thigh':    ['chicken thigh'],
    'hydro straw':      ['hydro flask', 'water bottle', 'straw'],
}


def load_coupons(coupon_path=None):
    """Load coupons from file or fetch fresh."""
    if coupon_path and Path(coupon_path).exists():
        with open(coupon_path) as f:
            return json.load(f).get('coupons', [])

    # Fetch fresh
    try:
        result = subprocess.run(
            ['python3', str(FETCH_SCRIPT)],
            capture_output=True, text=True, timeout=60
        )
        data = json.loads(result.stdout)
        if 'coupons' in data:
            # Cache it
            with open(COUPON_CACHE, 'w') as f:
                json.dump(data, f)
            return data['coupons']
    except Exception as e:
        print(json.dumps({'error': f'Failed to fetch coupons: {e}'}))
        sys.exit(1)
    return []


def load_patterns(min_purchases=2):
    """Load purchase patterns from DB."""
    if not DB_PATH.exists():
        print(json.dumps({'error': f'DB not found: {DB_PATH}'}))
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_name, purchase_count, avg_price, last_purchase_date,
               avg_days_between_purchase, preferred_store, preferred_category
        FROM purchase_patterns
        WHERE purchase_count >= ?
          AND avg_days_between_purchase > 0
          AND last_purchase_date IS NOT NULL
        ORDER BY purchase_count DESC
    """, (min_purchases,))
    rows = cursor.fetchall()
    conn.close()

    patterns = []
    for row in rows:
        name, count, avg_price, last_date, avg_days, store, category = row
        try:
            last = datetime.strptime(last_date, '%Y-%m-%d').date()
        except:
            continue
        days_since = (date.today() - last).days
        days_until_due = max(0, int(avg_days) - days_since)
        days_overdue = max(0, days_since - int(avg_days))

        patterns.append({
            'name': name,
            'purchase_count': count,
            'avg_price': round(avg_price, 2),
            'last_purchase_date': last_date,
            'avg_days_between': int(avg_days),
            'days_since_last': days_since,
            'days_until_due': days_until_due,
            'days_overdue': days_overdue,
            'is_due': days_since >= int(avg_days),
            'store': store,
            'category': category,
        })
    return patterns


def fuzzy_match(item_name, coupon_name):
    """Check if an item name and coupon name are likely the same product."""
    item_lower = item_name.lower().strip()
    coupon_lower = coupon_name.lower().strip()

    # Exact short-circuit
    if item_lower in coupon_lower or coupon_lower in item_lower:
        return True

    # Direct word match (meaningful words only, 4+ chars)
    item_words = [w for w in item_lower.replace('/', ' ').replace('-', ' ').split() if len(w) >= 4]
    for word in item_words:
        # Skip generic words that would cause false positives
        if word in ('with', 'size', 'pack', 'plus', 'ultra', 'kirkland', 'costco', 'instant', 'savings'):
            continue
        if word in coupon_lower:
            return True

    # Check match hints table
    for key, keywords in MATCH_HINTS.items():
        if key in item_lower:
            for kw in keywords:
                if kw in coupon_lower:
                    return True

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--coupons', help='Path to cached coupons JSON')
    parser.add_argument('--due-window', type=int, default=14,
                        help='Days overdue threshold to flag (default 14)')
    parser.add_argument('--min-purchases', type=int, default=2,
                        help='Minimum purchase count to include (default 2)')
    args = parser.parse_args()

    coupons = load_coupons(args.coupons)
    patterns = load_patterns(args.min_purchases)

    today = date.today()
    alerts = []
    due_items = []
    upcoming_items = []

    for pattern in patterns:
        # Check if due or overdue
        if pattern['is_due']:
            due_items.append(pattern)

            # Check if any coupon matches
            for coupon in coupons:
                if fuzzy_match(pattern['name'], coupon['name']):
                    sale_price = coupon.get('sale_price', '').replace('$','').replace(',','')
                    try:
                        sale_f = float(sale_price)
                        savings_pct = round((float(coupon['savings']) / (sale_f + float(coupon['savings']))) * 100)
                    except:
                        savings_pct = 0

                    alerts.append({
                        'item': pattern['name'],
                        'coupon_name': coupon['name'],
                        'avg_price': pattern['avg_price'],
                        'sale_price': coupon.get('sale_price', '?'),
                        'savings': coupon['savings'],
                        'savings_pct': savings_pct,
                        'valid': coupon['valid'],
                        'purchase_count': pattern['purchase_count'],
                        'avg_days_between': pattern['avg_days_between'],
                        'days_overdue': pattern['days_overdue'],
                        'last_purchase': pattern['last_purchase_date'],
                    })
                    break  # one match per pattern item is enough

        elif pattern['days_until_due'] <= 14:
            # Coming up soon — worth knowing about even without a coupon
            upcoming_items.append(pattern)

    output = {
        'generated': today.isoformat(),
        'alerts': alerts,
        'due_no_sale': [p['name'] for p in due_items if not any(a['item'] == p['name'] for a in alerts)],
        'upcoming_soon': [
            {'name': p['name'], 'due_in_days': p['days_until_due'], 'avg_days_between': p['avg_days_between']}
            for p in upcoming_items
        ],
        'patterns_checked': len(patterns),
        'coupons_checked': len(coupons),
    }
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
