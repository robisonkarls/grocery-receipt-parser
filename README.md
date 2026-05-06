# 🛒 Grocery Receipt Parser

Parse grocery receipts (PDF or photo) into a searchable local database.
Designed as an **OpenClaw agent skill** — send a receipt to your agent and it's stored automatically.

---

## Quick Start

```bash
git clone https://github.com/robisonkarls/grocery-receipt-parser
cd grocery-receipt-parser
python3 install.py
```

That's it. The installer handles everything:
- Creates `~/.grocery-receipts/` data directory
- Sets up SQLite database
- Installs Python packages (`pip install -r requirements.txt`)
- Pulls Ollama models (if Ollama is installed)
- Registers the OpenClaw skill (if OpenClaw is installed)
- Runs a smoke test

---

## Requirements

| Dependency | Required | Install |
|-----------|----------|---------|
| Python 3.8+ | ✅ Yes | — |
| Tesseract OCR | ✅ Yes | `brew install tesseract` / `apt install tesseract-ocr` |
| ImageMagick | ⚠️ Optional | `brew install imagemagick` — improves OCR quality |
| Ollama | ⚠️ Optional | https://ollama.com — enables LLM fallback for blurry photos |
| QMD | ⚠️ Optional | https://github.com/tobilu/qmd — enables semantic search |
| OpenClaw | ⚠️ Optional | https://openclaw.ai — Telegram/Discord/Slack integration |

---

## What It Does

```
You send a receipt (PDF or photo)
            ↓
1. Extract text  →  pypdfium2 (PDF) or PaddleOCR (image)
2. Parse text    →  regex parser (fast, no LLM needed for clean PDFs)
                    ↓ fallback: Ollama qwen2.5:3b (for messy images)
                    ↓ fallback: Ollama qwen2.5vl:7b (vision, for photos)
3. Save          →  SQLite database + Markdown file
4. Index         →  QMD semantic search
5. Reply         →  Summary sent back to you
```

### Supported receipt types

| Type | Example | Method |
|------|---------|--------|
| Digital PDF | Costco emailed receipt | Text extraction (instant) |
| Scanned PDF | Photo → PDF | PaddleOCR |
| Photo (JPEG/PNG) | Phone camera shot | PaddleOCR + preprocessing |
| Grocery receipt | Items, prices, totals | Regex parser |
| Fuel receipt | Litres, price/L, GST | Regex parser |
| Refund receipt | Negative totals, TPD lines | Regex parser |

---

## OpenClaw Integration

### 1. Install OpenClaw

```bash
npm install -g openclaw
openclaw setup
```

### 2. Run the installer (registers the skill automatically)

```bash
python3 install.py
```

The installer copies `SKILL.md` into your agent's `skills/` directory.
OpenClaw auto-discovers it on the next message.

### 3. Use it

Just send a receipt to your agent:

```
📎 [attach receipt.pdf]
```

Or with text:
```
parse this receipt
```

The agent replies with:
```
✅ Receipt saved!

🏪 Costco Wholesale — NW Calgary #543
📅 2026-05-04  16:35
💰 Total: $124.32 (tax $5.92)
💳 Mastercard
📦 8 items: Mini Cones, UV Skinz, KS Towel...
```

### Manual skill registration (if installer didn't find your workspace)

```bash
# Find your agent workspace
openclaw status

# Copy SKILL.md into skills directory
mkdir -p <workspace>/skills/grocery-receipt-parser
cp SKILL.md <workspace>/skills/grocery-receipt-parser/SKILL.md
```

---

## Standalone CLI

Works without OpenClaw:

```bash
# Parse a receipt
python3 bin/parse_receipt.py receipt.pdf
python3 bin/parse_receipt.py photo.jpg

# With custom data directory
GROCERY_DATA_DIR=/external/drive python3 bin/parse_receipt.py receipt.pdf

# Query your receipts (requires QMD)
cd ~/.grocery-receipts
qmd query "organic milk" -c receipts
qmd query "what did I buy at Costco last month?" -c receipts

# SQL analytics
sqlite3 ~/.grocery-receipts/db/groceries.db \
  "SELECT store_name, receipt_date, total_amount FROM receipts ORDER BY receipt_date DESC"
```

---

## Data Layout

```
~/.grocery-receipts/         ← GROCERY_DATA_DIR (default)
├── config.json              ← set by installer
├── receipts/
│   ├── images/              ← original photos/PDFs
│   └── *.md                 ← structured Markdown (QMD-indexed)
└── db/
    └── groceries.db         ← SQLite analytics database
```

---

## Architecture

### Parser pipeline

```
extract-pdf.py      — pypdfium2 direct text (PDF) or PaddleOCR (scanned)
preprocess.py       — OpenCV grayscale + adaptive threshold + deskew (images)
ocr-paddle.py       — PaddleOCR v3 wrapper
parse-regex.py      — primary parser: regex, no LLM, instant
parse-ollama.py     — fallback: qwen2.5:3b via Ollama, format:json mode
vision-ollama.py    — fallback: qwen2.5vl:7b vision model
generate-markdown.py— structured JSON → QMD-friendly Markdown
db-insert.py        — insert receipt + items into SQLite
```

### Ollama model stack

| Role | Model | Size | When used |
|------|-------|------|-----------|
| Text parser | `qwen2.5:3b` | 2GB | When regex confidence is low |
| Vision | `qwen2.5vl:7b` | 5.5GB | When OCR fails on image |
| Fast fallback | `llama3.2:1b` | 1.3GB | If qwen times out |

> For clean PDFs, **no Ollama needed** — regex handles 100% of Costco digital receipts.

---

## Roadmap

- [x] PDF text extraction
- [x] Scanned PDF OCR
- [x] Image OCR (PaddleOCR)
- [x] Regex parser (grocery, fuel, refund receipts)
- [x] LLM fallback (qwen2.5:3b)
- [x] Vision fallback (qwen2.5vl:7b)
- [x] SQLite database
- [x] QMD semantic search
- [x] OpenClaw skill registration
- [x] Cross-platform installer
- [ ] Costco coupon/sale event parsing
- [ ] Price adjustment alerts (notify when item you bought goes on sale)
- [ ] Multi-store support (Superstore, Save-On-Foods)
- [ ] Purchase prediction (when will I need to buy X again?)

---

## Contributing

PRs welcome. Built for the OpenClaw community.

**Repo**: https://github.com/robisonkarls/grocery-receipt-parser

---

## License

MIT
