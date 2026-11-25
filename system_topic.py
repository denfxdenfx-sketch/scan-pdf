#!/usr/bin/env python3
# system_topic.py
# Auto-detects delimiter, strips BOM, trims header whitespace.

import csv
import sys
from pathlib import Path


INPUT   = "/Users/priyanshu/marrow convertor/_all_questions_FINAL1.tagged.csv"
OUTPUT  = "/Users/priyanshu/marrow convertor/pyq/questions_with_st.csv"
SEP     = "-"


def clean(v) -> str:
    return (v or "").strip()


def sniff_delimiter(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        header = f.readline()
    tabs   = header.count("\t")
    commas = header.count(",")
    delim  = "\t" if tabs >= commas else ","
    print(f"detected delimiter: {repr(delim)}  (tabs={tabs}, commas={commas})")
    return delim


def main():
    src = Path(INPUT)
    if not src.exists():
        print(f"error: input not found: {src}", file=sys.stderr)
        sys.exit(1)

    delim = sniff_delimiter(src)

    with open(src, newline="", encoding="utf-8-sig") as fin, \
         open(OUTPUT, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin, delimiter=delim)
        if reader.fieldnames is None:
            print("error: no header row", file=sys.stderr)
            sys.exit(1)

        # Trim whitespace / \r from header names
        reader.fieldnames = [f.strip() for f in reader.fieldnames]
        print(f"columns: {reader.fieldnames}")

        if "system" not in reader.fieldnames:
            print(f"error: 'system' not in header — got {reader.fieldnames}", file=sys.stderr)
            sys.exit(1)
        if "subject" not in reader.fieldnames:
            print(f"error: 'subject' not in header — got {reader.fieldnames}", file=sys.stderr)
            sys.exit(1)

        fieldnames = list(reader.fieldnames)
        if "system_topic" in fieldnames:
            fieldnames.remove("system_topic")
        fieldnames.append("system_topic")

        writer = csv.DictWriter(fout, fieldnames=fieldnames,
                                delimiter=delim,
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        rows = 0
        blanks = 0
        samples = []  # first 3 non-blank for eyeballing

        for row in reader:
            system  = clean(row.get("system"))
            subject = clean(row.get("subject"))

            if system and subject:
                row["system_topic"] = f"{system}{SEP}{subject}"
                if len(samples) < 3:
                    samples.append((subject, system, row["system_topic"]))
            else:
                row["system_topic"] = ""
                blanks += 1

            writer.writerow({k: row.get(k, "") for k in fieldnames})
            rows += 1

    print(f"\nwrote {OUTPUT}")
    print(f"  rows: {rows}")
    print(f"  blank system_topic: {blanks}")
    if samples:
        print("\n  sample labels built:")
        for subj, sysv, lbl in samples:
            print(f"    subject={subj!r}  system={sysv!r}  →  {lbl!r}")


if __name__ == "__main__":
    main()