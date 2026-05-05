#!/usr/bin/env python3
"""
Ollama text parser: feeds raw OCR text to a local LLM and returns structured JSON.
Uses gemma4:e4b (already installed) by default.
"""

import sys
import json
import urllib.request
import urllib.error

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
DEFAULT_MODEL = 'gemma4:e4b'

PROMPT_TEMPLATE = """You are a grocery receipt parser. Extract structured data from this receipt text.

Return ONLY valid JSON with this exact schema (no markdown, no explanation):
{{
  "store": "store name",
  "location": "city/location if present",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "items": [
    {{"name": "item name", "price": 0.00, "qty": 1, "category": "produce|dairy|meat|grocery|household|other"}}
  ],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "Visa|Cash|Debit|etc",
  "transaction_id": "id if present"
}}

Rules:
- Prices must be numbers (not strings)
- Date must be YYYY-MM-DD format
- If a field is unknown, use null
- Do NOT include any text outside the JSON

Receipt text:
{text}"""

def parse_with_ollama(ocr_text: str, model: str = DEFAULT_MODEL) -> dict:
    prompt = PROMPT_TEMPLATE.format(text=ocr_text)

    payload = json.dumps({
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': {'temperature': 0.1}  # Low temp for consistent JSON
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            raw_response = result.get('response', '')

            # Strip markdown code blocks if present
            raw_response = raw_response.strip()
            if raw_response.startswith('```'):
                raw_response = raw_response.split('```')[1]
                if raw_response.startswith('json'):
                    raw_response = raw_response[4:]
            raw_response = raw_response.strip()

            structured = json.loads(raw_response)
            return {
                'success': True,
                'method': 'ollama-text',
                'model': model,
                'structured': structured
            }

    except urllib.error.URLError as e:
        return {
            'success': False,
            'method': 'ollama-text',
            'error': f'Ollama not reachable at {OLLAMA_URL}: {e}',
            'structured': None
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'method': 'ollama-text',
            'error': f'LLM returned invalid JSON: {e}',
            'raw_response': raw_response if 'raw_response' in dir() else '',
            'structured': None
        }
    except Exception as e:
        return {
            'success': False,
            'method': 'ollama-text',
            'error': str(e),
            'structured': None
        }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: parse-ollama.py <ocr_json_file>'}))
        sys.exit(1)

    with open(sys.argv[1]) as f:
        ocr_data = json.load(f)

    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    text = ocr_data.get('text', '')

    if not text.strip():
        print(json.dumps({'success': False, 'error': 'No text in OCR output'}))
        sys.exit(1)

    result = parse_with_ollama(text, model)
    print(json.dumps(result, indent=2))
