#!/usr/bin/env python3
import csv
import os
import re

# ═══════════════════════════════════════════════════════════════
# 👇 CONFIGURATION 👇
CSV_FILE = "neet pg inicet.csv"
TXT_FILE = "extracted_text.txt"
FIGURES_DIR = "pyq/_figures"
OUTPUT_CSV = "pyq/_all_questions_FINAL1.csv"
# ═══════════════════════════════════════════════════════════════

# Regexes
PAGE_SPLIT_RE = re.compile(r"--- PAGE (\d+) ---")
MARK_RE = re.compile(r"<<<FIGURE\s+q=(\d+)(?:_\d+)?\s+page=(\d+)\s+box=.*?>>>")
HEADER_RE = re.compile(
    r"^(?:Anatomy|Physiology|Biochemistry|Pharmacology|Microbiology|Pathology|"
    r"Community\s+Medicine|Forensic\s+Medicine|Ophthalmology|ENT|"
    r"Anesthesia|Dermatology|Psychiatry|Radiology|Medicine|Surgery|"
    r"Orthopedics|Paediatrics|Obstetrics\s+and\s+Gynecology|Obstetrics\s+&\s+Gynecology|"
    r"Obstetrics\s+and\s+Gynaecology)\s+"
    r"(?:AIIMS|NEET|INI-CET|INI\s*CET).*?\d{4}",
    re.MULTILINE | re.IGNORECASE
)

def norm(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]", "", s)
    s = s.replace("inicet", "").replace("and", "")
    return s

def build_lookup():
    with open(TXT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_paper = None
    section = "question"
    lookup = {}

    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith("--- PAGE"): continue

        if "Detailed Explanations" in line:
            section = "explanation"
            continue

        if HEADER_RE.match(line):
            current_paper = norm(line)
            lookup[current_paper] = {}
            section = "question"
            continue

        m = MARK_RE.search(line)
        if m and current_paper:
            qno = int(m.group(1))
            page = int(m.group(2))
            
            # Look for the actual file locally
            prefix = f"page_{page:04d}_q{qno:02d}"
            local_file = None
            if os.path.exists(FIGURES_DIR):
                for f in os.listdir(FIGURES_DIR):
                    if f.startswith(prefix) and f.endswith(('.jpg', '.png', '.jpeg')):
                        local_file = f
                        break
            
            if local_file:
                # Just the local path, no Cloudflare URL
                local_path = f"{FIGURES_DIR}/{local_file}"
                
                lookup[current_paper].setdefault(qno, {})
                if section == "question" and "q" not in lookup[current_paper][qno]:
                    lookup[current_paper][qno]["q"] = local_path
                elif section == "explanation" and "exp" not in lookup[current_paper][qno]:
                    lookup[current_paper][qno]["exp"] = local_path

    return lookup

def find_best_key(csv_key, all_keys):
    if csv_key in all_keys: return csv_key
    for key in all_keys:
        if key.startswith(csv_key) and len(key) <= len(csv_key) + 15: return key
        if csv_key.startswith(key) and len(csv_key) <= len(key) + 15: return key
    return None

def main():
    print("Building lookup from extracted_text.txt...")
    lookup = build_lookup()
    print(f"Found {len(lookup)} papers with figures.\n")

    print(f"Reading {CSV_FILE}...")
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    # Ensure the columns exist (they might already be there)
    for col in ("question_image_path", "explanation_image_path"):
        if col not in fieldnames:
            fieldnames.append(col)

    updated = 0
    all_keys = set(lookup.keys())

    for row in rows:
        subj = row.get("subject", "").replace(" ", "_")
        exam = row.get("exam", "").replace(" ", "_")
        year = row.get("year", "").strip()
        qno_str = row.get("question_no", "").strip()

        # Normalize to match the text file header (e.g., "Anatomy_AIIMS_2017")
        exam_clean = re.sub(r"[\(\)&]", "", exam)
        row_key = norm(subj + exam_clean + year)
        
        best_match = find_best_key(row_key, all_keys)

        if not best_match:
            continue

        try:
            qno = int(qno_str)
        except ValueError:
            continue

        figs = lookup[best_match].get(qno, {})
        
        if figs.get("q"):
            row["question_image_path"] = figs["q"]
        if figs.get("exp"):
            row["explanation_image_path"] = figs["exp"]

        if figs.get("q") or figs.get("exp"):
            updated += 1

    print(f"Updated {updated} rows with image paths.")
    print(f"Writing back to {OUTPUT_CSV}...")
    
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print("✅ Done!")

if __name__ == "__main__":
    main()