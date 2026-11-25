#!/usr/bin/env python3
"""
remove_20_words.py — Moves images with > 20 words to a junk folder.
"""

import os
import shutil
from PIL import Image
import pytesseract

FIGURES_DIR = "pyq/_figures"
JUNK_DIR = "pyq/_text_junk20 txt"
WORD_THRESHOLD = 20

def count_words(image_path):
    try:
        img = Image.open(image_path)
        # --psm 3 is best for general blocks of text
        text = pytesseract.image_to_string(img, config='--psm 3')
        return len(text.split())
    except Exception:
        return 0

def main():
    if not os.path.exists(FIGURES_DIR):
        print(f"[!] Folder not found: {FIGURES_DIR}")
        return
        
    os.makedirs(JUNK_DIR, exist_ok=True)
    
    files = sorted(f for f in os.listdir(FIGURES_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png')))
    
    print(f"Scanning {len(files)} images...")
    print(f"Moving anything with > {WORD_THRESHOLD} words to {JUNK_DIR}\n")
    
    moved = 0
    kept = 0
    
    for i, filename in enumerate(files, 1):
        path = os.path.join(FIGURES_DIR, filename)
        wc = count_words(path)
        
        if wc > WORD_THRESHOLD:
            shutil.move(path, os.path.join(JUNK_DIR, filename))
            moved += 1
            print(f"[{i:>4}/{len(files)}] MOVED: {filename} ({wc} words)")
        else:
            kept += 1
            if i % 50 == 0:
                print(f"[{i:>4}/{len(files)}] ... scanning (kept {kept})")

    print(f"\nDone. Kept {kept}, Moved {moved} to {JUNK_DIR}.")

if __name__ == "__main__":
    main()