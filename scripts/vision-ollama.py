#!/usr/bin/env python3
"""
Ollama vision fallback: sends receipt image directly to a vision LLM.
Used when OCR confidence is too low.
Requires a vision model: ollama pull llava  (or moondream:1.8b)
"""

import sys
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
DEFAULT_VISION_MODEL = 'moondream:1.8b'

VISION_PROMPT = """Look at this grocery receipt image and extract all the data.

Return ONLY valid JSON with this exact schema (no markdown, no explanation):
{
  "store": "store name",
  "location": "city/location if present",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "items": [
    {"name": "item name", "price": 0.00, "qty": 1, "category": "produce|dairy|meat|grocery|household|other"}
  ],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "Visa|Cash|Debit|etc",
  "transaction_id": "id if present"
}

Rules:
- Read every line item on the receipt carefully
- Prices must be numbers (not strings)
- Date must be YYYY-MM-DD format
- If a field is unknown, use null
- Do NOT include any text outside the JSON"""

def run_vision(image_path: str, model: str = DEFAULT_VISION_MODEL) -> dict:
    # Encode image to base64
    with open(image_path, 'rb') as f:
        image_b64 = base64.b64encode(f.read()).decode('utf-8')

    payload = json.dumps({
        'model': model,
        'prompt': VISION_PROMPT,
        'images': [image_b64],
        'stream': False,
        'options': {'temperature': 0.1}
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            raw_response = result.get('response', '').strip()

            # Strip markdown code blocks if present
            if raw_response.startswith('```'):
                raw_response = raw_response.split('```')[1]
                if raw_response.startswith('json'):
                    raw_response = raw_response[4:]
            raw_response = raw_response.strip()

            structured = json.loads(raw_response)
            return {
                'success': True,
                'method': 'ollama-vision',
                'model': model,
                'structured': structured
            }

    except urllib.error.URLError as e:
        return {
            'success': False,
            'method': 'ollama-vision',
            'error': f'Ollama not reachable: {e}',
            'structured': None
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'method': 'ollama-vision',
            'error': f'Vision LLM returned invalid JSON: {e}',
            'structured': None
        }
    except Exception as e:
        return {
            'success': False,
            'method': 'ollama-vision',
            'error': str(e),
            'structured': None
        }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: vision-ollama.py <image_path> [model]'}))
        sys.exit(1)

    image_path = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VISION_MODEL

    if not Path(image_path).exists():
        print(json.dumps({'success': False, 'error': f'Image not found: {image_path}'}))
        sys.exit(1)

    result = run_vision(image_path, model)
    print(json.dumps(result, indent=2))
