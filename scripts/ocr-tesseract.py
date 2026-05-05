#!/usr/bin/env python3
"""
Tesseract OCR wrapper for receipt text extraction.
Outputs JSON with extracted text and confidence score.
"""

import sys
import json
import subprocess
from pathlib import Path

def run_tesseract(image_path):
    """Run Tesseract OCR on image and return text."""
    try:
        # Run Tesseract with basic text output
        result = subprocess.run(
            ['tesseract', image_path, 'stdout', '-l', 'eng'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        text = result.stdout.strip()
        
        # Simple heuristic: if we got reasonable amount of text, confidence is decent
        if len(text) > 50:
            confidence = 0.75
        elif len(text) > 20:
            confidence = 0.50
        else:
            confidence = 0.25
        
        return {
            'success': bool(text),
            'method': 'tesseract',
            'confidence': confidence,
            'text': text,
            'raw_text': text
        }
        
    except FileNotFoundError:
        return {
            'success': False,
            'method': 'tesseract',
            'error': 'Tesseract not installed. Run: brew install tesseract',
            'confidence': 0.0,
            'text': ''
        }
    except Exception as e:
        return {
            'success': False,
            'method': 'tesseract',
            'error': str(e),
            'confidence': 0.0,
            'text': ''
        }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            'success': False,
            'error': 'Usage: ocr-tesseract.py <image_path>'
        }), file=sys.stderr)
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not Path(image_path).exists():
        print(json.dumps({
            'success': False,
            'error': f'Image not found: {image_path}'
        }), file=sys.stderr)
        sys.exit(1)
    
    result = run_tesseract(image_path)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
