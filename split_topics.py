#!/usr/bin/env python3
"""
Split extracted_text.txt into 63 individual topic files based on hardcoded 
chapter page numbers.
"""

import os
import re

INPUT_FILE      = "extracted_text.txt"
OUTPUT_DIR      = "topic_groups"

# Chapter Number, Title, Start Page
# The end page is implicitly (next_start_page - 1)
CHAPTERS = [
    (1,  "Gametogenesis", 5),
    (2,  "Pre-Embryonic Phase of Development", 19),
    (3,  "Embryonic Phase of Development", 30),
    (4,  "Placenta, Fetal Membranes and Twinning", 46),
    (5,  "Pharyngeal arches, Skeletal & Muscular Systems", 63),
    (6,  "Cardiovascular and Respiratory Systems", 87),
    (7,  "Alimentary, Hepatobiliary systems, Pancreas and...", 111),
    (8,  "Face, Nose & Palate, Eye, Ear", 132),
    (9,  "Nervous System and Endocrine Glands", 146),
    (10, "Urogenital System", 164),
    (11, "Cell Structure, Epithelia, Glands & Connective ...", 179),
    (12, "Bone, Cartilage & Muscular Tissue", 213),
    (13, "Nervous and Endocrine Systems", 230),
    (14, "Cardiovascular, Lymphatic and Respiratory Systems", 246),
    (15, "Digestive, Hepatobiliary & Genitourinary Systems", 262),
    (16, "Skin & Special Senses, Eye and Ear", 286),
    (17, "Cranial Nerves", 306),
    (18, "Meninges and dural venous sinuses", 327),
    (19, "Ventricular System and Subarachnoid Space", 341),
    (20, "Cerebrum", 361),
    (21, "White Matter of the Brain", 368),
    (22, "Basal Ganglia and Limbic System", 385),
    (23, "Diencephalon", 392),
    (24, "Brainstem", 404),
    (25, "Cerebellum", 422),
    (26, "Vascular supply of Brain", 434),
    (27, "Spinal Cord", 459),
    (28, "Osteology, Scalp and Face", 471),
    (29, "Deep fascia and Triangles of the neck", 501),
    (30, "Muscles, Neurovascular Anatomy of Head & Neck", 521),
    (31, "Glands of the Head and Neck", 556),
    (32, "Tongue and Palate", 582),
    (33, "Pharynx", 593),
    (34, "Larynx", 601),
    (35, "Upper Limb Bones and Joints", 619),
    (36, "Fossae and Spaces of the Upper Limb", 641),
    (37, "Breast", 658),
    (38, "Brachial Plexus and Nerves", 666),
    (39, "Muscles - Upper Limb", 703),
    (40, "Vessels-Upper limb", 733),
    (41, "General Anatomy of Thorax", 753),
    (42, "Thoracic Wall", 769),
    (43, "Mediastinum", 792),
    (44, "Diaphragm", 806),
    (45, "Heart", 815),
    (46, "Lungs and Pleura", 845),
    (47, "Anterior Abdominal Wall", 861),
    (48, "Abdominal cavity and Peritoneum", 878),
    (49, "GI Tract", 892),
    (50, "Hepatobiliary system, Spleen & Pancreas", 913),
    (51, "KUB & Adrenal Gland", 940),
    (52, "Internal and external genitalia", 972),
    (53, "Pelvis & Perineum", 997),
    (54, "Bones of the Lower Limb", 1022),
    (55, "Joints of the Lower Limb", 1040),
    (56, "Muscles of the Lower Limb", 1060),
    (57, "Nerves & Vessels of Lower Limb", 1088),
    (58, "Important Structures of Lower Limb", 1110),
    (59, "Vertebral Column", 1127),
    (60, "Bones, Joints and Cartilage", 1142),
    (61, "Muscles and Tendons", 1170),
    (62, "Cardiovascular, Lymphatic and Nervous Systems", 1187),
    (63, "Skin, Connective Tissue and Ligaments", 1205),
]

def load_text(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def split_by_pages(text):
    """
    Split text into chunks based on '--- PAGE N ---' markers.
    Returns a dict: { page_number: text_of_that_page }
    """
    pattern = re.compile(r"^-+\s*PAGE\s+(\d+)\s*-+$", re.MULTILINE | re.IGNORECASE)
    matches = list(pattern.finditer(text))
    pages = {}
    
    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        start_idx = match.start()
        
        if i + 1 < len(matches):
            end_idx = matches[i+1].start()
        else:
            end_idx = len(text)
            
        pages[page_num] = text[start_idx:end_idx].strip()

    return pages

def sanitize_filename(title):
    """Removes characters that are invalid in file names."""
    # Replace spaces with underscores, remove punctuation like '/', '\', ':', etc.
    clean = re.sub(r'[^a-zA-Z0-9_\- ]', '', title)
    return clean.strip().replace(' ', '_')

def main():
    if not os.path.isfile(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' not found.")
        return

    text = load_text(INPUT_FILE)
    pages_dict = split_by_pages(text)

    # Ensure the output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Group pages according to the chapter start pages and write each to a file
    for i, (ch_num, title, start_page) in enumerate(CHAPTERS):
        # Determine the end page (exclusive)
        if i + 1 < len(CHAPTERS):
            end_page = CHAPTERS[i+1][2]
        else:
            end_page = max(pages_dict.keys()) + 1 # to end of file

        # Gather all pages belonging to this chapter
        chapter_text = []
        for p in range(start_page, end_page):
            if p in pages_dict:
                chapter_text.append(pages_dict[p])
            else:
                print(f"Warning: Page {p} missing in text file for chapter '{title}'")

        full_chapter_text = "\n\n".join(chapter_text)
        
        # Generate the filename (e.g., topic_1_Gametogenesis.txt)
        safe_title = sanitize_filename(title)
        filename = os.path.join(OUTPUT_DIR, f"topic_{ch_num}_{safe_title}.txt")
        
        # Write the individual topic file
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(f"CHAPTER {ch_num}: {title}\n")
            f.write("=" * 70 + "\n\n")
            f.write(full_chapter_text + "\n")
            
        print(f"Created {filename}")

    print(f"\nDone! Generated {len(CHAPTERS)} individual topic files.")

if __name__ == "__main__":
    main()