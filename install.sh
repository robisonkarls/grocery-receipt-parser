#!/bin/bash
set -e

echo "🛒 Installing Grocery Receipt Parser..."
echo ""

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Data directory ────────────────────────────────────────────────────────────
# Default: ~/.grocery-receipts
# Override: GROCERY_DATA_DIR=/custom/path ./install.sh
DATA_DIR="${GROCERY_DATA_DIR:-$HOME/.grocery-receipts}"
echo "📁 Data directory: $DATA_DIR"
echo "   (Override with: GROCERY_DATA_DIR=/your/path ./install.sh)"
echo ""

# ─── Create directories ────────────────────────────────────────────────────────
mkdir -p "$DATA_DIR/receipts/images"
mkdir -p "$DATA_DIR/db"
echo "✅ Directories created"

# ─── Save config ───────────────────────────────────────────────────────────────
cat > "$DATA_DIR/config.json" << EOF
{
  "dataDir": "$DATA_DIR",
  "receiptsDir": "$DATA_DIR/receipts",
  "imagesDir": "$DATA_DIR/receipts/images",
  "dbPath": "$DATA_DIR/db/groceries.db",
  "repoDir": "$REPO_DIR"
}
EOF
echo "✅ Config saved: $DATA_DIR/config.json"

# ─── Create database ───────────────────────────────────────────────────────────
sqlite3 "$DATA_DIR/db/groceries.db" < "$REPO_DIR/schema.sql"
echo "✅ Database created: $DATA_DIR/db/groceries.db"

# ─── PATH hint ─────────────────────────────────────────────────────────────────
echo ""
if ! echo "$PATH" | grep -q "$REPO_DIR/bin"; then
    echo "⚠️  Add to your shell profile to use 'parse-receipt' globally:"
    echo "    export PATH=\"\$PATH:$REPO_DIR/bin\""
    echo "    export GROCERY_DATA_DIR=\"$DATA_DIR\""
fi

# ─── Check dependencies ────────────────────────────────────────────────────────
echo ""
echo "📦 Checking dependencies..."

MISSING=0

if ! command -v tesseract &> /dev/null; then
    echo "❌ Tesseract not found."
    echo "   macOS:  brew install tesseract"
    echo "   Ubuntu: apt-get install tesseract-ocr"
    MISSING=1
else
    echo "✅ Tesseract: $(tesseract --version 2>&1 | head -1)"
fi

if ! command -v magick &> /dev/null && ! command -v convert &> /dev/null; then
    echo "⚠️  ImageMagick not found (optional, improves OCR quality)"
    echo "   macOS:  brew install imagemagick"
    echo "   Ubuntu: apt-get install imagemagick"
else
    echo "✅ ImageMagick installed"
fi

if ! command -v sqlite3 &> /dev/null; then
    echo "❌ SQLite3 not found."
    echo "   macOS:  brew install sqlite3"
    echo "   Ubuntu: apt-get install sqlite3"
    MISSING=1
else
    echo "✅ SQLite3 installed"
fi

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found."
    echo "   macOS:  brew install python3"
    echo "   Ubuntu: apt-get install python3"
    MISSING=1
else
    echo "✅ Python3: $(python3 --version)"
fi

# ─── QMD setup (optional) ──────────────────────────────────────────────────────
echo ""
if ! command -v qmd &> /dev/null; then
    echo "⚠️  QMD not found (optional, enables semantic search)"
    echo "   Install: https://github.com/tobilu/qmd"
else
    echo "✅ QMD installed"
    echo "🔍 Setting up QMD collection..."

    # Remove existing collection if any
    qmd collection remove grocery-receipts 2>/dev/null || true

    # Add collection (qmd has a path-derivation bug, so we patch the DB after)
    qmd collection add grocery-receipts "$DATA_DIR/receipts" --pattern '*.md' 2>/dev/null || true

    # Find QMD's SQLite index path dynamically
    QMD_DB=$(qmd --help 2>&1 | grep "^Index:" | awk '{print $2}')
    QMD_DB="${QMD_DB:-$HOME/.cache/qmd/index.sqlite}"

    # Patch the path directly (workaround for qmd collection add path bug)
    if [ -f "$QMD_DB" ]; then
        sqlite3 "$QMD_DB" \
            "UPDATE store_collections SET path = '$DATA_DIR/receipts' WHERE name = 'grocery-receipts';" \
            2>/dev/null || true
        echo "✅ QMD collection path set to: $DATA_DIR/receipts"
        qmd update -c grocery-receipts 2>/dev/null || true
    else
        echo "⚠️  QMD index not found at: $QMD_DB"
    fi
fi

# ─── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [ "$MISSING" = "1" ]; then
    echo "⚠️  Some required dependencies are missing. Please install them and re-run."
else
    echo "✅ Installation complete!"
    echo ""
    echo "   Data:    $DATA_DIR"
    echo "   Repo:    $REPO_DIR"
    echo ""
    echo "   Try: $REPO_DIR/bin/parse-receipt <receipt-photo.jpg>"
fi
