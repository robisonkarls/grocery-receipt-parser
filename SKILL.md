# Grocery Receipt Parser — OpenClaw Skill

Parse grocery receipts into searchable, structured data via Telegram, Discord, Slack, or any OpenClaw channel.

## Installation

```bash
# 1. Install the tool
git clone https://github.com/robison/grocery-receipt-parser ~/projects/grocery-receipt-parser
cd ~/projects/grocery-receipt-parser
./install.sh

# 2. Link as OpenClaw skill (optional, for slash commands)
mkdir -p ~/.openclaw/skills
ln -s ~/projects/grocery-receipt-parser ~/.openclaw/skills/grocery-receipt-parser
```

## Usage

### Parse Receipt

**Send a photo in Telegram/Discord/Slack:**

```
📷 *attach receipt photo*
"Parse this receipt"
```

**Agent behavior**:
1. Save photo to `~/.grocery-receipts/receipts/images/`
2. Run Tesseract OCR
3. If confidence < 0.7 → fallback to EasyOCR
4. If confidence < 0.7 → fallback to Claude Vision
5. Extract structured data (store, date, items, total)
6. Generate Markdown receipt
7. Insert into SQLite database
8. Update QMD index
9. Reply with summary

### Search Receipts

**Natural language queries:**

```
/grocery-search organic strawberries
/grocery-search what did I buy at Costco last month
/grocery-search expensive cheese
```

Uses QMD semantic search on indexed receipt Markdown files.

### Analytics

```
/grocery-stats costco spending may
/grocery-stats average price per category
/grocery-stats items due for repurchase
```

Runs SQLite queries on structured receipt data.

## Agent Implementation

When the agent receives a photo message with "parse" intent:

```python
# Example OpenClaw agent pseudo-code
if message.has_photo and "parse" in message.text.lower():
    photo_path = save_attachment(message.photo)
    result = exec("parse-receipt", photo_path)
    reply(f"✅ Receipt parsed!\n{result.summary}")
```

## Commands

### `/parse-receipt <photo>`
Parse a receipt photo (if photo is attached, this is implicit).

### `/grocery-search <query>`
Search receipts with natural language.

### `/grocery-stats <query>`
Run analytics queries.

## Data Storage

- **Images**: `~/.grocery-receipts/receipts/images/*.jpg`
- **Markdown**: `~/.grocery-receipts/receipts/*.md` (QMD-indexed)
- **Database**: `~/.grocery-receipts/db/groceries.db`

## Requirements

- Tesseract OCR: `brew install tesseract`
- ImageMagick: `brew install imagemagick`
- SQLite3: `brew install sqlite3`
- QMD (optional): For semantic search
- Claude API (optional): For vision fallback

## Privacy

All data stays local. No cloud services required (except optional Claude Vision fallback).

## Roadmap

- [x] Tesseract OCR
- [x] Markdown generation
- [x] SQLite storage
- [x] QMD indexing
- [ ] OCR → structured data parser
- [ ] EasyOCR fallback
- [ ] Claude Vision fallback
- [ ] Purchase prediction alerts
- [ ] Telegram/Discord native integration

## Contributing

This is a community tool. PRs welcome!

Repo: https://github.com/robison/grocery-receipt-parser
