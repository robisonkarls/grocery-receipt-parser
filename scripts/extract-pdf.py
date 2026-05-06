#!/usr/bin/env python3
"""
Extract text from PDF receipts.
Strategy:
  1. Try pypdfium2 direct text extraction (text PDFs — fast, perfect quality)
  2. If empty → PDF is image-based → convert pages to images → PaddleOCR
"""

import sys
import json
import tempfile
from pathlib import Path

MIN_TEXT_LENGTH = 50  # Below this → assume scanned PDF, use OCR

def extract_text_pdf(pdf_path: str) -> dict:
    """Extract embedded text from a text-based PDF."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {'success': False, 'error': 'pypdfium2 not installed. Run: pip install pypdfium2'}

    try:
        doc = pdfium.PdfDocument(pdf_path)
        pages_text = []
        for page in doc:
            textpage = page.get_textpage()
            pages_text.append(textpage.get_text_range())
        import re
        text = '\n'.join(pages_text).strip()
        # Strip markdown artifacts (e.g. **KS TOWEL** → KS TOWEL)
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        return {'success': True, 'text': text, 'pages': len(pages_text)}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def extract_scanned_pdf(pdf_path: str) -> dict:
    """Convert PDF pages to images and run PaddleOCR on each."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {'success': False, 'error': 'pypdfium2 not installed'}

    try:
        import warnings
        warnings.filterwarnings('ignore')
        from paddleocr import PaddleOCR
    except ImportError:
        return {'success': False, 'error': 'PaddleOCR not installed. Run: pip install paddlepaddle paddleocr'}

    try:
        doc = pdfium.PdfDocument(pdf_path)
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
        all_text = []
        all_scores = []

        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(doc):
                # Render page to image at 300 DPI
                bitmap = page.render(scale=300/72)
                img_path = f"{tmp}/page_{i}.png"
                bitmap.to_pil().save(img_path)

                # Run PaddleOCR
                results = ocr.ocr(img_path)
                if results and results[0]:
                    data = dict(results[0])
                    texts  = data.get('rec_texts', [])
                    scores = data.get('rec_scores', [])
                    polys  = data.get('rec_polys', [])

                    lines = []
                    for j, text in enumerate(texts):
                        conf = scores[j] if j < len(scores) else 0.0
                        poly = polys[j] if j < len(polys) else None
                        y = float((poly[0][1] + poly[2][1]) / 2) if poly is not None else j * 10.0
                        lines.append((y, text, float(conf)))
                        all_scores.append(float(conf))

                    lines.sort(key=lambda l: l[0])
                    all_text.extend(t for _, t, _ in lines if t.strip())

        avg_conf = sum(all_scores) / len(all_scores) if all_scores else 0.0
        return {
            'success': True,
            'text': '\n'.join(all_text),
            'confidence': round(avg_conf, 3),
            'method': 'pdf-ocr'
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}

def extract_pdf(pdf_path: str) -> dict:
    """Main entry: try text extraction, fall back to OCR if needed."""

    # Step 1: Try direct text extraction
    text_result = extract_text_pdf(pdf_path)

    if text_result.get('success') and len(text_result.get('text', '')) >= MIN_TEXT_LENGTH:
        # Good text PDF
        return {
            'success': True,
            'method': 'pdf-text',
            'confidence': 1.0,
            'text': text_result['text'],
            'pages': text_result.get('pages', 1)
        }

    # Step 2: Scanned PDF — use OCR
    print("   📄 No embedded text found — running OCR on PDF pages...", file=sys.stderr)
    ocr_result = extract_scanned_pdf(pdf_path)

    if ocr_result.get('success'):
        return {
            'success': True,
            'method': 'pdf-ocr',
            'confidence': ocr_result.get('confidence', 0.0),
            'text': ocr_result['text'],
        }

    return {
        'success': False,
        'error': f"Both text extraction and OCR failed: {ocr_result.get('error', 'unknown')}",
        'confidence': 0.0,
        'text': ''
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: extract-pdf.py <pdf_path>'}))
        sys.exit(1)

    if not Path(sys.argv[1]).exists():
        print(json.dumps({'success': False, 'error': f'File not found: {sys.argv[1]}'}))
        sys.exit(1)

    result = extract_pdf(sys.argv[1])
    print(json.dumps(result, indent=2))
