#!/usr/bin/env python3
"""
extract_text.py — extract text + inline figure markers from a PDF.

Works in two modes:
  (default)    reads the PDF text layer directly  -> fast, for clean PDFs
  --ocr        renders each page and OCRs it       -> for PDFs with a broken
                                                    text layer (garbage
                                                    control chars, missing
                                                    ToUnicode, etc.)

Both modes emit the SAME output format:
  ========================================
  --- PAGE 7 ---
  ========================================

  <<<FIGURE q=1 page=7 box=48.0,120.5,564.0,300.2>>>
  Clinical examination
  Question 1:
  A soldier posted in Siachen is brought unconscious...
  a) Oral
  b) Rectal
  ...

Figure boxes come from page.get_images() / page.get_image_info()
(independent of the text layer — works even when text is broken).
Question assignment uses the same anchor logic as before.

Crop later with:
  pix = page.get_pixmap(dpi=300, clip=pymupdf.Rect(x0,y0,x1,y1))
"""

import argparse
import io
import re

import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    _OCR_OK = True
except ImportError:
    _OCR_OK = False


# ─────────────────────────── text decoding ───────────────────────────

def decode_char(c):
    o = ord(c)
    if 0xE000 <= o <= 0xF8FF:
        shifted = o - 0xE000
        if 32 <= shifted <= 0x7E:
            return chr(shifted)
    return c


def decode_text(s):
    return "".join(decode_char(c) for c in s)


# ─────────────────────────── OCR words ───────────────────────────────

def ocr_words(page, dpi=300, psm=6, min_conf=40):
    """OCR a page and return word tuples shaped like page.get_text('words'):
       (x0, y0, x1, y1, text, block_no, line_no, word_no)

    Coordinates are scaled from render pixels back to PDF points so the
    rest of the pipeline (group_lines, find_figure_boxes, render_page_text)
    is identical to the text-layer path.
    """
    if not _OCR_OK:
        raise RuntimeError("pytesseract / PIL not installed; cannot use --ocr")

    scale = 72.0 / dpi
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    data = pytesseract.image_to_data(
        img,
        config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    words = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        if not txt:
            continue
        if int(data["conf"][i]) < min_conf:
            continue
        x, y, w, h = (data["left"][i], data["top"][i],
                      data["width"][i], data["height"][i])
        words.append((
            x * scale, y * scale,
            (x + w) * scale, (y + h) * scale,
            txt,
            data["block_num"][i],
            data["par_num"][i],
            data["line_num"][i],
        ))
    return words


# ─────────────────────────── helpers ─────────────────────────────────

ANCHOR_RE = re.compile(r"(?:Question|Solution\s+to\s+Question)\s+(\d+)",
                       re.IGNORECASE)


def is_page_number(text):
    text = text.strip()
    if not text:
        return False
    return bool(re.match(
        r"^[\-\s]*(?:Page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d+)?[\-\s]*$",
        text, re.IGNORECASE
    ))


MIN_FIG_PT     = 120
TOP_MIN_FIG_PT = 100
PAGE_PAD       = 5
MAX_RATIO      = 0.60


def group_lines(words, y_tol=3.0):
    if not words:
        return []
    items = sorted(words, key=lambda w: (w[1], w[0]))
    lines, cur, cy = [], [], None
    for w in items:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], decode_text(w[4])
        if cy is None or abs(y0 - cy) <= y_tol:
            cur.append((x0, y0, x1, y1, text))
            cy = cy if cy is not None else y0
        else:
            lines.append(cur)
            cur, cy = [(x0, y0, x1, y1, text)], y0
    if cur:
        lines.append(cur)
    return [
        {
            "y0": min(w[1] for w in ln),
            "y1": max(w[3] for w in ln),
            "x0": min(w[0] for w in ln),
            "x1": max(w[2] for w in ln),
            "text": " ".join(w[4] for w in sorted(ln, key=lambda x: x[0])),
        }
        for ln in lines
    ]


# ─────────────────────────── figure detection ────────────────────────

def find_figure_boxes(lines, page_w, page_h, prev_qno=None,
                      pad=PAGE_PAD, min_gap=MIN_FIG_PT,
                      top_min_gap=TOP_MIN_FIG_PT, max_ratio=MAX_RATIO,
                      page=None):

    lines = [ln for ln in lines if not is_page_number(ln["text"])]

    anchors = []
    for ln in lines:
        m = ANCHOR_RE.search(ln["text"])
        if not m:
            continue
        try:
            qno = int(m.group(1))
        except ValueError:
            continue
        anchors.append((qno, ln["y0"], ln["y1"]))
    anchors.sort(key=lambda a: a[1])

    def qno_above(y):
        owner = prev_qno
        for q, ay0, ay1 in anchors:
            if ay0 < y:
                owner = q
            else:
                break
        return owner

    boxes = []
    seen_rects = set()

    # ── 1) Embedded image detection ──
    if page is not None:
        def try_add(x0, y0, x1, y1):
            w, h = x1 - x0, y1 - y0
            # tiny icon
            if w < 30 or h < 30:
                return
            # full-page background (watermark / border) — the reason your
            # PDF produced one giant false figure per page
            if w > page_w * 0.95 and h > page_h * 0.95:
                return
            # full-width short header banner
            if w > page_w * 0.95 and y0 < 120 and h < 160:
                return
            # bottom logo strip
            if y0 > page_h * 0.92 and h < 60:
                return

            key = (round(x0), round(y0), round(x1), round(y1))
            if key in seen_rects:
                return

            owner = qno_above(y0)
            if owner is None:
                if y0 < 150 and anchors:
                    owner = anchors[0][0]
                else:
                    return

            seen_rects.add(key)
            bx = (max(0, x0 - pad), max(0, y0 - pad),
                  min(page_w, x1 + pad), min(page_h, y1 + pad))
            boxes.append((owner, bx, "image"))

        try:
            for img in page.get_images(full=True):
                try:
                    bbox = page.get_image_bbox(img)
                except Exception:
                    continue
                try_add(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        except Exception:
            pass

        # get_image_info catches hidden XObjects / inline images that
        # get_images misses. Runs unconditionally now (was dead code when
        # gated by `if not boxes:` because the background image always
        # populated boxes first).
        try:
            for info in page.get_image_info():
                x0, y0, x1, y1 = info["bbox"]
                try_add(x0, y0, x1, y1)
        except Exception:
            pass

    # ── 2) Gap fallback only if no embedded images found ──
    if not boxes:
        if anchors and prev_qno is not None:
            first_top = anchors[0][1]
            if first_top >= top_min_gap:
                rows = [(ln["y0"], ln["y1"]) for ln in lines
                        if ln["y1"] < first_top]
                if rows:
                    last_y1 = max(r[1] for r in rows)
                    fig_top, fig_bot = 0, last_y1 - 2
                    if fig_bot - fig_top >= top_min_gap:
                        boxes.append((prev_qno,
                                      (pad, fig_top, page_w - pad, fig_bot),
                                      "top"))
                else:
                    boxes.append((prev_qno,
                                  (pad, 0, page_w - pad, first_top - 2),
                                  "top"))

        for i, (qno, ay0, ay1) in enumerate(anchors):
            band_top = ay1 + 1
            band_bot = anchors[i + 1][1] - 1 if i + 1 < len(anchors) else page_h
            if band_bot - band_top < min_gap:
                continue

            band_lines = [ln for ln in lines
                          if ln["y1"] > band_top and ln["y0"] < band_bot]
            band_lines.sort(key=lambda x: x["y0"])

            if not band_lines:
                if band_bot - band_top >= min_gap:
                    boxes.append((qno,
                                  (pad, band_top, page_w - pad, band_bot),
                                  "normal"))
                continue

            current_y = band_top
            for ln in band_lines:
                gap = ln["y0"] - current_y
                if gap >= min_gap:
                    fig_h = min(gap, page_h * max_ratio)
                    boxes.append((qno,
                                  (pad, current_y, page_w - pad,
                                   current_y + fig_h),
                                  "normal"))
                current_y = ln["y1"]

            final_gap = band_bot - current_y
            if final_gap >= min_gap:
                fig_h = min(final_gap, page_h * max_ratio)
                boxes.append((qno,
                              (pad, current_y, page_w - pad,
                               current_y + fig_h),
                              "normal"))

    return boxes


# ─────────────────────────── rendering ───────────────────────────────

def render_page_text(lines, boxes, page_no):
    boxes_by_q = {}
    for q, b, kind in boxes:
        boxes_by_q.setdefault(q, []).append(b)

    out = []

    # top-of-page images printed before text
    for q in list(boxes_by_q.keys()):
        remaining = []
        for idx, (x0, y0, x1, y1) in enumerate(boxes_by_q[q]):
            if y0 < 300:
                suffix = f"_{idx}" if idx > 0 else ""
                out.append(
                    f"<<<FIGURE q={q}{suffix} page={page_no} "
                    f"box={x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}>>>"
                )
            else:
                remaining.append((x0, y0, x1, y1))
        boxes_by_q[q] = remaining

    # text + inline markers
    for ln in lines:
        txt = ln["text"]
        m = ANCHOR_RE.search(txt)
        if m:
            try:
                qno = int(m.group(1))
            except ValueError:
                qno = None
            if qno in boxes_by_q:
                for idx, (x0, y0, x1, y1) in enumerate(boxes_by_q[qno]):
                    suffix = f"_{idx}" if idx > 0 else ""
                    out.append(
                        f"<<<FIGURE q={qno}{suffix} page={page_no} "
                        f"box={x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}>>>"
                    )
        out.append(txt)

    return "\n".join(out)


# ─────────────────────────── main extract ────────────────────────────

def extract(pdf_path, out_txt, page_range=None,
            use_ocr=False, ocr_dpi=300, ocr_psm=6):
    doc   = fitz.open(pdf_path)
    total = len(doc)

    if page_range:
        lo, hi = page_range
        page_idxs = list(range(max(1, lo) - 1, min(total, hi)))
    else:
        page_idxs = list(range(total))

    mode = "OCR" if use_ocr else "text-layer"
    print(f"Mode: {mode} | pages: {len(page_idxs)} / {total} "
          f"({page_idxs[0] + 1}–{page_idxs[-1] + 1})")

    pieces    = []
    fig_total = 0
    prev_qno  = None

    for i in page_idxs:
        page = doc[i]
        rect = page.rect

        if use_ocr:
            words = ocr_words(page, dpi=ocr_dpi, psm=ocr_psm)
        else:
            words = page.get_text("words")

        lines = group_lines(words)

        boxes = find_figure_boxes(lines, rect.width, rect.height,
                                  prev_qno=prev_qno, page=page)
        text = render_page_text(lines, boxes, i + 1)

        for ln in lines:
            m = ANCHOR_RE.search(ln["text"])
            if m:
                try:
                    prev_qno = int(m.group(1))
                except ValueError:
                    pass

        fig_total += len(boxes)
        print(f"  page {i + 1:>4}: {len(boxes)} fig, {len(words):>4} words")

        pieces.append(
            f"\n\n{'=' * 40}\n--- PAGE {i + 1} ---\n{'=' * 40}\n\n"
            + text
        )

    doc.close()

    final = out_txt
    if page_range:
        final = out_txt.replace(".txt",
                                f"_{page_range[0]}_{page_range[1]}.txt")
    if use_ocr:
        final = final.replace(".txt", "_ocr.txt")

    with open(final, "w", encoding="utf-8") as f:
        f.write("".join(pieces))
    print(f"\nSaved: {final}")
    print(f"Figures detected: {fig_total}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf",   default="Medicine_ed8 (1).pdf")
    ap.add_argument("--txt",   default="extracted_text.txt")
    ap.add_argument("--pages", nargs=2, type=int, metavar=("START", "END"))
    ap.add_argument("--ocr",   action="store_true",
                    help="OCR every page (use when the text layer is garbage)")
    ap.add_argument("--dpi",   type=int, default=300,
                    help="OCR render DPI (default 300)")
    ap.add_argument("--psm",   type=int, default=6,
                    help="Tesseract page-segmentation mode (default 6)")
    args = ap.parse_args()

    extract(args.pdf, args.txt, args.pages,
            use_ocr=args.ocr, ocr_dpi=args.dpi, ocr_psm=args.psm)
