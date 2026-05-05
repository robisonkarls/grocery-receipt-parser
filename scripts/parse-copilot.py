#!/usr/bin/env python3
"""
GitHub Copilot / OpenAI-compatible text parser for receipt data.
Uses the same API that OpenClaw uses — no extra API keys needed.
Reads auth from OpenClaw config.
"""

import sys, json, os, urllib.request
from pathlib import Path

# Try to read from OpenClaw config
def get_copilot_token():
    # Check env first
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN']
    # Try OpenClaw auth store
    auth_path = Path.home() / '.openclaw' / 'agents' / 'costa' / 'agent' / 'auth-profiles.json'
    if auth_path.exists():
        try:
            profiles = json.loads(auth_path.read_text()).get('profiles', {})
            for k, v in profiles.items():
                if 'token' in v:
                    return v['token']
        except Exception:
            pass
    return None

PROMPT_TEMPLATE = """Parse this grocery receipt text into structured JSON.

Rules:
- Lines with TPD/ prefix are discounts (negative prices)
- KS = Kirkland Signature brand
- Date format: convert any format to YYYY-MM-DD
- Return ONLY valid JSON, no markdown, no explanation

Schema:
{{
  "store": "store name",
  "location": "city/location",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "items": [{{"name": "item name", "price": 0.00, "qty": 1, "category": "produce|dairy|meat|grocery|household|other"}}],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "payment type",
  "transaction_id": "id if present"
}}

Receipt:
{text}"""

def parse_via_copilot(text: str) -> dict:
    token = get_copilot_token()
    if not token:
        return {'success': False, 'error': 'No GitHub token found', 'structured': None}

    payload = json.dumps({
        "model": "claude-sonnet-4.6",
        "messages": [
            {"role": "user", "content": PROMPT_TEMPLATE.format(text=text)}
        ],
        "temperature": 0.1,
        "max_tokens": 2000
    }).encode()

    req = urllib.request.Request(
        'https://api.individual.githubcopilot.com/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'Copilot-Integration-Id': 'vscode-chat',
            'Editor-Version': 'vscode/1.85.0',
            'Editor-Plugin-Version': 'copilot-chat/0.11.1',
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            raw = result['choices'][0]['message']['content'].strip()

            # Strip markdown code fences
            import re
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return {'success': False, 'error': 'No JSON in response', 'structured': None}

            structured = json.loads(m.group(0))
            return {'success': True, 'method': 'copilot', 'structured': structured}

    except Exception as e:
        return {'success': False, 'error': str(e), 'structured': None}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: parse-copilot.py <ocr_json>'}))
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    text = data.get('text', '')
    if not text.strip():
        print(json.dumps({'success': False, 'error': 'No text in input'}))
        sys.exit(1)

    result = parse_via_copilot(text)
    print(json.dumps(result, indent=2))
