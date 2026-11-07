"""Quantum Architect — electron configuration board and worksheet studio.

Two things in one service:
  * /play          the browser board (electron placement, rule feedback, scoring)
  * /worksheets    create + export electron-configuration worksheets (DOCX / PDF)

Runs on its own (`python app.py 5000`) or mounted inside the MNHS Review Center at
/games/quantum-architect. Mounted, it is a blueprint of the hub app: the hub hands
over the signed-in student and the staff level, so the answer keys open for a
teacher, an admin or the main admin and the old PIN screen is not needed.

Saved papers stay in data/worksheets.json in this folder. A worksheet is a
downloadable document, not a score, so the game adds no tables to quiz_app.db.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from functools import wraps

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, send_file, url_for)

from quantum import chemistry as qa
from quantum import atom_exports, atom_sheets, exports, store, worksheets as ws

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"

# Set by the Review Center when it mounts this game. With no hooks (the folder run
# on its own) nobody else is logged in, so the machine belongs to its teacher and
# the staff pages stay open.
identity = None        # callable -> {'name', 'grade', 'section', 'account'} or None
is_admin = None        # callable -> truthy for teacher, admin or main_admin
teacher_label = None   # callable -> the signed-in staff member's display name

bp = Blueprint("qa", __name__, template_folder="templates", static_folder="static")

# What the Review Center prints on its games page about this game.
MAX_Z = qa.MAX_Z
QUESTION_TYPES = len(ws.TYPE_LABELS)
TIER_NAMES = [label.split(" — ")[0] for label in ws.TIER_LABELS.values()]


def staff_mode() -> bool:
    """Whether this visitor may open the worksheet studio and the answer keys."""
    return True if is_admin is None else bool(is_admin())


def student() -> dict:
    return (identity() if callable(identity) else None) or {}


def staff_required(page: str):
    """Close a route to anyone the hub does not call staff.

    Standalone there is no hub to ask, so the person sitting at the machine keeps
    the studio open.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if staff_mode():
                return view(*args, **kwargs)
            return render_template(
                "qa_error.html", code=403,
                message="%s is for teachers. Sign in to the Review Center "
                        "with a staff account, then open it again." % page,
                **context()), 403
        return wrapper
    return decorator


def context() -> dict:
    label = (teacher_label() if callable(teacher_label) else "") or ""
    return {
        "teacher": staff_mode(),
        "teacher_label": label,
        "today": datetime.now().strftime("%B %d, %Y"),
        "tier_names": ws.TIER_LABELS,
        "tier_allowed": ws.TIERS,
        "type_labels": ws.TYPE_LABELS,
        "presets": {key: value for key, (_, value) in ws.PRESETS.items()},
        "quick_starts": QUICK_STARTS,
        "api_base": url_for("qa.index"),
        "back_url": current_app.config.get("QA_BACK_URL", ""),
        "login_url": current_app.config.get("QA_LOGIN_URL", ""),
        "student": student(),
    }


# --------------------------------------------------------------------------- #
# Home
# --------------------------------------------------------------------------- #

@bp.get("/")
def index():
    return render_template("qa_index.html", saved_count=len(store.list_all()), **context())


# --------------------------------------------------------------------------- #
# The board
# --------------------------------------------------------------------------- #

@bp.get("/play")
@bp.get("/play/<int:z>")
def play(z: int = 11):
    if not 1 <= z <= qa.MAX_Z:
        abort(404)
    layout = qa.periodic_layout()
    return render_template("qa_play.html", z=z, element=qa.engine_payload(z),
                           table=[
                               {"z": n, "symbol": qa.element_symbol(n),
                                "name": qa.element_name(n),
                                "block": qa.block_of(n), "exception": qa.is_exception(n),
                                "row": layout[n][0], "col": layout[n][1]}
                               for n in range(1, qa.MAX_Z + 1)
                           ],
                           **context())


@bp.get("/api/table")
def api_table():
    layout = qa.periodic_layout()
    return jsonify([
        {
            "z": n,
            "symbol": qa.element_symbol(n),
            "name": qa.element_name(n),
            "block": qa.block_of(n),
            "period": qa.period_of(n),
            "group": qa.group_of(n),
            "row": layout[n][0],
            "col": layout[n][1],
            "exception": qa.is_exception(n),
        }
        for n in range(1, qa.MAX_Z + 1)
    ])


@bp.get("/api/element/<int:z>")
def api_element(z: int):
    if not 1 <= z <= qa.MAX_Z:
        abort(404)
    return jsonify(qa.engine_payload(z))


@bp.get("/api/engine")
def api_engine():
    return jsonify(qa.engine_shared())


# --------------------------------------------------------------------------- #
# Worksheets: list, create, view
# --------------------------------------------------------------------------- #

QUICK_STARTS = {
    "quiz-periods1-3": {
        "label": "Quiz — Periods 1-3",
        "settings": {"title": "Electron Configuration Quiz 1", "tier": "standard",
                     "pool_mode": "preset", "preset": "period1_3", "item_count": 10,
                     "types": ["full_config", "orbital_diagram", "shell_notation",
                               "identify_element"]},
    },
    "quiz-period4": {
        "label": "Quiz — Period 4 and the 3d ladder",
        "settings": {"title": "Electron Configuration Quiz 2 (Period 4)", "tier": "standard",
                     "pool_mode": "preset", "preset": "period4", "item_count": 12,
                     "types": ["full_config", "shorthand", "orbital_diagram", "identify_element"]},
    },
    "exam-mixed": {
        "label": "Exam — mixed, all rules",
        "settings": {"title": "Quarterly Examination: Atomic Structure", "tier": "advanced",
                     "pool_mode": "preset", "preset": "periods1_4", "item_count": 20,
                     "marks": 3,
                     "types": ["full_config", "shorthand", "orbital_diagram",
                               "quantum_numbers", "ion", "find_error", "block_group"]},
    },
    "transition-exceptions": {
        "label": "Drill — transition metals and exceptions",
        "settings": {"title": "Transition Metals and Stability Exceptions", "tier": "advanced",
                     "pool_mode": "preset", "preset": "exception_prone", "item_count": 12,
                     "types": ["full_config", "exception_explain", "orbital_diagram", "ion"]},
    },
    "ions-drill": {
        "label": "Drill — ions",
        "settings": {"title": "Ion Formation and Configuration", "tier": "advanced",
                     "pool_mode": "preset", "preset": "ion_formers", "item_count": 14,
                     "types": ["ion", "full_config", "identify_element"]},
    },
    "grade8-shells": {
        "label": "Grades 7-8 — shells only",
        "settings": {"title": "Bohr Shell Practice", "tier": "grade8",
                     "pool_mode": "range", "z_min": 1, "z_max": 20, "item_count": 10,
                     "marks": 2,
                     "types": ["shell_notation", "full_config", "identify_element",
                               "block_group"]},
    },
}


def header_defaults(settings: dict) -> dict:
    """Fill in the paper header from whoever the Review Center says is here.

    A teacher's own name goes on the paper; a student's grade and section become the
    class and section, because those are the two boxes they would otherwise type.
    """
    if staff_mode() and not settings.get("teacher") and callable(teacher_label):
        settings["teacher"] = teacher_label() or ""
    who = student()
    if who:
        if not settings.get("class_name") and who.get("grade"):
            settings["class_name"] = f"{who['grade']} Science"
        if not settings.get("section") and who.get("section"):
            settings["section"] = who["section"]
    return settings


@bp.get("/worksheets")
@staff_required("The worksheet studio")
def worksheets_list():
    return render_template("qa_worksheets.html", records=store.list_all(), **context())


@bp.get("/worksheets/new")
@staff_required("The worksheet studio")
def worksheet_new():
    quick = request.args.get("quick")
    overrides = dict(QUICK_STARTS.get(quick, {}).get("settings", {}))
    settings = header_defaults(ws.default_settings(**overrides))
    settings["quick"] = quick or ""
    return render_template("qa_worksheet_new.html", s=settings,
                           quick=quick or "", error=None, **context())


def settings_from_form(form) -> dict:
    base = ws.default_settings()
    text_keys = ("title", "class_name", "section", "teacher", "instructions",
                 "custom_pool", "preset", "tier", "pool_mode", "notation_order",
                 "diagram_scope")
    int_keys = ("item_count", "marks", "z_min", "z_max", "seed")
    bool_keys = ("shuffle", "no_repeat", "avoid_heavy", "allow_shorthand",
                 "show_element_names")
    settings = dict(base)
    for key in text_keys:
        if key in form:
            settings[key] = form[key].strip()
    for key in int_keys:
        if key in form:
            try:
                settings[key] = max(0, int(form[key] or 0))
            except ValueError:
                settings[key] = base[key]
    for key in bool_keys:
        settings[key] = form.get(key) in ("on", "1", "true", "yes")
    if "date" in form and form["date"].strip():
        settings["date"] = form["date"].strip()
    if form.getlist("types"):
        settings["types"] = form.getlist("types")
    if form.getlist("error_kinds"):
        settings["error_kinds"] = form.getlist("error_kinds")
    return settings


@bp.post("/worksheets/create")
@staff_required("The worksheet studio")
def worksheet_create():
    settings = settings_from_form(request.form)
    try:
        worksheet = ws.generate(settings)
    except Exception as error:  # surface a bad range/type choice, do not 500
        return render_template("qa_worksheet_new.html", s=header_defaults(settings),
                               quick="",
                               error=f"The worksheet could not be generated: {error}. "
                                     "Check the element range and the question types selected.",
                               **context()), 400
    if not worksheet["items"]:
        return render_template("qa_worksheet_new.html", s=header_defaults(settings),
                               quick="",
                               error="No items matched. That element pool cannot answer the "
                                     "question types you picked — widen the range or the types.",
                               **context()), 400
    record = store.save(worksheet)
    return redirect(url_for("qa.worksheet_view", worksheet_id=record["id"]))


def load_or_404(worksheet_id: str) -> dict:
    record = store.get(worksheet_id)
    if record is None:
        abort(404)
    return record


@bp.get("/worksheets/<worksheet_id>")
@staff_required("The worksheet studio")
def worksheet_view(worksheet_id: str):
    record = load_or_404(worksheet_id)
    return render_template("qa_worksheet_view.html", worksheet=record, **context())


@bp.post("/worksheets/<worksheet_id>/regenerate")
@staff_required("The worksheet studio")
def worksheet_regenerate(worksheet_id: str):
    record = load_or_404(worksheet_id)
    settings = dict(record["settings"])
    settings["seed"] = int(settings.get("seed", 0)) + 1
    regenerated = ws.generate(settings)
    store.save(regenerated, worksheet_id=record["id"])
    return redirect(url_for("qa.worksheet_view", worksheet_id=record["id"]))


@bp.post("/worksheets/<worksheet_id>/delete")
@staff_required("The worksheet studio")
def worksheet_delete(worksheet_id: str):
    load_or_404(worksheet_id)
    store.delete(worksheet_id)
    return redirect(url_for("qa.worksheets_list"))


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

def _send(data: bytes, filename: str, mimetype: str):
    return send_file(io.BytesIO(data), download_name=filename, as_attachment=True,
                     mimetype=mimetype)


@bp.get("/worksheets/<worksheet_id>/export/<kind>")
@staff_required("The worksheet studio")
def worksheet_export(worksheet_id: str, kind: str):
    record = load_or_404(worksheet_id)
    builder, extension, mimetype = _exporter(kind)
    return _send(builder(record), exports.export_filename(record, False, extension), mimetype)


@bp.get("/worksheets/<worksheet_id>/answer-key")
@staff_required("The answer key")
def worksheet_answer_key(worksheet_id: str):
    record = load_or_404(worksheet_id)
    return render_template("qa_worksheet_key.html", worksheet=record, **context())


@bp.get("/worksheets/<worksheet_id>/answer-key/export/<kind>")
@staff_required("The answer key")
def worksheet_answer_key_export(worksheet_id: str, kind: str):
    record = load_or_404(worksheet_id)
    builder, extension, mimetype = _exporter(kind, teacher=True)
    return _send(builder(record), exports.export_filename(record, True, extension), mimetype)


def _exporter(kind: str, teacher: bool = False):
    mapping = {
        "docx": ((exports.teacher_docx if teacher else exports.student_docx), "docx", DOCX_MIME),
        "pdf": ((exports.teacher_pdf if teacher else exports.student_pdf), "pdf", PDF_MIME),
    }
    if kind not in mapping:
        abort(404)
    return mapping[kind]


# --------------------------------------------------------------------------- #
# Orbital-box worksheet: elements, arrows and the Bohr model on A4, teacher only
# --------------------------------------------------------------------------- #

def atom_settings_from_form(form) -> dict:
    settings = atom_sheets.default_settings()
    for key in ("title", "class_name", "section", "teacher", "date", "pool_mode",
                "preset", "custom_pool", "per_page", "instructions"):
        if key in form:
            settings[key] = form[key].strip()
    for key in ("z_min", "z_max"):
        if key in form:
            try:
                settings[key] = max(1, min(qa.MAX_Z, int(form[key] or settings[key])))
            except ValueError:
                pass
    settings["show_bohr"] = form.get("show_bohr") in ("on", "1", "true", "yes")
    if settings.get("per_page") not in atom_sheets.PER_PAGE_LABELS:
        settings["per_page"] = "auto"
    return header_defaults(settings)


@bp.get("/atom-worksheets")
@staff_required("The orbital box worksheet")
def atom_sheets_list():
    return render_template("qa_atom_sheets.html", records=store.list_atoms(), **context())


@bp.get("/atom-worksheets/new")
@staff_required("The orbital box worksheet")
def atom_sheet_new():
    settings = header_defaults(atom_sheets.default_settings())
    return render_template("qa_atom_sheet_new.html", s=settings,
                           per_page_labels=atom_sheets.PER_PAGE_LABELS,
                           error=None, **context())


@bp.post("/atom-worksheets/create")
@staff_required("The orbital box worksheet")
def atom_sheet_create():
    settings = atom_settings_from_form(request.form)
    elements = atom_sheets.resolve_elements(settings)
    if not elements:
        return render_template("qa_atom_sheet_new.html", s=settings,
                               per_page_labels=atom_sheets.PER_PAGE_LABELS,
                               error="That selection has no elements. Choose a named group, "
                                     "a Z range or a list such as 11 12 13 17.",
                               **context()), 400
    record = store.save_atom({"settings": settings, "elements": elements})
    return redirect(url_for("qa.atom_sheet_view", sheet_id=record["id"]))


def load_atom_or_404(sheet_id: str) -> dict:
    record = store.get_atom(sheet_id)
    if record is None:
        abort(404)
    return record


@bp.get("/atom-worksheets/<sheet_id>")
@staff_required("The orbital box worksheet")
def atom_sheet_view(sheet_id: str):
    record = load_atom_or_404(sheet_id)
    sheet = atom_sheets.build_sheet(record)
    return render_template("qa_atom_sheet_view.html", record=record, sheet=sheet,
                           key=request.args.get("key") == "1", **context())


@bp.post("/atom-worksheets/<sheet_id>/delete")
@staff_required("The orbital box worksheet")
def atom_sheet_delete(sheet_id: str):
    load_atom_or_404(sheet_id)
    store.delete_atom(sheet_id)
    return redirect(url_for("qa.atom_sheets_list"))


@bp.get("/atom-worksheets/<sheet_id>/export/<kind>")
@staff_required("The orbital box worksheet")
def atom_sheet_export(sheet_id: str, kind: str):
    record = load_atom_or_404(sheet_id)
    mapping = {
        "student": (atom_exports.student_pdf, False),
        "key": (atom_exports.key_pdf, True),
        "both": (atom_exports.both_pdf, True),
    }
    if kind not in mapping:
        abort(404)
    builder, teacher = mapping[kind]
    filename = exports.export_filename(record, teacher, "pdf")
    if kind == "both":
        filename = filename.replace("_ANSWER_KEY_", "_WITH_KEY_")
    return _send(builder(record), filename, PDF_MIME)


# --------------------------------------------------------------------------- #
# Pages this app owns an error for
# --------------------------------------------------------------------------- #

@bp.errorhandler(404)
def not_found(_error):
    return render_template("qa_error.html", code=404,
                           message="No such element, worksheet or page."), 404


@bp.errorhandler(403)
def forbidden(_error):
    return render_template("qa_error.html", code=403,
                           message="That page is for teachers."), 403


def mount(host_app, url_prefix="/games/quantum-architect", db_path=None):
    """Attach Quantum Architect to a host Flask app.

    No tables are created in the host database: the board is scored in the browser
    and a worksheet is a file a teacher downloads, so the catalogue stays in this
    folder. `db_path` is taken only so every game in the Review Center is mounted
    with the same call.
    """
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse
    import threading
    import webbrowser

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run Quantum Architect on this computer.")
    ap.add_argument("port", nargs="?", type=int, default=8050)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = Flask(__name__)
    host.config["TEMPLATES_AUTO_RELOAD"] = True
    mount(host, url_prefix="")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/" % args.port)).start()
    host.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
