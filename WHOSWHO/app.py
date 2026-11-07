"""Who's Who: the picture-and-clues game for the Review Center.

The admin writes an activity with a form (title, and for every person a picture,
the name and three clues). Pictures go to Google Drive in the MNHSREVIEWCENTER
folder, the activity itself is saved in whoswho.json in the root folder, and the
pages simply render that JSON.

A round scores 5 points and each revealed clue costs one:

    answer with no clue shown    5
    Reveal Clue 1, then answer   4
    Reveal Clue 2, then answer   3
    Reveal Clue 3, then answer   2      (a 10 second count then starts)
    not answered in time         1

The free clue is always the letters of the name, shuffled.

Runs on its own (`python app.py 8040`) or mounted inside the Review Center at
/games/whoswho, sharing quiz_app.db and the signed-in account.
"""
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

import ww_data as D
import ww_drive as drive

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "whoswho.db")

MAX_PLAYERS = 45
CLUE_COST = 1              # each revealed clue takes one point off the item
START_POINTS = 5           # a name given with no clue shown
MISS_POINTS = 1            # the item is over and nobody got it
CLINCH_SECONDS = 10        # the count down after the third clue
PODIUM = ["Champion", "First Place", "Second Place"]
MAX_UPLOAD = 8 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS ww_rooms(
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'lobby',
    idx INTEGER NOT NULL DEFAULT 0,
    host TEXT NOT NULL DEFAULT '',
    solo INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    finished TEXT
);
CREATE TABLE IF NOT EXISTS ww_players(
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES ww_rooms(id),
    token TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    joined TEXT NOT NULL,
    reveals INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    deadline TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ww_answers(
    id INTEGER PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES ww_rooms(id),
    player_id INTEGER NOT NULL REFERENCES ww_players(id),
    stage INTEGER NOT NULL,
    given TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
"""

bp = Blueprint("whoswho", __name__, template_folder="templates", static_folder="static")

# Set by the Review Center: a callable returning the signed-in student, and a
# callable saying whether that student may write activities.
identity = None
is_admin = None

_lock = threading.Lock()


# ----------------------------------------------------------------- database
def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    conn.close()


_thread = threading.local()


def db():
    conn = getattr(_thread, "conn", None)
    if conn is None:
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


def letters_of(name):
    return [ch for ch in re.sub(r"[^A-Za-z]", "", (name or "").upper())]


def jumble(name, seed="", tries=12):
    """The free clue: the letters of the name, shuffled out of order.

    A seed keeps one arrangement for a whole turn - the board is re-read every
    second and the player must be able to finish typing over steady letters.
    """
    letters = letters_of(name)
    if len(letters) < 2:
        return "".join(letters)
    pick = random.Random(seed) if seed else random
    order = "".join(letters)
    for _ in range(tries):
        shuffled = letters[:]
        pick.shuffle(shuffled)
        text = "".join(shuffled)
        if text != order:
            return text
    return order[::-1]


def normal(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace(".", " ")).strip()


def same_name(given, want):
    """The name counts however it is spaced or punctuated, but it must be whole.

    An initial stands in for the middle name, so "Jose Rizal" matches
    "Jose P. Rizal" - the picture and the clues identify the person, not the
    spelling of a middle name nobody remembers.
    """
    a = [w for w in normal(given).split() if w]
    b = [w for w in normal(want).split() if w]
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < len(b):
        return False
    if len(a) > len(b):
        b, a = a, b
    for short, full in zip(a, b):
        if short == full:
            continue
        if len(short) == 1 and full.upper().startswith(short.upper()):
            continue
        return False
    return True


def item_points(reveals):
    return max(START_POINTS - reveals * CLUE_COST, 2)


# ------------------------------------------------------------------- rooms
def new_code():
    while True:
        code = secrets.token_hex(3).upper()
        if not one("SELECT id FROM ww_rooms WHERE code=?", (code,)):
            return code


def room_by_code(code):
    return one("SELECT * FROM ww_rooms WHERE code=?", ((code or "").strip().upper(),))


def players_of(room_id):
    return many("SELECT * FROM ww_players WHERE room_id=? ORDER BY id", (room_id,))


def player_by_token(room_id, token):
    return one("SELECT * FROM ww_players WHERE room_id=? AND token=?",
               (room_id, (token or "").strip()))


def item_count(room):
    activity = D.get(room["slug"])
    return len(activity["persons"]) if activity else 0


def current_person(room):
    activity = D.get(room["slug"])
    if not activity or room["idx"] >= len(activity["persons"]):
        return None
    return activity["persons"][room["idx"]]


def standings(room_id):
    rows = [dict(p) for p in players_of(room_id)]
    hits = {r["player_id"]: r["first_at"] for r in many(
        "SELECT player_id, MIN(at) first_at FROM ww_answers"
        " WHERE room_id=? AND points>1 GROUP BY player_id", (room_id,))}
    for row in rows:
        row["first_hit"] = hits.get(row["id"]) or row["joined"]
    rows.sort(key=lambda r: (-r["score"], r["first_hit"], r["joined"]))
    return rows


def keep_player(response, code, token):
    response.set_cookie("ww_p_%s" % code, token, max_age=7 * 86400, path="/")


def join_player(room, nickname=None):
    if len(players_of(room["id"])) >= MAX_PLAYERS:
        return None
    who = signed_in()
    account = who["account"] if who else ""
    name = ""
    if who:
        name = re.sub(r"\s+", " ", who["name"]).strip()[:30]
    else:
        name = re.sub(r"\s+", " ", str(nickname or "")).strip()[:30] \
             or re.sub(r"\s+", " ", request.cookies.get("ww_nick", "")).strip()[:30]
    if not name:
        name = "Player %d" % (len(players_of(room["id"])) + 1)

    if account:
        existing = one("SELECT * FROM ww_players WHERE room_id=? AND account=?", (room["id"], account))
        if existing:
            return existing
    token = secrets.token_hex(6)
    while one("SELECT id FROM ww_players WHERE token=?", (token,)):
        token = secrets.token_hex(6)
    run("INSERT INTO ww_players(room_id, token, name, account, joined) VALUES(?,?,?,?,?)",
        (room["id"], token, name, account, now()))
    return one("SELECT * FROM ww_players WHERE token=?", (token,))


def start_round(room, me):
    """Reset every seat for a new pass, then show the first person."""
    run("UPDATE ww_players SET score=0, reveals=0, locked=0, deadline='' WHERE room_id=?",
        (room["id"],))
    run("UPDATE ww_rooms SET status='playing', idx=0 WHERE id=?", (room["id"],))
    return room_by_code(room["code"])


def advance(room):
    """Close items whose 10 second count has run out. Called from every poll.

    Nobody waits on a background timer: a poll that arrives after a deadline
    simply settles what has already expired, which is what a shared host such as
    PythonAnywhere allows.
    """
    with _lock:
        room = room_by_code(room["code"])
        if room["status"] != "playing":
            return room
        seats = players_of(room["id"])
        settled = False
        for p in seats:
            if p["locked"] or p["reveals"] < 3 or not p["deadline"]:
                continue
            if seconds_left(p["deadline"]) == 0:
                score(p, room, "", MISS_POINTS, "missed")
                settled = True
        if settled:
            room = room_by_code(room["code"])
            seats = players_of(room["id"])

        # A round only moves on when every seat has been settled, so one player
        # cannot drag the rest of the room away from a person they are close to.
        playing = [p for p in seats if not p["locked"]]
        if room["solo"]:
            if playing == []:
                room = next_item(room)
        elif seats and not playing:
            room = next_item(room)
        return room


def next_item(room):
    """Move to the next person, or finish the round when the list is done."""
    total = item_count(room)
    nxt = room["idx"] + 1
    if nxt >= total:
        run("UPDATE ww_rooms SET status='done', finished=? WHERE id=?", (now(), room["id"]))
        run("UPDATE ww_players SET reveals=0, locked=0, deadline='' WHERE room_id=?", (room["id"],))
        return room_by_code(room["code"])
    run("UPDATE ww_rooms SET idx=? WHERE id=?", (nxt, room["id"]))
    run("UPDATE ww_players SET reveals=0, locked=0, deadline='' WHERE room_id=?", (room["id"],))
    return room_by_code(room["code"])


def score(player, room, given, points, kind):
    run("INSERT INTO ww_answers(room_id, player_id, stage, given, points, at) VALUES(?,?,?,?,?,?)",
        (room["id"], player["id"], room["idx"], given, points, now()))
    run("UPDATE ww_players SET score=score+?, locked=1, deadline='' WHERE id=?",
        (points, player["id"]))


# -------------------------------------------------------------------- photo
def photo_for(person):
    """Local copy first, then Google Drive, and the Drive copy is kept locally."""
    if not person:
        return None
    stored = person.get("photo") or {}
    name = stored.get("file")
    if name and os.path.exists(D.photo_path(name)):
        return D.photo_path(name)
    drive_id = stored.get("drive_id")
    if not drive_id:
        return None
    raw = drive.download(drive_id)
    if not raw:
        return None
    kept = D.save_photo(raw, "image/jpeg", name)
    return D.photo_path(kept) if kept else None


# ------------------------------------------------------------------- routes
@bp.context_processor
def ctx():
    return {"back_url": current_app.config.get("WHOSWHO_BACK_URL"),
            "game_name": "Who's Who", "admin_ok": admin_allowed(),
            "start_points": START_POINTS, "clue_seconds": CLINCH_SECONDS,
            "max_players": MAX_PLAYERS}


@bp.route("/")
def index():
    return render_template("ww_index.html", rows=D.activities(),
                           drive_ok=drive.configured())


@bp.route("/a/<slug>")
def activity(slug):
    row = D.get(slug)
    if not row:
        abort(404)
    return render_template("ww_activity.html", act=row, drive_ok=drive.configured())


@bp.route("/photo/<slug>/<person_id>")
def photo(slug, person_id):
    row = D.get(slug)
    if not row:
        abort(404)
    person = next((p for p in row["persons"] if p["id"] == person_id), None)
    path = photo_for(person)
    if not path:
        return Response(app_icon(320), mimetype="image/png")
    return send_file(path, max_age=86400)


# ---------------------------------------------------------------- admin form
@bp.route("/new", methods=["GET", "POST"])
@bp.route("/edit/<slug>", methods=["GET", "POST"])
def write(slug=None):
    if not admin_allowed():
        return render_template("ww_closed.html"), 403
    existing = D.get(slug) if slug else None
    if request.method == "POST":
        return save_activity(existing)

    rows = ([{"id": p["id"], "name": p["name"], "clues": p["clues"], "photo": p["photo"],
              "preview": url_for("whoswho.photo", slug=existing["slug"], person_id=p["id"])}
             for p in existing["persons"]] if existing else
            [{"id": "", "name": "", "clues": ["", "", ""], "photo": {}, "preview": ""}])
    return render_template("ww_write.html", act=existing, rows=rows,
                           drive_ok=drive.configured(), notice=request.args.get("notice"),
                           error=request.args.get("error"),
                           missing=request.args.get("missing") or "")


def save_activity(existing):
    """Write the posted form into whoswho.json, pictures to Drive and to disk."""
    title = re.sub(r"\s+", " ", request.form.get("title") or "").strip()[:90]
    if not title:
        return redirect(url_for("whoswho.write", slug=existing["slug"] if existing else None,
                                error="title"))

    slug = existing["slug"] if existing else D.slugify(title)
    while not existing and D.get(slug):
        slug = "%s-%s" % (D.slugify(title), secrets.token_hex(2))

    names = request.form.getlist("name")
    clues = [request.form.getlist("clue%d" % n) for n in (1, 2, 3)]
    ids = request.form.getlist("person_id")
    old = {p["id"]: p for p in (existing["persons"] if existing else [])}

    people = []
    for i, raw in enumerate(names):
        name = re.sub(r"\s+", " ", raw or "").strip()[:80]
        if not name:
            continue
        pid = (ids[i] if i < len(ids) else "").strip() or D.new_person_id()
        person = {"id": pid, "name": name,
                  "clues": [(clues[n][i] if i < len(clues[n]) else "").strip()
                            for n in range(3)],
                  "photo": dict(old[pid]["photo"]) if pid in old else {"drive_id": "", "file": ""}}

        # keep_photo is indexed per row: an unchecked box posts nothing.
        if request.form.get("keep_photo%d" % i) == "1":
            people.append(person)
            continue
        person["photo"] = {"drive_id": "", "file": ""}
        upload = request.files.get("photo%d" % i)
        if upload and (upload.mimetype or "").startswith("image/"):
            blob = upload.read(MAX_UPLOAD + 1)
            if len(blob) > MAX_UPLOAD:
                return redirect(url_for("whoswho.write", slug=existing["slug"] if existing else None,
                                        error="big"))
            fname = D.save_photo(blob, upload.mimetype)
            drive_id = drive.upload(blob, "%s - %s%s" % (slug, D.slugify(name), _ext(upload.mimetype)),
                                    upload.mimetype)
            person["photo"] = {"drive_id": drive_id, "file": fname}
        people.append(person)

    if not people:
        return redirect(url_for("whoswho.write", slug=existing["slug"] if existing else None,
                                error="persons"))
    # Every person needs a picture: it is the clue the whole round is built on.
    missing = [str(i + 1) for i, p in enumerate(people)
               if not (p["photo"]["file"] or p["photo"]["drive_id"])]
    if missing:
        return redirect(url_for("whoswho.write", slug=existing["slug"] if existing else None,
                                error="photo", missing=",".join(missing)))
    D.put({"slug": slug, "title": title,
           "created": existing["created"] if existing else None, "persons": people})
    return redirect(url_for("whoswho.activity", slug=slug, notice="saved"))


def _ext(mime):
    return {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(mime, ".jpg")


# -------------------------------------------------------------- playing one
@bp.route("/play/<slug>", methods=["POST"])
def play(slug):
    row = D.get(slug)
    if not row or not row["persons"]:
        abort(404)
    solo = bool(request.form.get("solo"))
    code = new_code()
    run("INSERT INTO ww_rooms(code, slug, status, created, solo) VALUES(?,?,?,?,?)",
        (code, slug, "playing" if solo else "lobby", now(), 1 if solo else 0))
    room = room_by_code(code)
    me = join_player(room, request.form.get("nickname"))
    run("UPDATE ww_rooms SET host=? WHERE id=?", (me["token"], room["id"]))
    response = redirect(url_for("whoswho.room", code=code, p=me["token"]))
    keep_player(response, code, me["token"])
    if not me["account"]:
        response.set_cookie("ww_nick", me["name"], max_age=90 * 86400, path="/")
    return response


@bp.route("/join/<code>", methods=["GET", "POST"])
def join(code):
    room = room_by_code(code)
    if not room or room["solo"]:
        return redirect(url_for("whoswho.index"))
    known = player_by_token(room["id"], request.cookies.get("ww_p_%s" % room["code"], ""))
    if known:
        return redirect(url_for("whoswho.room", code=room["code"], p=known["token"]))
    if request.method == "POST":
        me = join_player(room, request.form.get("nickname"))
        if me is None:
            return redirect(url_for("whoswho.join", code=room["code"], full=1))
        response = redirect(url_for("whoswho.room", code=room["code"], p=me["token"]))
        keep_player(response, room["code"], me["token"])
        response.set_cookie("ww_nick", me["name"], max_age=90 * 86400, path="/")
        return response
    return render_template("ww_join.html", room=room, act=D.get(room["slug"]),
                           full=len(players_of(room["id"])) >= MAX_PLAYERS,
                           account=signed_in(), wanted=bool(request.args.get("full")))


@bp.route("/room/<code>")
def room(code):
    row = room_by_code(code)
    if not row:
        abort(404)
    token = request.args.get("p") or request.cookies.get("ww_p_%s" % code, "")
    me = player_by_token(row["id"], token)
    if not me:
        return redirect(url_for("whoswho.join", code=code))
    return render_template("ww_room.html", room=row, me=me, act=D.get(row["slug"]))


def state_json(room, me):
    room = advance(room)
    me = player_by_token(room["id"], me["token"])
    act = D.get(room["slug"])
    person = current_person(room)
    total = item_count(room)

    out = {"code": room["code"], "status": room["status"], "title": act["title"] if act else "",
           "slug": room["slug"], "solo": bool(room["solo"]), "host": room["host"] == me["token"],
           "index": room["idx"], "total": total, "clue_seconds": CLINCH_SECONDS,
           "start_points": START_POINTS,
           "me": {"name": me["name"], "score": me["score"], "reveals": me["reveals"],
                  "locked": bool(me["locked"]),
                  "seconds_left": seconds_left(me["deadline"]) if me["reveals"] >= 3 else 0},
           "players": [{"name": p["name"], "score": p["score"], "you": p["token"] == me["token"],
                        "locked": bool(p["locked"])} for p in players_of(room["id"])],
           "scores": [{"name": r["name"], "score": r["score"], "you": r["token"] == me["token"]}
                      for r in standings(room["id"])],
           "join_url": url_for("whoswho.join", code=room["code"], _external=True)}

    if room["status"] == "playing" and person:
        out["person"] = {"jumble": jumble(person["name"],
                                          "%s-%s" % (room["code"], room["idx"])),
                         "length": len(letters_of(person["name"])),
                         "clues": person["clues"], "reveals": me["reveals"],
                         "photo": bool((person.get("photo") or {}).get("drive_id")
                                       or (person.get("photo") or {}).get("file")),
                         "photo_url": url_for("whoswho.photo", slug=room["slug"],
                                              person_id=person["id"]),
                         "locked": bool(me["locked"]),
                         "points_next": item_points(me["reveals"])}
    if room["status"] == "done":
        out["past"] = [{"name": p["name"], "clues": p["clues"],
                        "photo": bool((p.get("photo") or {}).get("drive_id")
                                      or (p.get("photo") or {}).get("file")),
                        "photo_url": url_for("whoswho.photo", slug=room["slug"],
                                             person_id=p["id"])}
                       for p in (act["persons"] if act else [])]
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


@bp.route("/api/reveal/<code>", methods=["POST"])
def api_reveal(code):
    room = advance(room_by_code(code))
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me or room["status"] != "playing":
        return jsonify(error="not running"), 409
    wanted = max(1, min(3, int(request.values.get("level", 1) or 1)))
    if wanted <= me["reveals"] or me["locked"]:
        return jsonify(ok=True, reveals=me["reveals"])
    deadline = soon(CLINCH_SECONDS) if wanted >= 3 else ""
    run("UPDATE ww_players SET reveals=?, deadline=? WHERE id=?", (wanted, deadline, me["id"]))
    fresh = player_by_token(room["id"], me["token"])
    return jsonify(ok=True, reveals=fresh["reveals"],
                   seconds_left=seconds_left(fresh["deadline"]),
                   points_next=item_points(fresh["reveals"]))


@bp.route("/api/answer/<code>", methods=["POST"])
def api_answer(code):
    room = advance(room_by_code(code))
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me or room["status"] != "playing":
        return jsonify(points=0, reason="The round is not running."), 409
    if me["locked"]:
        return jsonify(points=0, reason="This person is already done for you."), 409
    person = current_person(room)
    if not person:
        return jsonify(points=0, reason="Nothing to answer."), 409

    given = (request.values.get("given") or "").strip()[:120]
    if same_name(given, person["name"]):
        points = item_points(me["reveals"])
        score(me, room, given, points, "hit")
        if room["solo"]:
            room = next_item(room)
        return jsonify(points=points, kind="hit", given=given,
                       answer=person["name"],
                       score=player_by_token(room["id"], me["token"])["score"],
                       status=room["status"])

    wrong = one("SELECT COUNT(*) c FROM ww_answers WHERE room_id=? AND player_id=? AND stage=?"
                " AND points<=1", (room["id"], me["id"], room["idx"]))["c"]
    if wrong >= 3 and me["reveals"] < 3:
        run("UPDATE ww_players SET reveals=3, deadline=? WHERE id=?",
            (soon(CLINCH_SECONDS), me["id"]))
    return jsonify(points=0, kind="no", given=given, tries_left=max(0, 3 - wrong - 1),
                   reason="Not that person - check the spelling of the name.")


@bp.route("/api/next/<code>", methods=["POST"])
def api_next(code):
    room = room_by_code(code)
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me:
        return jsonify(error="join again"), 401
    if not room["solo"] and room["host"] != me["token"]:
        return jsonify(error="only the host moves on"), 403
    room = advance(room)
    if room["status"] != "playing":
        return jsonify(ok=True, status=room["status"])
    room = next_item(room)
    return jsonify(ok=True, status=room["status"], index=room["idx"])


@bp.route("/api/reserve/<code>", methods=["POST"])
def api_reserve(code):
    """Give the item up: it counts as not answered, so the round can move on."""
    room = advance(room_by_code(code))
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not me or room["status"] != "playing":
        return jsonify(error="not running"), 409
    score(me, room, "", MISS_POINTS, "missed")
    if room["solo"]:
        room = next_item(room)
    return jsonify(ok=True, score=player_by_token(room["id"], me["token"])["score"],
                   status=room["status"])


@bp.route("/api/start/<code>", methods=["POST"])
def api_start(code):
    room = room_by_code(code)
    me = player_by_token(room["id"], request.values.get("p", ""))
    if not room or not me:
        return jsonify(error="no room"), 404
    if room["host"] != me["token"]:
        return jsonify(error="only the host starts"), 403
    room = start_round(room, me)
    return jsonify(ok=True, status=room["status"])


@bp.route("/delete/<slug>", methods=["POST"])
def delete(slug):
    if not admin_allowed():
        return render_template("ww_closed.html"), 403
    D.remove(slug)
    return redirect(url_for("whoswho.index"))


@bp.route("/scores")
def scores():
    rooms = many("SELECT * FROM ww_rooms WHERE status='done' ORDER BY id DESC LIMIT 60")
    rows = []
    for r in rooms:
        act = D.get(r["slug"])
        ranked = standings(r["id"])
        rows.append({"room": r, "title": act["title"] if act else r["slug"],
                     # Names stay inside the room; this list is open to anyone.
                     "top": ranked[0]["score"] if ranked else 0, "players": len(ranked)})
    return render_template("ww_scores.html", rows=rows)


@bp.route("/manifest.webmanifest")
def manifest():
    root = url_for("whoswho.index")
    doc = {"name": "Who's Who - MNHS Review Center", "short_name": "Who's Who",
           "start_url": root, "scope": root, "display": "standalone",
           "background_color": "#eef3f8", "theme_color": "#14213d",
           "icons": [{"src": "%sicon/192" % root, "sizes": "192x192", "type": "image/png"},
                    {"src": "%sicon/512" % root, "sizes": "512x512", "type": "image/png"}]}
    return Response(json.dumps(doc), mimetype="application/manifest+json")


@bp.route("/sw.js")
def sw():
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE, "static"), "sw.js")


@bp.route("/icon/<int:size>")
def icon(size):
    return Response(app_icon(min(max(size, 64), 512)), mimetype="image/png")


_icons = {}


def app_icon(size):
    """A navy tile with an amber question mark, drawn without Pillow."""
    if size in _icons:
        return _icons[size]
    import struct
    import zlib

    navy, amber = (20, 33, 61), (252, 163, 17)
    bars = [(0.36, 0.64, 0.24, 0.33), (0.58, 0.68, 0.30, 0.52),
            (0.42, 0.60, 0.46, 0.58), (0.47, 0.56, 0.56, 0.66),
            (0.47, 0.56, 0.72, 0.80)]

    def inside(x, y):
        return any(b[0] <= x < b[1] and b[2] <= y < b[3] for b in bars)

    rows = []
    for y in range(size):
        row = bytearray()
        fy = y / size
        for x in range(size):
            fx = x / size
            if 0.06 <= fx < 0.94 and 0.06 <= fy < 0.94:
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


def use_database(path):
    global DB
    DB = path
    init_db()


def mount(host_app, url_prefix="/games/whoswho", db_path=None, data_path=None):
    """Attach Who's Who to a host Flask app, sharing its database and JSON file."""
    if data_path:
        D.DATA_PATH = data_path
    use_database(db_path) if db_path else init_db()
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse
    import webbrowser

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run Who's Who on this computer.")
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
