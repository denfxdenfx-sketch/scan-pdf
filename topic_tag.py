#!/usr/bin/env python3
"""
Tag medical exam questions with chapter / topic / system using DeepSeek.

Reads a normalized questions CSV and appends three new columns:
chapter, topic, system.

Usage:
    1. Edit API_KEY_HARDCODED below (and INPUT_CSV / OUTPUT_CSV if needed).
    2. Run:
         python tag_questions.py
"""

import csv
import json
import sys
import time
from pathlib import Path

from openai import OpenAI

# ============================================================
# CONFIG — edit these
# ============================================================
API_KEY_HARDCODED = "sk-fec1ffa74d3c4bd3875734ab81a4661e"   # ← replace with your key
BASE_URL = "https://api.deepseek.com"
MODEL    = "deepseek-flash"         # deepseek-chat is retired; use flash or v4-pro

INPUT_CSV  = Path("_all_questions_FINAL1.normalized.csv")
OUTPUT_CSV = Path("_all_questions_FINAL1.tagged.csv")

BATCH_SIZE        = 10                # questions per API call
MAX_RETRIES       = 3
RETRY_BASE_DELAY  = 2                 # seconds
REQUEST_DELAY     = 0.5               # seconds between batches
QUESTION_TRUNC    = 600               # chars of question sent
EXPLANATION_TRUNC = 300               # chars of explanation sent
# ============================================================

client = OpenAI(api_key=API_KEY_HARDCODED, base_url=BASE_URL)

# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT = """You are a medical exam question classifier. You will receive a batch of multiple-choice questions from Indian postgraduate medical entrance exams (AIIMS, NEET, INI-CET). For each question, output THREE independent tags: chapter, topic, and system.

====================================================================
TAG 1 — chapter
====================================================================
The chapter or section name from the STANDARD MBBS TEXTBOOK for that subject.
Use the controlled vocabularies below EXACTLY. Pick the closest match.
Do not invent chapter names. Do not use chapter names from a different subject's list.

[ANATOMY — BD Chaurasia / Gray's Anatomy]
Upper Limb | Lower Limb | Thorax | Abdomen | Pelvis and Perineum |
Head and Neck | Neuroanatomy | Embryology | Histology | Osteology

[PHYSIOLOGY — Guyton & Hall]
General Physiology | Nerve and Muscle Physiology | Blood and Its Constituents |
Cardiovascular Physiology | Respiratory Physiology | Gastrointestinal Physiology |
Renal Physiology | The Endocrine System | Reproductive Physiology |
Central Nervous System

[BIOCHEMISTRY — Satyanarayana]
Biomolecules and the Cell | Carbohydrates | Lipids | Proteins and Amino Acids |
Nucleic Acids and Nucleotides | Enzymes | Vitamins | Digestion and Absorption |
Plasma Proteins | Hemoglobin and Porphyrins | Biological Oxidation |
Introduction to Metabolism | Metabolism of Carbohydrates | Metabolism of Lipids |
Metabolism of Amino Acids | Integration of Metabolism | Metabolism of Nucleotides |
Mineral Metabolism | Hormones | Organ Function Tests |
Water, Electrolyte and Acid-Base Balance | Tissue Proteins and Body Fluids |
Nutrition | DNA Replication, Recombination and Repair |
Transcription and Translation | Regulation of Gene Expression |
Recombinant DNA and Biotechnology | Human Genome Project | Gene Therapy |
Bioinformatics | Metabolism of Xenobiotics | Prostaglandins and Related Compounds |
Biological Membranes and Transport | Free Radicals and Antioxidants |
Environmental Biochemistry | Insulin, Glucose Homeostasis and Diabetes Mellitus |
Cancer | Acquired Immunodeficiency Syndrome | Immunology | Genetics

[PHARMACOLOGY — KD Tripathi]
General Pharmacological Principles | Drugs Acting on Autonomic Nervous System |
Autacoids and Related Drugs | Respiratory System Drugs | Hormones and Related Drugs |
Drugs Acting on Peripheral (Somatic) Nervous System |
Drugs Acting on Central Nervous System | Cardiovascular Drugs |
Drugs Acting on Kidney | Drugs Affecting Blood and Blood Formation |
Gastrointestinal Drugs | Antimicrobial Drugs |
Chemotherapy of Neoplastic Diseases | Miscellaneous Drugs

[MICROBIOLOGY — Ananthanarayan & Paniker]
General Microbiology | Immunology | Bacteriology | Virology | Mycology |
Parasitology | Hospital Acquired Infections

[PATHOLOGY — Robbins Basic Pathology]
Cell Injury, Cell Death, and Adaptations | Inflammation and Repair |
Hemodynamic Disorders, Thromboembolism, and Shock |
Diseases of the Immune System | Neoplasia | Genetic and Pediatric Diseases |
Environmental and Nutritional Diseases | General Pathology of Infectious Diseases |
Blood Vessels | Heart | Hematopoietic and Lymphoid Systems | Lung |
Kidney and Its Collecting System | Oral Cavities and Gastrointestinal Tract |
Liver and Gallbladder | Pancreas | Male Genital System and Lower Urinary Tract |
Female Genital System and Breast | Endocrine System |
Bones, Joints, and Soft Tissue Tumors | Peripheral Nerves and Muscles |
Central Nervous System | Skin

[COMMUNITY MEDICINE — Park]
Concept of Health and Disease |
Principles of Epidemiology and Epidemiologic Methods | Screening for Disease |
Epidemiology of Communicable Diseases |
Epidemiology of Chronic Non-Communicable Diseases | Health Programmes in India |
Demography and Family Planning |
Preventive Medicine in Obstetrics, Paediatrics and Geriatrics |
Nutrition and Health | Environment and Health | Hospital Waste Management |
Disaster Management | Occupational Health | Genetics and Health | Mental Health |
Health Information and Basic Medical Statistics |
Communication for Health Education | Health Planning and Management |
Health Care of the Community | International Health

[FORENSIC MEDICINE — Reddy]
Introduction | Legal Procedure | Medical Law and Ethics | Identification |
Medicolegal Autopsy | Death and Its Cause | Postmortem Changes |
Mechanical Injuries | Regional Injuries | Medicolegal Aspects of Wounds |
Thermal Deaths | Starvation | Mechanical Asphyxia |
Anaesthetic and Operative Deaths | Impotence and Sterility |
Virginity, Pregnancy and Delivery | Abortion | Sexual Offences | Infant Deaths |
Blood Stains | Artefacts | Forensic Science Laboratory | Forensic Psychiatry |
General Considerations (Toxicology) | Agricultural Poisons | Corrosive Poisons |
Metallic Poisons | Inorganic Irritant Poisons | Organic Irritant Poisons |
CNS Depressants | Psychotropic Drugs | Deliriant Poisons |
Drug Dependence and Abuse | Spinal Poisons | Cardiac Poisons | Asphyxiants |
Miscellaneous Poisons | Food Poisoning

[OPHTHALMOLOGY — Khurana]
Anatomy and Physiology of Eye | Optics and Refraction |
Diseases of Conjunctiva | Diseases of Cornea | Diseases of Sclera |
Diseases of Uveal Tract | Diseases of Lens | Glaucoma | Diseases of Vitreous |
Diseases of Retina | Neuro-ophthalmology | Disorders of Ocular Motility |
Disorders of Eyelids | Diseases of Lacrimal Apparatus | Diseases of Orbit |
Ocular Injuries | Ocular Therapeutics | Systemic and Community Ophthalmology

[ENT — Dhingra]
Diseases of Ear | Diseases of Nose and Paranasal Sinuses |
Diseases of Oral Cavity and Salivary Glands | Diseases of Pharynx |
Diseases of Larynx and Trachea | Thyroid Gland and Its Disorders |
Diseases of Oesophagus | Recent Advances

[ANESTHESIA]
General Anesthesia | Regional Anesthesia | Airway Management |
Anesthetic Equipment and Monitoring | Perioperative Complications |
Critical Care and Resuscitation | Pain Management | Special Anesthesia

[DERMATOLOGY — Neena Khanna]
Structure and Function of Skin | Diagnosis of Skin Diseases | Genodermatoses |
Papulosquamous Disorders | Bullous Disorders | Dermatitis |
Disorders of Skin Appendages | Disorders of Pigmentation |
Diseases of Cutaneous Vasculature |
Abnormal Vascular Responses, Panniculitis and Neutrophilic Dermatoses |
Cutaneous Response to Physical Stimuli | Adverse Drug Reactions |
Autoimmune Connective Tissue Diseases | Infections |
Sexually Transmitted Infections and HIV Infection |
Skin Diseases Caused by Arthropods, Worms and Protozoa |
Nevi and Skin Tumors | Cutaneous Manifestations of Internal Diseases |
Therapy of Skin Diseases

[PSYCHIATRY — Kaplan]
Mood Disorders | Anxiety Disorders | Psychotic Disorders |
Substance Use Disorders | Personality Disorders | Child Psychiatry |
Psychotherapy | Psychopharmacology

[RADIOLOGY]
Chest Imaging | Abdominal Imaging | Neuroimaging | Musculoskeletal Imaging |
Genitourinary Imaging | Vascular Imaging | Nuclear Medicine |
Interventional Radiology

[MEDICINE — Harrison's]
Disorders of the Cardiovascular System | Disorders of the Respiratory System |
Disorders of the Kidney and Urinary Tract |
Disorders of the Gastrointestinal System | Endocrinology and Metabolism |
Neurologic Disorders | Oncology and Hematology | Infectious Diseases |
Immune-Mediated, Inflammatory, and Rheumatologic Disorders |
Poisoning, Drug Overdose, and Envenomation

[SURGERY — Bailey & Love]
Basic Surgical Principles | Trauma | Elective Orthopaedics | Abdominal Surgery |
Cardiothoracic Surgery | Vascular Surgery | Genitourinary Surgery |
Transplantation | Breast and Endocrine | Head and Neck |
Skin and Subcutaneous Tissue

[ORTHOPEDICS]
Fractures and Dislocations | Bone and Joint Infections | Bone Tumors |
Metabolic Bone Disease | Spine | Sports Injuries | Pediatric Orthopedics |
Arthroplasty and Arthroscopy

[PAEDIATRICS — Ghai Essential Pediatrics]
Normal Growth and Its Disorders | Normal and Abnormal Development |
Fluid and Electrolyte Disturbances | Nutrition | Newborn Infants |
Immunity and Immunization | Infection and Infestations |
Diseases of Gastrointestinal System and Liver | Hematological Disorders |
Disorders of Respiratory System | Disorders of Cardiovascular System |
Disorders of Kidney and Urinary Tract | Endocrine and Metabolic Disorders |
Central Nervous System | Childhood Malignancies | Genetic Disorders |
Inborn Errors of Metabolism

[OBSTETRICS AND GYNECOLOGY — DC Dutta]
Anatomy of Female Reproductive Organs | Fundamentals of Reproduction |
Placenta and Fetal Membranes | Physiological Changes During Pregnancy |
Diagnosis of Pregnancy | Antenatal Care | Normal Labor | Normal Puerperium |
Hemorrhage in Early Pregnancy | Hypertensive Disorders in Pregnancy |
Antepartum Hemorrhage |
Medical and Surgical Illnesses Complicating Pregnancy |
Preterm Labor and Birth | Contracted Pelvis | Abnormal Uterine Action |
Operative Obstetrics | Safe Motherhood | Gynecological Disorders |
Reproductive Endocrinology | Fertility Regulation | Gynecological Oncology

====================================================================
TAG 2 — topic
====================================================================
A BROAD clinical category within the chapter.
- Mid-level granularity: broader than a single disease or drug, narrower than the chapter.
- Aim for 5 to 15 topics per chapter, not one topic per question.
- Use standard clinical category names. Title case. 2 to 4 words.
- The topic must plausibly belong inside the chosen chapter.
- Never output a specific disease name, drug name, organism name, or sign name as the topic.

Examples of correct topic granularity:
  Chapter "Heart" (Robbins) ->
    Ischemic Heart Disease | Valvular Heart Disease | Cardiomyopathies |
    Arrhythmias | Pericardial Disease | Congenital Heart Disease |
    Cardiac Tumors
  Chapter "Cardiovascular Drugs" (KD Tripathi) ->
    Antihypertensives | Antianginals | Antiarrhythmics |
    Heart Failure Drugs | Anticoagulants and Antiplatelets |
    Lipid-Lowering Drugs
  Chapter "Hematopoietic and Lymphoid Systems" (Robbins) ->
    Anemias | Coagulation Disorders | Leukemias | Lymphomas |
    Myeloproliferative Disorders | Plasma Cell Disorders
  Chapter "Diseases of Retina" (Khurana) ->
    Retinal Vascular Disease | Macular Disorders | Retinal Detachment |
    Retinal Dystrophies | Diabetic Retinopathy
  Chapter "Diseases of Ear" (Dhingra) ->
    Otitis Media | Hearing Loss | Vertigo | Tinnitus | Facial Nerve Disorders

Examples of INCORRECT topics (too specific — do not output these):
  "Mitral stenosis", "Warfarin", "Mycobacterium tuberculosis",
  "Cherry-red spot", "Rothera's test", "Glasgow Coma Scale"

====================================================================
TAG 3 — system
====================================================================
Exactly ONE of the following 13 values:

  Cardiovascular | Respiratory | Digestive | Urinary | Nervous |
  Musculoskeletal | Endocrine | Reproductive | Lymphatic/Immune |
  Integumentary | Special Senses | General/Systemic | Other

- Choose the organ system the question's clinical content belongs to.
- The system is a flat label. It has no topic list, no sub-values, and no
  hierarchy attached to it. Do not output anything nested under system.
- Blood, bone marrow, spleen, and lymphatics map to Lymphatic/Immune.
- Eye and ear map to Special Senses.
- Skin maps to Integumentary.
- General principles (biochemistry, molecular biology, genetics,
  general physiology, biostatistics) map to General/Systemic.
- Community Medicine, Forensic Medicine, Psychiatry, Anesthesia, and
  Radiology map to Other unless the question's clinical content clearly
  belongs to one specific organ system.

====================================================================
FEW-SHOT EXAMPLES
====================================================================
Example 1
Input: subject="Pathology", question="A 45-year-old man with a history of myocardial infarction presents with a rupture of the left ventricular wall. Histology shows coagulative necrosis with neutrophilic infiltration. What is the most likely time since infarction?", explanation="Coagulative necrosis with neutrophilic infiltration is seen 1-3 days after MI."
Output: {"id": 0, "chapter": "Heart", "topic": "Ischemic Heart Disease", "system": "Cardiovascular"}

Example 2
Input: subject="Pharmacology", question="A patient on warfarin is started on rifampicin. What is the expected change in INR?", explanation="Rifampicin is a CYP inducer and increases warfarin metabolism, reducing INR."
Output: {"id": 1, "chapter": "Drugs Affecting Blood and Blood Formation", "topic": "Anticoagulants and Antiplatelets", "system": "Lymphatic/Immune"}

Example 3
Input: subject="Anatomy", question="Nucleus pulposus is derived from which embryonic structure?", explanation="Nucleus pulposus is derived from the notochord."
Output: {"id": 2, "chapter": "Embryology", "topic": "Embryonic Derivatives", "system": "General/Systemic"}

Example 4
Input: subject="Medicine", question="A patient presents with hematuria, hypertension, and edema. Renal biopsy shows crescent formation. Anti-GBM antibodies are positive. What is the diagnosis?", explanation="Anti-GBM disease causes rapidly progressive glomerulonephritis with crescents."
Output: {"id": 3, "chapter": "Disorders of the Kidney and Urinary Tract", "topic": "Glomerular Disease", "system": "Urinary"}

Example 5
Input: subject="ENT", question="A 5-year-old child presents with a grape-like mass on the vocal cords causing hoarseness. What is the diagnosis?", explanation="Laryngeal papillomatosis caused by HPV 6 and 11."
Output: {"id": 4, "chapter": "Diseases of Larynx and Trachea", "topic": "Laryngeal Neoplasms", "system": "Respiratory"}

====================================================================
OUTPUT FORMAT — STRICT
====================================================================
Respond ONLY with a valid JSON array. Each element must be an object
with exactly four keys: "id", "chapter", "topic", "system".

- "id" is the integer id I provided for that question.
- "chapter" MUST come from the controlled vocabulary for that question's subject.
- "topic" MUST be a broad category as defined above.
- "system" MUST be exactly one of the 13 values listed above.
- The array must contain one object per input question, in the same order.
- No prose, no markdown fences, no explanations, no comments outside the JSON.

Correct output shape:
[
  {"id": 0, "chapter": "Heart", "topic": "Ischemic Heart Disease", "system": "Cardiovascular"},
  {"id": 1, "chapter": "Lung", "topic": "Obstructive Lung Disease", "system": "Respiratory"}
]
"""

# ============================================================
# API call with retries
# ============================================================
def call_deepseek(batch, start_id):
    payload = []
    for i, q in enumerate(batch):
        payload.append({
            "id": start_id + i,
            "subject": q.get("subject", ""),
            "question": (q.get("question") or "")[:QUESTION_TRUNC],
            "explanation": (q.get("explanation") or "")[:EXPLANATION_TRUNC],
        })

    user_msg = "Classify these questions:\n" + json.dumps(
        payload, ensure_ascii=False, indent=2
    )

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=4096,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)

            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        data = v
                        break
                else:
                    data = data.get("results", [])

            out = {}
            for item in data:
                out[int(item["id"])] = {
                    "chapter": item.get("chapter", "Other"),
                    "topic":   item.get("topic",   "Other"),
                    "system":  item.get("system",  "Other"),
                }
            return out

        except Exception as e:
            print(f"  attempt {attempt+1}/{MAX_RETRIES} failed: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                raise
    return {}


# ============================================================
# Main
# ============================================================
def main():
    if not INPUT_CSV.exists():
        sys.exit(f"Input not found: {INPUT_CSV}")

    with INPUT_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for col in ("chapter", "topic", "system"):
        if col not in fieldnames:
            fieldnames.append(col)

    total    = len(rows)
    tagged   = 0
    failed   = 0
    failures = []

    print(f"Input: {INPUT_CSV}  ({total} rows)", file=sys.stderr)
    print(f"Model: {MODEL}", file=sys.stderr)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        end   = batch_start + len(batch) - 1
        print(f"Batch {batch_start:>5}-{end:<5} ...", end=" ", file=sys.stderr)
        try:
            tags = call_deepseek(batch, batch_start)
            for i, row in enumerate(batch):
                tag = tags.get(batch_start + i, {})
                row["chapter"] = tag.get("chapter", "ERROR")
                row["topic"]   = tag.get("topic",   "ERROR")
                row["system"]  = tag.get("system",  "ERROR")
                if row["chapter"] != "ERROR":
                    tagged += 1
                else:
                    failures.append(batch_start + i)
            print(f"ok ({len(tags)}/{len(batch)})", file=sys.stderr)
        except Exception as e:
            failed += len(batch)
            failures.extend(range(batch_start, batch_start + len(batch)))
            for row in batch:
                row["chapter"] = "ERROR"
                row["topic"]   = "ERROR"
                row["system"]  = "ERROR"
            print(f"FAILED: {e}", file=sys.stderr)

        time.sleep(REQUEST_DELAY)

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames,
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(file=sys.stderr)
    print(f"Total rows    : {total}", file=sys.stderr)
    print(f"Tagged        : {tagged}", file=sys.stderr)
    print(f"Failed        : {failed}", file=sys.stderr)
    if failures:
        print(f"Failed row ids: {failures[:20]}{' ...' if len(failures) > 20 else ''}",
              file=sys.stderr)
    print(f"Output        : {OUTPUT_CSV.resolve()}", file=sys.stderr)


if __name__ == "__main__":
    main()