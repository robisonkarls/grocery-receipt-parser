# Grocery Receipt Parser

**Parse grocery receipts into searchable, structured data.**

Hybrid OCR + Vision LLM pipeline that extracts receipt data and stores it for semantic search and analytics.

## Features

- 📸 **OCR extraction** — Tesseract → EasyOCR → Claude Vision fallback
- 📝 **Markdown storage** — Human-readable, QMD-searchable receipts
- 🗄️ **SQLite analytics** — Spending totals, price trends, purchase predictions
- 🔍 **Semantic search** — Natural language queries via QMD
- 🤖 **OpenClaw integration** — Parse receipts from Telegram/Discord/Slack

---

## Installation

### Prerequisites

```bash
# macOS
brew install tesseract imagemagick sqlite3

# Optional: EasyOCR for better accuracy
pip3 install easyocr
```

### Install

```bash
git clone https://github.com/robison/grocery-receipt-parser
cd grocery-receipt-parser
./install.sh
```

This creates `~/.grocery-receipts/` for your receipt data.

---

## Usage

### Standalone CLI

```bash
# Parse a receipt
parse-receipt photo.jpg

# Search receipts (requires QMD)
grocery-search "organic strawberries"
grocery-search "what did I buy at Costco last month?"

# Analytics (SQLite queries)
sqlite3 ~/.grocery-receipts/db/groceries.db "SELECT SUM(total_amount) FROM receipts WHERE strftime('%Y-%m', receipt_date) = '2026-05'"
```

### With OpenClaw

Add this repo as an OpenClaw skill:

```bash
cd ~/.openclaw/agents/<your-agent>/workspace
ln -s ~/projects/grocery-receipt-parser SKILL-grocery-receipt-parser
```

Then in Telegram/Discord/Slack:

```
📷 *send receipt photo*
/parse-receipt

🔍 /grocery-search organic fruit
📊 /grocery-stats costco spending may
```

---

## Architecture

### Hybrid Storage: QMD + SQLite

- **QMD** (Markdown + embeddings) for semantic search
- **SQLite** for structured queries and analytics

### Pipeline

```
Receipt Photo
    ↓
Tesseract OCR (fast, free)
    ↓ (if confidence < 0.7)
EasyOCR (better quality)
    ↓ (if confidence < 0.7)
Claude Vision (handles messy receipts)
    ↓
Structured JSON
    ↓
├─→ Markdown file (~/.grocery-receipts/receipts/*.md)
└─→ SQLite database (~/.grocery-receipts/db/groceries.db)
    ↓
QMD indexing (semantic search)
```

### Data Layout

```
~/.grocery-receipts/
├── receipts/
│   ├── images/           # Original photos
│   └── *.md              # Markdown receipts (QMD-indexed)
├── db/
│   └── groceries.db      # SQLite for analytics
└── config.json           # User config (optional)
```

---

## Semantic Search Examples

```bash
# What fruit did I buy last month?
grocery-search "fruit purchases april 2026"

# Find that expensive cheese
grocery-search "expensive aged cheddar costco"

# Show all organic products
grocery-search "organic vegetables dairy eggs"
```

---

## Analytics Examples

```sql
-- Total spending per month
SELECT 
  strftime('%Y-%m', receipt_date) as month,
  SUM(total_amount) as total
FROM receipts
GROUP BY month
ORDER BY month DESC;

-- Average price per item category
SELECT 
  category,
  AVG(total_price) as avg_price,
  COUNT(*) as times_purchased
FROM items
WHERE category IS NOT NULL
GROUP BY category;

-- Items due for repurchase
SELECT 
  item_name,
  last_purchase_date,
  julianday('now') - julianday(last_purchase_date) as days_since
FROM purchase_patterns
WHERE days_since > avg_days_between_purchase
ORDER BY days_since DESC;
```

---

## Roadmap

- [x] Tesseract OCR wrapper
- [x] Markdown generator
- [x] SQLite schema + inserter
- [x] QMD collection setup
- [ ] OCR text → structured data parser
- [ ] EasyOCR fallback
- [ ] Claude Vision fallback
- [ ] Main orchestrator script
- [ ] OpenClaw SKILL.md
- [ ] Purchase prediction engine
- [ ] Web UI for manual review

---

## Contributing

PRs welcome! This is built for the OpenClaw community.

---

## License

MIT
