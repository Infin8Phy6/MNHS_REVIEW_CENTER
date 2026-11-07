"""Crossword sheets on PDF, drawn with reportlab.

Keeps the two-page shape of crossword_generator.py - grid first, a Name/Date/
Grade/Score header with the word list second - but the cells are true squares
and the take-home sheet prints numbered CLUES instead of the answers, so the
worksheet no longer gives the puzzle away.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 48
NAVY = (20 / 255, 33 / 255, 61 / 255)
BLANK_HEADER = ("Name ____________________    Grade ____________    "
                "Section ____________")


def worksheet_pdf(puzzle):
    """Empty squares with clue numbers, then the numbered clues: the handout."""
    return _sheet(puzzle, letters=False, answers=False)


def answer_key_pdf(puzzle):
    """The finished grid and every clue with its answer beside it."""
    return _sheet(puzzle, letters=True, answers=True)


def easy_pdf(puzzle):
    """Easy level word hunt: solved grid with no clue numbers, each definition
    followed by a blank the student writes the answer word on."""
    return _sheet(puzzle, letters=True, answers=False, numbers=False,
                  blanks=True)


def attempt_pdf(puzzle, attempt):
    """A student's finished attempt: solved grid and their own filled header."""
    header = "Name: %s    Date: %s    Grade: %s    Section: %s    Score: %d / %d" % (
        attempt.get("student", ""), (attempt.get("finished") or "")[:10],
        attempt.get("grade", ""), attempt.get("section", ""),
        int(attempt.get("score") or 0), int(attempt.get("max_points") or 30))
    return _sheet(puzzle, letters=True, answers=True, header=header)


def _sheet(puzzle, letters, answers, header=None, numbers=True, blanks=False):
    rows, cols = puzzle["rows"], puzzle["cols"]
    grid, placements = puzzle["grid"], puzzle["placements"]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    cell = min((PAGE_W - 2 * MARGIN) / cols,
               (PAGE_H - 4 * MARGIN) / rows, 30)
    width, height = cell * cols, cell * rows
    x0 = (PAGE_W - width) / 2
    y0 = PAGE_H - MARGIN - 26 - height

    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(*NAVY)
    c.drawCentredString(PAGE_W / 2, PAGE_H - MARGIN - 8, puzzle["title"][:70])

    number_at = {}
    if numbers:
        for p in placements:
            r, cc = p["at"]
            number_at.setdefault((r, cc), p["n"])

    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.7)
    for i in range(rows + 1):
        c.line(x0, y0 + i * cell, x0 + width, y0 + i * cell)
    for j in range(cols + 1):
        c.line(x0 + j * cell, y0, x0 + j * cell, y0 + height)

    for r in range(rows):
        for cc in range(cols):
            x, y = x0 + cc * cell, y0 + (rows - 1 - r) * cell
            if (r, cc) in number_at:
                c.setFont("Helvetica", max(5.5, cell * 0.28))
                c.setFillColorRGB(0.15, 0.2, 0.3)
                c.drawString(x + 1.5, y + cell - cell * 0.3, str(number_at[(r, cc)]))
            if letters and grid[r][cc]:
                c.setFont("Helvetica-Bold", cell * 0.55)
                c.setFillColorRGB(0, 0, 0)
                c.drawCentredString(x + cell / 2, y + cell * 0.22, grid[r][cc])

    c.showPage()
    _clue_page(c, puzzle, answers, header, blanks=blanks)
    c.save()
    return buf.getvalue()


def _clue_page(c, puzzle, answers, header, blanks=False):
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(MARGIN, PAGE_H - MARGIN, header or BLANK_HEADER)
    y = PAGE_H - MARGIN - 30

    def block(title, items):
        nonlocal y
        if not items:
            return
        if y < MARGIN + 24:
            c.showPage()
            y = PAGE_H - MARGIN
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, y, title)
        y -= 18
        c.setFont("Helvetica", 10)
        for n, clue, word in items:
            text = "%d.  %s" % (n, clue or "(no clue given)")
            if answers and word:
                text += "  -  %s" % word
            elif blanks:
                text += "  -  ________________"
            for line in _wrap(c, text, "Helvetica", 10, PAGE_W - 2 * MARGIN):
                if y < MARGIN:
                    c.showPage()
                    y = PAGE_H - MARGIN
                c.drawString(MARGIN, y, line)
                y -= 14
        y -= 8

    across = sorted((p["n"], p["clue"], p["word"]) for p in puzzle["placements"]
                    if p["dir"] == "H")
    down = sorted((p["n"], p["clue"], p["word"]) for p in puzzle["placements"]
                  if p["dir"] == "V")
    block("ACROSS", across)
    block("DOWN", down)


def _wrap(c, text, font, size, max_width):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if stringWidth(trial, font, size) > max_width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or [""]
