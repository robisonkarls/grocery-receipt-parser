#!/usr/bin/env python3
"""
PaddleOCR v3 wrapper for receipt text extraction.
"""

import sys
import json
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path

def run_paddle(image_path: str) -> dict:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return {'success': False, 'method': 'paddleocr',
                'error': 'PaddleOCR not installed. Run: pip install paddlepaddle paddleocr',
                'confidence': 0.0, 'text': ''}

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
        results = ocr.ocr(image_path)

        if not results:
            return {'success': False, 'method': 'paddleocr', 'confidence': 0.0, 'text': ''}

        result = results[0]  # OCRResult object (PaddleOCR v3)
        data = dict(result)

        texts  = data.get('rec_texts', [])
        scores = data.get('rec_scores', [])
        polys  = data.get('rec_polys', [])

        if not texts:
            return {'success': False, 'method': 'paddleocr', 'confidence': 0.0, 'text': ''}

        lines = []
        for i, text in enumerate(texts):
            conf = scores[i] if i < len(scores) else 0.0
            poly = polys[i] if i < len(polys) else None
            y_mid = float((poly[0][1] + poly[2][1]) / 2) if poly is not None else i * 10.0
            x_left = float(poly[0][0]) if poly is not None else 0.0
            lines.append({'text': text, 'confidence': round(float(conf), 3),
                          'y': round(y_mid, 1), 'x': round(x_left, 1)})

        lines.sort(key=lambda l: l['y'])
        avg_conf = sum(l['confidence'] for l in lines) / len(lines)
        full_text = '\n'.join(l['text'] for l in lines if l['text'].strip())

        return {
            'success': True,
            'method': 'paddleocr',
            'confidence': round(avg_conf, 3),
            'text': full_text,
            'lines': lines
        }

    except Exception as e:
        return {'success': False, 'method': 'paddleocr',
                'error': str(e), 'confidence': 0.0, 'text': ''}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: ocr-paddle.py <image_path>'}))
        sys.exit(1)
    if not Path(sys.argv[1]).exists():
        print(json.dumps({'success': False, 'error': f'Image not found: {sys.argv[1]}'}))
        sys.exit(1)
    print(json.dumps(run_paddle(sys.argv[1]), indent=2))
