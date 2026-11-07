"""Elemental Table Game: five rows of the periodic table with data missing.

Runs on its own (`python app.py 8040`) or mounted inside the Review Center at
/games/elemental-table, where it uses the signed-in student and the shared
quiz_app.db.

The app deals a table of five elements and nine columns - Element, Symbol, Mass
Number, Proton Number, Neutron Number, Electron Count, Valence Electron, Period
and Group - and empties five cells in every row, so the table is worth 25 points.
An empty cell is only ever left empty when the laws of the atom and the clues
still standing in that row pin the element down to one answer; that check is the
same candidate elimination a student does on paper, so nobody is asked for a
fact the table cannot give them.
"""
import io
import json
import os
import random
import re
import secrets
import sqlite3
from datetime import datetime
from itertools import combinations

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, send_file, url_for)

import etg_pdf

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "etable.db")

ROWS = 5                        # five elements at a time
BLANKS = 5                      # five cells emptied in every row
MAX_POINTS = ROWS * BLANKS      # ... which is the 25 points on the table
COLUMNS = ('name', 'symbol', 'mass', 'proton', 'neutron',
           'electron', 'valence', 'period', 'group')
HEADS = {'name': 'Element', 'symbol': 'Symbol', 'mass': 'Mass Number',
         'proton': 'Proton Number', 'neutron': 'Neutron Number',
         'electron': 'Electron Count', 'valence': 'Valence Electron',
         'period': 'Period', 'group': 'Group'}
NUMBERS = ('mass', 'proton', 'neutron', 'electron', 'valence', 'period', 'group')

# Only the main groups are dealt: there, the group tells the valence count and
# the period tells the shells, so every empty cell really is solvable.
MAIN_GROUPS = (1, 2, 13, 14, 15, 16, 17, 18)
MAIN_PERIODS = (1, 2, 3, 4)

# One person, two spellings - both are accepted in the Element column.
NAME_SPELLINGS = {'sulphur': 'sulfur', 'aluminum': 'aluminium'}

# Set by the Review Center: a callable returning the signed-in student.
identity = None
# Set by the Review Center: a callable saying whether the signer is staff.
# With no hook (standalone use) the machine belongs to the teacher, so staff
# pages stay open.
is_admin = None

bp = Blueprint("etg", __name__, template_folder="templates", static_folder="static")
_pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS etg_games(
    id       INTEGER PRIMARY KEY,
    token    TEXT NOT NULL UNIQUE,
    student  TEXT NOT NULL DEFAULT '',
    grade    TEXT NOT NULL DEFAULT '',
    section  TEXT NOT NULL DEFAULT '',
    account  TEXT NOT NULL DEFAULT '',
    grid     TEXT NOT NULL,
    answers  TEXT NOT NULL DEFAULT '[]',
    score    INTEGER NOT NULL DEFAULT 0,
    total    INTEGER NOT NULL DEFAULT 25,
    checked  INTEGER NOT NULL DEFAULT 0,
    created  TEXT NOT NULL,
    finished TEXT
);
CREATE TABLE IF NOT EXISTS etg_sheets(
    id      INTEGER PRIMARY KEY,
    token   TEXT NOT NULL UNIQUE,
    grid    TEXT NOT NULL,
    created TEXT NOT NULL
);
"""


# ----------------------------------------------------------------- database
def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def use_database(path):
    """Share another app's SQLite file instead of etable.db."""
    global DB, _pool
    DB = path
    init_db()
    _pool = None


# ------------------------------------------------------------- element pool
def valence_of(group, period):
    """The main-group rule: group 1 and 2 give their own count, 13-18 give ten less."""
    if group == 18:
        return 2 if period == 1 else 8
    return group if group < 13 else group - 10


def read_elements(path):
    if not path or not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return []
    try:
        return conn.execute(
            "SELECT z, symbol, name, mass, group_no, period FROM elements").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def load_pool():
    """Every element this game may deal, taken from the periodic table already stored.

    ELEMENTALS seeds the `elements` table into the shared database, so a mounted
    game reads the very same 118 rows the tiles use. Running on its own, it reads
    ELEMENTALS/elements.db beside this folder instead.
    """
    rows = read_elements(DB) or read_elements(
        os.path.join(os.path.dirname(BASE), "ELEMENTALS", "elements.db"))
    pool = []
    for z, symbol, name, mass, group, period in rows:
        group, period, z = int(group), int(period), int(z)
        if group not in MAIN_GROUPS or period not in MAIN_PERIODS:
            continue
        number = int(round(float(mass)))          # mass number = rounded atomic mass
        neutron = number - z
        if neutron < 0:
            continue
        pool.append({'z': z, 'symbol': str(symbol), 'name': str(name),
                     'mass': number, 'proton': z, 'neutron': neutron, 'electron': z,
                     'valence': valence_of(group, period), 'period': period,
                     'group': group})
    return sorted(pool, key=lambda e: e['z'])


def pool():
    global _pool
    if _pool is None:
        _pool = load_pool()
    return _pool


def by_z(z):
    for element in pool():
        if element['z'] == int(z):
            return element
    return None


def cell_value(element, column):
    """The value a column holds, in the shape the game compares and grades."""
    value = element[column]
    return str(value).strip().lower() if column in ('name', 'symbol') else int(value)


def cell_text(element, column):
    """The same value as it is printed in a cell that is already filled in."""
    value = element[column]
    return str(int(value)) if column in NUMBERS else str(value)


def spell(name):
    return NAME_SPELLINGS.get(str(name).strip().lower(), str(name).strip().lower())


# ------------------------------------------------------ dealing a solvable row
def possible(known):
    """The elements still standing after every clue in the row is applied.

    This is the deduction a student makes with the periodic table in front of
    them, so a row with exactly one element left is a row with one answer.
    """
    return [e for e in pool()
            if all(cell_value(e, column) == value for column, value in known.items())]


def solvable(element, blanks):
    known = {c: cell_value(element, c) for c in COLUMNS if c not in blanks}
    return len(possible(known)) == 1


def deal_row(element, rng):
    """Five of the nine cells emptied, chosen so the other four still give the answers."""
    patterns = [combo for combo in combinations(COLUMNS, BLANKS) if solvable(element, combo)]
    if not patterns:
        return list(COLUMNS[:BLANKS])
    return list(rng.choice(patterns))


def deal_grid(rng):
    picked = rng.sample(pool(), ROWS)
    return [{'z': e['z'], 'blanks': deal_row(e, rng)} for e in picked]


def grid_values(grid):
    """The dealt table with every cell worked out, ready to send to the browser."""
    rows = []
    for row in grid:
        element = by_z(row['z'])
        rows.append({
            'element': element['name'],
            'symbol': element['symbol'],
            'blanks': list(row['blanks']),
            'given': {c: cell_text(element, c) for c in COLUMNS if c not in row['blanks']},
            'truth': {c: cell_text(element, c) for c in COLUMNS},
        })
    return rows


# ------------------------------------------------------------------- grading
def group_number(raw):
    """Groups 8A, 8 and 18 name the same family, and the old 3A-7A counts are
    today's 13-17, so a typed group lands on the IUPAC number."""
    match = re.fullmatch(r'(\d{1,2})\s*[Aa]?', raw)
    if not match:
        return None
    number = int(match.group(1))
    if number in (1, 2) or 13 <= number <= 18:
        return number
    if 3 <= number <= 8:
        return number + 10
    return None


def canonical(column, text):
    """What the student typed, in the shape it is compared in, or None when unusable."""
    raw = str(text or '').strip()
    if not raw:
        return None
    if column == 'name':
        return spell(raw)
    if column == 'symbol':
        return raw.lower()
    if column == 'group':
        return group_number(raw)
    if re.fullmatch(r'\d+', raw):
        return int(raw)
    return None


def grade(column, text):
    return canonical(column, text)


# ---------------------------------------------------------------------- pages
@bp.context_processor
def ctx():
    return {'back_url': current_app.config.get('ETABLE_BACK_URL'),
            'tiles_url': current_app.config.get('ETABLE_TILES_URL'),
            'heads': HEADS, 'columns': COLUMNS, 'max_points': MAX_POINTS,
            'rows': ROWS, 'blanks': BLANKS,
            'staff_allowed': admin_allowed()}


def admin_allowed():
    """Standalone use is the teacher on their own machine, so it is allowed."""
    if is_admin is None:
        return True
    return bool(is_admin())


def signed_in():
    """The student already known to the app, so nobody types their name twice."""
    member = identity() if identity else None
    if not member:
        return {'name': '', 'grade': '', 'section': '', 'account': ''}
    return {'name': member.get('name') or '', 'grade': member.get('grade') or '',
            'section': member.get('section') or '', 'account': member.get('account') or ''}


def student_name(game):
    label = str(game['student'] or '').strip()
    if label:
        return label
    return str(game['account'] or '').split('@')[0] or 'Guest'


@bp.route("/")
def index():
    member = signed_in()
    return render_template('etg_index.html', student=member,
                           count=len(pool()),
                           periods=', '.join(str(p) for p in MAIN_PERIODS),
                           groups=', '.join(str(g) for g in MAIN_GROUPS))


@bp.route("/deal", methods=["POST"])
def deal():
    member = signed_in()
    name = (request.form.get('name') or '').strip()[:120] or member['name'] or 'Guest'
    grid = deal_grid(random.Random())
    token = secrets.token_urlsafe(12)
    conn = connect()
    conn.execute(
        "INSERT INTO etg_games(token, student, grade, section, account, grid, total, created)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (token, name, member['grade'], member['section'], member['account'],
         json.dumps(grid), MAX_POINTS, datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    conn.close()
    return redirect(url_for('etg.play', token=token))


def fetch_game(token):
    conn = connect()
    row = conn.execute("SELECT * FROM etg_games WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


@bp.route("/play/<token>")
def play(token):
    game = fetch_game(token)
    if not game:
        abort(404)
    grid = json.loads(game['grid'])
    return render_template('etg_play.html', game=game, token=token,
                           table=grid_values(grid), student=student_name(game),
                           answers=json.loads(game['answers'] or '[]'),
                           saved_score=game['score'], checked=bool(game['checked']))


@bp.route("/api/check/<token>", methods=["POST"])
def check(token):
    game = fetch_game(token)
    if not game:
        return jsonify({'error': 'gone'}), 404
    grid = json.loads(game['grid'])
    typed = (request.get_json(silent=True) or {}).get('cells') or {}

    marks, score = [], 0
    for index, row in enumerate(grid):
        element = by_z(row['z'])
        for column in row['blanks']:
            given = typed.get('%d:%s' % (index, column))
            ok = grade(column, given) is not None and \
                grade(column, given) == cell_value(element, column)
            if ok:
                score += 1
            marks.append({'r': index, 'col': column, 'given': str(given or '').strip(),
                          'truth': cell_text(element, column), 'ok': 1 if ok else 0})

    conn = connect()
    conn.execute(
        "UPDATE etg_games SET answers = ?, score = ?, checked = 1,"
        " finished = ? WHERE token = ?",
        (json.dumps(marks), score, datetime.now().isoformat(timespec='seconds'), token))
    conn.commit()
    conn.close()
    return jsonify({'score': score, 'total': MAX_POINTS, 'marks': marks,
                    'table': grid_values(grid)})


# ---------------------------------------------------------- staff worksheet
@bp.route("/worksheet")
def worksheet():
    if not admin_allowed():
        return render_template('etg_closed.html'), 403
    return render_template('etg_worksheet.html', token=None, table=None)


@bp.route("/worksheet/new", methods=["POST"])
def worksheet_new():
    if not admin_allowed():
        return render_template('etg_closed.html'), 403
    grid = deal_grid(random.Random())
    token = secrets.token_urlsafe(12)
    conn = connect()
    conn.execute("INSERT INTO etg_sheets(token, grid, created) VALUES(?,?,?)",
                 (token, json.dumps(grid),
                  datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    conn.close()
    return redirect(url_for('etg.worksheet_sheet', token=token))


def fetch_sheet(token):
    conn = connect()
    row = conn.execute("SELECT * FROM etg_sheets WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


@bp.route("/worksheet/<token>")
def worksheet_sheet(token):
    if not admin_allowed():
        return render_template('etg_closed.html'), 403
    sheet = fetch_sheet(token)
    if not sheet:
        abort(404)
    return render_template('etg_worksheet.html', token=token,
                           table=grid_values(json.loads(sheet['grid'])),
                           answers=request.args.get('answers') == '1')


@bp.route("/worksheet/<token>/worksheet.pdf")
def worksheet_pdf(token):
    sheet = _sheet_or_denied(token)
    if isinstance(sheet, tuple):
        return sheet
    table = grid_values(json.loads(sheet['grid']))
    return _send_pdf(etg_pdf.worksheet_pdf(table, HEADS, COLUMNS, MAX_POINTS),
                     "ElementalTable_Worksheet.pdf")


@bp.route("/worksheet/<token>/answer-key.pdf")
def worksheet_key_pdf(token):
    sheet = _sheet_or_denied(token)
    if isinstance(sheet, tuple):
        return sheet
    table = grid_values(json.loads(sheet['grid']))
    return _send_pdf(etg_pdf.answer_key_pdf(table, HEADS, COLUMNS, MAX_POINTS),
                     "ElementalTable_AnswerKey.pdf")


def _sheet_or_denied(token):
    if not admin_allowed():
        return render_template('etg_closed.html'), 403
    sheet = fetch_sheet(token)
    if not sheet:
        abort(404)
    return sheet


def _send_pdf(data, name):
    return send_file(io.BytesIO(data), mimetype='application/pdf',
                     as_attachment=True, download_name=name)


def mount(host_app, url_prefix="/games/elemental-table", db_path=None):
    """Attach Elemental Table Game to a host Flask app, optionally inside its database."""
    global _pool
    use_database(db_path) if db_path else init_db()
    _pool = None                       # the new file holds the periodic table to deal from
    host_app.register_blueprint(bp, url_prefix=url_prefix)


if __name__ == "__main__":
    import argparse
    import threading
    import webbrowser

    from flask import Flask

    ap = argparse.ArgumentParser(description="Run Elemental Table Game on this computer.")
    ap.add_argument("port", nargs="?", type=int, default=8040)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = Flask(__name__)
    host.config["TEMPLATES_AUTO_RELOAD"] = True
    mount(host, url_prefix="")

    if args.lan:
        print("Class devices on the same wifi:  http://localhost:%d" % args.port)
    print("Elemental Table Game is running at http://localhost:%d/  (Ctrl+C to stop)" % args.port)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/" % args.port)).start()
    host.run(host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, debug=False)
