"""Worksheet exports: editable DOCX and print-ready PDF, both A4 landscape.

Student version = questions + writing space. Teacher version = the same questions
with the answer, the teaching note and the marks. Spin is written as text ("up" /
"down") whenever the PDF font in use cannot draw arrows, so the key never depends on
a glyph that may be missing.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime

from quantum import chemistry as qa

SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
ARROW_WORDS = {"↑": "[up]", "↓": "[down]", "−": "-"}

DOCX_BASE_FONT = "Calibri"
DOCX_MONO_FONT = "Consolas"
LINE = "_" * 62


# --------------------------------------------------------------------------- #
# Text helpers shared by both writers
# --------------------------------------------------------------------------- #

def _split_superscripts(text: str) -> list[tuple[str, bool]]:
    """'1s² 4s¹' -> [('1s', False), ('2', True), (' 4s', False), ('1', True)]"""
    parts: list[tuple[str, bool]] = []
    buffer = ""
    for ch in text:
        if ch in SUPERSCRIPT_DIGITS or ch in "⁺⁻":
            if buffer:
                parts.append((buffer, False))
                buffer = ""
            value = str(SUPERSCRIPT_DIGITS.index(ch)) if ch in SUPERSCRIPT_DIGITS else ("+" if ch == "⁺" else "-")
            if parts and parts[-1][1]:
                parts[-1] = (parts[-1][0] + value, True)
            else:
                parts.append((value, True))
        else:
            buffer += ch
    if buffer:
        parts.append((buffer, False))
    return parts


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_text(text: str, arrows: bool) -> str:
    """Reportlab markup: unicode superscripts become <super>, arrows optionally
    become words when the selected font has no arrow glyphs."""
    if not arrows:
        for glyph, word in ARROW_WORDS.items():
            text = text.replace(glyph, word)
        text = text.replace("up and down", "[up] and [down]")
    rendered = []
    for chunk, is_super in _split_superscripts(text):
        rendered.append(f"<super>{_escape_xml(chunk)}</super>" if is_super else _escape_xml(chunk))
    return "".join(rendered)


def _pdf_block(text: str, arrows: bool) -> str:
    return "<br/>".join(_pdf_text(line.strip(), arrows) for line in text.split("\n"))


def _diagram_text(rows: list[dict]) -> str:
    return "\n".join(
        f"{row['sublevel']:>3} " + " ".join(f"[{box.center(2)}]" for box in row["boxes"])
        for row in rows
    )


def _answer_text(item: dict) -> str:
    return _diagram_text(item["diagram"]) if item.get("diagram") else item["answer"]


def _answer_extra_lines(item: dict) -> list[str]:
    lines = list(item.get("answer_lines") or [])
    if item["type"] == "full_config" and item.get("answer_shorthand"):
        lines.append(f"shorthand: {item['answer_shorthand']}")
    if item["type"] == "ion" and item.get("answer_shorthand"):
        lines.append(f"shorthand: {item['answer_shorthand']}")
    return lines


def _workspace_lines(item: dict) -> int:
    if item["type"] == "orbital_diagram":
        return 3
    return max(1, item.get("workspace", 2))


def _type_summary(worksheet: dict) -> str:
    return ", ".join(f"{count} × {label}" for label, count in worksheet["type_summary"].items() if count)


def _footer_text(worksheet: dict, teacher: bool) -> str:
    settings = worksheet["settings"]
    return (
        f"Generated {datetime.now():%Y-%m-%d %H:%M} · seed {settings['seed']} · "
        f"{len(worksheet['items'])} items · {_type_summary(worksheet)} · "
        f"notation order: {settings['notation_order']} · "
        + ("TEACHER COPY — do not distribute" if teacher else "answer key held by the teacher")
    )


def export_filename(worksheet: dict, teacher: bool, extension: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", worksheet["settings"]["title"]).strip("_") or "Worksheet"
    suffix = "ANSWER_KEY" if teacher else "student"
    return f"{base}_{suffix}_{datetime.now():%Y%m%d}.{extension}"


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #

def _docx_setup(doc):
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Cm(29.7), Cm(21.0)
    section.left_margin = section.right_margin = Cm(1.4)
    section.top_margin = section.bottom_margin = Cm(1.2)
    style = doc.styles["Normal"]
    style.font.name = DOCX_BASE_FONT
    style.font.size = Pt(10)


def _docx_cell(cell, width, text, *, size=10, mono=False, center=False, italic=False):
    """Write possibly multi-line text into a table cell, keeping superscripts."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt
    cell.width = width
    paragraphs = [cell.paragraphs[0]]
    for _ in text.split("\n")[1:]:
        paragraphs.append(cell.add_paragraph())
    lines = text.split("\n")
    for index, para in enumerate(paragraphs):
        para.paragraph_format.space_before = Pt(1)
        para.paragraph_format.space_after = Pt(1)
        if center:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for chunk, is_super in _split_superscripts(lines[index]):
            run = para.add_run(chunk)
            run.font.superscript = is_super
            run.font.name = DOCX_MONO_FONT if mono else DOCX_BASE_FONT
            run.font.size = Pt(size)
            run.italic = italic


def _docx_header_table(doc, worksheet: dict, teacher: bool):
    from docx.shared import Cm, Pt
    settings = worksheet["settings"]
    widths = [Cm(6.6)] * 4

    table = doc.add_table(rows=3, cols=4)
    table.style = "Table Grid"
    table.autofit = False

    title_cell = table.rows[0].cells[0]
    for i in (1, 2, 3):
        title_cell = title_cell.merge(table.rows[0].cells[i])
    para = title_cell.paragraphs[0]
    run = para.add_run("QUANTUM ARCHITECT")
    run.bold = True
    run.font.size = Pt(15)
    run.font.name = DOCX_BASE_FONT
    second = title_cell.add_paragraph()
    second.paragraph_format.space_after = Pt(2)
    subtitle = second.add_run(settings["title"])
    subtitle.font.size = Pt(12)
    subtitle.font.name = DOCX_BASE_FONT
    if teacher:
        tag = second.add_run("    |    ANSWER KEY — TEACHER COPY")
        tag.bold = True
        tag.font.size = Pt(11)
        tag.font.name = DOCX_BASE_FONT

    row1 = [["Class", settings["class_name"] or "______________"],
            ["Section", settings["section"] or "______________"],
            ["Date", settings["date"]],
            ["Total marks", str(worksheet["total_marks"])]]
    if teacher:
        row2 = [["Teacher", settings["teacher"] or "______________"],
                ["Elements covered", str(worksheet["element_count"])],
                ["Notation order",
                 f"{settings['notation_order']}"
                 f"{' (grouped by n)' if settings['notation_order'] == 'shell' else ' (energy order)'}"],
                ["Seed", str(settings["seed"])]]
    else:
        row2 = [["Name", "________________________"],
                ["Score", f"________ / {worksheet['total_marks']}"],
                ["Set", settings["section"] or "________"],
                ["Items", str(len(worksheet["items"]))]]

    for i, (label, value) in enumerate(row1):
        _docx_cell(table.rows[1].cells[i], widths[i], f"{label}: {value}", size=9.5)
    for i, (label, value) in enumerate(row2):
        _docx_cell(table.rows[2].cells[i], widths[i], f"{label}: {value}", size=9.5)

    _docx_set_table_widths(table, widths)
    intro = doc.add_paragraph()
    intro.paragraph_format.space_before = Pt(4)
    intro.paragraph_format.space_after = Pt(4)
    run = intro.add_run("Instructions: " + settings["instructions"])
    run.italic = True
    run.font.size = Pt(9.5)
    run.font.name = DOCX_BASE_FONT


def _docx_set_table_widths(table, widths):
    for row in table.rows:
        for i, width in enumerate(widths):
            if i < len(row.cells):
                row.cells[i].width = width


def _docx_item_table(doc, worksheet: dict, teacher: bool):
    from docx.shared import Cm
    settings = worksheet["settings"]
    if teacher:
        widths = [Cm(1.1), Cm(9.0), Cm(8.2), Cm(7.2), Cm(1.4)]
        labels = ["#", "Question", "Answer", "Teacher note", "Marks"]
    else:
        widths = [Cm(1.1), Cm(17.6), Cm(8.4), Cm(1.4)]
        labels = ["#", "Question", "Answer space", "Marks"]

    table = doc.add_table(rows=1, cols=len(labels))
    table.style = "Table Grid"
    table.autofit = False
    for i, label in enumerate(labels):
        _docx_cell(table.rows[0].cells[i], widths[i], label, size=9.5, center=(i != 1))

    for index, item in enumerate(worksheet["items"]):
        cells = table.add_row().cells
        if index and index % 4 == 0:
            # Four items to an A4 page: this row starts a fresh page.
            cells[0].paragraphs[0].paragraph_format.page_break_before = True
        _docx_cell(cells[0], widths[0], str(item["number"]), center=True, size=9.5)
        _docx_cell(cells[1], widths[1], item["prompt"], size=9.5)
        if teacher:
            answer = _answer_text(item)
            extras = _answer_extra_lines(item)
            note_lines = [f"{n}. {line}" for n, line in enumerate(extras, start=1)] if extras else []
            _docx_cell(cells[2], widths[2], "\n".join([answer] + note_lines), mono=True, size=8.5)
            _docx_cell(cells[3], widths[3], item["note"] or "—", size=8)
            _docx_cell(cells[4], widths[4], str(item["marks"]), center=True, size=9.5)
        else:
            _docx_cell(cells[2], widths[2], "\n".join([LINE] * _workspace_lines(item)),
                       mono=True, size=8)
            _docx_cell(cells[3], widths[3], str(item["marks"]), center=True, size=9.5)

    _docx_set_table_widths(table, widths)


def _docx_footer(doc, worksheet: dict, teacher: bool):
    from docx.shared import Pt
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(6)
    run = para.add_run(_footer_text(worksheet, teacher))
    run.italic = True
    run.font.size = Pt(8.5)
    run.font.name = DOCX_BASE_FONT


def _docx_bytes(doc) -> bytes:
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def student_docx(worksheet: dict) -> bytes:
    import docx
    doc = docx.Document()
    _docx_setup(doc)
    _docx_header_table(doc, worksheet, teacher=False)
    _docx_item_table(doc, worksheet, teacher=False)
    _docx_footer(doc, worksheet, teacher=False)
    return _docx_bytes(doc)


def teacher_docx(worksheet: dict) -> bytes:
    import docx
    doc = docx.Document()
    _docx_setup(doc)
    _docx_header_table(doc, worksheet, teacher=True)
    _docx_item_table(doc, worksheet, teacher=True)
    _docx_footer(doc, worksheet, teacher=True)
    return _docx_bytes(doc)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

PDF_TEXT_CANDIDATES = [
    ("DejaVuSans", ("C:\\Windows\\Fonts\\DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ("LiberationSans", ("C:\\Windows\\Fonts\\liberation\\LiberationSans-Regular.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")),
    ("Arial", ("C:\\Windows\\Fonts\\arial.ttf",)),
    ("SegoeUI", ("C:\\Windows\\Fonts\\segoeui.ttf",)),
    ("Calibri", ("C:\\Windows\\Fonts\\calibri.ttf",)),
    ("Tahoma", ("C:\\Windows\\Fonts\\tahoma.ttf",)),
    ("MSansSerif", ("C:\\Windows\\Fonts\\micross.ttf",)),
    ("LucidaSansUnicode", ("C:\\Windows\\Fonts\\l_10646.ttf",)),
    ("Helvetica-Neue", ("/System/Library/Fonts/Helvetica.ttc",)),
]
PDF_MONO_CANDIDATES = [
    ("DejaVuSansMono", ("C:\\Windows\\Fonts\\DejaVuSansMono.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
    ("LiberationMono", ("C:\\Windows\\Fonts\\liberation\\LiberationMono-Regular.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf")),
    ("Consolas", ("C:\\Windows\\Fonts\\consola.ttf",)),
    ("CourierNew", ("C:\\Windows\\Fonts\\cour.ttf",)),
    ("LucidaConsole", ("C:\\Windows\\Fonts\\lucon.ttf",)),
]
_HAS_ARROW = {}


def _font_has_arrow(name: str, path: str) -> bool:
    """Register a TTF and probe it for the spin arrows. Reportlab 4 and 5 expose
    the unicode map as face.charToGlyph; older builds called it face.charmap."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if name in _HAS_ARROW:
        return _HAS_ARROW[name]
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        face = pdfmetrics.getFont(name).face
        cmap = getattr(face, "charToGlyph", None) or getattr(face, "charmap", {}) or {}
        arrow = 0x2191 in cmap and 0x2193 in cmap
    except Exception:
        arrow = False
    _HAS_ARROW[name] = arrow
    return arrow


def _pick_font(candidates):
    for name, paths in candidates:
        for path in paths:
            if os.path.isfile(path) and _font_has_arrow(name, path):
                return name
    return None


def _pdf_fonts():
    """(text font, mono font, arrows_available). The PDF must be able to draw ↑ and ↓,
    so a font is only accepted when the glyph map really contains both."""
    body = _pick_font(PDF_TEXT_CANDIDATES)
    if body is None:
        return "Helvetica", "Courier", False
    mono = _pick_font(PDF_MONO_CANDIDATES) or body
    return body, mono, True


def student_pdf(worksheet: dict) -> bytes:
    return _pdf(worksheet, teacher=False)


def teacher_pdf(worksheet: dict) -> bytes:
    return _pdf(worksheet, teacher=True)


def _pdf(worksheet: dict, teacher: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                   PageBreak, Spacer, Table, TableStyle)

    body, mono, arrows = _pdf_fonts()
    settings = worksheet["settings"]
    page = landscape(A4)
    width, height = page
    margin = 12 * mm
    usable = width - 2 * margin

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=page, leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
        title=f"{settings['title']} — {'answer key' if teacher else 'student copy'}",
        author="Quantum Architect",
    )
    doc.addPageTemplates([PageTemplate(
        id="main",
        frames=[Frame(margin, margin, usable, height - 2 * margin, id="frame",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
        onPage=_pdf_page_decorations,
    )])

    styles = {
        "prompt": ParagraphStyle("prompt", fontName=body, fontSize=9, leading=12),
        "cell": ParagraphStyle("cell", fontName=body, fontSize=8.6, leading=11),
        "answer": ParagraphStyle("answer", fontName=mono, fontSize=8.4, leading=11),
        "note": ParagraphStyle("note", fontName=body, fontSize=7.6, leading=9.6),
        "center": ParagraphStyle("center", fontName=body, fontSize=8.6, leading=11,
                                 alignment=1),
        "rule": ParagraphStyle("rule", fontName=mono, fontSize=8, leading=13,
                               textColor=colors.HexColor("#9aa5b1")),
        "label": ParagraphStyle("label", fontName=body, fontSize=8, leading=10.5,
                                textColor=colors.HexColor("#4b5563")),
        "title": ParagraphStyle("title", fontName=body, fontSize=14, leading=17,
                                textColor=colors.HexColor("#0f172a")),
    }

    story = [_pdf_header_table(worksheet, teacher, arrows, styles, usable, mm)]
    story.append(Spacer(1, 3 * mm))

    if teacher:
        cols = [10 * mm, usable * 0.30, usable * 0.28, usable * 0.23, usable * 0.05]
        labels = ["#", "Question", "Answer", "Teacher note", "Marks"]
    else:
        cols = [10 * mm, usable * 0.60, usable * 0.30, usable * 0.05]
        labels = ["#", "Question", "Answer space", "Marks"]

    data = [[Paragraph(f"<b>{label}</b>", styles["cell"]) for label in labels]]
    for item in worksheet["items"]:
        row = [
            Paragraph(str(item["number"]), styles["center"]),
            Paragraph(_pdf_block(item["prompt"], arrows), styles["prompt"]),
        ]
        if teacher:
            answer = _pdf_block(_answer_text(item), arrows)
            extras = [_pdf_text(line, arrows) for line in _answer_extra_lines(item)]
            note = _pdf_text(item["note"] or "—", arrows)
            row.append(Paragraph("<br/>".join([answer] + [f"<i>{e}</i>" for e in extras]),
                                 styles["answer"]))
            row.append(Paragraph(note, styles["note"]))
        else:
            row.append(Paragraph("<br/>".join([LINE] * _workspace_lines(item)), styles["rule"]))
        row.append(Paragraph(str(item["marks"]), styles["center"]))
        data.append(row)

    # Four items to an A4 page: the header page carries items 1-4, and every
    # further group of four starts on a fresh page with its own column heads.
    per_page = 4
    header_row = data[0]
    for start in range(0, len(data) - 1, per_page):
        if start:
            story.append(PageBreak())
        chunk = [header_row] + data[1 + start:1 + start + per_page]
        table = Table(chunk, colWidths=cols, repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbe3f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
        ]))
        story.append(table)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_pdf_text(_footer_text(worksheet, teacher), arrows), styles["label"]))

    doc.build(story)
    return buffer.getvalue()


def _pdf_page_decorations(canvas, doc):
    from reportlab.lib.units import mm
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColorRGB(0.35, 0.4, 0.47)
    canvas.drawRightString(doc.pagesize[0] - 12 * mm, 7 * mm, f"page {doc.page}")
    canvas.restoreState()


def _pdf_header_table(worksheet: dict, teacher: bool, arrows: bool, styles: dict,
                      usable: float, mm) -> Table:
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    settings = worksheet["settings"]
    title = (f"<b>QUANTUM ARCHITECT</b> &nbsp;·&nbsp; {_pdf_text(settings['title'], arrows)}")
    if teacher:
        title += " &nbsp;·&nbsp; <b>ANSWER KEY — TEACHER COPY</b>"

    if teacher:
        facts = [
            f"Teacher: {settings['teacher'] or '____________'}",
            f"Class: {settings['class_name'] or '____________'}",
            f"Elements: {worksheet['element_count']}",
            f"Notation: {settings['notation_order']}",
            f"Total marks: {worksheet['total_marks']}",
        ]
    else:
        facts = [
            "Name ____________________",
            f"Grade ____________   Section ____________",
            f"Date: {settings['date']}",
            f"Score: ____ / {worksheet['total_marks']}",
            f"Items: {len(worksheet['items'])}",
        ]

    cols = [usable / 5.0] * 5
    data = [
        [Paragraph(title, styles["title"]), "", "", "", ""],
        [Paragraph(_pdf_text("Instructions: " + settings["instructions"], arrows),
                   styles["label"]), "", "", "", ""],
        [Paragraph(_pdf_text(fact, arrows), styles["label"]) for fact in facts],
    ]
    table = Table(data, colWidths=cols)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ("SPAN", (0, 0), (-1, 0)),
        ("SPAN", (0, 1), (-1, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#eef2ff")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table
