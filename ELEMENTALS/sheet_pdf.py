"""Symbol Sprint activity sheets on PDF, drawn with reportlab.

The handout is the tile grid the teachers asked for: twenty tiles on one A4
page, two columns of ten, and the answer space sits inside each tile. A tile
carries the item number and its clues, trimmed to the room the tile has. The
answer key is the same twenty tiles with the element named and its symbol
printed, so a staff member can print either version straight from the sheet.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 24
GAP = 4
COLS, ROWS = 2, 10           # twenty tiles a page: two columns of ten
CELL_W = (PAGE_W - 2 * MARGIN - GAP) / COLS
NAVY = (20 / 255, 33 / 255, 61 / 255)
GREY = (0.25, 0.3, 0.4)
TITLE = "ELEMENTALS - Periodic Table Symbol Sprint"
BLANK_HEADER = ("Name __________________   Grade ____________   "
                "Section ____________")
CLUE = 6.0                   # clue text size: the one fixed trade for 20-a-page
CLUE_LEAD = 7.2


def worksheet_pdf(items, total):
    """The class copy: clues in the tiles, answer space left empty."""
    return _sheet(items, total, answers=False)


def answer_key_pdf(items, total):
    """The staff copy: the same tiles with the element and its symbol printed."""
    return _sheet(items, total, answers=True)


def _fit(text, font, size, width):
    """Shorten the text until it prints inside a tile without spilling."""
    if not text:
        return ""
    while text and stringWidth(text, font, size) > width:
        text = text[:-2] + "."
    return text


def _tile(c, item, x, y_top, h, answers):
    w = CELL_W
    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.7)
    c.rect(x, y_top - h, w, h, fill=0, stroke=1)
    pad = 4
    inner = w - 2 * pad
    y = y_top - pad - 7
    c.setFillColorRGB(*NAVY)
    c.setFont("Helvetica-Bold", 7)
    name = item['name'] if answers else "_" * 30
    c.drawString(x + pad, y, _fit("%d.  %s" % (item['n'], name),
                                  "Helvetica-Bold", 7, inner))
    y -= 9
    c.setFont("Helvetica", CLUE)
    c.setFillColorRGB(*GREY)
    floor = y_top - h + pad + 10          # the symbol line owns the tile footer
    for text in item['clues']:
        if y - CLUE_LEAD < floor:
            break
        c.drawString(x + pad, y, _fit("- " + str(text), "Helvetica", CLUE, inner))
        y -= CLUE_LEAD
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 7.5)
    answer_line = y_top - h + pad + 3
    c.drawString(x + pad, answer_line, "Symbol:")
    if answers:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + pad + 32, answer_line, item['symbol'])
    else:
        c.setFont("Helvetica", 8)
        c.drawString(x + pad + 32, answer_line,
                     _fit("_" * 60, "Helvetica", 8, inner - 32))


def _head(c, answers, total):
    top = TITLE + "  -  ANSWER KEY (staff)" if answers else TITLE
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(*NAVY)
    c.drawString(MARGIN, PAGE_H - MARGIN, top)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(MARGIN, PAGE_H - MARGIN - 11, BLANK_HEADER)
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*GREY)
    note = ("The element named and the symbol printed in each tile - for the teacher."
            if answers else
            "Read the clues in each tile and write the chemical symbol in the "
            "Symbol space inside the tile.   %d tiles." % total)
    c.drawString(MARGIN, PAGE_H - MARGIN - 20, note)
    return PAGE_H - MARGIN - 28


def _sheet(items, total, answers):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    per_page = COLS * ROWS
    for start in range(0, max(len(items), 1), per_page):
        y_top = _head(c, answers, total)
        cell_h = (y_top - MARGIN - GAP * (ROWS - 1)) / ROWS
        for index, item in enumerate(items[start:start + per_page]):
            col, row = divmod(index, ROWS)      # column-first: ten tiles a column
            x = MARGIN + col * (CELL_W + GAP)
            y = y_top - row * (cell_h + GAP)
            _tile(c, item, x, y, cell_h, answers)
        c.showPage()
    c.save()
    return buf.getvalue()
