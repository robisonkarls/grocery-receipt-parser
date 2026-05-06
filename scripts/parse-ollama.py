#!/usr/bin/env python3
"""
Ollama text parser: feeds raw OCR/PDF text to a local LLM → structured JSON.
Uses qwen2.5:3b by default (fast, excellent JSON compliance).
Uses Ollama native format:"json" to force valid JSON output every time.
"""

import sys
import json
import urllib.request
import urllib.error

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
DEFAULT_MODEL = 'qwen2.5:3b'
FALLBACK_MODEL = 'llama3.2:1b'

PROMPT_TEMPLATE = """Extract structured data from this grocery receipt text.

Return a JSON object with these exact fields:
- store: store name (string)
- location: city or location (string or null)
- date: date in YYYY-MM-DD format (string)
- time: time in HH:MM format (string or null)
- items: array of items, each with name (string), price (number), qty (number, default 1), category (string: produce/dairy/meat/grocery/household/other)
- subtotal: subtotal amount (number)
- tax: tax amount (number)
- total: total amount (number)
- payment_method: payment type (string or null)
- transaction_id: transaction ID (string or null)

Rules:
- Lines with TPD/ are instant savings/discounts — include as negative price items
- KS prefix means Kirkland Signature
- Barcode numbers at start of lines should be ignored
- Trailing 2 on price lines is a tax code, not quantity
- Prices must be numbers not strings

Receipt text:
{text}"""

def parse_with_ollama(ocr_text: str, model: str = DEFAULT_MODEL) -> dict:
    payload = json.dumps({
        'model': model,
        'prompt': PROMPT_TEMPLATE.format(text=ocr_text),
        'stream': False,
        'format': 'json',  # Ollama native JSON mode — forces valid JSON output
        'options': {'temperature': 0}
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            structured = json.loads(result.get('response', '{}'))

            if not structured.get('store') and not structured.get('items'):
                return {'success': False, 'method': model,
                        'error': 'Empty response', 'structured': None}

            return {'success': True, 'method': model, 'structured': structured}

    except urllib.error.URLError as e:
        return {'success': False, 'method': model,
                'error': f'Ollama not reachable: {e}', 'structured': None}
    except Exception as e:
        return {'success': False, 'method': model,
                'error': str(e), 'structured': None}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: parse-ollama.py <ocr_json_file>'}))
        sys.exit(1)

    with open(sys.argv[1]) as f:
        ocr_data = json.load(f)

    text = ocr_data.get('text', '')
    if not text.strip():
        print(json.dumps({'success': False, 'error': 'No text in OCR output'}))
        sys.exit(1)

    # Try primary model first, fall back to llama3.2:1b
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    result = parse_with_ollama(text, model)

    if not result.get('success') and model != FALLBACK_MODEL:
        result = parse_with_ollama(text, FALLBACK_MODEL)

    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
