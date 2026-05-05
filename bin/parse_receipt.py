#!/usr/bin/env python3
"""
parse-receipt — Grocery receipt parser
Supports: JPEG/PNG photos + PDF receipts
Pipeline: detect type → extract text → Ollama parse → fallback vision → DB + QMD

Usage:
  python3 parse_receipt.py <image_or_pdf_path>
  GROCERY_DATA_DIR=/custom/path python3 parse_receipt.py <path>
"""

import os, sys, json, shutil, subprocess, uuid
from pathlib import Path
from datetime import datetime

REPO_DIR = Path(__file__).parent.parent.resolve()
SCRIPTS  = REPO_DIR / 'scripts'
CONF_THRESHOLD = 0.85

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

def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'db').mkdir(parents=True, exist_ok=True)

def run_script(script, *args):
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
        subprocess.run(['qmd', 'update', '-c', 'receipts'], capture_output=True, cwd=str(DATA_DIR))
        subprocess.run(['qmd', 'embed',  '-c', 'receipts'], capture_output=True, cwd=str(DATA_DIR))
        print("   ✅ QMD index updated")

def parse_text(text, receipt_id):
    """Try Copilot first (fast), fall back to Ollama (local)."""
    ocr_json = DATA_DIR / f"{receipt_id}-ocr.json"
    ocr_json.write_text(json.dumps({'text': text, 'confidence': 1.0}))
    
    # Try Copilot first (fast, uses existing auth)
    result = run_script('parse-copilot.py', str(ocr_json))
    if result.get('success') and result.get('structured'):
        return result
    
    # Fallback to Ollama (local, slower)
    print("   ↳ Copilot unavailable, trying Ollama...")
    return run_script('parse-ollama.py', str(ocr_json))

def vision_fallback(image_path):
    return run_script('vision-ollama.py', str(image_path), 'llava')

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"❌ File not found: {src}"); sys.exit(1)

    ensure_dirs()
    receipt_id = f"{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    is_pdf = src.suffix.lower() == '.pdf'
    print(f"📸 Receipt ID: {receipt_id}")
    print(f"   Source: {src.name} ({'PDF' if is_pdf else 'Image'})")

    # Save original
    dest = IMAGES_DIR / f"{receipt_id}{src.suffix}"
    shutil.copy2(src, dest)

    structured = None
    method = 'unknown'
    ocr_text = ''

    # ── PDF: extract text directly (confidence = 1.0) ────────────────────────
    if is_pdf:
        print("\n📄 Extracting PDF text...")
        result = run_script('extract-pdf.py', str(src))
        if result.get('success'):
            ocr_text = result['text']
            print(f"   ✅ {len(ocr_text)} chars extracted")
            print("\n🧠 Parsing with Ollama (gemma4:e4b)...")
            parse = parse_text(ocr_text, receipt_id)
            if parse.get('success') and parse.get('structured'):
                structured = parse['structured']
                method = 'pdf+ollama'
                print(f"   ✅ {len(structured.get('items',[]))} items found")
            else:
                print(f"   ❌ {parse.get('error','unknown')}")
        else:
            print(f"   ❌ {result.get('error')}")

    # ── Image: preprocess → PaddleOCR → Ollama parse ─────────────────────────
    else:
        print("\n🔧 Preprocessing image...")
        pre = DATA_DIR / f"{receipt_id}-pre.jpg"
        pre_result = run_script('preprocess.py', str(dest), str(pre))
        ocr_input = str(pre) if pre_result.get('success') else str(dest)
        print(f"   {'✅' if pre_result.get('success') else '⚠️ '} Preprocessed")

        print("\n🔍 Running PaddleOCR...")
        ocr = run_script('ocr-paddle.py', ocr_input)
        ocr_conf = ocr.get('confidence', 0.0)
        ocr_text = ocr.get('text', '')
        print(f"   📊 Confidence: {ocr_conf:.0%}")

        if ocr.get('success') and ocr_text.strip():
            print("\n🧠 Parsing with Ollama (gemma4:e4b)...")
            parse = parse_text(ocr_text, receipt_id)
            if parse.get('success') and parse.get('structured'):
                s = parse['structured']
                if s.get('items') and s.get('store'):
                    structured = s
                    method = 'paddleocr+ollama'
                    print(f"   ✅ {len(s.get('items',[]))} items found")
                else:
                    print(f"   ⚠️  0 items or no store — switching to vision fallback")

        if not structured:
            print("\n👁️  Running vision fallback (llava)...")
            vis = vision_fallback(dest)
            if vis.get('success') and vis.get('structured'):
                structured = vis['structured']
                method = 'vision-llava'
                print(f"   ✅ {len(structured.get('items',[]))} items found")
            else:
                print(f"   ❌ {vis.get('error','unknown')}")
                print("\n⚠️  All methods failed. Send a clearer photo.")
                sys.exit(1)

    if not structured:
        print("\n⚠️  Could not extract data."); sys.exit(1)

    # ── Generate Markdown ─────────────────────────────────────────────────────
    print("\n📝 Generating Markdown...")
    full = {'success': True, 'method': method, 'confidence': 1.0,
            'text': ocr_text, 'structured': structured}
    full_json = DATA_DIR / f"{receipt_id}-full.json"
    full_json.write_text(json.dumps(full, indent=2))

    md = subprocess.run([sys.executable, str(SCRIPTS / 'generate-markdown.py'), str(full_json)],
                        capture_output=True, text=True)
    if md.returncode == 0:
        md_path = RECEIPTS_DIR / f"{receipt_id}.md"
        md_path.write_text(md.stdout)
        print(f"   ✅ {md_path.name}")
    else:
        print(f"   ⚠️  {md.stderr[:100]}")

    # ── Insert into SQLite ────────────────────────────────────────────────────
    print("\n🗄️  Saving to database...")
    db = run_script('db-insert.py', receipt_id, str(full_json), str(dest))
    if db.get('success'):
        print(f"   ✅ {db.get('items_inserted',0)} items inserted")
    else:
        print(f"   ⚠️  {db.get('error','unknown')}")

    # ── Update QMD ───────────────────────────────────────────────────────────
    print("\n🔍 Updating QMD index...")
    update_qmd()

    # ── Summary ──────────────────────────────────────────────────────────────
    items = structured.get('items', [])
    print(f"""
✅ Receipt parsed!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏪  Store:    {structured.get('store','Unknown')}
📍  Location: {structured.get('location') or '—'}
📅  Date:     {structured.get('date','Unknown')}  {structured.get('time','') or ''}
💰  Total:    ${structured.get('total') or 0:.2f}
🧾  Tax:      ${structured.get('tax') or 0:.2f}
📦  Items:    {len(items)}
💳  Payment:  {structured.get('payment_method') or '—'}
🔬  Method:   {method}
🆔  ID:       {receipt_id}

Items:""")
    for item in items:
        disc = " 🏷️" if item.get('price', 0) < 0 else ""
        print(f"  {'➖' if item.get('price',0) < 0 else '•'} {item['name']:30s} ${item['price']:.2f}{disc}")

if __name__ == '__main__':
    main()
