"""Quantum Architect inside the Review Center: the mount, the prefix and the staff gate.

Run from the Review Center folder:
    python "Quantum Architect/checks/check_hub_mount.py"

It imports the real hub app (which mounts every game in its folders), so a route,
template or asset path that only works when this game stands alone fails here.
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # Quantum Architect
ROOT = os.path.dirname(HERE)                                            # Review Center
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import app as hub                                                      # noqa: E402
import quantum_architect_game as game                                   # noqa: E402

failures = []


def check(condition, label):
    print(("  ok   " if condition else "  FAIL ") + label)
    if not condition:
        failures.append(label)


def main():
    hub.app.config["TESTING"] = True
    client = hub.app.test_client()
    base = "/games/quantum-architect"

    print("\n== the hub knows the game ==")
    check(hub.QUANTUM_READY, "app.py mounted Quantum Architect")
    check(base in [rule.rule for rule in hub.app.url_map.iter_rules() if rule.endpoint == "qa.index"]
          or any(rule.rule.startswith(base) for rule in hub.app.url_map.iter_rules()),
          "the game answers under " + base)
    check(callable(game.is_admin), "the hub handed the game its own staff test")
    check(callable(game.teacher_label) and callable(game.identity),
          "the hub handed the game the signed-in teacher and student")
    with hub.app.test_request_context(base + "/"):
        check(not game.is_admin(), "with nobody signed in, the hub does not call this visitor staff")

    print("\n== its own pages, not the hub's ==")
    home = client.get(base + "/")
    check(home.status_code == 200, "GET " + base + "/ -> " + str(home.status_code))
    body = home.get_data(as_text=True)
    check("Build the atom" in body, "home page is Quantum Architect's own")
    check("quiz-form" not in body and "Review Hub" not in body,
          "the hub's home template did not take over the page")
    check(base + "/static/css/app.css" in body, "the stylesheet is served from the game's own prefix")
    check("/games" in body, "the page carries the way back to Educational Games")
    check(hub.app.config.get("QA_LOGIN_URL") == "/admin/login",
          "the sign-in link points at the staff door, not the learner's /login")
    check("/admin/login" in body, "a visitor with no staff session is offered that door")
    check("Create worksheet" not in body,
          "the studio links stay off the page for a visitor with no staff session")

    board = client.get(base + "/play/24")
    text = board.get_data(as_text=True)
    check(board.status_code == 200 and "Orbital board" in text, "the board opens on chromium")
    check('window.QA_BASE = "' + base + '/"' in text,
          "the board script is told the game's address before it fetches")
    check(base + "/static/js/game.js" in text, "the board script loads from the game's prefix")

    print("\n== the engine APIs ==")
    check(client.get(base + "/api/engine").get_json()["fillOrder"][:3] == ["1s", "2s", "2p"],
          "api/engine keeps its order under the prefix")
    check(client.get(base + "/api/element/26").get_json()["z"] == 26, "api/element answers for iron")
    check(len(client.get(base + "/api/table").get_json()) == 118, "api/table still lists 118")
    check(client.get(base + "/api/element/999").status_code == 404, "an unknown element is a 404")

    print("\n== the studio and its papers follow the hub's staff session ==")
    was_admin = game.is_admin
    game.is_admin = lambda: False           # what the hub sets for a signed-in learner
    learner_pages = {"/worksheets": "the saved-paper list", "/worksheets/new": "the paper form",
                     "/atom-worksheets": "the orbital-sheet list",
                     "/atom-worksheets/new": "the orbital-sheet form"}
    for path, label in learner_pages.items():
        refused = client.get(base + path)
        check(refused.status_code == 403 and "for teachers" in refused.get_data(as_text=True),
              "a learner with no staff session is refused " + label + " (403)")

    game.is_admin = lambda: True            # what the hub sets for teacher, admin, main admin
    try:
        import quantum.worksheets as ws                                      # noqa: E402
        settings = ws.default_settings(tier="standard", item_count=6, seed=42)
        form = {key: (",".join(map(str, value)) if isinstance(value, list) else str(value))
                for key, value in settings.items()}
        for flag in ("shuffle", "no_repeat", "avoid_heavy", "allow_shorthand", "show_element_names"):
            if settings[flag]:
                form[flag] = "on"
        made = client.post(base + "/worksheets/create", data=form, follow_redirects=True)
        check(made.status_code == 200 and "Electron Configuration Practice" in
              made.get_data(as_text=True), "create lands on the saved paper")
        from urllib.parse import urlparse                                  # noqa: E402
        worksheet_id = urlparse(made.request.url).path.rstrip("/").split("/")[-1]

        for kind, magic in (("docx", b"PK"), ("pdf", b"%PDF")):
            file_response = client.get("%s/worksheets/%s/export/%s" % (base, worksheet_id, kind))
            check(file_response.status_code == 200 and
                  file_response.data[:len(magic)] == magic,
                  "student " + kind + " downloads from inside the hub")

        teacher_key = client.get("%s/worksheets/%s/answer-key" % (base, worksheet_id))
        check(teacher_key.status_code == 200 and "Answer key" in teacher_key.get_data(as_text=True),
              "a staff session opens the key page")
        teacher_pdf = client.get("%s/worksheets/%s/answer-key/export/pdf" % (base, worksheet_id))
        check(teacher_pdf.status_code == 200 and teacher_pdf.data[:5] == b"%PDF-",
              "a staff session downloads the key PDF")
        header = client.get(base + "/worksheets/new").get_data(as_text=True)
        check('name="teacher"' in header, "the paper header form is reachable for staff")
        check("Sign in as" not in header, "a signed-in teacher is not offered a sign-in prompt")
    finally:
        game.is_admin = lambda: False
        student_key = client.get("%s/worksheets/%s/answer-key" % (base, worksheet_id))
        check(student_key.status_code == 403 and "for teachers" in student_key.get_data(as_text=True),
              "the same learner session is refused the key (403)")
        student_pdf = client.get("%s/worksheets/%s/answer-key/export/pdf" % (base, worksheet_id))
        check(student_pdf.status_code == 403, "the key PDF is refused too")
        game.is_admin = was_admin

    print("\n== orbital box sheets inside the hub ==")
    import quantum.atom_sheets as atom_sheets                                # noqa: E402
    from quantum import store as qa_store                                    # noqa: E402
    sheet_settings = atom_sheets.default_settings(pool_mode="range", z_min=1, z_max=4)
    sheet_form = {key: str(sheet_settings[key]) for key in
                  ("title", "class_name", "section", "teacher", "date", "pool_mode",
                   "preset", "custom_pool", "per_page", "instructions", "z_min", "z_max")}
    if sheet_settings["show_bohr"]:
        sheet_form["show_bohr"] = "on"

    game.is_admin = lambda: True
    sheet_id = None
    try:
        made_sheet = client.post(base + "/atom-worksheets/create", data=sheet_form,
                                 follow_redirects=True)
        body = made_sheet.get_data(as_text=True)
        check(made_sheet.status_code == 200 and body.count('class="a4-sheet"') == 2,
              "staff create lands on a two-page preview")
        sheet_id = urlparse(made_sheet.request.url).path.rstrip("/").split("/")[-1]
        for kind in ("student", "key", "both"):
            file_response = client.get("%s/atom-worksheets/%s/export/%s"
                                       % (base, sheet_id, kind))
            check(file_response.status_code == 200 and file_response.data[:5] == b"%PDF-",
                  "orbital-sheet " + kind + " PDF downloads from inside the hub")
    finally:
        game.is_admin = lambda: False
        if sheet_id:
            refused = client.get("%s/atom-worksheets/%s" % (base, sheet_id))
            check(refused.status_code == 403 and "for teachers" in refused.get_data(as_text=True),
                  "a learner is refused the orbital sheet preview (403)")
            refused = client.get("%s/atom-worksheets/%s/export/key" % (base, sheet_id))
            check(refused.status_code == 403, "and refused its answer key PDF")
        game.is_admin = was_admin

    print("\n== the board is open to everyone ==")
    check(client.get(base + "/play/26").status_code == 200,
          "a learner still plays: the board needs no staff session")

    print("\n== the hub's own pages still answer ==")
    for url in ("/", "/home", "/games", "/quiz"):
        response = client.get(url)
        check(response.status_code in (200, 302),
              "GET %s -> %d, nothing the game registers stole it" % (url, response.status_code))

    games = client.get("/games").get_data(as_text=True)
    check("Quantum Architect" in games and base in games,
          "the Educational Games page carries the new card")

    import quantum.store as store                                          # noqa: E402
    store.delete(worksheet_id)   # the HTTP delete route is staff-only now
    check(store.get(worksheet_id) is None, "the test paper was cleaned up")
    if sheet_id:
        qa_store.delete_atom(sheet_id)
        check(qa_store.get_atom(sheet_id) is None, "the test orbital sheet was cleaned up")

    print()
    if failures:
        print("%d hub-mount check(s) FAILED:" % len(failures))
        for item in failures:
            print("  - " + item)
        return 1
    print("All hub-mount checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
