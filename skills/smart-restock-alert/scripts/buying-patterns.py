#!/usr/bin/env python3
"""
Show Robison's buying patterns for all products — cadence, avg price,
days since last purchase, whether due/overdue, and price range.

Usage:
  python3 buying-patterns.py                    # full report
  python3 buying-patterns.py --category meat    # filter by category
  python3 buying-patterns.py --due-only         # only items due/overdue
  python3 buying-patterns.py --min-purchases 3  # only items bought 3+ times
  python3 buying-patterns.py --json             # machine-readable JSON output
"""

import sqlite3
import argparse
import json
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path.home() / '.grocery-receipts' / 'db' / 'groceries.db'

# Items to exclude from pattern reports (noise)
EXCLUDE_PATTERNS = [
    'tpd/', 'instant savings', 'refund', 'return/', 'unleaded fuel',
    'eco fee', 'tax', 'change'
]

CATEGORY_EMOJI = {
    'meat':      '🥩',
    'produce':   '🥦',
    'dairy':     '🥛',
    'grocery':   '🛒',
    'household': '🧹',
    'other':     '📦',
    'fuel':      '⛽',
    'appliance': '🔌',
    'refund':    '↩️',
}


def should_exclude(name):
    name_lower = name.lower()
    return any(p in name_lower for p in EXCLUDE_PATTERNS)


def load_patterns(min_purchases=1, category=None, due_only=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
        SELECT item_name, purchase_count, avg_price, min_price, max_price,
               last_purchase_date, avg_days_between_purchase,
               preferred_store, preferred_category
        FROM purchase_patterns
        WHERE purchase_count >= ?
        ORDER BY purchase_count DESC, last_purchase_date DESC
    """
    cursor.execute(query, (min_purchases,))
    rows = cursor.fetchall()
    conn.close()

    today = date.today()
    patterns = []

    for row in rows:
        name, count, avg_price, min_price, max_price, last_date, avg_days, store, cat = row

        if should_exclude(name):
            continue
        if category and (cat or '').lower() != category.lower():
            continue

        days_since = None
        days_until_due = None
        days_overdue = None
        is_due = False
        status = 'once'

        if last_date:
            try:
                last = datetime.strptime(last_date, '%Y-%m-%d').date()
                days_since = (today - last).days
            except:
                pass

        if avg_days and avg_days > 0 and days_since is not None:
            days_until_due = max(0, int(avg_days) - days_since)
            days_overdue = max(0, days_since - int(avg_days))
            is_due = days_since >= int(avg_days)

            if days_overdue > 0:
                status = 'overdue'
            elif days_until_due == 0:
                status = 'due'
            elif days_until_due <= 7:
                status = 'soon'
            else:
                status = 'ok'
        elif count == 1:
            status = 'once'

        if due_only and status not in ('due', 'overdue', 'soon'):
            continue

        patterns.append({
            'name': name,
            'category': cat or 'other',
            'purchase_count': count,
            'avg_price': round(avg_price, 2) if avg_price else 0,
            'min_price': round(min_price, 2) if min_price else 0,
            'max_price': round(max_price, 2) if max_price else 0,
            'last_purchase_date': last_date,
            'days_since_last': days_since,
            'avg_days_between': int(avg_days) if avg_days and avg_days > 0 else None,
            'days_until_due': days_until_due,
            'days_overdue': days_overdue,
            'is_due': is_due,
            'status': status,
            'store': store,
        })

    return patterns


def cadence_label(avg_days):
    if avg_days is None:
        return 'bought once'
    if avg_days <= 7:
        return f'every ~{avg_days}d (weekly)'
    if avg_days <= 16:
        return f'every ~{avg_days}d (biweekly)'
    if avg_days <= 35:
        return f'every ~{avg_days}d (monthly)'
    if avg_days <= 100:
        return f'every ~{avg_days}d (~{round(avg_days/30)}mo)'
    return f'every ~{avg_days}d (~{round(avg_days/30)}mo)'


def status_label(p):
    s = p['status']
    if s == 'overdue':
        return f"⚠️  OVERDUE {p['days_overdue']}d"
    if s == 'due':
        return '🔴 DUE NOW'
    if s == 'soon':
        return f"🟡 due in {p['days_until_due']}d"
    if s == 'ok':
        return f"✅ due in {p['days_until_due']}d"
    return '🔵 bought once'


def print_report(patterns):
    if not patterns:
        print("No patterns found.")
        return

    # Group by category
    categories = {}
    for p in patterns:
        cat = p['category']
        categories.setdefault(cat, []).append(p)

    cat_order = ['meat', 'produce', 'dairy', 'grocery', 'household', 'other', 'fuel', 'appliance', 'refund']
    sorted_cats = sorted(categories.keys(), key=lambda c: cat_order.index(c) if c in cat_order else 99)

    total = len(patterns)
    due_count = sum(1 for p in patterns if p['status'] in ('due', 'overdue'))
    soon_count = sum(1 for p in patterns if p['status'] == 'soon')

    print(f"\n{'='*58}")
    print(f"  🛒  BUYING PATTERNS REPORT  —  {date.today().strftime('%B %d, %Y')}")
    print(f"{'='*58}")
    print(f"  {total} products tracked  |  {due_count} due/overdue  |  {soon_count} due soon")
    print(f"{'='*58}\n")

    for cat in sorted_cats:
        items = categories[cat]
        emoji = CATEGORY_EMOJI.get(cat, '📦')
        print(f"{emoji}  {cat.upper()}")
        print(f"{'─'*58}")

        for p in items:
            name = p['name'][:35].ljust(35)
            count_str = f"×{p['purchase_count']}".rjust(3)
            price_str = f"avg ${p['avg_price']:.2f}"
            if p['min_price'] != p['max_price']:
                price_str += f" (${p['min_price']:.2f}–${p['max_price']:.2f})"

            cadence = cadence_label(p['avg_days_between'])
            status = status_label(p)
            last = p['last_purchase_date'] or 'unknown'

            print(f"  {name} {count_str}  {price_str}")
            print(f"    {'Last: ' + last:<22} {cadence}")
            print(f"    {status}")
            print()

        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', help='Filter by category (meat/produce/dairy/grocery/household/other)')
    parser.add_argument('--due-only', action='store_true', help='Show only due/overdue/soon items')
    parser.add_argument('--min-purchases', type=int, default=1, help='Min purchase count (default 1)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    patterns = load_patterns(
        min_purchases=args.min_purchases,
        category=args.category,
        due_only=args.due_only
    )

    if args.json:
        print(json.dumps(patterns, indent=2))
    else:
        print_report(patterns)


if __name__ == '__main__':
    main()
