#!/bin/bash
set -e

echo "🛒 Installing Grocery Receipt Parser..."
echo ""

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$HOME/.grocery-receipts"

# 1. Create data directory
echo "📁 Creating data directory..."
mkdir -p "$DATA_DIR/receipts/images"
mkdir -p "$DATA_DIR/db"

# 2. Create database
echo "🗄️  Creating database..."
sqlite3 "$DATA_DIR/db/groceries.db" < "$REPO_DIR/schema.sql"

# 3. Add bin to PATH (optional)
if ! echo "$PATH" | grep -q "$REPO_DIR/bin"; then
    echo ""
    echo "⚠️  Add to your PATH to use 'parse-receipt' globally:"
    echo "    export PATH=\"\$PATH:$REPO_DIR/bin\""
    echo ""
    echo "Or create a symlink:"
    echo "    ln -s $REPO_DIR/bin/parse-receipt /usr/local/bin/parse-receipt"
fi

# 4. Check dependencies
echo ""
echo "📦 Checking dependencies..."

if ! command -v tesseract &> /dev/null; then
    echo "❌ Tesseract not found. Install: brew install tesseract"
else
    echo "✅ Tesseract installed"
fi

if ! command -v magick &> /dev/null; then
    echo "⚠️  ImageMagick not found. Install: brew install imagemagick"
else
    echo "✅ ImageMagick installed"
fi

if ! command -v sqlite3 &> /dev/null; then
    echo "❌ SQLite3 not found. Install: brew install sqlite3"
else
    echo "✅ SQLite3 installed"
fi

if ! command -v qmd &> /dev/null; then
    echo "⚠️  QMD not found (optional, for semantic search)"
else
    echo "✅ QMD installed"
    
    # 5. Set up QMD collection
    echo ""
    echo "🔍 Setting up QMD collection..."
    # Note: qmd collection add has a path derivation bug, so we patch the DB directly
    qmd collection remove grocery-receipts 2>/dev/null || true
    qmd collection add grocery-receipts "$DATA_DIR/receipts" --pattern '*.md'
    QMD_DB=$(sqlite3 /Users/bot/.cache/qmd/index.sqlite ".databases" 2>/dev/null | grep -o '[^ ]*index.sqlite' || echo "$HOME/.cache/qmd/index.sqlite")
    sqlite3 "$QMD_DB" "UPDATE store_collections SET path = '$DATA_DIR/receipts' WHERE name = 'grocery-receipts';" 2>/dev/null || true
    qmd update -c grocery-receipts
    echo "✅ QMD collection created"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Data directory: $DATA_DIR"
echo "Try: $REPO_DIR/bin/parse-receipt <receipt-photo.jpg>"
