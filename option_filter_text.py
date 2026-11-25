#!/usr/bin/env python3
"""
filter_text_junk.py — Catch text blocks with "Option X" or a) b) c) d) lines.
"""

import os
import shutil
import re
from PIL import Image
import pytesseract

FIGURES_DIR = "pyq/_figures"
JUNK_DIR = "pyq/text_junk_option"

# Regexes
OPTION_WORD_RE = re.compile(r"\boption\s+[a-d]\b", re.IGNORECASE)
OPTION_LINE_RE = re.compile(r"^\s*[a-dA-D][\)\.]\s+", re.MULTILINE)

def analyze_image(image_path):
    """Returns (has_option_word, option_line_count)."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, config='--psm 3')
        
        has_option = bool(OPTION_WORD_RE.search(text))
        option_lines = len(OPTION_LINE_RE.findall(text))
        
        return has_option, option_lines
    except Exception:
        return False, 0

def main():
    if not os.path.exists(FIGURES_DIR):
        print(f"[!] Folder not found: {FIGURES_DIR}")
        return
    os.makedirs(JUNK_DIR, exist_ok=True)

    files = sorted(f for f in os.listdir(FIGURES_DIR)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))

    total = len(files)
    moved = 0
    kept = 0

    print(f"Scanning {total} images in {FIGURES_DIR}\n")
    print(f"{'IDX':<12} {'FILENAME':<28} {'OPT':>5} {'LINES':>5} {'DECISION'}")
    print("-" * 70)

    for i, filename in enumerate(files, 1):
        path = os.path.join(FIGURES_DIR, filename)

        has_option, option_lines = analyze_image(path)

        # Move if it has "Option A/B/C/D" OR >= 3 lines starting with a) b) c) d)
        is_text = has_option or (option_lines >= 3)

        if is_text:
            shutil.move(path, os.path.join(JUNK_DIR, filename))
            moved += 1
            if option_lines >= 3:
                verdict = f"MOVED ({option_lines} lines a/b/c/d)"
            else:
                verdict = "MOVED ('Option X')"
        else:
            kept += 1
            verdict = "kept"

        print(f"[{i:>4}/{total}] {filename:<28} {str(has_option):>5} {option_lines:>5}  {verdict}")

    print("-" * 70)
    print(f"\nDone. Scanned {total}, kept {kept}, moved {moved} to {JUNK_DIR}")

if __name__ == "__main__":
    main()