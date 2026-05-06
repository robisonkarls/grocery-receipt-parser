#!/usr/bin/env python3
"""
Grocery Receipt Parser — Cross-platform installer
Works on macOS, Linux, and Windows.

Usage:
  python3 install.py                          # default ~/.grocery-receipts
  GROCERY_DATA_DIR=/custom/path python3 install.py
"""

import os
import sys
import json
import sqlite3
import platform
import subprocess
import shutil
from pathlib import Path

REPO_DIR     = Path(__file__).parent.resolve()
OS           = platform.system()
DEFAULT_DIR  = Path.home() / '.grocery-receipts'
DATA_DIR     = Path(os.environ.get('GROCERY_DATA_DIR', DEFAULT_DIR))

REQUIRED_OLLAMA_MODELS = {
    'text':   'qwen2.5:3b',     # text parser — 2GB
    'vision': 'qwen2.5vl:7b',  # vision fallback — 5.5GB
}
OLLAMA_FALLBACK = 'llama3.2:1b'   # 1.3GB fast fallback

BANNER = """
╔══════════════════════════════════════════╗
║   🛒  Grocery Receipt Parser Installer   ║
╚══════════════════════════════════════════╝"""

def title(s): print(f"\n{s}")
def ok(s):    print(f"   ✅ {s}")
def warn(s):  print(f"   ⚠️  {s}")
def err(s):   print(f"   ❌ {s}")
def info(s):  print(f"   → {s}")

def run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)

def cmd_exists(name):
    return shutil.which(name) is not None

def install_hint(pkg):
    return {
        'Darwin':  f"brew install {pkg}",
        'Linux':   f"sudo apt-get install {pkg}",
        'Windows': f"winget install {pkg}",
    }.get(OS, f"install {pkg}")

# ─── Step 1: Directories ──────────────────────────────────────────────────────

def step_directories():
    title("📁 Creating data directories...")
    (DATA_DIR / 'receipts' / 'images').mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'db').mkdir(parents=True, exist_ok=True)
    ok(f"Data dir: {DATA_DIR}")

# ─── Step 2: Database ─────────────────────────────────────────────────────────

def step_database():
    title("🗄️  Setting up database...")
    db_path = DATA_DIR / 'db' / 'groceries.db'
    schema  = REPO_DIR / 'schema.sql'
    if not schema.exists():
        err(f"schema.sql not found"); sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.executescript(schema.read_text())
    conn.close()
    ok(f"Database: {db_path}")

# ─── Step 3: Config ───────────────────────────────────────────────────────────

def step_config():
    title("💾 Saving config...")
    config = {
        "dataDir":    str(DATA_DIR),
        "receiptsDir":str(DATA_DIR / 'receipts'),
        "imagesDir":  str(DATA_DIR / 'receipts' / 'images'),
        "dbPath":     str(DATA_DIR / 'db' / 'groceries.db'),
        "repoDir":    str(REPO_DIR),
        "os":         OS
    }
    (DATA_DIR / 'config.json').write_text(json.dumps(config, indent=2))
    ok(f"Config: {DATA_DIR / 'config.json'}")

# ─── Step 4: System dependencies ─────────────────────────────────────────────

def step_system_deps():
    title("📦 Checking system dependencies...")
    missing = []

    if cmd_exists('tesseract'):
        v = run(['tesseract','--version'], capture_output=True, text=True).stderr.split('\n')[0]
        ok(f"Tesseract: {v}")
    else:
        err(f"Tesseract not found — {install_hint('tesseract')}")
        if OS == 'Linux': info("Ubuntu/Debian: sudo apt-get install tesseract-ocr")
        missing.append('tesseract')

    if cmd_exists('magick') or cmd_exists('convert'):
        ok("ImageMagick installed")
    else:
        warn(f"ImageMagick not found (optional) — {install_hint('imagemagick')}")

    ok(f"SQLite3 {sqlite3.sqlite_version} (built-in)")

    return missing

# ─── Step 5: Python packages ──────────────────────────────────────────────────

def step_python_deps():
    title("🐍 Installing Python packages...")
    req = REPO_DIR / 'requirements.txt'
    if not req.exists():
        warn("requirements.txt not found, skipping"); return

    result = run(
        [sys.executable, '-m', 'pip', 'install', '-r', str(req), '-q'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        ok("Python packages installed")
    else:
        warn(f"pip install failed: {result.stderr[:200]}")
        info("Try manually: pip install -r requirements.txt")

# ─── Step 6: QMD ─────────────────────────────────────────────────────────────

def step_qmd():
    title("🔍 Setting up QMD semantic search...")
    if not cmd_exists('qmd'):
        warn("QMD not found (optional, enables semantic search)")
        info("Install: https://github.com/tobilu/qmd")
        return

    ok("QMD found")
    receipts_dir = str(DATA_DIR / 'receipts')

    run(['qmd','collection','remove','receipts'], capture_output=True)
    run(['qmd','collection','add','receipts','--pattern','*.md'],
        capture_output=True, cwd=str(DATA_DIR))

    # Verify path using sqlite
    try:
        qmd_help = run(['qmd','--help'], capture_output=True, text=True).stdout
        qmd_db = None
        for line in qmd_help.split('\n'):
            if line.startswith('Index:'):
                qmd_db = Path(line.split(':',1)[1].strip())
        if qmd_db and qmd_db.exists():
            conn = sqlite3.connect(qmd_db)
            conn.execute(
                "UPDATE store_collections SET path=? WHERE name='receipts'",
                (receipts_dir,)
            )
            conn.commit(); conn.close()
            ok(f"QMD collection: receipts → {receipts_dir}")
    except Exception as e:
        warn(f"QMD path fix failed: {e}")

# ─── Step 7: Ollama models ────────────────────────────────────────────────────

def step_ollama():
    title("🦙 Checking Ollama models...")
    if not cmd_exists('ollama'):
        warn("Ollama not found (optional, enables LLM parsing fallback)")
        info("Install: https://ollama.com")
        return

    ok("Ollama found")

    # Check which models are installed
    result = run(['ollama','list'], capture_output=True, text=True)
    installed = result.stdout

    for role, model in REQUIRED_OLLAMA_MODELS.items():
        if model.split(':')[0] in installed:
            ok(f"{role} model: {model}")
        else:
            info(f"Pulling {role} model: {model} (this may take a few minutes)...")
            pull = run(['ollama','pull', model])
            if pull.returncode == 0:
                ok(f"{model} ready")
            else:
                warn(f"Failed to pull {model}")

    # Fast fallback
    if 'llama3.2' not in installed:
        info(f"Pulling fast fallback: {OLLAMA_FALLBACK}...")
        run(['ollama','pull', OLLAMA_FALLBACK])
        ok(f"Fallback model ready")

# ─── Step 8: OpenClaw skill registration ─────────────────────────────────────

def step_openclaw():
    title("🦞 OpenClaw integration...")
    if not cmd_exists('openclaw'):
        warn("OpenClaw not found — skipping agent skill registration")
        info("If you use OpenClaw, add this skill manually:")
        info(f"  Link {REPO_DIR}/SKILL.md into your agent's skills/ directory")
        return

    # Find active agent workspace
    result = run(['openclaw','status','--json'], capture_output=True, text=True)
    if result.returncode != 0:
        warn("Could not determine OpenClaw agent workspace")
        return

    try:
        status = json.loads(result.stdout)
        workspace = Path(status.get('workspace', ''))
        if not workspace.exists():
            warn(f"Agent workspace not found: {workspace}")
            return

        skills_dir = workspace / 'skills' / 'grocery-receipt-parser'
        skills_dir.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md into agent workspace
        skill_src  = REPO_DIR / 'SKILL.md'
        skill_dest = skills_dir / 'SKILL.md'
        import shutil as _shutil
        _shutil.copy2(skill_src, skill_dest)
        ok(f"Skill registered: {skill_dest}")
        info("OpenClaw will auto-discover the skill on next message")

    except Exception as e:
        warn(f"OpenClaw registration failed: {e}")
        info(f"Manual: copy {REPO_DIR}/SKILL.md → <agent-workspace>/skills/grocery-receipt-parser/SKILL.md")

# ─── Step 9: PATH hint ────────────────────────────────────────────────────────

def step_path_hint():
    bin_dir = REPO_DIR / 'bin'
    title("🔧 PATH setup...")
    if OS == 'Windows':
        info(f'Add to PATH: setx PATH "%PATH%;{bin_dir}"')
        info(f'Set data dir: setx GROCERY_DATA_DIR "{DATA_DIR}"')
    else:
        profile = '~/.zshrc' if OS == 'Darwin' else '~/.bashrc'
        info(f'Add to {profile}:')
        print(f'   export PATH="$PATH:{bin_dir}"')
        print(f'   export GROCERY_DATA_DIR="{DATA_DIR}"')

# ─── Step 10: Smoke test ─────────────────────────────────────────────────────

def step_test():
    title("🧪 Running smoke test...")
    test_script = REPO_DIR / 'scripts' / 'parse-regex.py'
    if not test_script.exists():
        warn("Smoke test skipped — parse-regex.py not found"); return

    import tempfile, json as _json
    sample = {
        "text": "NW CALGARY #543\n1978314 MINI CONES 12.99 2\nSUBTOTAL 12.99\nTAX 0.65\n**** TOTAL 13.64\n05/04/2026 16:35"
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        _json.dump(sample, f)
        tmp = f.name

    result = run([sys.executable, str(test_script), tmp],
                 capture_output=True, text=True)
    Path(tmp).unlink()

    try:
        out = _json.loads(result.stdout)
        if out.get('success') and out['structured'].get('total') == 13.64:
            ok("Smoke test passed — receipt parser working")
        else:
            warn(f"Smoke test: unexpected result: {result.stdout[:200]}")
    except Exception:
        warn(f"Smoke test failed: {result.stderr[:200]}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(BANNER)
    print(f"\n   OS:     {OS} ({platform.machine()})")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   Data:   {DATA_DIR}")
    print(f"   Repo:   {REPO_DIR}")
    print(f"\n   Override data dir: GROCERY_DATA_DIR=/path python3 install.py")

    step_directories()
    step_database()
    step_config()
    sys_missing = step_system_deps()
    step_python_deps()
    step_qmd()
    step_ollama()
    step_openclaw()
    step_path_hint()
    step_test()

    print("\n" + "─" * 44)
    if sys_missing:
        print(f"⚠️  Missing system deps: {', '.join(sys_missing)}")
        print("   Install them and re-run: python3 install.py")
    else:
        print("✅ Installation complete!")
        print(f"\n   Send a receipt PDF to your OpenClaw agent")
        print(f"   Or test manually:")
        print(f"   python3 {REPO_DIR}/bin/parse_receipt.py <receipt.pdf>")

if __name__ == '__main__':
    main()
