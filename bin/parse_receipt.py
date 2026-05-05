#!/usr/bin/env python3
"""
parse-receipt — Grocery receipt parser
Pipeline: OpenCV preprocessing → PaddleOCR → Ollama text parser → Ollama vision fallback

Usage:
  python3 parse_receipt.py <image_path>
  GROCERY_DATA_DIR=/custom/path python3 parse_receipt.py <image_path>
"""

import os
import sys
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from datetime import datetime

REPO_DIR = Path(__file__).parent.parent.resolve()
SCRIPTS  = REPO_DIR / 'scripts'

# ─── Resolve data directory ────────────────────────────────────────────────────
def resolve_data_dir():
    if os.environ.get('GROCERY_DATA_DIR'):
        return Path(os.environ['GROCERY_DATA_DIR'])
    config_path = Path.home() / '.grocery-receipts' / 'config.json'
    if config_path.exists():
        try:
            return Path(json.loads(config_path.read_text())['dataDir'])
        except Exception:
            pass
    return Path.home() / '.grocery-receipts'

DATA_DIR     = resolve_data_dir()
IMAGES_DIR   = DATA_DIR / 'receipts' / 'images'
RECEIPTS_DIR = DATA_DIR / 'receipts'
DB_PATH      = DATA_DIR / 'db' / 'groceries.db'
CONF_THRESHOLD = 0.80  # Below this → try next method

def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'db').mkdir(parents=True, exist_ok=True)

def run_script(script: str, *args) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {'success': False, 'error': result.stderr or result.stdout}

def update_qmd():
    if shutil.which('qmd'):
        subprocess.run(['qmd', 'update', '-c', 'receipts'],
                       capture_output=True, cwd=str(DATA_DIR))
        subprocess.run(['qmd', 'embed', '-c', 'receipts'],
                       capture_output=True, cwd=str(DATA_DIR))
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
    receipt_id = f"{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    tmp = Path(f'/tmp/{receipt_id}')

    print(f"📸 Receipt ID: {receipt_id}")
    print(f"   Source: {image_path}")

    # ── Step 1: Save original image ──────────────────────────────────────────
    dest_image = IMAGES_DIR / f"{receipt_id}.jpg"
    shutil.copy2(image_path, dest_image)
    print(f"   ✅ Image saved")

    # ── Step 2: OpenCV preprocessing ─────────────────────────────────────────
    print("\n🔧 Preprocessing image...")
    pre_path = str(tmp) + '-pre.jpg'
    pre_result = run_script('preprocess.py', str(dest_image), pre_path)
    if pre_result.get('success'):
        ocr_input = pre_path
        print(f"   ✅ Preprocessed (deskew: {pre_result.get('deskew_angle', 0)}°)")
    else:
        ocr_input = str(dest_image)
        print(f"   ⚠️  Preprocessing failed, using original")

    # ── Step 3: PaddleOCR ────────────────────────────────────────────────────
    print("\n🔍 Running PaddleOCR...")
    ocr_result = run_script('ocr-paddle.py', ocr_input)
    ocr_conf = ocr_result.get('confidence', 0.0)
    ocr_text = ocr_result.get('text', '')

    if ocr_result.get('success') and ocr_conf >= CONF_THRESHOLD:
        print(f"   ✅ Confidence: {ocr_conf:.0%} — good quality")
        method = 'paddleocr'
    elif ocr_result.get('success') and ocr_text:
        print(f"   ⚠️  Confidence: {ocr_conf:.0%} — low, will try LLM parser anyway")
        method = 'paddleocr-low'
    else:
        print(f"   ❌ PaddleOCR failed: {ocr_result.get('error', 'unknown')}")
        print(f"   ↳ Falling back to vision LLM...")
        method = 'vision-fallback'

    # ── Step 4: Parse text with Ollama ───────────────────────────────────────
    structured = None

    if method in ('paddleocr', 'paddleocr-low') and ocr_text.strip():
        print("\n🧠 Parsing with Ollama (gemma4:e4b)...")
        ocr_json_path = str(tmp) + '-ocr.json'
        Path(ocr_json_path).write_text(json.dumps(ocr_result))

        parse_result = run_script('parse-ollama.py', ocr_json_path)
        if parse_result.get('success') and parse_result.get('structured'):
            structured = parse_result['structured']
            method = f"paddleocr+ollama"
            print(f"   ✅ Parsed successfully")
            items_count = len(structured.get('items', []))
            print(f"   📦 Items found: {items_count}")
        else:
            print(f"   ❌ Ollama parsing failed: {parse_result.get('error', 'unknown')}")
            print(f"   ↳ Falling back to vision LLM...")
            method = 'vision-fallback'

    # ── Step 5: Vision LLM fallback ──────────────────────────────────────────
    if method == 'vision-fallback' or structured is None:
        print("\n👁️  Running vision fallback (Ollama llava)...")
        vision_result = run_script('vision-ollama.py', str(dest_image))
        if vision_result.get('success') and vision_result.get('structured'):
            structured = vision_result['structured']
            method = 'ollama-vision'
            print(f"   ✅ Vision extraction succeeded")
            items_count = len(structured.get('items', []))
            print(f"   📦 Items found: {items_count}")
        else:
            print(f"   ❌ Vision fallback failed: {vision_result.get('error', 'unknown')}")
            print(f"\n⚠️  All extraction methods failed. Raw OCR text saved for manual review.")
            print(f"   OCR text:\n{ocr_text[:500]}")
            sys.exit(1)

    # ── Step 6: Generate Markdown ─────────────────────────────────────────────
    print("\n📝 Generating Markdown receipt...")
    full_data = {
        'success': True,
        'method': method,
        'confidence': ocr_conf,
        'text': ocr_text,
        'structured': structured
    }
    full_json_path = str(tmp) + '-full.json'
    Path(full_json_path).write_text(json.dumps(full_data, indent=2))

    md_result = subprocess.run(
        [sys.executable, str(SCRIPTS / 'generate-markdown.py'), full_json_path],
        capture_output=True, text=True
    )
    if md_result.returncode == 0:
        md_path = RECEIPTS_DIR / f"{receipt_id}.md"
        md_path.write_text(md_result.stdout)
        print(f"   ✅ {md_path.name}")
    else:
        print(f"   ⚠️  Markdown generation failed: {md_result.stderr[:200]}")

    # ── Step 7: Insert into SQLite ────────────────────────────────────────────
    print("\n🗄️  Saving to database...")
    db_result = run_script('db-insert.py', receipt_id, full_json_path, str(dest_image))
    if db_result.get('success'):
        print(f"   ✅ {db_result.get('items_inserted', 0)} items inserted")
    else:
        print(f"   ⚠️  DB insert failed: {db_result.get('error', 'unknown')}")

    # ── Step 8: Update QMD ───────────────────────────────────────────────────
    print("\n🔍 Updating QMD index...")
    update_qmd()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
✅ Receipt parsed successfully!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏪  Store:   {structured.get('store', 'Unknown')}
📅  Date:    {structured.get('date', 'Unknown')}
💰  Total:   ${structured.get('total', 0):.2f}
📦  Items:   {len(structured.get('items', []))}
🔬  Method:  {method}
📄  ID:      {receipt_id}
""")

if __name__ == '__main__':
    main()
