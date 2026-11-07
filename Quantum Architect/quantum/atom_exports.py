"""A4 portrait PDFs for the orbital-box worksheet, student and answer key.

Two small elements share a page - top half and bottom half, with a cut line
between them - and a large configuration gets the whole page. Every block prints
the sublevel boxes (empty for the student, arrows for the key), the mℓ values
under the boxes, and the Bohr model in the upper right.

Arrows are drawn as vector strokes rather than glyphs, so the sheet prints the
same on a machine whose fonts have no arrow characters.
"""

from __future__ import annotations

import io
import math
import os

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from quantum import atom_sheets
from quantum.exports import _pdf_fonts, _split_superscripts

PAGE_W, PAGE_H = A4
MARGIN = 12 * mm
BODY_TOP = 30 * mm
BODY_BOTTOM = 13 * mm

INK = HexColor("#0f172a")
MUTED = HexColor("#64748b")
RULE = HexColor("#94a3b8")
SOFT = HexColor("#e2e8f0")
RED = HexColor("#dc2626")
BLUE = HexColor("#1d4ed8")
NUCLEUS = HexColor("#e879f9")

BOLD_CANDIDATES = [
    ("DejaVuSans-Bold", ("C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ("LiberationSans-Bold", ("C:\\Windows\\Fonts\\liberation\\LiberationSans-Bold.ttf",
                             "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")),
    ("Arial-Bold", ("C:\\Windows\\Fonts\\arialbd.ttf",)),
    ("SegoeUIBold", ("C:\\Windows\\Fonts\\segoeuib.ttf",)),
    ("CalibriBold", ("C:\\Windows\\Fonts\\calibrib.ttf",)),
    ("TahomaBold", ("C:\\Windows\\Fonts\\tahomabd.ttf",)),
]


def _bold_font() -> str | None:
    for name, paths in BOLD_CANDIDATES:
        for path in paths:
            if not os.path.isfile(path):
                continue
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    return None


def student_pdf(record: dict) -> bytes:
    return _build(record, "student")


def key_pdf(record: dict) -> bytes:
    return _build(record, "key")


def both_pdf(record: dict) -> bytes:
    """Student pages followed by the answer-key pages in one file."""
    return _build(record, "both")


def _build(record: dict, mode: str) -> bytes:
    body, mono, _arrows = _pdf_fonts()
    bold = _bold_font() or body
    sheet = atom_sheets.build_sheet(record)
    pages = sheet["pages"]
    variants = [False, True] if mode == "both" else [mode == "key"]
    total = max(1, len(pages) * len(variants))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    titles = {"student": "student copy", "key": "answer key",
              "both": "student copy + answer key"}
    c.setTitle("%s - %s" % (record["settings"]["title"], titles[mode]))
    c.setAuthor("Quantum Architect")
    page_no = 0
    for teacher in variants:
        for blocks in pages:
            page_no += 1
            _draw_page(c, record, blocks, teacher, page_no, total, body, bold, mono)
            c.showPage()
    c.save()
    return buffer.getvalue()


def _draw_page(c, record, blocks, teacher, page_no, total, body, bold, mono):
    _draw_header(c, record, teacher, body, bold)
    content_height = PAGE_H - BODY_TOP - BODY_BOTTOM
    width = PAGE_W - 2 * MARGIN
    if len(blocks) >= 2:
        gap = 5 * mm
        block_height = (content_height - gap) / 2
        _draw_block(c, record, blocks[0], MARGIN, BODY_TOP, width, block_height,
                    teacher, body, bold, mono, full=False)
        _cut_line(c, BODY_TOP + block_height + gap / 2, body)
        _draw_block(c, record, blocks[1], MARGIN, BODY_TOP + block_height + gap,
                    width, block_height, teacher, body, bold, mono, full=False)
    elif blocks:
        _draw_block(c, record, blocks[0], MARGIN, BODY_TOP, width, content_height,
                    teacher, body, bold, mono, full=True)
    _footer(c, teacher, page_no, total, body)


def _draw_header(c, record, teacher, body, bold):
    settings = record["settings"]
    title = settings["title"] or "Orbital Box Worksheet"
    baseline = 15 * mm
    c.setFont(bold, 15)
    c.setFillColor(INK)
    c.drawString(MARGIN, PAGE_H - baseline, title)

    if teacher:
        c.setFont(bold, 9.5)
        c.setFillColor(RED)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - baseline,
                          "ANSWER KEY  ·  TEACHER COPY")

    facts = ("Name: ____________________________    Class: %s    Section: %s    Date: %s"
             % (settings.get("class_name") or "____________",
                settings.get("section") or "____________",
                settings.get("date") or "____________"))
    if teacher:
        facts = ("Teacher: %s    Class: %s    Section: %s    Date: %s"
                 % (settings.get("teacher") or "____________",
                    settings.get("class_name") or "____________",
                    settings.get("section") or "____________",
                    settings.get("date") or "____________"))
    c.setFont(body, 8)
    c.setFillColor(MUTED)
    c.drawString(MARGIN, PAGE_H - 21 * mm, facts)

    instruction = settings.get("instructions", "")
    if teacher:
        instruction = ("Teacher copy: the boxes carry the correct spins; the configuration, "
                       "energy order and shell counts are printed under each diagram.")
    c.setFont(body, 7.2)
    c.setFillColor(MUTED)
    c.drawString(MARGIN, PAGE_H - 25.5 * mm, instruction)

    c.setStrokeColor(SOFT)
    c.setLineWidth(0.8)
    c.line(MARGIN, PAGE_H - 27.5 * mm, PAGE_W - MARGIN, PAGE_H - 27.5 * mm)


def _footer(c, teacher, page_no, total, body):
    c.setFont(body, 6.8)
    c.setFillColor(MUTED)
    c.drawString(MARGIN, 7 * mm, "Quantum Architect  ·  Orbital box worksheet")
    c.drawRightString(PAGE_W - MARGIN, 7 * mm,
                      ("ANSWER KEY" if teacher else "student copy")
                      + "  ·  page %d of %d" % (page_no, total))


def _draw_block(c, record, block, x, top, width, height, teacher, body, bold, mono, full):
    show_bohr = bool(record["settings"].get("show_bohr", True))
    pad = 3.5 * mm
    c.setStrokeColor(SOFT)
    c.setLineWidth(0.7)
    c.roundRect(x, PAGE_H - top - height, width, height, 2.5 * mm, stroke=1, fill=0)

    inner_x = x + pad
    inner_w = width - 2 * pad
    inner_top = top + pad
    inner_bottom = top + height - pad

    title = "Z = %d    %s  ·  %s" % (block["z"], block["symbol"], block["name"])
    _text(c, inner_x, inner_top + 4.4 * mm, title, bold, 12, INK)
    meta = "period %d  ·  group %s  ·  %s-block  ·  %d valence electrons" % (
        block["period"], block["group_label"], block["block"], block["valence"])
    _text(c, inner_x + inner_w, inner_top + 4.2 * mm, meta, body, 7.2, MUTED, align="right")

    c.setStrokeColor(SOFT)
    c.setLineWidth(0.6)
    c.line(inner_x, PAGE_H - (inner_top + 6.6 * mm),
           inner_x + inner_w, PAGE_H - (inner_top + 6.6 * mm))

    content_top = inner_top + 8.5 * mm
    answer_height = 16 * mm if teacher else 1.5 * mm
    rows_bottom = inner_bottom - answer_height
    rows = block["rows"]
    available = rows_bottom - content_top
    row_height = min((24 * mm if full else 18 * mm),
                     available / max(1, len(rows)))
    # Centre the group of rows in the block instead of stacking it under the
    # title, so a one-row element does not leave the whole half-page empty.
    start_top = content_top + max(0.0, (available - row_height * len(rows)) / 2)

    left_w = inner_w * 0.64 if show_bohr else inner_w
    label_w = 11 * mm
    gap = 1.7 * mm
    max_boxes = max(len(row["ml"]) for row in rows)
    box_cap = 20 * mm if full else 18 * mm
    box_w = min(box_cap, (left_w - label_w - (max_boxes - 1) * gap) / max_boxes)
    box_h = max(5 * mm, min(16 * mm if full else 12 * mm, row_height - 6 * mm))
    group_w = max_boxes * box_w + (max_boxes - 1) * gap
    box_left = inner_x + label_w + max(0.0, (left_w - label_w - group_w) / 2)

    for index, row in enumerate(rows):
        center = start_top + index * row_height + row_height / 2
        _text(c, inner_x + 0.5 * mm, center + 3.1 * mm, row["sublevel"], mono, 10, INK)
        box_top = center - box_h / 2
        for orbit, ml in enumerate(row["ml"]):
            bx = box_left + orbit * (box_w + gap)
            by = PAGE_H - (box_top + box_h)
            c.setStrokeColor(INK)
            c.setLineWidth(0.9)
            c.rect(bx, by, box_w, box_h, stroke=1, fill=0)
            _text(c, bx + box_w / 2, box_top + box_h + 2.2 * mm,
                  ("−" if ml < 0 else "") + str(abs(ml)), body, 5.2, MUTED, align="center")
            if teacher:
                _draw_spins(c, row["boxes"][orbit], bx, by, box_w, box_h)

    if show_bohr:
        right_x = inner_x + left_w + 2 * mm
        right_w = inner_w - left_w - 2 * mm
        _text(c, right_x + right_w / 2, content_top + 2.8 * mm,
              "Bohr model", bold, 7.4, MUTED, align="center")
        size = min(right_w - 2 * mm, 76 * mm if full else 54 * mm)
        center_top = content_top + 5 * mm + size / 2
        _draw_bohr(c, right_x + right_w / 2, center_top, size, block["bohr"], body, bold)

    if teacher:
        _draw_answers(c, block, inner_x, inner_w, inner_bottom, body, bold, mono)


def _draw_spins(c, arrows, bx, by, box_w, box_h):
    if not arrows:
        return
    height = box_h * 0.62
    bottom = by + box_h * 0.19
    if arrows == "↑↓":
        _arrow(c, bx + box_w * 0.30, bottom, height, up=True)
        _arrow(c, bx + box_w * 0.70, bottom, height, up=False)
    elif arrows == "↓":
        _arrow(c, bx + box_w * 0.5, bottom, height, up=False)
    else:
        _arrow(c, bx + box_w * 0.5, bottom, height, up=True)


def _arrow(c, x, y_bottom, height, up=True):
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.setLineCap(1)
    head = 1.15 * mm
    if up:
        top = y_bottom + height
        c.line(x, y_bottom, x, top)
        c.line(x, top, x - head, top - 1.9 * mm)
        c.line(x, top, x + head, top - 1.9 * mm)
    else:
        bottom = y_bottom
        top = y_bottom + height
        c.line(x, top, x, bottom)
        c.line(x, bottom, x - head, bottom + 1.9 * mm)
        c.line(x, bottom, x + head, bottom + 1.9 * mm)


def _draw_bohr(c, cx, center_top, size, bohr, body, bold):
    radius = size / 2 - 1.5 * mm
    center_y = PAGE_H - center_top
    for ring in bohr["rings"]:
        r = radius * ring["r"] / 88.0
        color = RED if ring["valence"] else RULE
        c.setStrokeColor(color)
        c.setLineWidth(0.9 if ring["valence"] else 0.55)
        c.circle(cx, center_y, r, stroke=1, fill=0)
        dot = max(0.45, min(0.95, 12.0 / max(1, ring["count"]))) * mm
        c.setFillColor(color)
        for point in ring["dots"]:
            dx = cx + (point["x"] - 100) / 88.0 * radius
            dy = center_y - (point["y"] - 100) / 88.0 * radius
            c.circle(dx, dy, dot, stroke=0, fill=1)
        _text(c, cx, center_top - r - 1.1 * mm,
              ring["letter"] + str(ring["count"]), bold, 5.3,
              RED if ring["valence"] else MUTED, align="center")

    c.setFillColor(NUCLEUS)
    c.circle(cx, center_y, 2.7 * mm, stroke=0, fill=1)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont(bold, 6.2)
    c.drawCentredString(cx, center_y - 2.1, bohr["symbol"])


def _draw_answers(c, block, x, width, bottom, body, bold, mono):
    y1 = bottom - 8.5 * mm
    y2 = bottom - 11.8 * mm
    y3 = bottom - 15.0 * mm

    c.setStrokeColor(SOFT)
    c.setLineWidth(0.5)
    c.setDash([1.4, 1.4], 0)
    c.line(x, PAGE_H - (bottom - 5.6 * mm), x + width, PAGE_H - (bottom - 5.6 * mm))
    c.setDash([])

    cursor = _rich(c, x, y1, "Configuration: ", bold, 7.2, MUTED)
    size = _fit_rich_size(block["config"], mono, 8.2, x + width - cursor)
    _rich(c, cursor, y1, block["config"], mono, size, INK)

    cursor = _rich(c, x, y2, "Energy order: ", bold, 6.8, MUTED)
    size = _fit_rich_size(block["config_fill"], mono, 7.2, x + width - cursor)
    _rich(c, cursor, y2, block["config_fill"], mono, size, INK)

    shells = "  ·  ".join("%s %d" % (ring["letter"], ring["count"])
                          for ring in block["bohr"]["rings"])
    _rich(c, x, y3,
          "Shells: %s    ·    %s    ·    valence %d"
          % (block["shell_text"], shells, block["valence"]),
          body, 7.0, MUTED)


def _cut_line(c, y_top, body):
    y = PAGE_H - y_top
    c.saveState()
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.setDash([2, 2], 0)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    c.setDash([])
    c.setFont(body, 5.8)
    c.setFillColor(MUTED)
    c.drawCentredString(PAGE_W / 2, y + 1.5 * mm, "cut here")
    c.restoreState()


# --------------------------------------------------------------------------- #
# Text helpers (superscript-aware, because the key prints 1s² 2s² 2p⁶)
# --------------------------------------------------------------------------- #

def _text(c, x, y_top, text, font, size, color=INK, align="left"):
    c.setFont(font, size)
    c.setFillColor(color)
    y = PAGE_H - y_top
    if align == "right":
        c.drawRightString(x, y, text)
    elif align == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _rich_width(text, font, size):
    total = 0.0
    for chunk, is_super in _split_superscripts(text):
        total += stringWidth(chunk, font, size * 0.66 if is_super else size)
    return total


def _fit_rich_size(text, font, size, max_width, floor=5.2):
    while size > floor and _rich_width(text, font, size) > max_width:
        size -= 0.2
    return size


def _rich(c, x, y_top, text, font, size, color=INK):
    """Draw text with unicode superscripts raised; returns the right edge."""
    c.setFillColor(color)
    y = PAGE_H - y_top
    for chunk, is_super in _split_superscripts(text):
        drawn = size * 0.66 if is_super else size
        c.setFont(font, drawn)
        c.drawString(x, y + (size * 0.34 if is_super else 0), chunk)
        x += stringWidth(chunk, font, drawn)
    return x
