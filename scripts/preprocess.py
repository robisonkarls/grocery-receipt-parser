#!/usr/bin/env python3
"""
OpenCV image preprocessor for receipt photos.
Grayscale + adaptive threshold + deskew + morphological closing.
"""

import sys
import cv2
import numpy as np
from pathlib import Path

def preprocess(image_path: str, output_path: str) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        return {'success': False, 'error': f'Cannot read image: {image_path}'}

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Adaptive threshold — handles uneven lighting across receipt
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15, C=10
    )

    # 3. Morphological closing — reconnect broken characters (crumpled receipts)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # 4. Deskew — correct tilt from handheld shots
    coords = np.column_stack(np.where(closed > 0))
    angle = 0.0
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

    if abs(angle) > 0.5:  # Only rotate if tilt is significant
        h, w = closed.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        closed = cv2.warpAffine(
            closed, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

    cv2.imwrite(output_path, closed)
    return {
        'success': True,
        'output': output_path,
        'deskew_angle': round(angle, 2)
    }

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: preprocess.py <input> <output>")
        sys.exit(1)
    import json
    result = preprocess(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
