# Grocery Receipt Parser

**Parse grocery receipts into searchable, structured data.**

Hybrid OCR + Vision LLM pipeline that extracts receipt data and stores it for semantic search and analytics. Works on **macOS, Linux, and Windows**.

---

## Features

- 📸 **OCR extraction** — Tesseract → EasyOCR → Claude Vision fallback
- 📝 **Markdown storage** — Human-readable, QMD-searchable receipts
- 🗄️ **SQLite analytics** — Spending totals, price trends, purchase predictions
- 🔍 **Semantic search** — Natural language queries via QMD
- 🤖 **OpenClaw integration** — Parse receipts from Telegram/Discord/Slack
- 🌍 **Cross-platform** — macOS, Linux, Windows

---

## Requirements

- Python 3.8+
- Tesseract OCR
- ImageMagick (optional, improves OCR quality)
- QMD (optional, enables semantic search)

---

## Installation

### 1. Clone

```bash
git clone https://github.com/robisonkarls/grocery-receipt-parser
cd grocery-receipt-parser
```

### 2. Install dependencies

**macOS**
```bash
brew install tesseract imagemagick
```

**Ubuntu/Debian**
```bash
sudo apt-get install tesseract-ocr imagemagick python3
```

**Windows**
```powershell
winget install tesseract    # or: choco install tesseract
winget install imagemagick  # or: choco install imagemagick
```

### 3. Run installer

```bash
python3 install.py
```

**Custom data directory:**
```bash
GROCERY_DATA_DIR=/external/drive python3 install.py         # macOS/Linux
set GROCERY_DATA_DIR=D:\MyData && python3 install.py        # Windows
```

This creates your data directory (default: `~/.grocery-receipts`) and saves the path to `config.json` so you don't need to set the env var again.

---

## Usage

### Parse a receipt

```bash
# macOS/Linux
python3 bin/parse_receipt.py photo.jpg

# Windows
python bin\parse_receipt.py photo.jpg

# Or via shell launcher (macOS/Linux)
bin/parse-receipt photo.jpg

# Or via Windows launcher
bin\parse-receipt.bat photo.jpg
```

### Search receipts (requires QMD)

```bash
qmd query "organic strawberries" -c grocery-receipts
qmd query "what did I buy at Costco last month?" -c grocery-receipts
qmd query "expensive cheese" -c grocery-receipts
```

### Analytics (SQLite)

```bash
sqlite3 ~/.grocery-receipts/db/groceries.db \
  "SELECT store_name, receipt_date, total_amount FROM receipts ORDER BY receipt_date DESC;"
```

### With OpenClaw (Telegram/Discord/Slack)

```
📷 *send receipt photo*
"parse this receipt"

/grocery-search organic fruit
/grocery-stats costco may spending
```

---

## Data layout

```
~/.grocery-receipts/          ← default, or GROCERY_DATA_DIR
├── config.json               ← set by installer
├── receipts/
│   ├── images/               ← original photos
│   └── *.md                  ← structured Markdown (QMD-indexed)
└── db/
    └── groceries.db          ← SQLite for analytics
```

---

## Architecture

```
Receipt Photo
    ↓
Tesseract OCR (fast, free, local)
    ↓ (confidence < 70%)
EasyOCR (better on warped images)       [TODO]
    ↓ (confidence < 70%)
Claude Vision (handles anything)        [TODO]
    ↓
Structured JSON
    ↓
├── Markdown file → QMD semantic search
└── SQLite row   → analytics + predictions
```

---

## Roadmap

- [x] Cross-platform installer (Python)
- [x] Tesseract OCR wrapper
- [x] Markdown generator
- [x] SQLite schema + inserter
- [x] Purchase pattern tracking
- [x] QMD semantic search setup
- [ ] OCR text → structured data parser
- [ ] EasyOCR fallback
- [ ] Claude Vision fallback
- [ ] Full end-to-end pipeline
- [ ] OpenClaw SKILL integration
- [ ] Purchase prediction alerts

---

## Contributing

PRs welcome. This is built for the OpenClaw community.

---

## License

MIT
