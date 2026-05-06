#!/usr/bin/env python3
"""
Regex-based receipt parser. Handles Costco grocery and fuel receipts.
No LLM needed for clean text. Returns same JSON schema as LLM parsers.
Falls back to None fields rather than hallucinating.
"""

import re
import sys
import json
from datetime import datetime

# ── Patterns ──────────────────────────────────────────────────────────────────

DATE_PATTERNS = [
    r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',   # 2026/05/04 or 2026-05-04
    r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',   # 05/04/2026 or 04/05/2026
]
TIME_PATTERN  = re.compile(r'\b(\d{1,2}):(\d{2})(?::\d{2})?\b')
PRICE_PATTERN = re.compile(r'\$?([\d,]+\.\d{2})')

# Costco grocery line: barcode name price tax_code
GROCERY_LINE  = re.compile(
    r'^\s*\d{5,8}\s+(.+?)\s+([\d,]+\.\d{2})\s*[2BGHT]?\s*$'
)
# Discount/TPD line: TPD/barcode  amount-
DISCOUNT_LINE = re.compile(
    r'^\s*TPD/\d+\s+([\d,]+\.\d{2})-\s*$'
)
# Price-only line (name on previous line): just a price
PRICE_ONLY    = re.compile(r'^\s*([\d,]+\.\d{2})\s*[2BGHT]?\s*$')

SUBTOTAL_KW   = re.compile(r'\bSUBTOTAL\b', re.I)
TAX_KW        = re.compile(r'\b(TAX|GST|HST|PST)\b.*?([\d,]+\.\d{2})([-]?)', re.I)
TOTAL_KW      = re.compile(r'(?:\*+\s*)?TOTAL\b.*?([\d,]+\.\d{2})([-]?)', re.I)
ITEMS_SOLD_KW = re.compile(r'ITEMS?\s+SOLD\s*[=:]\s*(\d+)', re.I)

PAYMENT_KW    = re.compile(
    r'\b(VISA|MASTERCARD|MASTER\s*CARD|DEBIT|CASH|AMEX|INTERAC)\b', re.I
)

# Fuel receipt patterns
FUEL_SALE_KW  = re.compile(r'Fuel\s+Sale\s+\$?([\d,]+\.\d{2})', re.I)
FUEL_LTRS_KW  = re.compile(r'Ltrs:\s*([\d.]+)', re.I)
FUEL_PPL_KW   = re.compile(r'Price/Ltrs?:\s*\$?([\d.]+)', re.I)
FUEL_GRADE_KW = re.compile(r'Grade:\s*(\w+)', re.I)

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_price(s):
    try:
        return round(float(s.replace(',', '')), 2)
    except Exception:
        return None

def parse_date(text):
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            g = m.groups()
            # Determine which format
            if len(g[0]) == 4:          # YYYY-MM-DD
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            else:                        # MM/DD/YYYY or DD/MM/YYYY
                # Costco CA uses MM/DD/YYYY
                mo, d, y = int(g[0]), int(g[1]), int(g[2])
            try:
                return datetime(y, mo, d).strftime('%Y-%m-%d')
            except ValueError:
                # Try swapping day/month
                try:
                    return datetime(y, d, mo).strftime('%Y-%m-%d')
                except ValueError:
                    pass
    return None

def parse_time(text):
    m = TIME_PATTERN.search(text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None

def parse_store(lines):
    for line in lines[:8]:
        l = line.strip()
        if re.search(r'COSTCO', l, re.I):
            return 'Costco Wholesale'
        if re.search(r'#\d{3,}', l):
            return 'Costco Wholesale'
    return 'Unknown'
def parse_location(lines):
    for line in lines[:6]:
        l = line.strip()
        if re.search(r'#\d+', l) or re.search(r'\b(CALGARY|EDMONTON|VANCOUVER|TORONTO)\b', l, re.I):
            return l
    return None

def parse_payment(text):
    m = PAYMENT_KW.search(text)
    if m:
        pay = m.group(1).upper()
        return 'Mastercard' if 'MASTER' in pay else pay.title()
    return None

def parse_transaction_id(text):
    for pat in [r'Trn[:\s]+(\w+)', r'Transaction#[:\s]*(\w+)', r'Invoice\s+Number[:\s]+(\w+)', r'Ref[:\s]+(\w+)']:
        m = re.search(pat, text, re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None

# ── Grocery parser ────────────────────────────────────────────────────────────

def parse_grocery(lines, text):
    items = []
    pending_name = None

    for line in lines:
        line = line.rstrip()

        # Discount line
        dm = DISCOUNT_LINE.match(line)
        if dm:
            items.append({
                'name': 'Instant Savings',
                'price': -parse_price(dm.group(1)),
                'qty': 1,
                'category': 'other'
            })
            pending_name = None
            continue

        # Grocery line with barcode
        gm = GROCERY_LINE.match(line)
        if gm:
            name = gm.group(1).strip()
            price = parse_price(gm.group(2))
            if price and price < 500:  # sanity check
                items.append({
                    'name': name,
                    'price': price,
                    'qty': 1,
                    'category': categorize(name)
                })
                pending_name = None
            continue

        # Price-only line (item name was on previous line)
        pm = PRICE_ONLY.match(line)
        if pm and pending_name:
            price = parse_price(pm.group(1))
            if price and price < 500:
                items.append({
                    'name': pending_name,
                    'price': price,
                    'qty': 1,
                    'category': categorize(pending_name)
                })
                pending_name = None
            continue

        # Could be a pending item name (no barcode, no price yet)
        stripped = line.strip()
        if stripped and not re.search(r'\d{5,}', stripped) and not SUBTOTAL_KW.search(stripped):
            if not re.search(r'(SUBTOTAL|TOTAL|TAX|GST|APPROVED|CHANGE|ITEM)', stripped, re.I):
                pending_name = stripped if len(stripped) > 2 else None

    # Extract totals
    subtotal = tax = total = None
    for line in lines:
        if SUBTOTAL_KW.search(line):
            m = PRICE_PATTERN.search(line)
            if m: subtotal = parse_price(m.group(1))
        tm = TAX_KW.search(line)
        if tm:
            tax = parse_price(tm.group(2))
            if tm.group(3) == '-': tax = -tax if tax else tax
        tot = TOTAL_KW.search(line)
        if tot and not SUBTOTAL_KW.search(line):
            total = parse_price(tot.group(1))
            if tot.group(2) == '-': total = -total if total else total

    return items, subtotal, tax, total

# ── Fuel parser ───────────────────────────────────────────────────────────────

def parse_fuel(lines, text):
    fuel_sale = FUEL_SALE_KW.search(text)
    ltrs = FUEL_LTRS_KW.search(text)
    ppl = FUEL_PPL_KW.search(text)
    grade = FUEL_GRADE_KW.search(text)

    if not fuel_sale:
        return None, None, None, None

    total = parse_price(fuel_sale.group(1))
    litres = float(ltrs.group(1)) if ltrs else None
    price_per_l = float(ppl.group(1)) if ppl else None
    grade_name = grade.group(1) if grade else 'Unleaded'

    name = f"Fuel - {grade_name}"
    if litres: name += f" {litres:.3f}L"
    if price_per_l: name += f" @ ${price_per_l}/L"

    items = [{'name': name, 'price': total, 'qty': 1, 'category': 'fuel'}]

    # Tax from GST line
    gst_m = re.search(r'GST\s+Included\s*=?\s*\$?([\d.]+)', text, re.I)
    tax = parse_price(gst_m.group(1)) if gst_m else None
    subtotal = round(total - tax, 2) if tax else total

    return items, subtotal, tax, total

# ── Categorizer ───────────────────────────────────────────────────────────────

def categorize(name):
    name_up = name.upper()
    if any(w in name_up for w in ['CHICKEN','BEEF','PORK','SALMON','FISH','MEAT','TURKEY']):
        return 'meat'
    if any(w in name_up for w in ['MILK','CHEESE','BUTTER','YOGURT','CREAM','DAIRY']):
        return 'dairy'
    if any(w in name_up for w in ['APPLE','BANANA','BERRY','FRUIT','VEGETABLE','SALAD','ORGANIC']):
        return 'produce'
    if any(w in name_up for w in ['TOWEL','SOAP','DETERGENT','SOFTENER','SPONGE','TISSUE','LAUNDRY','LNDRY']):
        return 'household'
    if any(w in name_up for w in ['FUEL','GAS','UNLEADED','DIESEL']):
        return 'fuel'
    return 'grocery'

# ── Main ──────────────────────────────────────────────────────────────────────

def parse(text):
    lines = text.split('\n')

    store    = parse_store(lines)
    location = parse_location(lines)
    date     = parse_date(text)
    time     = parse_time(text)
    payment  = parse_payment(text)
    txn_id   = parse_transaction_id(text)

    # Detect receipt type
    is_fuel = bool(FUEL_SALE_KW.search(text))
    is_refund = bool(re.search(r'TOTAL.*?[\d.]+\s*-', text) or re.search(r'AMOUNT:\s*\$[\d.]+\s*-', text))

    if is_fuel:
        items, subtotal, tax, total = parse_fuel(lines, text)
    else:
        items, subtotal, tax, total = parse_grocery(lines, text)

    # Confidence: how many key fields did we get?
    found = sum(1 for v in [store, date, total, items] if v)
    confidence = found / 4.0

    return {
        'success': confidence >= 0.5,
        'method': 'regex',
        'confidence': round(confidence, 2),
        'receipt_type': 'fuel' if is_fuel else ('refund' if is_refund else 'grocery'),
        'structured': {
            'store': store,
            'location': location,
            'date': date,
            'time': time,
            'items': items or [],
            'subtotal': subtotal,
            'tax': tax,
            'total': total,
            'payment_method': payment,
            'transaction_id': txn_id
        }
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: parse-regex.py <ocr_json_file>'}))
        sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    text = data.get('text', '')
    if not text.strip():
        print(json.dumps({'success': False, 'error': 'No text'}))
        sys.exit(1)
    result = parse(text)
    print(json.dumps(result, indent=2))
