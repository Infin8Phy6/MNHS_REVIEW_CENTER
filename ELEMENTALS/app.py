"""ELEMENTALS - a periodic table symbol game.

Runs on its own (python app.py, or double-click run.bat) or mounted inside the
MNHS Review Center, where it shares that app's database and lives under /game.

    python app.py            start the server and open the game in a browser
    python app.py 8020       use another port
    python app.py --lan      also let other computers in the room connect

Everything the game needs lives in elements.db, which is created and filled
from periodic_data.py and clue_data.py the first time the app starts.
"""

import io
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import webbrowser
from datetime import datetime

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect,
                   render_template, request, send_file, send_from_directory, session, url_for)

import clue_data
import periodic_data as PD
import sheet_pdf

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "elements.db")
TOTAL_ITEMS = 10
TILES_PER_SHEET = 20
CHOICES = 6

# standard: clues plus six symbol buttons, any letter case counts.
# hard:     clues only, no buttons, and the typed symbol must be capitalised
#           the way the periodic table writes it (Fe, not fe or FE).
LEVELS = {
    "standard": "With choices",
    "hard": "Hard - spell the symbol",
}

# Elements with no stable isotope: the database holds the mass number of the
# longest-lived isotope, which a real tile prints in brackets.
RADIOGRAPHIC = {43, 61} | set(range(84, 89)) | set(range(93, 104))

FAMILY_LABEL = {
    "alkali": "Alkali metal",
    "alkaline": "Alkaline earth metal",
    "transition": "Transition metal",
    "post": "Post-transition metal",
    "metalloid": "Metalloid",
    "nonmetal": "Reactive nonmetal",
    "halogen": "Halogen",
    "noble": "Noble gas",
    "lanthanide": "Lanthanide",
    "actinide": "Actinide",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS elements(
    z             INTEGER PRIMARY KEY,
    symbol        TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL UNIQUE,
    mass          REAL NOT NULL,
    group_no      INTEGER NOT NULL,
    period        INTEGER NOT NULL,
    series        TEXT NOT NULL DEFAULT '',
    family        TEXT NOT NULL,
    metal_class   TEXT NOT NULL,
    state         TEXT NOT NULL,
    oxidation     TEXT NOT NULL,
    config        TEXT NOT NULL,
    config_pretty TEXT NOT NULL,
    symbol_origin TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS clues(
    id   INTEGER PRIMARY KEY,
    z    INTEGER NOT NULL REFERENCES elements(z),
    ord  INTEGER NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (z, ord)
);
CREATE TABLE IF NOT EXISTS games(
    id       INTEGER PRIMARY KEY,
    token    TEXT NOT NULL UNIQUE,
    student  TEXT NOT NULL,
    grade    TEXT NOT NULL DEFAULT '',
    section  TEXT NOT NULL DEFAULT '',
    account  TEXT NOT NULL DEFAULT '',
    level    TEXT NOT NULL DEFAULT 'standard',
    total    INTEGER NOT NULL,
    score    INTEGER NOT NULL DEFAULT 0,
    started  TEXT NOT NULL,
    finished TEXT,
    seconds  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answers(
    id          INTEGER PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    idx         INTEGER NOT NULL,
    z           INTEGER NOT NULL REFERENCES elements(z),
    choices     TEXT NOT NULL,
    given       TEXT,
    ok          INTEGER,
    answered_at TEXT
);
CREATE TABLE IF NOT EXISTS ws_sheets(
    id      INTEGER PRIMARY KEY,
    token   TEXT NOT NULL UNIQUE,
    picks   TEXT NOT NULL,
    created TEXT NOT NULL
);
"""

INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS answers_game_idx_uq ON answers(game_id, idx)",
    "CREATE INDEX IF NOT EXISTS clues_z_idx ON clues(z)",
]

# All routes sit on a blueprint so the game can be mounted either at the root of
# its own server or under /game inside the Review Center. Templates and scripts
# build their URLs from url_for, so both mounts work from one set of files.
bp = Blueprint("game", __name__, template_folder="templates", static_folder="static")


def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    for sql in INDEXES:
        conn.execute(sql)
    # A database written before the levels existed still needs the column.
    if "level" not in [r[1] for r in conn.execute("PRAGMA table_info(games)")]:
        conn.execute("ALTER TABLE games ADD COLUMN level TEXT NOT NULL DEFAULT 'standard'")
    # Same for the account column that ties a round to a Review Center login.
    if "account" not in [r[1] for r in conn.execute("PRAGMA table_info(games)")]:
        conn.execute("ALTER TABLE games ADD COLUMN account TEXT NOT NULL DEFAULT ''")
    if conn.execute("SELECT COUNT(*) FROM elements").fetchone()[0] == 0:
        with conn:
            for z, symbol, name, mass, grp, per, series, family, cls, state, ox, origin in PD.ROWS:
                conn.execute(
                    "INSERT INTO elements(z, symbol, name, mass, group_no, period, series,"
                    " family, metal_class, state, oxidation, config, config_pretty, symbol_origin)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (z, symbol, name, mass, grp, per, series, family, cls, state, ox,
                     PD.electron_config(z), PD.config_pretty(z), origin),
                )
            for symbol, texts in clue_data.CLUES.items():
                row = conn.execute("SELECT z FROM elements WHERE symbol=?", (symbol,)).fetchone()
                if row:
                    for i, text in enumerate(texts, start=1):
                        conn.execute("INSERT INTO clues(z, ord, text) VALUES(?,?,?)", (row[0], i, text))
    conn.close()


# --------------------------------------------------------------- database
_thread = threading.local()


def db():
    conn = getattr(_thread, "conn", None)
    if conn is None:
        # timeout: inside the Review Center this file also holds accounts and
        # quiz results, so a brief lock from the other connection is normal.
        conn = sqlite3.connect(DB, check_same_thread=False, timeout=20)
        conn.row_factory = sqlite3.Row
        _thread.conn = conn
    return conn


def one(sql, args=()):
    return db().execute(sql, args).fetchone()


def many(sql, args=()):
    return db().execute(sql, args).fetchall()


def run(sql, args=()):
    conn = db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ tiles
def mass_text(row):
    if row["z"] in RADIOGRAPHIC:
        return "[%d]" % round(row["mass"])
    return PD.MASS_DISPLAY.get(row["z"], "%g" % row["mass"])


def tile(row):
    """One database row as the data a periodic-table tile is drawn from."""
    if row["series"] == "L":
        place = "Lanthanide series"
    elif row["series"] == "A":
        place = "Actinide series"
    else:
        place = "Group %d, period %d" % (row["group_no"], row["period"])
    family_label = FAMILY_LABEL.get(row["family"], row["family"])
    where = place if place.startswith(family_label) else "%s · %s" % (place, family_label)
    return {
        "z": row["z"],
        "symbol": row["symbol"],
        "name": row["name"],
        "mass": row["mass"],
        "mass_text": mass_text(row),
        "group_no": row["group_no"],
        "period": row["period"],
        "series": row["series"],
        "place": place,
        "where": where,
        "family": row["family"],
        "family_label": family_label,
        "class": row["metal_class"],
        "state": row["state"],
        "oxidation": row["oxidation"],
        "oxidation_pretty": PD.ox_pretty(row["oxidation"]),
        "config": row["config"],
        "config_pretty": row["config_pretty"],
        "symbol_origin": row["symbol_origin"],
    }


def element(z):
    return one("SELECT * FROM elements WHERE z=?", (z,))


def ask_tile(row):
    """The tile while it is still a mystery: the name and the colour, and nothing
    that hands the symbol or the atomic number over in the page source."""
    t = tile(row)
    return {"name": t["name"], "family": t["family"], "family_label": t["family_label"]}


def pool():
    """The elements the game may draw: those with clues written for them."""
    return [r["z"] for r in many("SELECT DISTINCT z FROM clues ORDER BY z")]


# ------------------------------------------------------------------ games
def build_game(student, grade, section, level="standard", account=""):
    zs = pool()
    picks = random.sample(zs, min(TOTAL_ITEMS, len(zs)))
    token = secrets.token_hex(5)
    while one("SELECT id FROM games WHERE token=?", (token,)):
        token = secrets.token_hex(5)
    cur = run("INSERT INTO games(token, student, grade, section, account, level, total, started)"
              " VALUES(?,?,?,?,?,?,?,?)",
              (token, student, grade, section, account, level, len(picks), now()))
    game_id = cur.lastrowid
    for i, z in enumerate(picks):
        if level == "hard":
            options = []                      # no buttons: the student types the symbol
        else:
            wrong = random.sample([o for o in zs if o != z], CHOICES - 1)
            options = random.sample([z] + wrong, CHOICES)
        run("INSERT INTO answers(game_id, idx, z, choices) VALUES(?,?,?,?)",
            (game_id, i, z, json.dumps(options)))
    # Remember which rounds this browser started, so the score list on a shared
    # Review Center database can stay private to the player who made them.
    # A standalone copy holds one person's rounds on one machine anyway.
    if current_app.config.get("ELEMENTALS_BACK_URL"):
        started = session.setdefault("elementals_games", [])
        if token not in started:
            started.append(token)
        del started[:-30]
    return token


def game_of(token):
    return one("SELECT * FROM games WHERE token=?", (token,))


def current_row(game):
    return one("SELECT * FROM answers WHERE game_id=? AND given IS NULL ORDER BY idx LIMIT 1", (game["id"],))


def close_game(game):
    seconds = int((datetime.now() - datetime.strptime(game["started"], "%Y-%m-%d %H:%M:%S")).total_seconds())
    run("UPDATE games SET finished=?, seconds=? WHERE id=? AND finished IS NULL", (now(), seconds, game["id"]))
    return game_of(game["token"])


def summary(game):
    rows = many("SELECT idx, given, ok, z FROM answers WHERE game_id=? ORDER BY idx", (game["id"],))
    items = [{"idx": r["idx"] + 1, "tile": tile(element(r["z"])), "given": r["given"] or "", "ok": bool(r["ok"])}
             for r in rows]
    return {
        "student": game["student"], "grade": game["grade"], "section": game["section"],
        "level": game["level"], "level_label": LEVELS.get(game["level"], "With choices"),
        "total": game["total"], "score": sum(1 for i in items if i["ok"]), "items": items,
        "started": game["started"], "seconds": game["seconds"] or 0,
        "date": datetime.now().strftime("%d %B %Y"),
    }


@bp.context_processor
def ctx():
    return {"total_elements": one("SELECT COUNT(*) c FROM elements")["c"],
            "clued_elements": len(pool()),
            "levels": LEVELS,
            "families": FAMILY_LABEL,
            "db_name": os.path.basename(DB),
            "staff_allowed": admin_allowed(),
            "back_url": current_app.config.get("ELEMENTALS_BACK_URL")}


# The Review Center sets this when the game is mounted; standalone use leaves
# it unset, and the machine belongs to the teacher, so staff pages stay open.
is_admin = None


def admin_allowed():
    if is_admin is None:
        return True
    return bool(is_admin())


def _worksheet_gate():
    if not admin_allowed():
        return render_template("ws_closed.html"), 403
    return None


# ----------------------------------------------------------------- routes
# The Review Center sets this to a callable that returns the signed-in student
# as {'name': ..., 'grade': ..., 'section': ..., 'account': <email>}, or None
# when nobody is signed in. Standalone mode leaves it alone and asks for a name
# like it always did.
student_defaults = None


def signed_in():
    """Identity taken from the Review Center account, if the game is mounted."""
    return student_defaults() if student_defaults else None


@bp.route("/")
def index():
    return render_template("index.html", total=TOTAL_ITEMS, levels=LEVELS,
                           missing=request.args.get("missing"),
                           account=signed_in())


@bp.route("/start", methods=["POST"])
def start():
    account = signed_in()
    if account:
        # The account already knows who is playing, so the form carries no
        # identity and nothing here can be typed over.
        student = account["name"][:60]
        grade = account["grade"][:20]
        section = account["section"][:20]
    else:
        student = (request.form.get("student") or "").strip()[:60]
        if len(student) < 2:
            return redirect(url_for("game.index", missing=1))
        grade = (request.form.get("grade") or "").strip()[:20]
        section = (request.form.get("section") or "").strip()[:20]
    level = request.form.get("level")
    if level not in LEVELS:
        level = "standard"
    token = build_game(student, grade, section, level,
                       account["account"] if account else "")
    return redirect(url_for("game.play", token=token))


@bp.route("/play/<token>")
def play(token):
    game = game_of(token)
    if not game:
        abort(404)
    return render_template("play.html", game=game)


@bp.route("/api/state/<token>")
def api_state(token):
    game = game_of(token)
    if not game:
        return jsonify(error="This activity link is not saved on this computer."), 404
    row = current_row(game)
    if row is None:
        game = close_game(game)
    out = {"student": game["student"], "grade": game["grade"], "section": game["section"],
           "level": game["level"], "level_label": LEVELS.get(game["level"], LEVELS["standard"]),
           "total": game["total"], "score": game["score"], "finished": row is None}
    if row is not None:
        target = element(row["z"])
        out.update(idx=row["idx"] + 1, tile=ask_tile(target),
                   clues=[c["text"] for c in many("SELECT text FROM clues WHERE z=? ORDER BY ord", (row["z"],))])
        if game["level"] == "hard":
            out["letters"] = len(target["symbol"])   # how long the answer is, and nothing more
        else:
            out["choices"] = [{"z": z, "symbol": element(z)["symbol"]} for z in json.loads(row["choices"])]
    else:
        out["summary"] = summary(game)
    return jsonify(out)


@bp.route("/api/answer/<token>", methods=["POST"])
def api_answer(token):
    game = game_of(token)
    if not game:
        return jsonify(error="This activity link is not saved on this computer."), 404
    row = current_row(game)
    if row is None:
        return jsonify(error="This activity is already finished.", finished=True), 409
    body = request.get_json(silent=True) or {}
    given = str(body.get("symbol") or "").strip()[:8]
    correct = tile(element(row["z"]))
    hard = game["level"] == "hard"
    if hard:
        # The hard level is about writing the symbol the way the table does.
        ok = given == correct["symbol"]
        near = (not ok) and given.upper() == correct["symbol"].upper()
    else:
        ok = given.upper() == correct["symbol"].upper()
        near = False
    run("UPDATE answers SET given=?, ok=?, answered_at=? WHERE id=?", (given, 1 if ok else 0, now(), row["id"]))
    run("UPDATE games SET score=(SELECT COUNT(*) FROM answers WHERE game_id=? AND ok=1) WHERE id=?",
        (game["id"], game["id"]))
    left = one("SELECT COUNT(*) c FROM answers WHERE game_id=? AND given IS NULL", (game["id"],))["c"]
    return jsonify(ok=ok, given=given, correct=correct, score=game_of(token)["score"],
                   total=game["total"], remaining=left, level=game["level"], near=near)


@bp.route("/api/sheet/<token>", methods=["POST"])
def api_sheet(token):
    """Keep a copy of the printed sheet in the app folder as well as the browser download."""
    game = game_of(token)
    if not game:
        return jsonify(error="This activity link is not saved on this computer."), 404
    data = request.get_data()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) > 8_000_000:
        return jsonify(error="That is not a PNG."), 400
    folder = os.path.join(BASE, "sheets")
    os.makedirs(folder, exist_ok=True)
    name = "%s_%s_%s.png" % (re.sub(r"\W+", "_", game["student"]).strip("_")[:40] or "student",
                             datetime.now().strftime("%Y-%m-%d"), game["token"][:6])
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(data)
    return jsonify(saved=True, file=url_for("game.sheet_file", name=name),
                   folder="sheets/" + name)


@bp.route("/sheets/<name>")
def sheet_file(name):
    if not re.fullmatch(r"[\w.-]+\.png", name):
        abort(404)
    return send_from_directory(os.path.join(BASE, "sheets"), name)


@bp.route("/table")
def table():
    tiles = [tile(r) for r in many("SELECT * FROM elements ORDER BY z")]
    for t in tiles:
        if t["series"] == "L":
            t["row"], t["col"] = 9, t["z"] - 54          # lanthanides under the table
        elif t["series"] == "A":
            t["row"], t["col"] = 11, t["z"] - 86         # actinides on their own row
        else:
            t["row"], t["col"] = t["period"], t["group_no"]
    return render_template("table.html", tiles=tiles)


@bp.route("/results")
def results():
    account = signed_in()
    if account:
        # On the shared Review Center database a student only sees their own
        # rounds; standalone mode still lists everything on the machine.
        games = many("SELECT * FROM games WHERE account=? ORDER BY id DESC LIMIT 80",
                     (account["account"],))
    elif current_app.config.get("ELEMENTALS_BACK_URL"):
        # Nobody is signed in on the school's database, so listing every round
        # would put the whole class's names in front of this player.
        started = session.get("elementals_games", [])
        if started:
            marks = ",".join("?" * len(started))
            games = many("SELECT * FROM games WHERE token IN (%s)"
                         " ORDER BY id DESC LIMIT 80" % marks, tuple(started))
        else:
            games = []
    else:
        games = many("SELECT * FROM games ORDER BY id DESC LIMIT 80")
    return render_template("results.html", games=games, account=account)


@bp.route("/install")
def install():
    return render_template("install.html")


# ---------------------------------------------------------- staff worksheet
def _tile_count():
    """Tiles on a fresh activity sheet: the form asks for 20, in steps of ten."""
    try:
        count = int(request.form.get("tiles", TILES_PER_SHEET))
    except (TypeError, ValueError):
        count = TILES_PER_SHEET
    return max(10, min(40, count // 10 * 10))


@bp.route("/worksheet")
def worksheet():
    denied = _worksheet_gate()
    if denied:
        return denied
    return render_template("elementals_worksheet.html", token=None, items=None,
                           tiles=TILES_PER_SHEET)


@bp.route("/worksheet/new", methods=["POST"])
def worksheet_new():
    denied = _worksheet_gate()
    if denied:
        return denied
    tiles = _tile_count()
    picks = random.sample(pool(), min(tiles, len(pool())))
    token = secrets.token_hex(6)
    while one("SELECT id FROM ws_sheets WHERE token=?", (token,)):
        token = secrets.token_hex(6)
    run("INSERT INTO ws_sheets(token, picks, created) VALUES(?,?,?)",
        (token, json.dumps(picks), now()))
    return redirect(url_for("game.activity", token=token))


def sheet_items(zs):
    """One printed item per element: its three clues, name and symbol."""
    items = []
    for index, z in enumerate(zs, start=1):
        row = element(z)
        if not row:
            continue
        clues = [c["text"] for c in many(
            "SELECT text FROM clues WHERE z=? ORDER BY ord", (z,))]
        items.append({"n": index, "name": row["name"], "symbol": row["symbol"],
                      "clues": clues})
    return items


def _fetch_sheet(token):
    row = one("SELECT * FROM ws_sheets WHERE token=?", (token or "",))
    return dict(row) if row else None


@bp.route("/worksheet/<token>")
def worksheet_sheet(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    sheet = _fetch_sheet(token)
    if not sheet:
        abort(404)
    items = sheet_items(json.loads(sheet["picks"]))
    return render_template("elementals_worksheet.html", token=token,
                           items=items, tiles=len(items))


def _activity_view(token, answers):
    denied = _worksheet_gate()
    if denied:
        return denied
    sheet = _fetch_sheet(token)
    if not sheet:
        abort(404)
    return render_template("elementals_activity.html", token=token,
                           items=sheet_items(json.loads(sheet["picks"])),
                           answers=answers)


@bp.route("/worksheet/<token>/activity")
def activity(token):
    """The printable activity sheet: 20 tiles a page, answer space inside each tile."""
    return _activity_view(token, answers=False)


@bp.route("/worksheet/<token>/activity-key")
def activity_key(token):
    """The same sheet with every tile's element named and its symbol printed."""
    return _activity_view(token, answers=True)


@bp.route("/worksheet/<token>/worksheet.pdf")
def worksheet_pdf(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    sheet = _fetch_sheet(token)
    if not sheet:
        abort(404)
    items = sheet_items(json.loads(sheet["picks"]))
    return _send_pdf(sheet_pdf.worksheet_pdf(items, len(items)),
                     "ELEMENTALS_SymbolSprint_Worksheet.pdf")


@bp.route("/worksheet/<token>/answer-key.pdf")
def worksheet_key_pdf(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    sheet = _fetch_sheet(token)
    if not sheet:
        abort(404)
    items = sheet_items(json.loads(sheet["picks"]))
    return _send_pdf(sheet_pdf.answer_key_pdf(items, len(items)),
                     "ELEMENTALS_SymbolSprint_AnswerKey.pdf")


def _send_pdf(data, name):
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=True, download_name=name)


@bp.route("/download")
def download():
    """Hand out the whole app as one zip so a student can install it on their own machine."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("app.py", "periodic_data.py", "clue_data.py", "sheet_pdf.py",
                     "requirements.txt",
                     "INSTALL.md", "run.bat", "run.command", "elements.db"):
            p = os.path.join(BASE, name)
            if os.path.exists(p):
                z.write(p, "ELEMENTALS/" + name)
        for folder in ("templates", "static"):
            for f in sorted(os.listdir(os.path.join(BASE, folder))):
                p = os.path.join(BASE, folder, f)
                if os.path.isfile(p):
                    z.write(p, "ELEMENTALS/%s/%s" % (folder, f))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name="ELEMENTALS.zip")


@bp.route("/manifest.webmanifest")
def manifest():
    home = url_for("game.index")
    doc = {
        "name": "ELEMENTALS - Periodic Table Symbol Sprint",
        "short_name": "ELEMENTALS",
        "description": "Guess the chemical symbol from the clues. Runs offline on your own computer.",
        "start_url": home,
        "scope": home,
        "display": "standalone",
        "background_color": "#eef3f8",
        "theme_color": "#14213d",
        "icons": [
            {"src": url_for("game.icon", size=192), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": url_for("game.icon", size=512), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": url_for("game.icon", size=512, maskable=1), "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }
    return Response(json.dumps(doc), mimetype="application/manifest+json")


@bp.route("/sw.js")
def sw():
    return send_file(os.path.join(BASE, "static", "sw.js"), mimetype="application/javascript")


@bp.route("/icon/<int:size>")
def icon(size):
    name = "icon-%d%s.png" % (size, "m" if request.args.get("maskable") else "")
    path = os.path.join(BASE, "static", name)
    if not os.path.exists(path):
        make_icons()
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png")


def make_icons():
    """Draw the app icon - an amber element tile - with Pillow if it is installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    for size, maskable in ((192, False), (512, False), (512, True)):
        img = Image.new("RGBA", (size, size), (20, 33, 61, 255))
        d = ImageDraw.Draw(img)
        pad = int(size * (0.22 if maskable else 0.08))
        d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=int(size * 0.07),
                            fill=(252, 163, 17, 255))
        bar = pad + int(size * 0.17)
        d.rectangle([pad, pad, bar, size - pad], fill=(20, 33, 61, 255))
        try:
            font = ImageFont.truetype("arialbd.ttf", int(size * 0.34))
        except OSError:
            font = ImageFont.load_default()
        d.text(((bar + size - pad) / 2, size * 0.55), "El", fill=(20, 33, 61, 255), font=font, anchor="mm")
        img.save(os.path.join(BASE, "static", "icon-%d%s.png" % (size, "m" if maskable else "")))


def lan_ip():
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def use_database(path):
    """Share another app's SQLite file instead of elements.db."""
    global DB
    DB = path
    init_db()


def mount(host_app, url_prefix="/game", db_path=None):
    """Attach ELEMENTALS to a host Flask app, optionally inside its database."""
    use_database(db_path) if db_path else init_db()
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run ELEMENTALS on this computer.")
    ap.add_argument("port", nargs="?", type=int, default=8000, help="port (default 8000)")
    ap.add_argument("--lan", action="store_true", help="also let other computers on the network connect")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = ap.parse_args()

    host = Flask(__name__)
    host.config["TEMPLATES_AUTO_RELOAD"] = True
    mount(host, url_prefix="")

    if args.lan:
        print("Class devices on the same wifi:  http://%s:%d" % (lan_ip(), args.port))
    print("ELEMENTALS is running at http://localhost:%d/   (Ctrl+C to stop)" % args.port)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/" % args.port)).start()
    host.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
