"""End-to-end smoke test for the blueprint, the worksheet store and both export paths.

The blueprint is mounted on a bare Flask app at the site root here, which is how the
folder runs on its own. Quantum Architect/checks/check_hub_mount.py is the one that
proves it still works inside the Review Center.

Run from the project folder:  python checks/check_app.py
"""

import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import app as qa_app            # noqa: E402
import quantum.atom_sheets as atom_sheets   # noqa: E402
import quantum.exports as exports   # noqa: E402
import quantum.store as store   # noqa: E402
import quantum.worksheets as ws  # noqa: E402

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "samples")

failures = []

SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def make_client():
    """The game on its own app, mounted at the root exactly as `python app.py` does."""
    from flask import Flask
    host = Flask("qa_check")
    qa_app.mount(host, url_prefix="")
    host.config["TESTING"] = True
    return host.test_client()


def flat(text):
    """Superscripts survive a .docx round-trip only as ordinary digits, and Word
    keeps the runs apart, so compare flattened text."""
    return text.translate(SUP).replace(" ", "").replace("\n", "")


def check(condition, label):
    print(("  ok   " if condition else "  FAIL ") + label)
    if not condition:
        failures.append(label)


def note_docx(data, label):
    """A .docx is a zip of XML parts - open it and read the body text back."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        bad = archive.testzip()
        check(bad is None and "word/document.xml" in archive.namelist(),
              label + ": valid OOXML package")
        import docx
        document = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs)
        for part in document.tables:
            for row in part.rows:
                for cell in row.cells:
                    text += "\n" + cell.text
        check("1s" in text or "s" in text, label + ": opens in python-docx with content")
        landscape = abs(document.sections[0].page_width - document.sections[0].page_height)
        check(landscape > 0 and document.sections[0].page_width > document.sections[0].page_height,
              label + ": A4 landscape (" + str(round(document.sections[0].page_width.cm, 1))
              + " x " + str(round(document.sections[0].page_height.cm, 1)) + " cm)")
        return document.tables, text
    except Exception as error:
        check(False, label + ": unreadable (" + repr(error) + ")")
        return [], ""


def note_pdf(data, label):
    check(data[:5] == b"%PDF-" and b"%%EOF" in data[-40:], label + ": well-formed PDF header/EOF")
    check(len(data) > 2000, label + ": non-trivial size (" + str(len(data)) + " bytes)")


def form_for(tier, **overrides):
    settings = ws.default_settings(tier=tier, **overrides)
    form = {
        "title": settings["title"], "class_name": settings["class_name"],
        "section": settings["section"], "teacher": settings["teacher"],
        "date": settings["date"], "instructions": settings["instructions"],
        "tier": tier, "pool_mode": settings["pool_mode"], "preset": settings["preset"],
        "z_min": str(settings["z_min"]), "z_max": str(settings["z_max"]),
        "custom_pool": settings["custom_pool"], "notation_order": settings["notation_order"],
        "diagram_scope": settings["diagram_scope"],
        "item_count": str(settings["item_count"]), "marks": str(settings["marks"]),
        "seed": str(settings["seed"]),
        "types": settings["types"], "error_kinds": settings["error_kinds"],
    }
    for flag in ("shuffle", "no_repeat", "avoid_heavy", "allow_shorthand", "show_element_names"):
        if settings[flag]:
            form[flag] = "on"
    return form


def atom_form(**overrides):
    settings = atom_sheets.default_settings(**overrides)
    form = {key: settings[key] for key in
            ("title", "class_name", "section", "teacher", "date", "pool_mode",
             "preset", "custom_pool", "per_page", "instructions")}
    form["z_min"] = str(settings["z_min"])
    form["z_max"] = str(settings["z_max"])
    if settings["show_bohr"]:
        form["show_bohr"] = "on"
    return form


def pdf_pages(data):
    """Reportlab writes the page count into /Type /Pages /Count N; read it without
    adding a PDF parser dependency just for the check."""
    counts = re.findall(rb"/Count (\d+)", data)
    return int(counts[0]) if counts else 0


def note_board_hooks(client):
    """game.js runs in a browser this host cannot drive, so its assumptions are
    checked against the template markup and the payloads it is fed instead."""
    print("\n== board script matches the template and the payloads ==")
    with open(os.path.join(ROOT, "static", "js", "game.js"), encoding="utf-8") as handle:
        js = handle.read()
    with open(os.path.join(ROOT, "templates", "qa_play.html"), encoding="utf-8") as handle:
        html = handle.read()

    check("window.QA_BASE" in html and "BASE + 'api/" in js,
          "the board fetches through the address the page hands it, not a hard-coded root")

    used = set(re.findall(r"el\('([^']+)'\)", js))
    defined = set(re.findall(r'id="([^"]+)"', html))
    missing = sorted(used - defined)
    check(used and not missing, "all %d ids game.js reaches for exist in play.html" % len(used) +
          ("" if not missing else " - missing: " + ", ".join(missing)))

    payload = client.get("/api/element/26").get_json()
    keys = set(re.findall(r"\bDATA\.([A-Za-z_]\w*)", js))
    missing = sorted(keys - set(payload))
    check(keys and not missing, "all %d DATA.<key> reads exist in /api/element" % len(keys) +
          ("" if not missing else " - missing: " + ", ".join(missing)))

    shared = qa_app.qa.engine_shared()
    keys = set(re.findall(r"\bSHARED\.([A-Za-z_]\w*)", js))
    missing = sorted(keys - set(shared))
    check(keys and not missing, "all %d SHARED.<key> reads exist in /api/engine" % len(keys) +
          ("" if not missing else " - missing: " + ", ".join(missing)))

    keys = set(re.findall(r"\bSHARED\.scoring\.([A-Za-z_]\w*)", js))
    missing = sorted(keys - set(shared["scoring"]))
    check(keys and not missing, "all %d SHARED.scoring.<key> reads exist" % len(keys) +
          ("" if not missing else " - missing: " + ", ".join(missing)))

    sublevels = payload["sublevels"]
    keys = set(re.findall(r"\bs\.([A-Za-z_]\w*)", js)) | set(re.findall(r"\bsub\.([A-Za-z_]\w*)", js))
    noise = {"length", "map", "filter", "forEach", "push", "indexOf", "includes", "find",
             "name", "center", "join", "replace", "checked", "value", "textContent"}
    missing = sorted(k for k in keys if k not in sublevels[0] and k not in noise)
    check(not missing, "sublevel fields read by the board exist on the payload" +
          ("" if not missing else " - missing: " + ", ".join(missing)))

    check("application/json" in html and "element-data" in html,
          "play.html embeds the first element as JSON for the board")

    table = client.get("/api/table").get_json()
    check(all({"row", "col"} <= set(row) for row in table),
          "/api/table carries the grid row and column for every element")
    check(len({(row["row"], row["col"]) for row in table}) == qa_app.qa.MAX_Z,
          "no two elements share a grid cell")


def main():
    client = make_client()
    pre_existing = [r["id"] for r in store.list_all()]
    pre_existing_atoms = [r["id"] for r in store.list_atoms()]
    created = []
    created_atoms = []

    print("\n== pages and engine APIs ==")
    for url in ("/", "/play", "/play/24", "/play/29", "/worksheets", "/worksheets/new"):
        response = client.get(url)
        check(response.status_code == 200, "GET " + url + " -> " + str(response.status_code))

    print("\n== engine APIs ==")
    engine = client.get("/api/engine").get_json()
    check(engine["fillOrder"][:4] == ["1s", "2s", "2p", "3s"], "/api/engine fill order")
    check(engine["scoring"]["starThresholds"] == [0.55, 0.75, 0.90], "/api/engine star thresholds")
    check("aufbau" in engine["messages"], "/api/engine carries the rule wording")

    chromium = client.get("/api/element/24").get_json()
    check(chromium["isException"] and chromium["expected"], "/api/element/24 flags the Cr exception")
    check(chromium["full"].replace(" ", "").startswith("1s"), "/api/element/24 full configuration")
    table = client.get("/api/table").get_json()
    check(len(table) == 118, "/api/table returns 118 elements")

    print("\n== the picker is an 18-column periodic table ==")
    play_html = client.get("/play").get_data(as_text=True)
    check(play_html.count('class="pt-cell') == 118,
          "the picker renders all 118 elements")
    check(play_html.count('class="pt-group"') == 18, "the grid has 18 group headers")
    check(play_html.count('class="pt-period"') == 7, "the grid has 7 period labels")
    check(play_html.count('class="pt-placeholder"') == 2,
          "the two f-block gaps are marked")
    check('grid-column: 2; grid-row: 2' in play_html,
          "H sits in group 1, period 1 (one offset for the label column)")
    check('grid-column: 19; grid-row: 2' in play_html,
          "He sits in group 18, period 1")

    note_board_hooks(client)

    print("\n== worksheet create -> store -> view ==")
    for tier in ("grade8", "standard", "advanced"):
        response = client.post("/worksheets/create", data=form_for(tier))
        check(response.status_code == 302, tier + ": create redirects to the worksheet view")
        location = response.headers.get("Location", "")
        worksheet_id = location.rstrip("/").split("/")[-1]
        created.append(worksheet_id)
        view = client.get("/worksheets/" + worksheet_id)
        check(view.status_code == 200, tier + ": GET view")
        record = store.get(worksheet_id)
        check(record is not None and len(record["items"]) > 0,
              tier + ": " + str(len(record["items"])) + " items stored")
        check(record["total_marks"] == sum(i["marks"] for i in record["items"]),
              tier + ": total marks matches the items")

    print("\n== impossible request is handled, not a 500 ==")
    bad = client.post("/worksheets/create", data=form_for("advanced", pool_mode="range",
                                                          z_min=1, z_max=2,
                                                          types=["shorthand"]))
    check(bad.status_code == 400, "H/He noble-gas shorthand pool yields no items -> 400 "
                                  "(" + str(bad.status_code) + ")")
    check(b"No items matched" in bad.data, "the failure page explains what to change")

    print("\n== orbital box sheets: create -> preview -> PDFs ==")
    for url in ("/atom-worksheets", "/atom-worksheets/new"):
        response = client.get(url)
        check(response.status_code == 200, "GET " + url + " -> " + str(response.status_code))

    response = client.post("/atom-worksheets/create", data=atom_form())
    check(response.status_code == 302, "create redirects to the sheet view")
    atom_id = response.headers.get("Location", "").rstrip("/").split("/")[-1]
    created_atoms.append(atom_id)
    atom_record = store.get_atom(atom_id)
    check(atom_record is not None and atom_record["elements"] == list(range(1, 21)),
          "the saved sheet carries the first twenty elements")

    student_page = client.get("/atom-worksheets/" + atom_id)
    check(student_page.status_code == 200, "GET the student preview")
    student_html = student_page.get_data(as_text=True)
    check(student_html.count('class="a4-sheet"') == 10,
          "the preview paginates the first 20 as 10 A4 pages")
    check(student_html.count('class="sheet-block') == 20, "every element gets a block")
    check(student_html.count('class="sub-arrow"') == 0,
          "the student preview leaves every orbital box empty")
    check(student_html.count('class="cut-line"') == 10,
          "two-element pages carry a cut line between the halves")
    check('class="bohr-ring' in student_html, "the Bohr model is drawn in each block")

    key_page = client.get("/atom-worksheets/%s?key=1" % atom_id)
    check(key_page.status_code == 200, "GET the answer-key preview")
    key_html = key_page.get_data(as_text=True)
    check(key_html.count('class="sub-arrow"') > 0, "the key fills the orbital boxes")
    check("ANSWER KEY" in key_html, "the key preview is labelled")
    check("1s¹" in key_html and "3p⁶" in key_html, "the key prints the configurations")

    expected = {"student": 10, "key": 10, "both": 20}
    for kind in ("student", "key", "both"):
        response = client.get("/atom-worksheets/%s/export/%s" % (atom_id, kind))
        check(response.status_code == 200, "atom sheet " + kind + ": 200")
        data = response.data
        check(data[:5] == b"%PDF-" and b"%%EOF" in data[-40:],
              "atom sheet " + kind + ": well-formed PDF")
        check(pdf_pages(data) == expected[kind],
              "atom sheet " + kind + ": %d A4 pages" % expected[kind])
        path = os.path.join(OUT_DIR, "atom_sheet_" + kind + ".pdf")
        with open(path, "wb") as handle:
            handle.write(data)
        print("       saved " + path)

    forced = client.post("/atom-worksheets/create",
                         data=atom_form(pool_mode="range", z_min=11, z_max=13, per_page="1"))
    forced_id = forced.headers.get("Location", "").rstrip("/").split("/")[-1]
    created_atoms.append(forced_id)
    check(client.get("/atom-worksheets/" + forced_id).get_data(as_text=True)
          .count('class="a4-sheet"') == 3, "forcing one element per page gives three pages")

    bad_atom = client.post("/atom-worksheets/create",
                           data=atom_form(pool_mode="custom", custom_pool="no numbers here"))
    check(bad_atom.status_code == 400, "an empty element list is explained, not a 500")

    print("\n== exports (student copy) ==")
    sample = store.get(created[1])
    os.makedirs(OUT_DIR, exist_ok=True)
    for kind, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
        response = client.get("/worksheets/%s/export/%s" % (sample["id"], kind))
        check(response.status_code == 200, "student " + kind + ": 200")
        data = response.data
        check(data[:len(magic)] == magic, "student " + kind + ": starts with " + str(magic))
        path = os.path.join(OUT_DIR, "student_" + kind + "_sample." + kind)
        with open(path, "wb") as handle:
            handle.write(data)
        if kind == "docx":
            tables, _ = note_docx(data, "student " + kind)
            check(len(tables) == 2, "student docx: header table + one table for the questions")
            check(len(tables[1].rows) == len(sample["items"]) + 1,
                  "student docx: %d question rows (items + header row)" % (len(tables[1].rows) - 1))
            check(len(tables[1].columns) == 4, "student docx: 4 columns (#, Question, Answer space, Marks)")
        else:
            note_pdf(data, "student pdf")
        print("       saved " + path)

    print("\n== answers do not leak into student copies ==")
    config_items = [i for i in sample["items"] if i["type"] == "full_config"]
    check(bool(config_items), "the sample paper contains a full-configuration item")

    def leaked_into(text, items):
        """Some questions quote a configuration on purpose (find the error, name the
        element), so strip every prompt before hunting for answer strings."""
        haystack = flat(text)
        for item in sample["items"]:
            haystack = haystack.replace(flat(item["prompt"]), " ")
        return [i["answer"] for i in items if flat(i["answer"]) in haystack]

    student_html = client.get("/worksheets/" + sample["id"]).get_data(as_text=True)
    found = leaked_into(student_html, config_items)
    check(not found, "student view page does not print any answer" +
          (" (leaked: %s)" % found[:2] if found else ""))

    student_file = client.get("/worksheets/%s/export/docx" % sample["id"]).data
    tables, student_docx_text = note_docx(student_file, "student docx body")
    found = leaked_into(student_docx_text, config_items)
    check(not found, "student DOCX question cells carry no answers" +
          (" (leaked: %s)" % found[:2] if found else ""))
    answer_cells = [row.cells[2].text for row in tables[1].rows][1:]
    check(all(cell.replace("_", "").replace("\n", "").strip() == "" for cell in answer_cells),
          "student DOCX answer column is blank ruled space only")
    check("1s" not in "".join(answer_cells), "student DOCX answer column has no configuration text")

    print("\n== the studio and the key follow the staff hook ==")
    qa_app.is_admin = lambda: False        # what the Review Center hands a learner
    for url in ("/worksheets", "/worksheets/new", "/worksheets/%s" % sample["id"]):
        refused = client.get(url)
        check(refused.status_code == 403 and "for teachers" in refused.get_data(as_text=True),
              "a visitor the hub does not call staff is refused " + url + " (403)")
    student_key = client.get("/worksheets/%s/answer-key" % sample["id"])
    check(student_key.status_code == 403 and "for teachers" in student_key.get_data(as_text=True),
          "a visitor the hub does not call staff is refused the key (403)")
    student_file = client.get("/worksheets/%s/answer-key/export/pdf" % sample["id"])
    check(student_file.status_code == 403, "and refused the key PDF")
    for url in ("/atom-worksheets", "/atom-worksheets/new",
                "/atom-worksheets/" + atom_id,
                "/atom-worksheets/%s?key=1" % atom_id,
                "/atom-worksheets/%s/export/student" % atom_id,
                "/atom-worksheets/%s/export/key" % atom_id):
        refused = client.get(url)
        check(refused.status_code == 403 and "for teachers" in refused.get_data(as_text=True),
              "a visitor the hub does not call staff is refused " + url + " (403)")

    qa_app.is_admin = lambda: True         # teacher, admin or main_admin
    check(client.get("/worksheets/new").status_code == 200, "a staff session opens the studio again")
    check(client.get("/atom-worksheets/new").status_code == 200,
          "a staff session opens the orbital sheet studio")
    atom_list = client.get("/atom-worksheets").get_data(as_text=True)
    check(atom_record["settings"]["title"] in atom_list,
          "the saved orbital sheet appears in the staff list")
    key_page = client.get("/worksheets/%s/answer-key" % sample["id"])
    check(key_page.status_code == 200, "teacher GET answer key -> 200")
    body = key_page.get_data(as_text=True)
    check("Answer key" in body, "answer key page rendered")
    first_answer = sample["items"][0]["answer"]
    check(first_answer.split()[0] in body,
          "answer key shows item 1 answer (" + first_answer.split()[0] + ")")

    for kind in ("docx", "pdf"):
        response = client.get("/worksheets/%s/answer-key/export/%s" % (sample["id"], kind))
        check(response.status_code == 200, "teacher key " + kind + ": 200")
        data = response.data
        path = os.path.join(OUT_DIR, "answer_key_" + kind + "_sample." + kind)
        with open(path, "wb") as handle:
            handle.write(data)
        if kind == "docx":
            tables, text = note_docx(data, "teacher docx")
            check("Teacher note" in text, "teacher docx: marking column present")
            check(len(tables) == 2, "teacher docx: header table + answers table")
            check(len(tables[1].rows) == len(sample["items"]) + 1,
                  "teacher docx: %d answer rows" % (len(tables[1].rows) - 1))
            check(len(tables[1].columns) == 5, "teacher docx: 5 columns (#, Question, Answer, Note, Marks)")
            check(all(flat(i["answer"]) in flat(text) for i in config_items),
                  "teacher docx: every full-configuration answer is printed in the file")
            check("Teacher:" in text and "Seed:" in text,
                  "teacher docx: teacher metadata block instead of a Name/Score line")
            check("________________________" not in text,
                  "teacher docx: no blank answer space for students")
        else:
            note_pdf(data, "teacher pdf")
        print("       saved " + path)

    qa_app.is_admin = None                 # run on its own, this machine is the teacher's
    open_key = client.get("/worksheets/%s/answer-key" % sample["id"])
    check(open_key.status_code == 200, "with no hub to ask, the folder keeps the key open")

    print("\n== regenerate + delete ==")
    regen = client.post("/worksheets/%s/regenerate" % sample["id"])
    check(regen.status_code == 302, "regenerate redirects")
    again = store.get(sample["id"])
    check(again["settings"]["seed"] == sample["settings"]["seed"] + 1, "regenerate bumps the seed")
    check([i["answer"] for i in again["items"]] != [i["answer"] for i in sample["items"]]
          or len(again["items"]) != len(sample["items"]), "regenerate changes the paper")

    for worksheet_id in [r["id"] for r in store.list_all()
                         if r["id"] not in pre_existing] + created:
        client.post("/worksheets/%s/delete" % worksheet_id)
    check([r["id"] for r in store.list_all()] == pre_existing,
          "smoke-test worksheets cleaned up")

    for atom_sheet_id in [r["id"] for r in store.list_atoms()
                          if r["id"] not in pre_existing_atoms] + created_atoms:
        client.post("/atom-worksheets/%s/delete" % atom_sheet_id)
    check([r["id"] for r in store.list_atoms()] == pre_existing_atoms,
          "smoke-test orbital sheets cleaned up")

    print("\n== direct export calls (no HTTP) ==")
    other = ws.generate(ws.default_settings(tier="advanced", pool_mode="preset",
                                            preset="transition", item_count=8, seed=7))
    for builder, label in ((exports.student_docx, "docx/student"), (exports.teacher_docx, "docx/teacher")):
        data = builder(other)
        note_docx(data, "direct " + label)
    for builder, label in ((exports.student_pdf, "pdf/student"), (exports.teacher_pdf, "pdf/teacher")):
        note_pdf(builder(other), "direct " + label)

    print()
    if failures:
        print(str(len(failures)) + " app check(s) FAILED:")
        for item in failures:
            print("  - " + item)
        return 1
    print("All app checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
