---
name: grocery-receipt-parser
description: >
  Parse grocery receipts into the database. Triggered when Robison sends
  a receipt image (JPG, PNG) or PDF document in Telegram. Also triggered
  by phrases like "parse this receipt", "add to database", "log this receipt",
  "scan this receipt". Handles Costco, Superstore, Save-On, and any grocery store.
---

# Grocery Receipt Parser Skill

## Trigger Conditions

- User sends a **photo** attachment (receipt image)
- User sends a **PDF/document** attachment (digital receipt)
- User says "parse", "scan", "log receipt", "add to database"

## Architecture

The agent does the LLM parsing step (not a subprocess). Scripts handle
file I/O, OCR, DB, and QMD. This avoids auth issues with external APIs.

## Step-by-Step Workflow

### Step 1 — Find the file

Inbound media lands in `~/.openclaw/media/inbound/`. Find the most recent receipt file:

```bash
ls -t ~/.openclaw/media/inbound/ | head -10
```

Match by extension: `.pdf`, `.jpg`, `.jpeg`, `.png`

### Step 2 — Extract text

**For PDF:**
```bash
python3 ~/projects/grocery-receipt-parser/scripts/extract-pdf.py <path>
```
Returns `{"success": true, "text": "...", "confidence": 1.0}`

**For image:**
```bash
# Preprocess
python3 ~/projects/grocery-receipt-parser/scripts/preprocess.py <path> /tmp/pre.jpg
# OCR
python3 ~/projects/grocery-receipt-parser/scripts/ocr-paddle.py /tmp/pre.jpg
```
Returns `{"success": true, "text": "...", "confidence": 0.xx, "lines": [...]}`

### Step 3 — Parse text into structured JSON (AGENT does this)

Use your own intelligence to parse the extracted text. Do NOT call a subprocess.

Parse the raw text into this schema:
```json
{
  "store": "store name",
  "location": "city/location",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "items": [
    {"name": "item name", "price": 0.00, "qty": 1, "category": "produce|dairy|meat|grocery|household|other"}
  ],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "Visa|Mastercard|Debit|Cash",
  "transaction_id": "id if present"
}
```

**Costco-specific rules:**
- Lines with `TPD/` prefix = instant savings/discounts (negative price)
- `KS` prefix = Kirkland Signature
- Barcode numbers at start of lines = ignore
- `2` at end of price line = tax code, not quantity

### Step 4 — Save to database + QMD

Write structured JSON to a temp file, then run:

```bash
RECEIPT_ID="$(date +%Y%m%d)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:6])')"
FULL_JSON="/tmp/${RECEIPT_ID}-full.json"

# Write JSON (agent constructs this)
echo '<structured_json>' > "$FULL_JSON"

# Generate markdown
python3 ~/projects/grocery-receipt-parser/scripts/generate-markdown.py "$FULL_JSON" \
  > ~/.grocery-receipts/receipts/${RECEIPT_ID}.md

# Insert into SQLite
python3 ~/projects/grocery-receipt-parser/scripts/db-insert.py \
  "$RECEIPT_ID" "$FULL_JSON" "<original_file_path>"

# Update QMD
cd ~/.grocery-receipts && qmd update -c receipts && qmd embed -c receipts
```

### Step 5 — Reply to user

```
✅ Receipt saved!

🏪 {store} — {location}
📅 {date} {time}
💰 Total: ${total} (tax ${tax})
💳 {payment_method}
📦 {n} items: {item1}, {item2}, ...
💾 Saved to database + search index

🔍 Try: qmd query "organic milk" -c receipts
```

## Data Paths

- Data dir: `~/.grocery-receipts/`
- Images: `~/.grocery-receipts/receipts/images/`
- Markdown: `~/.grocery-receipts/receipts/*.md`
- Database: `~/.grocery-receipts/db/groceries.db`
- QMD collection: `receipts` (collection name, not path)

## Error Handling

- OCR confidence < 0.7 on image → tell user to send a clearer photo
- PDF with no text → auto-falls back to OCR via extract-pdf.py
- DB insert fails → report the error, do not silently fail

