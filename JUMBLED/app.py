"""Jumbled Letters: a synchronized multiplayer word game for the Review Center.

Runs on its own (`python app.py 8030`) or mounted inside the Review Center at
/games/jumbled, where it uses the signed-in account as the player name and the
shared quiz_app.db.
"""
import io
import json
import os
import random
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect,
                   render_template, request, send_file, url_for)

import jl_sheet_pdf
import words as W

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "jumbled.db")

WORD_SECONDS = 90        # each jumble is on the screen for 90 seconds
MAX_PLAYERS = 45         # the room the spec asks for
PODIUM = ["Champion", "First Place", "Second Place"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jl_rooms(
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'lobby',
    grade TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    quarter TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    words TEXT NOT NULL DEFAULT '[]',
    idx INTEGER NOT NULL DEFAULT 0,
    deadline TEXT NOT NULL DEFAULT '',
    clincher TEXT NOT NULL DEFAULT '',
    clincher_deadline TEXT NOT NULL DEFAULT '',
    tied TEXT NOT NULL DEFAULT '[]',
    host TEXT NOT NULL DEFAULT '',
    solo INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    finished TEXT
);
CREATE TABLE IF NOT EXISTS jl_players(
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES jl_rooms(id),
    token TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    joined TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jl_answers(
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES jl_rooms(id),
    player_id INTEGER NOT NULL REFERENCES jl_players(id),
    stage INTEGER NOT NULL DEFAULT 0,
    given TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jl_sheets(
    id INTEGER PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    grade TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    quarter TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    words TEXT NOT NULL DEFAULT '[]',
    created TEXT NOT NULL
);
"""

bp = Blueprint("jumbled", __name__, template_folder="templates", static_folder="static")

# Set by the Review Center: a callable returning the signed-in student, and the
# Grade -> Subject -> Quarter -> Topic tree used by the quiz specification form.
identity = None
spec = None
# Set by the Review Center: a callable saying whether the signer is staff.
# Standalone use belongs to the teacher on the machine, so staff pages stay open.
is_admin = None

_lock = threading.Lock()


# ----------------------------------------------------------------- database
def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    # A room created before single-player existed has no flag column yet.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(jl_rooms)")]
    if "solo" not in cols:
        conn.execute("ALTER TABLE jl_rooms ADD COLUMN solo INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


_thread = threading.local()


def db():
    conn = getattr(_thread, "conn", None)
    if conn is None:
        # The same file holds accounts, quiz results and ELEMENTALS, so a short
        # lock from another writer is normal.
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
    """A deadline the clock helpers can read back — stored as plain text."""
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


# -------------------------------------------------------------------- rooms
def load_spec():
    """The same tree the quiz setup page uses."""
    if spec:
        return spec
    path = os.path.join(os.path.dirname(BASE), "matatag_spec.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    return {level: {subject: {quarter: topics for quarter, topics in quarters.items()}
                    for subject, quarters in subjects.items()}
            for level, subjects in raw.items()}


def signed_in():
    return identity() if identity else None


def tree_json():
    """The quiz-specification choices as plain lists for the setup page.

    The Review Center hands over its own tree, where a topic maps to its question
    count, and standalone mode reads the spec file, where topics are a list.
    """
    out = {}
    for level, subjects in load_spec().items():
        if not level:
            continue
        for subject, quarters in subjects.items():
            if not subject:
                continue
            for quarter, topics in quarters.items():
                names = list(topics) if topics else []
                out.setdefault(level, {}).setdefault(subject, {})[quarter] = names
    return out


def new_code():
    while True:
        code = secrets.token_hex(3).upper()
        if not one("SELECT id FROM jl_rooms WHERE code=?", (code,)):
            return code


def room_by_code(code):
    return one("SELECT * FROM jl_rooms WHERE code=?", ((code or "").strip().upper(),))


def players_of(room_id):
    return many("SELECT * FROM jl_players WHERE room_id=? ORDER BY id", (room_id,))


def player_by_token(room_id, token):
    return one("SELECT * FROM jl_players WHERE room_id=? AND token=?",
               (room_id, (token or "").strip()))


def words_of(room):
    return json.loads(room["words"] or "[]")


def current_stage(room):
    """(-1, clincher word) while a tie-break runs, otherwise (index, word)."""
    if room["status"] == "clincher":
        return -1, json.loads(room["clincher"] or "{}")
    if room["idx"] < total_of(room):
        return room["idx"], words_of(room)[room["idx"]]
    return room["idx"], None


def total_of(room):
    return len(words_of(room))


def standings(room):
    """Total points, then the tie-break word, then who got there first."""
    hits = many("SELECT player_id, MIN(at) first_at FROM jl_answers"
                " WHERE room_id=? AND points>0 GROUP BY player_id", (room["id"],))
    first = {r["player_id"]: r["first_at"] for r in hits}
    bonus = {r["player_id"]: (r["pts"], r["at"]) for r in many(
        "SELECT player_id, SUM(points) pts, MIN(at) at FROM jl_answers"
        " WHERE room_id=? AND stage=-1 GROUP BY player_id", (room["id"],))}

    out = []
    for p in players_of(room["id"]):
        pts, at = bonus.get(p["id"], (0, ""))
        out.append({"token": p["token"], "name": p["name"], "account": p["account"],
                    "score": p["score"], "joined": p["joined"], "clincher": pts or 0,
                    "first_hit": first.get(p["id"]) or p["joined"], "clincher_hit": at})
    out.sort(key=lambda r: (-r["score"], -r["clincher"],
                            r["clincher_hit"] or "9999", r["first_hit"], r["joined"]))
    return out


def tie_group(room):
    """Players whose shared score decides the 1st, 2nd or 3rd place spot."""
    ranked = standings(room)
    if len(ranked) < 2:
        return []
    cut = min(3, len(ranked) - 1)
    tied_scores = set()
    for boundary in range(cut):
        if ranked[boundary]["score"] == ranked[boundary + 1]["score"]:
            tied_scores.add(ranked[boundary]["score"])
    if not tied_scores:
        return []
    return [r["token"] for r in ranked if r["score"] in tied_scores]


def move_on(room):
    """Put the next jumble on the board, or finish the round. Caller holds _lock."""
    nxt = room["idx"] + 1
    if nxt < total_of(room):
        run("UPDATE jl_rooms SET idx=?, deadline=? WHERE id=?",
            (nxt, soon(WORD_SECONDS), room["id"]))
        return

    tied = tie_group(room)
    if not tied:
        run("UPDATE jl_rooms SET status='done', finished=? WHERE id=?",
            (now(), room["id"]))
        return

    used = {w["word"] for w in words_of(room)}
    extra = [w for w in W.words_for(room["grade"], room["subject"], room["topic"], 40)
             if w not in used]
    pick = random.choice(extra) if extra else random.choice(words_of(room))["word"]
    clin = {"word": pick, "jumble": W.jumble(pick)}
    run("UPDATE jl_rooms SET status='clincher', clincher=?, clincher_deadline=?,"
        " tied=? WHERE id=?", (json.dumps(clin), soon(WORD_SECONDS),
                               json.dumps(tied), room["id"]))


def advance(room):
    """Move the clock forward. Called from every poll, so it is idempotent."""
    with _lock:
        room = room_by_code(room["code"])
        changed = False
        if room["status"] == "playing" and seconds_left(room["deadline"]) == 0:
            move_on(room)
            changed = True
        elif room["status"] == "clincher" and seconds_left(room["clincher_deadline"]) == 0:
            resolve_clincher(room)
            changed = True
        return room_by_code(room["code"]) if changed else room


def pass_on(room, player, stage):
    """End a jumble early: the board moves on once a player has earned it.

    Earning it means the topic word plus MIN_VALID_TO_PASS other real words from
    the same letters, so the class still gets the bonus thinking before the next
    tile appears. The clincher keeps its full clock - a tie-break is not passed on.
    """
    with _lock:
        fresh = room_by_code(room["code"])
        if fresh["status"] != "playing" or stage != fresh["idx"] or stage < 0:
            return False
        solved, valid, bonus = my_history(fresh, player, stage)
        if not solved or bonus < W.MIN_VALID_TO_PASS:
            return False
        move_on(fresh)
        return True


def resolve_clincher(room):
    """standings() already ranks the tied players by tie-break points and speed."""
    run("UPDATE jl_rooms SET status='done', finished=? WHERE id=?", (now(), room["id"]))


# ------------------------------------------------------------------- routes
@bp.context_processor
def ctx():
    return {"back_url": current_app.config.get("JUMBLED_BACK_URL"),
            "game_name": "Jumbled Letters",
            "word_seconds": WORD_SECONDS, "max_players": MAX_PLAYERS,
            "words_per_round": W.WORDS_PER_ROUND,
            "min_valid_to_pass": W.MIN_VALID_TO_PASS,
            "target_points": W.TARGET_POINTS, "valid_points": W.VALID_POINTS,
            "staff_allowed": admin_allowed()}


@bp.route("/")
def setup():
    return render_template("jl_setup.html", tree=tree_json(), account=signed_in(),
                           missing=request.args.get("missing"))


# ---------------------------------------------------------- staff worksheet
def admin_allowed():
    """Standalone use is the teacher on their own machine, so it is allowed."""
    if is_admin is None:
        return True
    return bool(is_admin())


def _worksheet_gate():
    if not admin_allowed():
        return render_template("jl_closed.html"), 403
    return None


WORKSHEET_WORDS = 10      # the ten jumbles the worksheet prints by default


@bp.route("/worksheet")
def worksheet():
    denied = _worksheet_gate()
    if denied:
        return denied
    return render_template("jl_worksheet.html", tree=tree_json(), token=None,
                           items=None, path=None,
                           missing=request.args.get("missing"))


@bp.route("/worksheet/new", methods=["POST"])
def worksheet_new():
    denied = _worksheet_gate()
    if denied:
        return denied
    grade = (request.form.get("grade") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    quarter = (request.form.get("quarter") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    try:
        count = int(request.form.get("count") or WORKSHEET_WORDS)
    except ValueError:
        count = WORKSHEET_WORDS
    count = max(5, min(20, count))
    picked = W.pick(grade, subject, topic, count)
    if not picked:
        return redirect(url_for("jumbled.worksheet", missing=1))

    token = secrets.token_hex(6)
    while one("SELECT id FROM jl_sheets WHERE token=?", (token,)):
        token = secrets.token_hex(6)
    run("INSERT INTO jl_sheets(token, grade, subject, quarter, topic, words, created)"
        " VALUES(?,?,?,?,?,?,?)",
        (token, grade, subject, quarter, topic, json.dumps(picked), now()))
    return redirect(url_for("jumbled.worksheet_show", token=token))


def _fetch_sheet(token):
    row = one("SELECT * FROM jl_sheets WHERE token=?", ((token or "").strip(),))
    return dict(row) if row else None


def _sheet_items(row):
    return [{"n": index + 1, "word": p["word"], "jumble": p["jumble"]}
            for index, p in enumerate(json.loads(row["words"] or "[]"))]


def _sheet_path(row):
    return [row["grade"], row["subject"], row["quarter"], row["topic"]]


@bp.route("/worksheet/<token>")
def worksheet_show(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    row = _fetch_sheet(token)
    if not row:
        abort(404)
    return render_template("jl_worksheet.html", tree=tree_json(), token=token,
                           items=_sheet_items(row), path=_sheet_path(row),
                           missing=None,
                           answers=request.args.get("answers") == "1")


@bp.route("/worksheet/<token>/worksheet.pdf")
def worksheet_pdf(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    row = _fetch_sheet(token)
    if not row:
        abort(404)
    return _send_pdf(jl_sheet_pdf.worksheet_pdf(_sheet_path(row), _sheet_items(row)),
                     "JumbledLetters_Worksheet.pdf")


@bp.route("/worksheet/<token>/answer-key.pdf")
def worksheet_key_pdf(token):
    denied = _worksheet_gate()
    if denied:
        return denied
    row = _fetch_sheet(token)
    if not row:
        abort(404)
    return _send_pdf(jl_sheet_pdf.answer_key_pdf(_sheet_path(row), _sheet_items(row)),
                     "JumbledLetters_AnswerKey.pdf")


def _send_pdf(data, name):
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=True, download_name=name)


@bp.route("/create", methods=["POST"])
def create():
    grade = (request.form.get("grade") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    quarter = (request.form.get("quarter") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    picked = W.pick(grade, subject, topic)
    if not picked:
        return redirect(url_for("jumbled.setup", missing=1))

    solo = 1 if request.form.get("solo") else 0
    code = new_code()
    status = "playing" if solo else "lobby"
    deadline = soon(WORD_SECONDS) if solo else ""
    run("INSERT INTO jl_rooms(code, status, grade, subject, quarter, topic, words, solo,"
        " idx, deadline, created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (code, status, grade, subject, quarter, topic, json.dumps(picked), solo,
         0, deadline, now()))
    room = room_by_code(code)

    me = join_player(room, request.form.get("nickname"))
    run("UPDATE jl_rooms SET host=? WHERE id=?", (me["token"], room["id"]))
    response = redirect(url_for("jumbled.room", code=code, p=me["token"]))
    keep_player(response, code, me["token"])
    if not signed_in():
        # The typed name is the one on the sheet, so it is worth remembering.
        response.set_cookie("jl_nick", me["name"], max_age=90 * 86400, path="/")
    return response


def keep_player(response, code, token):
    """Remember which player this device is, so a refresh does not join twice."""
    response.set_cookie("jl_p_%s" % code, token, max_age=7 * 86400, path="/")


def clean_name(raw):
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    return text[:30]


def join_player(room, nickname=None):
    """Account name when signed in, otherwise the nickname they choose."""
    if len(players_of(room["id"])) >= MAX_PLAYERS:
        return None

    who = signed_in()
    account = who["account"] if who else ""
    if who:
        name = clean_name(who["name"])
    else:
        name = clean_name(nickname) or clean_name(request.cookies.get("jl_nick", ""))
    if not name:
        name = "Player %d" % (len(players_of(room["id"])) + 1)

    if account:
        existing = one("SELECT * FROM jl_players WHERE room_id=? AND account=?", (room["id"], account))
        if existing:
            return existing

    token = secrets.token_hex(6)
    while one("SELECT id FROM jl_players WHERE token=?", (token,)):
        token = secrets.token_hex(6)
    run("INSERT INTO jl_players(room_id, token, name, account, joined) VALUES(?,?,?,?,?)",
        (room["id"], token, name, account, now()))
    return one("SELECT * FROM jl_players WHERE token=?", (token,))


@bp.route("/join/<code>", methods=["GET", "POST"])
def join(code):
    room = room_by_code(code)
    if not room:
        abort(404)
    if room["solo"]:
        # A solo round belongs to the player who started it.
        return redirect(url_for("jumbled.setup"))
    full = len(players_of(room["id"])) >= MAX_PLAYERS
    known = player_by_token(room["id"], request.cookies.get("jl_p_%s" % room["code"], ""))
    if known:
        # This device already joined, so a revisit goes straight back to the round.
        return redirect(url_for("jumbled.room", code=room["code"], p=known["token"]))
    if request.method == "POST":
        me = join_player(room, request.form.get("nickname"))
        if me is None:
            return redirect(url_for("jumbled.join", code=room["code"], full=1))
        response = redirect(url_for("jumbled.room", code=room["code"], p=me["token"]))
        keep_player(response, room["code"], me["token"])
        response.set_cookie("jl_nick", me["name"], max_age=90 * 86400, path="/")
        return response
    return render_template("jl_join.html", room=room, full=full, account=signed_in(),
                           wanted=bool(request.args.get("full")))


@bp.route("/room/<code>")
def room(code):
    room_row = room_by_code(code)
    if not room_row:
        abort(404)
    token = request.args.get("p") or request.cookies.get("jl_p_%s" % code, "")
    me = player_by_token(room_row["id"], token)
    if not me:
        return redirect(url_for("jumbled.join", code=code))
    return render_template("jl_room.html", room=room_row, me=me)


def my_history(room, player, stage):
    """What this player already scored on the word being answered."""
    rows = many("SELECT given, points FROM jl_answers WHERE room_id=? AND player_id=? AND stage=?",
                (room["id"], player["id"], stage))
    solved = any(r["points"] == W.TARGET_POINTS for r in rows)
    valid = {r["given"].lower() for r in rows if 0 < r["points"] < W.TARGET_POINTS}
    return solved, valid, len(valid)


def is_cleared(room, index):
    """True when somebody earned this jumble rather than running out its clock."""
    row = one("SELECT 1 AS ok FROM jl_answers WHERE room_id=? AND stage=? GROUP BY player_id"
              " HAVING SUM(CASE WHEN points=? THEN 1 ELSE 0 END) >= 1"
              " AND SUM(CASE WHEN points>0 AND points<? THEN 1 ELSE 0 END) >= ? LIMIT 1",
              (room["id"], index, W.TARGET_POINTS, W.TARGET_POINTS, W.MIN_VALID_TO_PASS))
    return bool(row)


def reveal_of(room, index):
    """A finished word: what it was and who answered it first."""
    past = words_of(room)[index]
    first = one("SELECT p.name FROM jl_answers a JOIN jl_players p ON p.id=a.player_id"
                " WHERE a.room_id=? AND a.stage=? AND a.points=? ORDER BY a.id LIMIT 1",
                (room["id"], index, W.TARGET_POINTS))
    return {"jumble": past["jumble"], "word": past["word"], "index": index + 1,
            "cleared": is_cleared(room, index),
            "first": first["name"] if first else None}


def state_json(room, me):
    room = advance(room)
    stage, word = current_stage(room)
    tied = json.loads(room["tied"] or "[]")
    running = room["status"] in ("playing", "clincher")

    out = {"code": room["code"], "status": room["status"], "grade": room["grade"],
           "subject": room["subject"], "quarter": room["quarter"], "topic": room["topic"],
           "total": total_of(room), "solo": bool(room["solo"]),
           "word_seconds": WORD_SECONDS, "host": room["host"] == me["token"],
           "tied": tied,
           "me": {"token": me["token"], "name": me["name"], "score": me["score"]},
           "players": [{"name": p["name"], "score": p["score"], "you": p["token"] == me["token"]}
                       for p in players_of(room["id"])],
           "scores": [{"name": r["name"], "score": r["score"], "clincher": r["clincher"],
                       "you": r["token"] == me["token"]} for r in standings(room)],
           "join_url": url_for("jumbled.join", code=room["code"], _external=True)}

    if running:
        out["seconds_left"] = seconds_left(room["clincher_deadline"] if stage == -1 else room["deadline"])
        if word:
            out["word"] = {"jumble": word["jumble"], "length": len(word["word"]),
                           "number": stage + 1 if stage >= 0 else None,
                           "clincher": stage == -1,
                           "may_answer": stage != -1 or me["token"] in tied}
            if stage >= 0:
                solved, valid, bonus = my_history(room, me, stage)
                out["progress"] = {"solved": solved, "bonus": bonus,
                                   "need": W.MIN_VALID_TO_PASS}
        if room["idx"] > 0 or stage == -1:
            out["revealed"] = reveal_of(room, max(0, room["idx"] - 1))
    if room["status"] == "done":
        out["words"] = [reveal_of(room, i) for i in range(total_of(room))]
        out["clincher_word"] = json.loads(room["clincher"] or "{}")
        out["tied"] = tied
    return out


@bp.route("/api/state/<code>")
def api_state(code):
    room = room_by_code(code)
    if not room:
        return jsonify(error="no room"), 404
    me = player_by_token(room["id"], request.args.get("p", ""))
    if not me:
        return jsonify(error="join again"), 401
    return jsonify(state_json(room, me))


@bp.route("/api/start/<code>", methods=["POST"])
def api_start(code):
    room = room_by_code(code)
    if not room:
        return jsonify(error="no room"), 404
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me or room["host"] != me["token"]:
        return jsonify(error="only the host starts"), 403
    if room["status"] != "lobby":
        return jsonify(ok=True, status=room["status"])
    run("UPDATE jl_rooms SET status='playing', idx=0, deadline=? WHERE id=?",
        (soon(WORD_SECONDS), room["id"]))
    return jsonify(ok=True, status="playing")


@bp.route("/api/answer/<code>", methods=["POST"])
def api_answer(code):
    room = room_by_code(code)
    if not room:
        return jsonify(error="no room"), 404
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me:
        return jsonify(error="join again"), 401
    room = advance(room)
    if room["status"] not in ("playing", "clincher"):
        return jsonify(points=0, reason="The round is not running."), 409
    if room["status"] == "clincher" and me["token"] not in json.loads(room["tied"] or "[]"):
        return jsonify(points=0, reason="Only the tied players answer the clincher."), 409

    stage, word = current_stage(room)
    left = seconds_left(room["clincher_deadline"] if stage == -1 else room["deadline"])
    if not word or left <= 0:
        return jsonify(points=0, reason="That word is finished."), 409

    given = W.normal(request.values.get("given", ""))
    solved, valid, bonus = my_history(room, me, stage)
    verdict = W.check(given, word["word"], valid, solved, bonus)
    if verdict["points"]:
        run("INSERT INTO jl_answers(room_id, player_id, stage, given, points, at) VALUES(?,?,?,?,?,?)",
            (room["id"], me["id"], stage, given, verdict["points"], now()))
        run("UPDATE jl_players SET score=score+? WHERE id=?", (verdict["points"], me["id"]))
    passed = pass_on(room, me, stage)
    room = room_by_code(room["code"])
    return jsonify(points=verdict["points"], kind=verdict["kind"], reason=verdict["reason"],
                   given=given, score=one("SELECT score FROM jl_players WHERE id=?", (me["id"],))["score"],
                   passed=passed,
                   seconds_left=seconds_left(room["deadline"]) if room["status"] == "playing" else 0)


@bp.route("/result/<code>")
def result(code):
    """The A4 sheet a single player hands the teacher: one page, their own name on it."""
    room = room_by_code(code)
    if not room:
        abort(404)
    if not room["solo"]:
        # A room round belongs on its own board, not on a sheet.
        return redirect(url_for("jumbled.room", code=code))
    me = player_by_token(room["id"], request.args.get("p", ""))
    if not me:
        return redirect(url_for("jumbled.setup"))

    mine = {}
    for row in many("SELECT stage, given, points FROM jl_answers WHERE room_id=? AND player_id=?"
                    " ORDER BY id", (room["id"], me["id"])):
        mine.setdefault(row["stage"], []).append(row)

    lines = []
    for index, past in enumerate(words_of(room)):
        rows = mine.get(index, [])
        lines.append({
            "number": index + 1,
            "jumble": past["jumble"],
            "word": past["word"],
            "solved": any(r["points"] == W.TARGET_POINTS for r in rows),
            "bonus": [r["given"] for r in rows if 0 < r["points"] < W.TARGET_POINTS],
        })

    sheet = {
        "name": me["name"],
        "room": room["code"],
        "path": [room["grade"], room["subject"], room["quarter"], room["topic"]],
        "score": me["score"],
        "solved": sum(1 for line in lines if line["solved"]),
        "bonus": sum(len(line["bonus"]) for line in lines),
        "total": total_of(room),
        "target_points": W.TARGET_POINTS,
        "valid_points": W.VALID_POINTS,
        "words": lines,
        "started": room["created"],
        "finished": room["finished"],
    }
    return render_template("jl_result.html", sheet=sheet, **ctx())


@bp.route("/scores")
def scores():
    rooms = many("SELECT * FROM jl_rooms WHERE status='done' ORDER BY id DESC LIMIT 60")
    rows = []
    for r in rooms:
        ranked = standings(r)
        # Names stay inside the room. This page is open to anyone with the link,
        # so it only reports how the round went, not who was in it.
        rows.append({"room": r, "top": ranked[0]["score"] if ranked else 0,
                     "players": len(ranked)})
    return render_template("jl_scores.html", rows=rows)


@bp.route("/manifest.webmanifest")
def manifest():
    root = url_for("jumbled.setup")
    doc = {"name": "Jumbled Letters - MNHS Review Center", "short_name": "Jumbled Letters",
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
    """A navy tile with an amber J, drawn without Pillow."""
    if size in _icons:
        return _icons[size]
    import struct
    import zlib

    navy, amber = (20, 33, 61), (252, 163, 17)
    rows = []
    bars = [(0.34, 0.66, 0.26, 0.33), (0.54, 0.63, 0.26, 0.70),
            (0.36, 0.63, 0.63, 0.72), (0.36, 0.45, 0.54, 0.72)]

    def inside(x, y):
        return any(b[0] <= x < b[1] and b[2] <= y < b[3] for b in bars)

    for y in range(size):
        row = bytearray()
        fy = y / size
        for x in range(size):
            fx = x / size
            if 0.08 <= fx < 0.92 and 0.08 <= fy < 0.92:
                pixel = navy if inside(fx, fy) else amber
            else:
                pixel = navy
            row += bytes(pixel) + b"\xff"
        rows.append(b"\x00" + bytes(row))

    raw = zlib.compress(b"".join(rows), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def send_static(name):
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE, "static"), name)


def use_database(path):
    """Share another app's SQLite file instead of jumbled.db."""
    global DB
    DB = path
    init_db()


def mount(host_app, url_prefix="/games/jumbled", db_path=None):
    """Attach Jumbled Letters to a host Flask app, optionally inside its database."""
    use_database(db_path) if db_path else init_db()
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse
    import threading
    import webbrowser

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run Jumbled Letters on this computer.")
    ap.add_argument("port", nargs="?", type=int, default=8030)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = Flask(__name__)
    host.config["TEMPLATES_AUTO_RELOAD"] = True
    mount(host, url_prefix="")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/" % args.port)).start()
    host.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
