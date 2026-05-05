#!/usr/bin/env python3
"""
Grocery Receipt Parser — Cross-platform installer
Works on macOS, Linux, and Windows.
"""

import os
import sys
import json
import sqlite3
import platform
import subprocess
from pathlib import Path

# ─── Resolve data directory ────────────────────────────────────────────────────
# Priority: GROCERY_DATA_DIR env > default ~/.grocery-receipts
DEFAULT_DATA_DIR = Path.home() / '.grocery-receipts'
DATA_DIR = Path(os.environ.get('GROCERY_DATA_DIR', DEFAULT_DATA_DIR))
REPO_DIR = Path(__file__).parent.resolve()
OS = platform.system()  # 'Darwin', 'Linux', 'Windows'

def print_header():
    print("🛒 Grocery Receipt Parser — Installer")
    print(f"   OS:      {OS} ({platform.machine()})")
    print(f"   Python:  {sys.version.split()[0]}")
    print(f"   Data:    {DATA_DIR}")
    print(f"   Repo:    {REPO_DIR}")
    print(f"   (Override: GROCERY_DATA_DIR=/custom/path python3 install.py)")
    print()

def create_directories():
    print("📁 Creating directories...")
    (DATA_DIR / 'receipts' / 'images').mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'db').mkdir(parents=True, exist_ok=True)
    print("   ✅ Done")

def create_database():
    print("🗄️  Creating database...")
    db_path = DATA_DIR / 'db' / 'groceries.db'
    schema_path = REPO_DIR / 'schema.sql'

    if not schema_path.exists():
        print(f"   ❌ schema.sql not found at {schema_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text())
    conn.close()
    print(f"   ✅ {db_path}")

def save_config():
    print("💾 Saving config...")
    config = {
        "dataDir": str(DATA_DIR),
        "receiptsDir": str(DATA_DIR / 'receipts'),
        "imagesDir": str(DATA_DIR / 'receipts' / 'images'),
        "dbPath": str(DATA_DIR / 'db' / 'groceries.db'),
        "repoDir": str(REPO_DIR),
        "os": OS
    }
    config_path = DATA_DIR / 'config.json'
    config_path.write_text(json.dumps(config, indent=2))
    print(f"   ✅ {config_path}")

def cmd_exists(cmd):
    """Check if a command exists on the system."""
    import shutil
    return shutil.which(cmd) is not None

def install_hint(package):
    """Return OS-appropriate install instruction."""
    hints = {
        'Darwin': f"brew install {package}",
        'Linux':  f"sudo apt-get install {package}  # or: sudo dnf install {package}",
        'Windows': f"winget install {package}  # or: choco install {package}"
    }
    return hints.get(OS, f"install {package}")

def check_dependencies():
    print("📦 Checking dependencies...")
    missing = []

    # Tesseract
    if cmd_exists('tesseract'):
        result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
        version = result.stderr.split('\n')[0] if result.stderr else 'installed'
        print(f"   ✅ Tesseract: {version}")
    else:
        print(f"   ❌ Tesseract not found")
        print(f"      Install: {install_hint('tesseract')}")
        if OS == 'Linux':
            print(f"      Ubuntu/Debian: sudo apt-get install tesseract-ocr")
        missing.append('tesseract')

    # ImageMagick (optional)
    if cmd_exists('magick') or cmd_exists('convert'):
        print(f"   ✅ ImageMagick installed")
    else:
        print(f"   ⚠️  ImageMagick not found (optional, improves OCR quality)")
        print(f"      Install: {install_hint('imagemagick')}")

    # SQLite3
    print(f"   ✅ SQLite3: {sqlite3.sqlite_version} (built-in)")

    # Python packages
    try:
        import PIL
        print(f"   ✅ Pillow installed")
    except ImportError:
        print(f"   ⚠️  Pillow not found (optional)")
        print(f"      Install: pip install pillow")

    return missing

def setup_qmd():
    """Set up QMD collection for semantic search.

    Strategy: cd into DATA_DIR and name the collection 'receipts'.
    QMD derives the path as cwd+name = DATA_DIR/receipts — always correct,
    no SQLite patching needed, works on any OS.
    """
    if not cmd_exists('qmd'):
        print("   ⚠️  QMD not found (optional, enables semantic search)")
        print("      Install: https://github.com/tobilu/qmd")
        return

    print("   ✅ QMD found")

    # Remove old collection (any name) cleanly
    subprocess.run(['qmd', 'collection', 'remove', 'receipts'],
                   capture_output=True, cwd=str(DATA_DIR))
    subprocess.run(['qmd', 'collection', 'remove', 'grocery-receipts'],
                   capture_output=True)

    # Add collection named 'receipts' from DATA_DIR.
    # QMD derives path as: cwd + name = DATA_DIR/receipts ✅
    result = subprocess.run(
        ['qmd', 'collection', 'add', 'receipts', '--pattern', '*.md'],
        capture_output=True, text=True, cwd=str(DATA_DIR)
    )

    if result.returncode == 0:
        print(f"   ✅ QMD collection 'receipts' → {DATA_DIR / 'receipts'}")
        subprocess.run(['qmd', 'update', '-c', 'receipts'],
                       capture_output=True, cwd=str(DATA_DIR))
        print("   ✅ QMD index updated")
    else:
        print(f"   ⚠️  QMD collection setup failed: {result.stderr.strip()}")

def print_path_hint():
    bin_dir = REPO_DIR / 'bin'
    if OS == 'Windows':
        print(f"⚠️  Add to your PATH:")
        print(f"   setx PATH \"%PATH%;{bin_dir}\"")
        print(f"   setx GROCERY_DATA_DIR \"{DATA_DIR}\"")
    else:
        shell_profile = '~/.zshrc' if OS == 'Darwin' else '~/.bashrc'
        print(f"⚠️  Add to {shell_profile} to use globally:")
        print(f"   export PATH=\"$PATH:{bin_dir}\"")
        print(f"   export GROCERY_DATA_DIR=\"{DATA_DIR}\"")

def main():
    print_header()
    create_directories()
    create_database()
    save_config()

    print()
    missing = check_dependencies()

    print()
    print("🔍 Setting up QMD (semantic search)...")
    setup_qmd()

    print()
    print_path_hint()

    print()
    if missing:
        print(f"⚠️  Missing required dependencies: {', '.join(missing)}")
        print("   Install them and re-run this script.")
    else:
        print("✅ Installation complete!")
        print()
        print(f"   Try: python3 {REPO_DIR / 'bin' / 'parse_receipt.py'} <receipt.jpg>")

if __name__ == '__main__':
    main()
