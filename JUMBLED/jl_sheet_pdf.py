"""Jumbled Letters worksheets on PDF, drawn with reportlab.

Each item is the shuffled letters in little boxes, exactly as the board shows
them, with a line under the boxes for the student to write the word on. The
answer key prints the topic word on that line.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 48
NAVY = (20 / 255, 33 / 255, 61 / 255)
GOLD = (0.98, 0.94, 0.72)
BOX_BG = (0.93, 0.94, 0.96)
TITLE = "Jumbled Letters - Topic Word Sprint"
BLANK_HEADER = ("Name ____________________    Grade ____________    "
                "Section ____________")


def worksheet_pdf(path, items):
    """Ten boxed jumbles with a blank line under each - what the class gets."""
    return _sheet(path, items, answers=False)


def answer_key_pdf(path, items):
    """The same ten jumbles with the topic word written on the line."""
    return _sheet(path, items, answers=True)


def _sheet(path, items, answers):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def head(first):
        c.setFont("Helvetica-Bold", 15)
        c.setFillColorRGB(*NAVY)
        top = TITLE if first else TITLE + " (continued)"
        if answers:
            top += "  -  ANSWER KEY"
        c.drawString(MARGIN, PAGE_H - MARGIN, top)
        y = PAGE_H - MARGIN - 16
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.2, 0.25, 0.35)
        where = " -  ".join(p for p in path if p)
        if where:
            c.drawString(MARGIN, y, "Words taken from: " + where)
            y -= 16
        if first:
            c.setFont("Helvetica", 11)
            c.setFillColorRGB(0, 0, 0)
            if answers:
                c.drawString(MARGIN, y, "Prepared by the teacher - the topic word is written "
                                        "under each jumble.")
            else:
                c.drawString(MARGIN, y,
                             "Unscramble the letters in the boxes and write the word on the line.")
                y -= 18
                c.drawString(MARGIN, y, BLANK_HEADER)
            y -= 20
        return y - 8

    y = head(True)
    line = PAGE_W - 2 * MARGIN
    for item in items:
        letters = list(item['jumble'])
        box = min(24.0, (line - 30) / max(len(letters), 1))
        if y - (box + 34) < MARGIN:
            c.showPage()
            y = head(False)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(*NAVY)
        c.drawString(MARGIN, y - box + 2, "%d." % item['n'])
        x = MARGIN + 26
        for ch in letters:
            c.setFillColorRGB(*BOX_BG)
            c.rect(x, y - box, box - 3, box, fill=1, stroke=0)
            c.setStrokeColorRGB(*NAVY)
            c.setLineWidth(0.8)
            c.rect(x, y - box, box - 3, box, fill=0, stroke=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", box * 0.55)
            c.drawCentredString(x + (box - 3) / 2, y - box * 0.72, ch.upper())
            x += box
        y -= box + 14
        c.setFont("Helvetica", 11)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(MARGIN + 26, y, "Answer:")
        if answers:
            c.setFont("Helvetica-Bold", 13)
            c.setFillColorRGB(*NAVY)
            c.drawString(MARGIN + 26 + 46, y, item['word'])
            c.setFillColorRGB(0, 0, 0)
        else:
            c.drawString(MARGIN + 26 + 46, y, "_" * 34)
        y -= 26
    c.showPage()
    c.save()
    return buf.getvalue()
