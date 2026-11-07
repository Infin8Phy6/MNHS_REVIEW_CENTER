"""Elemental Table worksheets on PDF, drawn with reportlab.

The handout keeps the landscape shape of etg_export.js - nine columns, five
rows - but leaves the 25 dealt cells empty for a student to fill in, and the
answer key prints the same table with every cell filled.
"""
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 36
NAVY = (20 / 255, 33 / 255, 61 / 255)
GOLD = (0.98, 0.94, 0.72)
GREY = (0.93, 0.94, 0.96)
BLANK_HEADER = ("Name ________________________    Grade ____________    "
                "Section ____________")


def worksheet_pdf(table, heads, columns, max_points):
    """The dealt table with its 25 cells left empty - what the class gets."""
    return _sheet(table, heads, columns, max_points, answers=False)


def answer_key_pdf(table, heads, columns, max_points):
    """The same table every cell filled; the dealt blanks shown in bold."""
    return _sheet(table, heads, columns, max_points, answers=True)


def _fit(c, text, width, size):
    while size > 6 and stringWidth(str(text), "Helvetica-Bold", size) > width - 8:
        size -= 0.5
    return size


def _sheet(table, heads, columns, max_points, answers):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    rows, cols = len(table), len(columns)

    title = "Elemental Table Game - Fill the Table"
    if answers:
        title += "   -   ANSWER KEY"
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(*NAVY)
    c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN - 6, title)

    c.setFont("Helvetica", 11)
    c.setFillColorRGB(0, 0, 0)
    if answers:
        c.drawString(MARGIN, PAGE_H - MARGIN - 26,
                     "The cells the worksheet leaves empty are printed in bold on a gold cell.")
    else:
        c.drawString(MARGIN, PAGE_H - MARGIN - 26, BLANK_HEADER)

    top = PAGE_H - MARGIN - 42
    bottom = MARGIN + 26
    row_h = (top - bottom) / (rows + 1)
    base_w = (PAGE_W - 2 * MARGIN) / (cols + 0.5)
    widths = [base_w * 1.5] + [base_w] * (cols - 1)
    x0 = (PAGE_W - sum(widths)) / 2

    y = top - row_h
    x = x0
    for index, column in enumerate(columns):
        c.setFillColorRGB(*NAVY)
        c.rect(x, y, widths[index], row_h, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        size = _fit(c, heads[column], widths[index], 10.5)
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(x + widths[index] / 2, y + row_h / 2 - size * 0.35,
                            heads[column])
        x += widths[index]

    for r, row in enumerate(table):
        ry = top - (r + 2) * row_h
        x = x0
        for index, column in enumerate(columns):
            w = widths[index]
            blank = column in row['blanks']
            if blank:
                c.setFillColorRGB(*(GOLD if answers else GREY))
                c.rect(x, ry, w, row_h, fill=1, stroke=0)
            text = row['truth'][column] if answers else row['given'].get(column, '')
            c.setFillColorRGB(0, 0, 0)
            if text:
                size = _fit(c, text, w, 12)
                c.setFont("Helvetica-Bold" if blank else "Helvetica", size)
                c.drawCentredString(x + w / 2, ry + row_h / 2 - size * 0.35, text)
            c.setStrokeColorRGB(*NAVY)
            c.setLineWidth(0.7)
            c.rect(x, ry, w, row_h, fill=0, stroke=1)
            x += w

    note = ("Fill the shaded cells. In every row the printed cells are the clues: mass number ="
            " protons + neutrons, protons = electrons in a neutral atom, and the group gives"
            " the valence count."
            if not answers else
            "One element per row; only the main groups of periods 1-4 are dealt.")
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.25, 0.3, 0.4)
    c.drawCentredString(PAGE_W / 2, MARGIN + 8, note)
    c.showPage()
    c.save()
    return buf.getvalue()
