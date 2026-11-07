"""Crosswords: teacher-built crossword puzzles for the Review Center.

Runs on its own (`python app.py 8040`) or mounted inside the Review Center at
/games/crossword, where it uses the signed-in student as the player and the
shared quiz_app.db. A teacher lists ten words with clues; the app interlocks
them into one letter grid. Students click successive tiles, press Check and
earn three points for every exact word, thirty at the most. Every finish -
by button, by clock or by the teacher closing the puzzle - reveals the total,
and the sheet can be downloaded as PNG or PDF.
"""
import io
import json
import os
import random
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect,
                   render_template, request, send_file, url_for)

import cw_gen
import cw_pdf

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "crossword.db")

WORDS_PER_PUZZLE = 10
POINTS_PER_WORD = 3
MAX_POINTS = WORDS_PER_PUZZLE * POINTS_PER_WORD
MIN_LIMIT, MAX_LIMIT = 60, 3600
DEFAULT_LIMIT = 900

SCHEMA = """
CREATE TABLE IF NOT EXISTS cw_puzzles(
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    time_limit INTEGER NOT NULL DEFAULT 900,
    seed INTEGER NOT NULL DEFAULT 0,
    rows INTEGER NOT NULL DEFAULT 0,
    cols INTEGER NOT NULL DEFAULT 0,
    grid TEXT NOT NULL DEFAULT '[]',
    placements TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    closed TEXT
);
CREATE TABLE IF NOT EXISTS cw_attempts(
    id INTEGER PRIMARY KEY,
    puzzle_id INTEGER NOT NULL REFERENCES cw_puzzles(id),
    token TEXT NOT NULL UNIQUE,
    account TEXT NOT NULL DEFAULT '',
    student TEXT NOT NULL DEFAULT '',
    grade TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT '',
    started TEXT NOT NULL,
    deadline TEXT NOT NULL,
    finished TEXT,
    reason TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    board TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cw_scores(
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES cw_attempts(id),
    number INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 3,
    given TEXT NOT NULL,
    at TEXT NOT NULL,
    UNIQUE(attempt_id, number)
);
"""

bp = Blueprint("crossword", __name__, template_folder="templates", static_folder="static")

# Set by the Review Center: the signed-in student, the staff checks and the
# staff email that owns a puzzle. Standalone use leaves them all None.
identity = None
is_admin = None
is_officer = None
staff_account = None

_lock = threading.Lock()


# ----------------------------------------------------------------- database
def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cw_attempts)")]
    if "board" not in cols:  # attempts gain a board of their own in v2
        conn.execute("ALTER TABLE cw_attempts ADD COLUMN board TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


_thread = threading.local()


def db():
    conn = getattr(_thread, "conn", None)
    if conn is None:
        # The same file holds accounts, quiz results and the other games, so a
        # short lock from another writer is normal.
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


def soon(seconds):
    return (datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def stamp(text):
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")


def seconds_left(until):
    end = stamp(until)
    if not end:
        return 0
    return max(0, int((end - datetime.now()).total_seconds()))


# ------------------------------------------------------------------ helpers
def signed_in():
    return identity() if identity else None


def admin_allowed():
    """Standalone use is the teacher on their own machine, so it is allowed."""
    if is_admin is None:
        return True
    return bool(is_admin())


def officer_allowed():
    if is_officer is None:
        return admin_allowed()
    return bool(is_officer())


def current_staff_account():
    if staff_account is None:
        return ""
    try:
        return staff_account() or ""
    except Exception:
        return ""


def puzzle_data(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "time_limit": row["time_limit"],
        "rows": row["rows"],
        "cols": row["cols"],
        "grid": json.loads(row["grid"]),
        "placements": json.loads(row["placements"]),
        "created_by": row["created_by"],
        "created": row["created"],
    }


def fetch_puzzle(pid):
    row = one("SELECT * FROM cw_puzzles WHERE id=?", (pid,))
    return puzzle_data(row) if row else None


def fetch_attempt(token):
    row = one("SELECT * FROM cw_attempts WHERE token=?", (token,))
    return row


def board_for(attempt, puzzle):
    """The board this attempt plays. Every start rebuilds a fresh layout from
    the puzzle's own words, so a repeat never shows the same picture; an older
    attempt without a board falls back to the puzzle's original."""
    raw = attempt["board"] if "board" in attempt.keys() else ""
    if raw:
        fresh = dict(puzzle)
        fresh.update(json.loads(raw))
        return fresh
    return puzzle


def owned(row):
    """An attempt belongs to the student who started it; staff may review any."""
    if admin_allowed():
        return True
    user = signed_in()
    if not user:
        return True  # standalone play keeps working without accounts
    return user.get("account") == row["account"]


def solve_rows(attempt_id):
    return {r["number"] for r in many(
        "SELECT number FROM cw_scores WHERE attempt_id=?", (attempt_id,))}


def finalize(attempt, reason):
    """Stamp the end, then re-tally from cw_scores so the total is the truth."""
    total = one("SELECT COALESCE(SUM(points), 0) t FROM cw_scores WHERE attempt_id=?",
                (attempt["id"],))["t"]
    run("UPDATE cw_attempts SET finished=?, reason=?, score=? WHERE id=? AND finished IS NULL",
        (now(), reason, total, attempt["id"]))
    return total


def state_for(attempt, puzzle):
    solved = solve_rows(attempt["id"])
    revealed = bool(attempt["finished"])
    seconds = 0 if revealed else seconds_left(attempt["deadline"])
    clues = []
    for p in puzzle["placements"]:
        entry = {"n": p["n"], "dir": p["dir"], "clue": p["clue"],
                 "length": len(p["word"]), "solved": p["n"] in solved,
                 "at": p["at"]}
        if entry["solved"] or revealed:
            entry["word"] = p["word"]
        clues.append(entry)
    return {
        "puzzle": {"id": puzzle["id"], "title": puzzle["title"],
                   "status": puzzle["status"]},
        "rows": puzzle["rows"], "cols": puzzle["cols"], "grid": puzzle["grid"],
        "clues": clues, "seconds_left": seconds, "score": attempt["score"],
        "max_points": MAX_POINTS, "points": POINTS_PER_WORD,
        "finished": revealed, "reason": attempt["reason"],
        "token": attempt["token"],
    }


# ------------------------------------------------------------------- pages
@bp.context_processor
def ctx():
    return {"back_url": current_app.config.get("CROSSWORDS_BACK_URL"),
            "game_name": "Crosswords",
            "words_per_puzzle": WORDS_PER_PUZZLE,
            "points_per_word": POINTS_PER_WORD,
            "max_points": MAX_POINTS}


@bp.route("/")
def index():
    rows = many("SELECT * FROM cw_puzzles WHERE status='open' ORDER BY id DESC")
    user = signed_in()
    best = {}
    if user:
        for r in many("SELECT puzzle_id, MAX(score) s, COUNT(*) tries FROM cw_attempts "
                      "WHERE account=? AND finished IS NOT NULL GROUP BY puzzle_id",
                     (user["account"],)):
            best[r["puzzle_id"]] = {"score": r["s"], "tries": r["tries"]}
    return render_template("cw_index.html", puzzles=[
        {"row": r, "best": best.get(r["id"])} for r in rows])


@bp.route("/start/<int:pid>", methods=["POST"])
def start(pid):
    puzzle = fetch_puzzle(pid)
    if not puzzle or puzzle["status"] != "open":
        abort(404)
    user = signed_in() or {"name": "", "grade": "", "section": "", "account": ""}
    token = secrets.token_hex(12)
    board = ""
    try:
        fresh = cw_gen.build([(p["word"], p["clue"]) for p in puzzle["placements"]],
                             random.randrange(1 << 40))
    except cw_gen.GenerationError:
        pass  # this word set refuses to re-interlock; keep the stored board
    if fresh:
        board = json.dumps({k: fresh[k] for k in
                            ("rows", "cols", "grid", "placements")})
    run("INSERT INTO cw_attempts(puzzle_id, token, account, student, grade,"
        " section, started, deadline, board) VALUES(?,?,?,?,?,?,?,?,?)",
        (pid, token, user["account"], user["name"], user["grade"], user["section"],
         now(), soon(puzzle["time_limit"]), board))
    return redirect(url_for("crossword.play", token=token))


@bp.route("/play/<token>")
def play(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    if attempt["finished"]:
        return redirect(url_for("crossword.result", token=token))
    if seconds_left(attempt["deadline"]) == 0:
        finalize(attempt, "timeout")
        return redirect(url_for("crossword.result", token=token))
    puzzle = fetch_puzzle(attempt["puzzle_id"])
    return render_template("cw_play.html", attempt=attempt,
                           puzzle=board_for(attempt, puzzle))


@bp.route("/result/<token>")
def result(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    if not attempt["finished"]:
        finalize(attempt, "finish")
        attempt = fetch_attempt(token)
    puzzle = board_for(attempt, fetch_puzzle(attempt["puzzle_id"]))
    data = state_for(attempt, puzzle)
    data["student"] = dict(attempt)
    sheet = json.dumps({
        "title": puzzle["title"], "rows": puzzle["rows"], "cols": puzzle["cols"],
        "grid": puzzle["grid"], "clues": data["clues"],
        "name": attempt["student"], "grade": attempt["grade"],
        "section": attempt["section"], "score": attempt["score"],
        "max": MAX_POINTS, "date": (attempt["finished"] or "")[:10],
        "reason": attempt["reason"],
    })
    return render_template("cw_result.html", attempt=attempt, puzzle=puzzle,
                           data=data, sheet=sheet)


# ------------------------------------------------------------- teacher side
@bp.route("/manage")
def manage():
    if not admin_allowed():
        return render_template("cw_closed.html"), 403
    rows = many("SELECT * FROM cw_puzzles ORDER BY id DESC")
    stats = {r["pid"]: r for r in many(
        "SELECT puzzle_id pid, COUNT(*) plays, MAX(score) best FROM cw_attempts "
        "WHERE finished IS NOT NULL GROUP BY puzzle_id")}
    return render_template("cw_admin.html", rows=rows, stats=stats,
                           notice=request.args.get("notice"),
                           problem=request.args.get("problem"),
                           words=WORDS_PER_PUZZLE, default_limit=DEFAULT_LIMIT)


@bp.route("/manage/create", methods=["POST"])
def create():
    if not admin_allowed():
        return render_template("cw_closed.html"), 403
    title = (request.form.get("title") or "").strip()[:120]
    try:
        limit = int(request.form.get("time_limit") or DEFAULT_LIMIT)
    except ValueError:
        limit = DEFAULT_LIMIT
    limit = max(MIN_LIMIT, min(MAX_LIMIT, limit))
    words = request.form.getlist("word[]")
    clues = request.form.getlist("clue[]")
    pairs = [(w, c) for w, c in zip(words, clues)]
    pairs = [(w, c) for w, c in pairs if clean_present(w)]

    problem = ""
    if len(title) < 2:
        problem = "Give the puzzle a title."
    elif len(pairs) != WORDS_PER_PUZZLE:
        problem = ("List exactly %d words with their clues - %d came in."
                   % (WORDS_PER_PUZZLE, len(pairs)))
    else:
        try:
            seed = random.randrange(1 << 40)
            board = cw_gen.build(pairs, seed)
        except cw_gen.GenerationError as exc:
            problem = str(exc)
        else:
            with _lock:
                run("INSERT INTO cw_puzzles(title, time_limit, seed, rows, cols,"
                    " grid, placements, created_by, created) VALUES(?,?,?,?,?,?,?,?,?)",
                    (title, limit, seed, board["rows"], board["cols"],
                     json.dumps(board["grid"]), json.dumps(board["placements"]),
                     current_staff_account(), now()))
            pid = one("SELECT MAX(id) m FROM cw_puzzles")["m"]
            return redirect(url_for("crossword.manage",
                                    notice="Puzzle #%d is ready for your class." % pid))
    return render_template("cw_admin.html",
                           rows=many("SELECT * FROM cw_puzzles ORDER BY id DESC"),
                           stats={}, notice="", problem=problem,
                           form={"title": title, "time_limit": limit,
                                 "words": words, "clues": clues},
                           words=WORDS_PER_PUZZLE, default_limit=DEFAULT_LIMIT), 400


def clean_present(word):
    return bool((word or "").strip())


@bp.route("/manage/close/<int:pid>", methods=["POST"])
def close(pid):
    if not admin_allowed():
        return render_template("cw_closed.html"), 403
    run("UPDATE cw_puzzles SET status='closed', closed=? WHERE id=?", (now(), pid))
    for row in many("SELECT * FROM cw_attempts WHERE puzzle_id=? AND finished IS NULL",
                    (pid,)):
        finalize(row, "closed")
    return redirect(url_for("crossword.manage", notice="Puzzle #%d is closed." % pid))


@bp.route("/manage/delete/<int:pid>", methods=["POST"])
def delete(pid):
    if not admin_allowed():
        return render_template("cw_closed.html"), 403
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    account = current_staff_account()
    if not officer_allowed() and puzzle["created_by"] != account:
        return render_template("cw_closed.html"), 403
    ids = [r["id"] for r in many("SELECT id FROM cw_attempts WHERE puzzle_id=?", (pid,))]
    for aid in ids:
        run("DELETE FROM cw_scores WHERE attempt_id=?", (aid,))
    run("DELETE FROM cw_attempts WHERE puzzle_id=?", (pid,))
    run("DELETE FROM cw_puzzles WHERE id=?", (pid,))
    return redirect(url_for("crossword.manage", notice="Puzzle #%d deleted." % pid))


@bp.route("/scores/<int:pid>")
def scores(pid):
    if not admin_allowed():
        return render_template("cw_closed.html"), 403
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    rows = many(
        "SELECT COALESCE(NULLIF(account,''), token) key, MAX(student) student,"
        " MAX(grade) grade, MAX(section) section, MAX(score) best,"
        " COUNT(*) tries, SUM(CASE WHEN finished IS NULL THEN 1 ELSE 0 END) live"
        " FROM cw_attempts WHERE puzzle_id=? AND finished IS NOT NULL"
        " GROUP BY COALESCE(NULLIF(account,''), token) ORDER BY best DESC, MAX(finished)",
        (pid,))
    return render_template("cw_scores.html", puzzle=puzzle, rows=rows,
                           max_points=MAX_POINTS)


# ---------------------------------------------------------------------- API
@bp.route("/api/state/<token>")
def api_state(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    puzzle = board_for(attempt, fetch_puzzle(attempt["puzzle_id"]))
    if not attempt["finished"] and seconds_left(attempt["deadline"]) == 0:
        finalize(attempt, "timeout")
        attempt = fetch_attempt(token)
    if not attempt["finished"] and puzzle["status"] != "open":
        finalize(attempt, "closed")
        attempt = fetch_attempt(token)
    return jsonify(state_for(attempt, puzzle))


@bp.route("/api/check/<token>", methods=["POST"])
def api_check(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    puzzle = board_for(attempt, fetch_puzzle(attempt["puzzle_id"]))
    if attempt["finished"]:
        return jsonify({"ok": False, "reason": "finished"})
    if puzzle["status"] != "open":
        finalize(attempt, "closed")
        return jsonify({"ok": False, "reason": "closed"})
    if seconds_left(attempt["deadline"]) == 0:
        finalize(attempt, "timeout")
        return jsonify({"ok": False, "reason": "timeout"})

    body = request.get_json(silent=True) or {}
    cells = [[int(r), int(c)] for r, c in (body.get("cells") or [])]
    number = body.get("n")
    if len(cells) < 2:
        return jsonify({"ok": True, "matched": False, "score": attempt["score"],
                        "seconds_left": seconds_left(attempt["deadline"])})

    solved = solve_rows(attempt["id"])
    hits = [p for p in puzzle["placements"] if
            (number is None or p["n"] == number) and
            (cells == p["cells"] or cells == p["cells"][::-1])]
    if not hits:
        return jsonify({"ok": True, "matched": False, "score": attempt["score"],
                        "seconds_left": seconds_left(attempt["deadline"])})
    hit = hits[0]
    if hit["n"] in solved:
        return jsonify({"ok": True, "matched": True, "already": True,
                        "n": hit["n"], "score": attempt["score"],
                        "seconds_left": seconds_left(attempt["deadline"])})

    cur = run("INSERT OR IGNORE INTO cw_scores(attempt_id, number, points, given, at)"
              " VALUES(?,?,?,?,?)",
              (attempt["id"], hit["n"], POINTS_PER_WORD, hit["word"], now()))
    if cur.rowcount == 0:  # two taps raced; the first one already banked it
        return jsonify({"ok": True, "matched": True, "already": True,
                        "n": hit["n"], "score": attempt["score"],
                        "seconds_left": seconds_left(attempt["deadline"])})
    score = attempt["score"] + POINTS_PER_WORD
    run("UPDATE cw_attempts SET score=? WHERE id=?", (score, attempt["id"]))
    fresh = score >= MAX_POINTS
    if fresh:
        finalize(fetch_attempt(token), "finish")
    return jsonify({"ok": True, "matched": True, "already": False, "n": hit["n"],
                    "points": POINTS_PER_WORD, "score": score,
                    "complete": fresh,
                    "seconds_left": seconds_left(attempt["deadline"])})


@bp.route("/api/finish/<token>", methods=["POST"])
def api_finish(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    reason = "timeout" if (not attempt["finished"] and
                           seconds_left(attempt["deadline"]) == 0) else "finish"
    if not attempt["finished"]:
        finalize(attempt, reason)
    return jsonify({"ok": True, "result": url_for("crossword.result", token=token)})


# ---------------------------------------------------------------- downloads
@bp.route("/worksheet/<int:pid>")
def worksheet_print(pid):
    """The printable handout: empty grid, numbered clues, Name/Grade/Section line."""
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return render_template("cw_printable.html", puzzle=puzzle, mode="blank")


@bp.route("/worksheet/<int:pid>/key")
def worksheet_print_key(pid):
    """The same sheet with the grid solved and every clue answered - staff only."""
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return render_template("cw_printable.html", puzzle=puzzle, mode="key")


@bp.route("/worksheet/<int:pid>/easy")
def worksheet_print_easy(pid):
    """Easy level word hunt: filled grid with no clue numbers, definitions
    given with a blank where the answer word goes."""
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return render_template("cw_printable.html", puzzle=puzzle, mode="easy")


@bp.route("/pdf/unsolved/<int:pid>")
def pdf_unsolved(pid):
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return _send(cw_pdf.worksheet_pdf(puzzle), "crossword-%d-worksheet.pdf" % pid)


@bp.route("/pdf/solved/<int:pid>")
def pdf_solved(pid):
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return _send(cw_pdf.answer_key_pdf(puzzle), "crossword-%d-answer-key.pdf" % pid)


@bp.route("/pdf/easy/<int:pid>")
def pdf_easy(pid):
    if not admin_allowed():
        abort(403)
    puzzle = fetch_puzzle(pid)
    if not puzzle:
        abort(404)
    return _send(cw_pdf.easy_pdf(puzzle), "crossword-%d-easy.pdf" % pid)


@bp.route("/pdf/attempt/<token>")
def pdf_attempt(token):
    attempt = fetch_attempt(token)
    if not attempt or not owned(attempt):
        abort(403)
    if not attempt["finished"]:
        finalize(attempt, "finish")
        attempt = fetch_attempt(token)
    puzzle = board_for(attempt, fetch_puzzle(attempt["puzzle_id"]))
    info = dict(attempt)
    info["max_points"] = MAX_POINTS
    return _send(cw_pdf.attempt_pdf(puzzle, info),
                 "crossword-result-%s.pdf" % token[:8])


def _send(data, name):
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=True, download_name=name)


# ------------------------------------------------------- app shell plumbing
@bp.route("/manifest.webmanifest")
def manifest():
    root = url_for("crossword.index")
    doc = {"name": "Crosswords - MNHS Review Center", "short_name": "Crosswords",
           "start_url": root, "scope": root, "display": "standalone",
           "background_color": "#eef3f8", "theme_color": "#14213d",
           "icons": [{"src": "%sicon/192" % root, "sizes": "192x192", "type": "image/png"},
                     {"src": "%sicon/512" % root, "sizes": "512x512", "type": "image/png"}]}
    return Response(json.dumps(doc), mimetype="application/manifest+json")


@bp.route("/sw.js")
def sw():
    return send_static("sw.js")


@bp.route("/icon/<int:size>")
def icon(size):
    return Response(app_icon(min(max(size, 64), 512)), mimetype="image/png")


_icons = {}


def app_icon(size):
    """A navy tile with an amber X of crossing bars, drawn without Pillow."""
    if size in _icons:
        return _icons[size]
    import struct
    import zlib

    navy, amber = (20, 33, 61), (252, 163, 17)
    rows = []
    for y in range(size):
        row = bytearray()
        fy = y / size
        for x in range(size):
            fx = x / size
            inside = (0.26 <= fx <= 0.74 and 0.26 <= fy <= 0.74 and
                      (abs(fx - fy) < 0.07 or abs(fx + fy - 1) < 0.07))
            if 0.08 <= fx < 0.92 and 0.08 <= fy < 0.92:
                pixel = amber if inside else navy
            else:
                pixel = navy
            row += bytes(pixel) + b"\xff"
        rows.append(b"\x00" + bytes(row))

    raw = zlib.compress(b"".join(rows), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    _icons[size] = png
    return png


def send_static(name):
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE, "static"), name)


def use_database(path):
    """Share another app's SQLite file instead of crossword.db."""
    global DB
    DB = path
    init_db()


def mount(host_app, url_prefix="/games/crossword", db_path=None):
    """Attach Crosswords to a host Flask app, optionally inside its database."""
    use_database(db_path) if db_path else init_db()
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse
    import webbrowser

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run Crosswords on this computer.")
    ap.add_argument("port", nargs="?", type=int, default=8040)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = Flask(__name__)
    host.config["TEMPLATES_AUTO_RELOAD"] = True
    mount(host, url_prefix="")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/" % args.port)).start()
    host.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
