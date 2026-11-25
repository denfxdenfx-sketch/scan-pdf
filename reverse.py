#!/usr/bin/env python3
"""
reverse_filter.py — Moves all files from text_junk back to _figures.
"""

import os
import shutil

FIGURES_DIR = "pyq/_figures"
JUNK_DIR = "pyq/_text_junk20"

def main():
    if not os.path.exists(JUNK_DIR):
        print(f"[!] Junk folder not found: {JUNK_DIR}")
        return
    if not os.path.exists(FIGURES_DIR):
        print(f"[!] Figures folder not found: {FIGURES_DIR}")
        return

    files = os.listdir(JUNK_DIR)
    if not files:
        print("Junk folder is empty. Nothing to reverse.")
        return

    moved = 0
    print(f"Moving {len(files)} files from {JUNK_DIR} back to {FIGURES_DIR}...\n")

    for filename in files:
        src = os.path.join(JUNK_DIR, filename)
        dest = os.path.join(FIGURES_DIR, filename)
        
        # Only move files, ignore subdirectories
        if os.path.isfile(src):
            shutil.move(src, dest)
            moved += 1
            print(f"  Restored: {filename}")

    print(f"\nDone. Moved {moved} files back to {FIGURES_DIR}.")

if __name__ == "__main__":
    main()