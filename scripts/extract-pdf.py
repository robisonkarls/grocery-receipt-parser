#!/usr/bin/env python3
"""
Extract text from PDF receipts using pypdfium2.
Returns same JSON format as OCR scripts for pipeline compatibility.
"""
import sys, json
from pathlib import Path

def extract_pdf(pdf_path: str) -> dict:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {'success': False, 'method': 'pdf', 'error': 'pypdfium2 not installed. Run: pip install pypdfium2', 'confidence': 0.0, 'text': ''}

    try:
        doc = pdfium.PdfDocument(pdf_path)
        pages = []
        for page in doc:
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
        text = '\n'.join(pages).strip()

        return {
            'success': True,
            'method': 'pdf',
            'confidence': 1.0,  # PDF text is perfect quality
            'text': text,
            'pages': len(pages)
        }
    except Exception as e:
        return {'success': False, 'method': 'pdf', 'error': str(e), 'confidence': 0.0, 'text': ''}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: extract-pdf.py <pdf_path>'}))
        sys.exit(1)
    print(json.dumps(extract_pdf(sys.argv[1]), indent=2))
