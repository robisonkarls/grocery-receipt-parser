---
name: smart-restock-alert
description: Analyze Robison's grocery purchase patterns against current Costco coupons to identify smart restocking opportunities. Use when asked about what to buy at Costco, what's on sale that Robison usually buys, restocking reminders, or when the weekly Friday cron job runs. Triggers on phrases like "what should I buy", "anything I need at Costco", "smart shopping", "restock alert", "what am I due for", "show my buying patterns", "what do I usually buy".
---

# Smart Restock Alert

Two scripts work together: one shows all buying patterns, the other cross-references them with current Costco coupons to flag smart buy opportunities.

## Scripts

### 1. `buying-patterns.py` — Full purchase history report

Shows everything Robison buys, grouped by category, with cadence, avg price, and due status.

```bash
python3 ~/.openclaw/skills/smart-restock-alert/scripts/buying-patterns.py

# Filter options
--category meat|produce|dairy|grocery|household|other
--due-only              # only show due/overdue/soon items
--min-purchases 2       # only items bought 2+ times
--json                  # machine-readable output
```

**Status indicators:**
- ⚠️ OVERDUE — past due date
- 🔴 DUE NOW — due today
- 🟡 due in Xd — due within 7 days
- ✅ due in Xd — on track
- 🔵 bought once — no cadence yet

### 2. `restock-check.py` — Smart buy alerts (due + on sale)

Cross-references due items against current Costco coupons.

```bash
python3 ~/.openclaw/skills/smart-restock-alert/scripts/restock-check.py

# Use cached coupons (faster)
--coupons /tmp/costco-coupons.json
--due-window 14         # days overdue threshold (default 14)
--min-purchases 2       # min purchase history (default 2)
```

**Output sections:**
- `alerts` — items due/overdue AND currently on sale → **buy now**
- `due_no_sale` — items due but no current coupon
- `upcoming_soon` — due within 14 days (buy ahead if on sale)

## Presenting results to Robison

### Buying patterns (full report)
Summarize the report in a readable Telegram message. Highlight:
- Items due or overdue
- Items with established cadence (bought 2+ times)
- Any patterns worth noting (e.g. "you buy butter every 3 days")

### Restock alerts
```
🛒 Smart Restock Alert

🎯 BUY NOW — on sale + you're due:
• KS Bacon — buy every ~25 days, last bought Apr 17
  On sale: $22.99 (save $4) until May 24

📦 DUE but no current sale:
• Mini Cucumbers (1 day overdue)
• Butter (due today)

⏰ Coming up soon:
• KS Sour Cream — due in 9 days
```

## Data sources

- DB: `~/.grocery-receipts/db/groceries.db` (table: `purchase_patterns`)
- Coupons: fetched via `~/.openclaw/skills/costco-coupons/scripts/fetch-coupons.py`

## Cron integration

The Friday 8am cron job (`costco-coupon-refund-check`) runs both scripts and sends a combined Telegram message with refund opportunities + restock alerts.

## Improving match accuracy

The `MATCH_HINTS` dict in `restock-check.py` maps DB item name fragments to coupon keywords. Add entries when false positives or missed matches occur. The more receipts in the DB, the better the cadence data.
