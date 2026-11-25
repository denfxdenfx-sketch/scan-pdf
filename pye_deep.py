#!/usr/bin/env python3
"""
pyq_pipeline.py — one-file pipeline:
    pyq/<Subject>/*.txt  →  DeepSeek clean  →  pyq/<Subject>/*.csv

Usage:
    python pyq_pipeline.py --dry-run
    python pyq_pipeline.py --file Anatomy_AIIMS_2017 --workers 1
    python pyq_pipeline.py --only Anatomy --workers 2
    python pyq_pipeline.py --workers 3
    python pyq_pipeline.py --force --workers 3
    python pyq_pipeline.py --merge
    python pyq_pipeline.py --report
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ──────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────
API_KEY  = "sk-fec1ffa74d3c4bd3875734ab81a4661e"
API_URL  = "https://api.deepseek.com/chat/completions"
MODEL    = "deepseek-chat"

INPUT_ROOT  = "pyq"
OUTPUT_ROOT = "pyq"

CSV_COLUMNS = [
    "question_no", "question",
    "option_a", "option_b", "option_c", "option_d",
    "correct_option", "explanation",
]

MAX_WORKERS     = 3
MAX_RETRIES     = 4
RETRY_BACKOFF   = 5
REQUEST_TIMEOUT = 300

# 25k chars input keeps the JSON reply well inside max_tokens=16384
MAX_CHUNK_CHARS = 25_000
MAX_OUTPUT_TOKENS = 16_384

# ──────────────────────────────────────────────────────────────────────
# PROMPT
# ──────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = r"""You are a meticulous medical-PG exam data cleaner.
You receive the raw OCR text of ONE previous-year question paper
(Anatomy / Physiology / etc.). Return STRICT JSON only — no markdown fences,
no commentary, no explanation of your process.

SCHEMA (exact keys, exact casing):
{
  "questions": [
    {
      "question_no": <int>,
      "question": "<clean question stem>",
      "option_a": "<text>",
      "option_b": "<text>",
      "option_c": "<text>",
      "option_d": "<text>",
      "correct_option": "a" | "b" | "c" | "d" | "",
      "explanation": "<cleaned explanation as markdown bullets, using \\n escapes>"
    }
  ]
}

RULES
1. Output only the JSON object. Nothing before or after.
2. Clean OCR noise thoroughly:
   - remove 'MARROW', '©MARROW', stray page numbers,
     '--- PAGE N ---' separators, '====' rules
   - fix option labels: 'ajA' -> 'a)', 'a)A' -> 'a)', 'Cc)' -> 'c)',
     'b)B' -> 'b)'
   - fix 'AlIMS' -> 'AIIMS', 'INICET' -> 'INI-CET'
3. Option labels a) b) c) d) — exactly one option per option_a..option_d.
   If the raw option is only a picture label ('A','B','C','D'), keep the
   single letter as the option text (do NOT invent text).
4. correct_option:
   - take from Answer Key section
   - if garbled/missing, infer from the explanation text
   - if still unresolved, use ""
5. explanation — this is the most important rule:
   - Take the SAME information from 'Solution to Question N:' and rewrite
     it as clean markdown bullets.
   - Bullet marker is the two characters '- ' at the start of a bullet.
   - Between bullets, use the LITERAL TWO-CHARACTER SEQUENCE \n
     (backslash + n). NEVER emit a real line break inside the JSON string.
   - NEVER emit an unescaped double-quote " inside any string value.
     If you need to quote a term, use single quotes ' instead.
   - Keep ALL facts, numbers, tables, drug names, nerve roots.
   - Do NOT add facts. Do NOT drop facts. Do NOT summarize away detail.
   - Keep each bullet concise (≤ 25 words); prefer more bullets over
     long paragraphs so the JSON fits the token budget.
   - If the solution contained a table, render each row as one bullet with
     ' | ' separators between columns.
   - If there is no explanation for a question, use "".
   - Strip watermarks, page numbers, figure captions.
6. Emit every question in ascending question_no. Do not merge or skip.
7. If a question is image-based (options are literally 'A','B','C','D'),
   still emit it normally.
8. Do not dedupe across chunks — the caller handles that.
9. The whole reply MUST be a single-line JSON object (no pretty-printing,
   no real newlines outside of string literals, and no real newlines inside
   them either — use \n).
10. Return ONLY the JSON object.
"""

# ──────────────────────────────────────────────────────────────────────
# CHUNKER
# ──────────────────────────────────────────────────────────────────────
Q_RE       = re.compile(r"^\s*Question\s+(\d+)\s*:", re.MULTILINE | re.IGNORECASE)
ANS_HDR_RE = re.compile(r"^\s*Answer\s*Key\s*$", re.MULTILINE | re.IGNORECASE)
EXP_HDR_RE = re.compile(r"^\s*Detailed\s+Explanations?\s*$", re.MULTILINE | re.IGNORECASE)


def _split_sections(text):
    m_ans = ANS_HDR_RE.search(text)
    m_exp = EXP_HDR_RE.search(text)

    q_end = m_ans.start() if m_ans else (m_exp.start() if m_exp else len(text))
    questions = text[:q_end]

    if m_ans and m_exp:
        answers      = text[m_ans.start():m_exp.start()]
        explanations = text[m_exp.start():]
    elif m_ans:
        answers, explanations = text[m_ans.start():], ""
    elif m_exp:
        answers, explanations = "", text[m_exp.start():]
    else:
        answers, explanations = "", ""

    return questions, answers, explanations


def _question_offsets(qblock):
    return [(int(m.group(1)), m.start()) for m in Q_RE.finditer(qblock)]


def split_topic(text):
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    questions, answers, explanations = _split_sections(text)
    offsets = _question_offsets(questions)
    if not offsets:
        return [text]

    header = questions[:offsets[0][1]]
    tail   = "\n\n" + answers + "\n\n" + explanations

    chunks = []
    cur_start = offsets[0][1]
    cur_len   = len(header)

    for i in range(1, len(offsets) + 1):
        boundary = offsets[i][1] if i < len(offsets) else len(questions)
        seg_len  = boundary - cur_start

        if cur_len + seg_len + len(tail) > MAX_CHUNK_CHARS and cur_start < boundary:
            prev_end = offsets[i - 1][1] if i - 1 < len(offsets) else boundary
            chunks.append(header + questions[cur_start:prev_end] + tail)
            cur_start = offsets[i - 1][1]
            cur_len   = len(header)

        cur_len += seg_len

    if cur_start < len(questions):
        chunks.append(header + questions[cur_start:] + tail)

    return chunks or [text]

# ──────────────────────────────────────────────────────────────────────
# JSON CLEANING & REPAIR
# ──────────────────────────────────────────────────────────────────────
def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    # take substring between first '{' and last '}'
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        text = text[s:e + 1]
    return text.strip()


def _repair_json(text: str) -> str:
    """
    Walk the text; inside string literals:
      - convert raw \n  -> \\n
      - convert raw \r  -> \\r
      - convert raw \t  -> \\t
      - keep existing escapes intact
    Then remove trailing commas before } or ].
    """
    out = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                out.append(ch)
                esc = False
                continue
            if ch == "\\":
                out.append(ch)
                esc = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            if ch == "\n":
                out.append("\\n"); continue
            if ch == "\r":
                out.append("\\r"); continue
            if ch == "\t":
                out.append("\\t"); continue
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)

    repaired = "".join(out)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)  # trailing commas
    return repaired


def _extract_json(text: str) -> dict:
    text = _strip_fences(text)

    # attempt 1: as-is
    try:
        return json.loads(text)
    except json.JSONDecodeError as e1:
        first_err = e1

    # attempt 2: repair (raw newlines in strings, trailing commas)
    try:
        return json.loads(_repair_json(text))
    except json.JSONDecodeError:
        pass

    # attempt 3: repair + try to close truncated JSON
    repaired = _repair_json(text)
    # If truncated (no closing brace), try appending closers.
    if not repaired.rstrip().endswith("}"):
        # count braces / brackets to close
        opens = repaired.count("{") - repaired.count("}")
        opens_b = repaired.count("[") - repaired.count("]")
        repaired = repaired + ("]" * max(opens_b, 0)) + ("}" * max(opens, 0))
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"JSON invalid even after repair: {first_err}") from first_err

# ──────────────────────────────────────────────────────────────────────
# CLEANER (DeepSeek)
# ──────────────────────────────────────────────────────────────────────
def clean_chunk(raw_chunk: str) -> list:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": raw_chunk},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": MAX_OUTPUT_TOKENS,
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(API_URL, headers=headers,
                              json=payload, timeout=REQUEST_TIMEOUT)
            if r.status_code == 429:
                raise RuntimeError("rate limited (429)")
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return _extract_json(content).get("questions", [])
        except Exception as e:
            last_err = e
            wait = RETRY_BACKOFF * attempt
            print(f"   [retry {attempt}/{MAX_RETRIES}] {e} — sleeping {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"DeepSeek failed after {MAX_RETRIES} retries: {last_err}")

# ──────────────────────────────────────────────────────────────────────
# DRIVER HELPERS
# ──────────────────────────────────────────────────────────────────────
def find_txt_files(root, only_subject=None, only_stem=None):
    for subject in sorted(os.listdir(root)):
        if only_subject and subject != only_subject:
            continue
        subdir = os.path.join(root, subject)
        if not os.path.isdir(subdir):
            continue
        for fname in sorted(os.listdir(subdir)):
            if not fname.lower().endswith(".txt"):
                continue
            if fname.startswith("_"):
                continue
            if only_stem and os.path.splitext(fname)[0] != only_stem:
                continue
            yield subject, os.path.join(subdir, fname)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _norm(v):
    return "" if v is None else str(v)


def write_csv(questions, csv_path):
    by_no = {}
    for q in questions:
        try:
            n = int(q.get("question_no"))
        except (TypeError, ValueError):
            continue
        by_no[n] = q
    ordered = [by_no[n] for n in sorted(by_no)]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for q in ordered:
            w.writerow({k: _norm(q.get(k, "")) for k in CSV_COLUMNS})
    return len(ordered)


def process_one(subject, txt_path, dry_run=False):
    base     = os.path.splitext(txt_path)[0]
    csv_path = base + ".csv"

    if os.path.exists(csv_path) and not dry_run:
        return (subject, txt_path, "skip (csv exists)", 0)

    raw    = read_text(txt_path)
    chunks = split_topic(raw)

    if dry_run:
        print(f"[dry-run] {txt_path}  chunks={len(chunks)}  chars={len(raw)}")
        return (subject, txt_path, f"dry-run chunks={len(chunks)}", 0)

    all_q = []
    for i, chunk in enumerate(chunks, 1):
        print(f"   {os.path.basename(txt_path)}  chunk {i}/{len(chunks)}  "
              f"({len(chunk)} chars)")
        try:
            all_q.extend(clean_chunk(chunk))
        except Exception as e:
            print(f"   !! chunk {i} failed: {e}")
            traceback.print_exc()

    if not all_q:
        return (subject, txt_path, "ERROR: no questions returned", 0)

    n = write_csv(all_q, csv_path)
    return (subject, txt_path, "ok", n)

# ──────────────────────────────────────────────────────────────────────
# MERGE / REPORT
# ──────────────────────────────────────────────────────────────────────
def _split_name(stem):
    parts = stem.split("_")
    if len(parts) >= 3:
        return parts[0], "_".join(parts[1:-1]), parts[-1]
    return stem, "", ""


def merge_all(root):
    out_csv = os.path.join(root, "_all_questions.csv")
    fields  = ["subject", "exam", "year",
               "question_no", "question",
               "option_a", "option_b", "option_c", "option_d",
               "correct_option", "explanation"]
    rows = []

    for subject in sorted(os.listdir(root)):
        subdir = os.path.join(root, subject)
        if not os.path.isdir(subdir):
            continue
        for fname in sorted(os.listdir(subdir)):
            if not fname.lower().endswith(".csv") or fname.startswith("_"):
                continue
            path = os.path.join(subdir, fname)
            subj, exam, year = _split_name(os.path.splitext(fname)[0])
            with open(path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    r["subject"] = subj
                    r["exam"]    = exam
                    r["year"]    = year
                    rows.append(r)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\nMerged {len(rows)} rows → {out_csv}")


def report_unresolved(root):
    out = os.path.join(root, "_unresolved_answers.csv")
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject", "exam", "year", "question_no", "question"])
        for subject in sorted(os.listdir(root)):
            subdir = os.path.join(root, subject)
            if not os.path.isdir(subdir):
                continue
            for fname in sorted(os.listdir(subdir)):
                if not fname.lower().endswith(".csv") or fname.startswith("_"):
                    continue
                path = os.path.join(subdir, fname)
                subj, exam, year = _split_name(os.path.splitext(fname)[0])
                with open(path, newline="", encoding="utf-8") as fh:
                    for r in csv.DictReader(fh):
                        if not r.get("correct_option", "").strip():
                            w.writerow([subj, exam, year,
                                        r.get("question_no", ""),
                                        r.get("question", "")])
                            n += 1
    print(f"Unresolved answers: {n}  (see {out})")

# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="PYQ txt → DeepSeek → CSV pipeline")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit",   type=int, default=0)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--force",   action="store_true")
    ap.add_argument("--merge",   action="store_true")
    ap.add_argument("--report",  action="store_true")
    ap.add_argument("--only",    type=str, default=None)
    ap.add_argument("--file",    type=str, default=None)
    args = ap.parse_args()

    if not os.path.isdir(INPUT_ROOT):
        print(f"Error: folder '{INPUT_ROOT}' not found.")
        sys.exit(1)

    if args.merge:
        merge_all(INPUT_ROOT); return
    if args.report:
        report_unresolved(INPUT_ROOT); return

    files = list(find_txt_files(INPUT_ROOT, args.only, args.file))
    if args.limit:
        files = files[:args.limit]

    print(f"Files: {len(files)}  workers={args.workers}  "
          f"dry_run={args.dry_run}  force={args.force}  "
          f"max_chunk={MAX_CHUNK_CHARS}  max_tokens={MAX_OUTPUT_TOKENS}")

    if args.force:
        for _, p in files:
            c = os.path.splitext(p)[0] + ".csv"
            if os.path.exists(c):
                os.remove(c)

    ok = err = skip = total_q = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_one, s, p, args.dry_run): (s, p)
                for s, p in files}
        for fut in as_completed(futs):
            subject, path, status, n = fut.result()
            print(f"[{status:>22}] {subject} :: {os.path.basename(path)}  ({n} Q)")
            if status == "ok":
                ok += 1; total_q += n
            elif status.startswith("skip") or status.startswith("dry-run"):
                skip += 1
            else:
                err += 1

    print(f"\nDONE. ok={ok}  skipped={skip}  errors={err}  "
          f"total_questions={total_q}")

    if ok and not args.dry_run:
        report_unresolved(INPUT_ROOT)


if __name__ == "__main__":
    main()