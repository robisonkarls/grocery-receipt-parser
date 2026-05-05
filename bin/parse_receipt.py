#!/usr/bin/env python3
"""
parse-receipt — Cross-platform grocery receipt parser
Works on macOS, Linux, and Windows.

Usage:
  python3 parse_receipt.py <image_path>
  GROCERY_DATA_DIR=/custom/path python3 parse_receipt.py <image_path>
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import uuid
from pathlib import Path
from datetime import datetime

# ─── Resolve paths ─────────────────────────────────────────────────────────────
def resolve_config():
    """Resolve data directory from env > config.json > default."""
    if os.environ.get('GROCERY_DATA_DIR'):
        return Path(os.environ['GROCERY_DATA_DIR'])

    default = Path.home() / '.grocery-receipts'
    config_path = default / 'config.json'
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            return Path(config['dataDir'])
        except Exception:
            pass

    return default

REPO_DIR  = Path(__file__).parent.parent.resolve()
DATA_DIR  = resolve_config()
IMAGES_DIR = DATA_DIR / 'receipts' / 'images'
RECEIPTS_DIR = DATA_DIR / 'receipts'
DB_PATH   = DATA_DIR / 'db' / 'groceries.db'
OS = platform.system()

def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'db').mkdir(parents=True, exist_ok=True)

def preprocess_image(src: Path, dest: Path) -> Path:
    """Preprocess image to improve OCR accuracy. Returns path to use for OCR."""
    # Try ImageMagick v7 (magick) then v6 (convert)
    for cmd in ['magick', 'convert']:
        if shutil.which(cmd):
            try:
                args = [cmd, str(src),
                        '-auto-orient',
                        '-colorspace', 'Gray',
                        '-contrast-stretch', '0',
                        '-sharpen', '0x1',
                        str(dest)]
                subprocess.run(args, check=True, capture_output=True)
                return dest
            except subprocess.CalledProcessError:
                pass
    print("   ⚠️  ImageMagick not found, skipping preprocessing")
    return src

def run_ocr_tesseract(image_path: Path) -> dict:
    """Run Tesseract OCR and return result dict."""
    script = REPO_DIR / 'scripts' / 'ocr-tesseract.py'
    result = subprocess.run(
        [sys.executable, str(script), str(image_path)],
        capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {'success': False, 'confidence': 0.0, 'text': '', 'method': 'tesseract'}

def update_qmd():
    """Re-index QMD collection after new receipt."""
    if shutil.which('qmd'):
        subprocess.run(['qmd', 'update', '-c', 'grocery-receipts'], capture_output=True)
        subprocess.run(['qmd', 'embed', '-c', 'grocery-receipts'], capture_output=True)
        print("   ✅ QMD index updated")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)

    ensure_dirs()

    # Generate receipt ID
    receipt_id = f"{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    print(f"📸 Processing receipt: {receipt_id}")

    # Save original image
    dest_image = IMAGES_DIR / f"{receipt_id}.jpg"
    shutil.copy2(image_path, dest_image)
    print(f"   ✅ Image saved: {dest_image}")

    # Preprocess
    pre_image = DATA_DIR / f"{receipt_id}-pre.jpg"
    ocr_input = preprocess_image(dest_image, pre_image)

    # OCR
    print("🔍 Running OCR...")
    ocr_result = run_ocr_tesseract(ocr_input)
    confidence = ocr_result.get('confidence', 0.0)
    print(f"   📊 Tesseract confidence: {confidence:.0%}")

    # TODO: EasyOCR fallback (confidence < 0.7)
    # TODO: Claude Vision fallback (confidence < 0.7)
    # TODO: Parse OCR text → structured data
    # TODO: Generate Markdown receipt
    # TODO: Insert into SQLite

    # Save raw OCR for debugging
    ocr_out = DATA_DIR / f"{receipt_id}-ocr.json"
    ocr_out.write_text(json.dumps(ocr_result, indent=2))
    print(f"   💾 Raw OCR saved: {ocr_out}")

    # Update QMD index
    update_qmd()

    print()
    if confidence < 0.7:
        print("⚠️  Low OCR confidence — Claude Vision fallback not yet implemented.")
    else:
        print(f"✅ Receipt processed: {receipt_id}")
    print(f"   Data dir: {DATA_DIR}")

if __name__ == '__main__':
    main()
