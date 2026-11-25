#!/usr/bin/env python3
"""
crop_from_boxes.py — Crops figures from the PDF using exact bounding boxes 
from extract_text.py.
- Saves as JPEG to save massive amounts of disk space.
- Uses OCR to crop out "Detailed Explanations" and "© MARROW".
- Erases the faint background MARROW watermark.
"""

import argparse
import os
import re
import sys
import io
import fitz
import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageChops, ImageDraw

MARK_RE = re.compile(
    r"<<<FIGURE\s+q=(\d+)(?:_\d+)?\s+page=(\d+)\s+"
    r"box=([\d.]+),([\d.]+),([\d.]+),([\d.]+)>>>"
)

def parse_markers(txt_path):
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    out = []
    for m in MARK_RE.finditer(raw):
        qno = int(m.group(1))
        page = int(m.group(2))
        x0, y0, x1, y1 = (float(m.group(3)), float(m.group(4)),
                          float(m.group(5)), float(m.group(6)))
        out.append((page, qno, (x0, y0, x1, y1)))
    return out

def _erase_watermarks_and_crop(image_bytes):
    """
    Takes the exact image crop, removes bottom text/watermarks, 
    and returns a compressed JPEG.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        h, w = img_cv.shape[:2]

        # --- Step A: Find and remove bottom text ("Detailed Explanations" & "©MARROW") ---
        footer_h = int(h * 0.30)
        footer_img = img_cv[h - footer_h:h, 0:w]
        
        data = pytesseract.image_to_data(footer_img, config='--psm 6', output_type=pytesseract.Output.DICT)
        top_of_bottom_text = h

        for i, text in enumerate(data['text']):
            upper_text = text.upper()
            if "MARROW" in upper_text or "EXPLANATION" in upper_text:
                y_in_footer = data['top'][i]
                y_in_full = (h - footer_h) + y_in_footer
                if y_in_full < top_of_bottom_text:
                    top_of_bottom_text = y_in_full

        # Crop the image up to the topmost bottom text we found
        if top_of_bottom_text < h:
            img_cv = img_cv[0:top_of_bottom_text, 0:w]
            h, w = img_cv.shape[:2]

        # --- Step B: Find and erase the faint background watermark ---
        hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
        
        # Target faint teal/blue
        lower_teal = np.array([80, 10, 120])
        upper_teal = np.array([130, 100, 255])
        mask = cv2.inRange(hsv, lower_teal, upper_teal)
        isolated_watermark = cv2.bitwise_not(mask)

        wm_data = pytesseract.image_to_data(isolated_watermark, config='--psm 11', output_type=pytesseract.Output.DICT)

        _, buffer = cv2.imencode('.png', img_cv)
        img_pil = Image.open(io.BytesIO(buffer.tobytes())).convert("RGB")
        draw = ImageDraw.Draw(img_pil)

        for i, text in enumerate(wm_data['text']):
            if "MARROW" in text.upper():
                x, y = wm_data['left'][i], wm_data['top'][i]
                bw, bh = wm_data['width'][i], wm_data['height'][i]
                pad = 10
                draw.rectangle([x - pad, y - pad, x + bw + pad, y + bh + pad], fill="white")

        # --- Step C: Trim white borders ---
        bg = Image.new(img_pil.mode, img_pil.size, (255, 255, 255))
        diff = ImageChops.difference(img_pil, bg)
        bbox = diff.getbbox()
        if bbox:
            padding = 10
            bbox = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(img_pil.width, bbox[2] + padding),
                min(img_pil.height, bbox[3] + padding)
            )
            img_pil = img_pil.crop(bbox)

        # --- Step D: Save as JPEG to save disk space ---
        out_bytes = io.BytesIO()
        img_pil.save(out_bytes, format="JPEG", quality=85, optimize=True)
        return out_bytes.getvalue()

    except Exception as e:
        print(f"Warning: Processing failed: {e}")
        return image_bytes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="Pyqs_ed8(1).pdf")
    ap.add_argument("--txt", default="extracted_text.txt")
    ap.add_argument("--out", default=os.path.join("pyq", "_figures"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--pages", nargs=2, type=int, metavar=("START", "END"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.txt):
        sys.exit(f"'{args.txt}' not found.")
    if not os.path.exists(args.pdf):
        sys.exit(f"PDF not found: {args.pdf}")

    markers = parse_markers(args.txt)
    if not markers:
        sys.exit(f"No markers found in {args.txt}")

    print(f"Markers found: {len(markers)}")

    if args.pages:
        lo, hi = args.pages
        markers = [m for m in markers if lo <= m[0] <= hi]
        print(f"Filter pages {lo}–{hi}: {len(markers)} markers")

    os.makedirs(args.out, exist_ok=True)
    doc = fitz.open(args.pdf)

    saved = 0
    skipped = 0

    for page_no, qno, (x0, y0, x1, y1) in markers:
        if page_no < 1 or page_no > len(doc):
            skipped += 1
            continue

        page = doc[page_no - 1]
        rect = fitz.Rect(x0, y0, x1, y1) & page.rect

        if rect.is_empty:
            skipped += 1
            continue

        # Save as .jpg instead of .png
        path = os.path.join(args.out, f"page_{page_no:04d}_q{qno:02d}.jpg")

        if args.dry_run:
            print(f"Would save: {os.path.basename(path)}")
            saved += 1
            continue

        # Render exact bbox
        pix = page.get_pixmap(clip=rect, dpi=args.dpi)
        
        # Clean and save
        cleaned_bytes = _erase_watermarks_and_crop(pix.tobytes("png"))

        with open(path, "wb") as f:
            f.write(cleaned_bytes)

        saved += 1

    doc.close()
    print(f"\nSaved {saved} crops → {args.out}/")
    if skipped:
        print(f"Skipped {skipped} invalid markers")

if __name__ == "__main__":
    main()