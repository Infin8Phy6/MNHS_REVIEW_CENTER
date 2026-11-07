import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, session, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = 'secret_quiz_key_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)

basedir = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(basedir, 'quiz_app.db')
ADMIN_DB_PATH = os.path.join(basedir, 'admin.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# A class answering at the same time is a burst of small writes. The default
# five-second wait turns into "database is locked" when the modem laptop is
# slower than the hosted server; half a minute outlasts the burst.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 30}}
# A resource upload is streamed straight to Drive; this only stops someone
# posting a hundred megabytes at the process. The ceiling itself is set in the
# PDF Studio section below (PDF_STUDIO_MAX_BYTES), and the materials form keeps
# its own tighter 20 MB check further down.
if basedir not in sys.path:
    sys.path.insert(0, basedir)
import drive_store  # noqa: E402  (needs basedir so it also works when started from elsewhere)
import mail_send  # noqa: E402

try:
    # PDF Studio's jobs, with no window attached: the staff page runs these on
    # the server. Missing libraries only close that page, never the whole app.
    import pdf_tools as PDF_STUDIO  # noqa: E402
    PDF_STUDIO_READY = True
except Exception as studio_error:  # pragma: no cover - depends on the host's packages
    PDF_STUDIO = None
    PDF_STUDIO_READY = False
    app.logger.warning('PDF Studio is disabled: %s', studio_error)

db = SQLAlchemy(app)

SUFFIX_CHOICES = ['N/A', 'Sr', 'Jr', 'I', 'II', 'III', 'IV', 'V']
# What the school ran on before grades and sections were kept in the database.
# These only fill the Grades & Sections page the first time the app starts with
# an empty registry; after that the main admin's list is the one everything
# reads, so a section can never grow a new spelling.
DEFAULT_GRADES = ['Grade 7', 'Grade 8', 'Grade 9', 'Grade 10']
DEFAULT_SECTIONS = {
    'Grade 8': ['ORION', 'MILKYWAY'],
    'Grade 10': ['CREST', 'PRIME', 'SOVEREIGN', 'VANGUARD'],
}
# The weekday boxes on the Classes page, in the order a week runs. A schedule
# saves these labels only, so a class list never grows a 'Mondays' spelling.
CLASS_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
# The parts of the Classes page that build the school's class list. The main
# admin owns these; an admin works below them, with the teachers they supervise.
REGISTRY_ACTIONS = ('add_grade', 'rename_grade', 'delete_grade', 'add_section',
                    'rename_section', 'delete_section', 'merge_section')
# Who signs in through /admin/login, and what each level may reach, is kept in
# admin.db - a small SQLite file beside quiz_app.db. It is built and seeded the
# first time the app runs without it (or after it is deleted), taking the wording
# from admin.json when that file lists a level. Edits made in admin.db take
# effect on the next request: no restart, and no second login to maintain.
DEFAULT_ADMIN_EMAIL = 'angelesedgardo17@gmail.com'
DEFAULT_ADMIN_PASSWORD = 'sired110492'
# Lowest to highest: a teacher, an admin, the owner.
ADMIN_LEVELS = ['teacher', 'admin', 'main_admin']
# What the Staff page may hand out. A second main_admin is written into admin.db
# by hand, so the page can never demote or remove a row it cannot show again.
HANDOUT_LEVELS = ['teacher', 'admin']
# Each spelling below is what one admin.db capability unlocks somewhere in app.py,
# so a row written any of these ways still works.
CAPABILITY_ALIASES = {
    'manage_database': ('manage database', 'manage the database', 'database'),
    'create_quizzes': ('can create quizzes', 'create quizzes', 'quiz'),
    'create_summative_tests': ('can create summative tests', 'create summative tests',
                               'summative', 'can create summative test'),
    'post_materials': ('can post materials', 'post materials', 'materials', 'hand out materials'),
    'manage_teachers': ('manage teachers', 'manage teacher', 'staff'),
    'manage_students': ('manage students', 'manage student', 'learners'),
    'manage_classes': ('can manage classes', 'manage classes', 'classes'),
    'manage_teacher_assignment': ('manage teacher assignment', 'teacher assignment',
                                  'assign teachers', 'assign a teacher'),
    'view_assessment_results': ('can view assessment results', 'view assessment results',
                                'assessment results', 'results', 'assessment'),
    'record_marks': ('record marks for the teacher', 'record marks', 'marks'),
    'add_admins': ('can add other admin', 'add other admin', 'add admin'),
    'assign_teacher_to_admin': ('can assign a teacher to an admin',
                                'assign a teacher to an admin'),
}
# What each level may do when nothing else says: the school's own split of
# owner / admin / teacher.
DEFAULT_ROLE_CAPS = {
    'main_admin': ['manage database', 'can add other admin', 'can create quizzes',
                   'can create summative tests', 'can post materials', 'manage teachers',
                   'manage students', 'can manage classes', 'manage teacher assignment',
                   'can view assessment results', 'record marks for the teacher',
                   'can assign a teacher to an admin'],
    'admin': ['can manage classes', 'manage teacher assignment',
              'can view assessment results', 'record marks for the teacher'],
    'teacher': ['can create quizzes', 'can create summative tests', 'record marks'],
}


def admin_sql(statement, args=(), one=False, as_rows=False):
    """Run one statement against admin.db; never raises if the file is unreadable."""
    if not os.path.exists(ADMIN_DB_PATH) and not statement.strip().upper().startswith('CREATE'):
        # The file was deleted while the app ran: build it again straight away,
        # so nobody is locked out before the next start-up.
        ensure_admin_db()
    conn = None
    try:
        conn = sqlite3.connect(ADMIN_DB_PATH, timeout=5)
        cur = conn.execute(statement, tuple(args))
        if as_rows or statement.strip().upper().startswith('SELECT'):
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
            if one:
                return rows[0] if rows else None
            return rows
        conn.commit()
        return True
    except Exception:
        return None if one else []
    finally:
        if conn:
            conn.close()


# admin.db is tiny and read on nearly every request: hold what is read for a
# second, so an edit made in a database browser lands without re-opening the
# file on every query.
_ADMIN_DB_CACHE = {}
_ADMIN_DB_CACHE_AT = 0.0


def admin_db_cache(key, query):
    global _ADMIN_DB_CACHE_AT
    now = time.time()
    if now - _ADMIN_DB_CACHE_AT >= 1.0:
        _ADMIN_DB_CACHE.clear()
        _ADMIN_DB_CACHE_AT = now
    if key not in _ADMIN_DB_CACHE:
        _ADMIN_DB_CACHE[key] = query()
    return _ADMIN_DB_CACHE[key]


def load_admin_config():
    path = os.path.join(basedir, 'admin.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


ADMIN_CONFIG = load_admin_config()
# The old admin.json keys, folded onto the admin.db level names.
LEGACY_LEVEL_KEYS = {'main_admin': 'main_admin', 'main': 'main_admin', 'admin': 'admin',
                     'teacher': 'teacher', 'sub': 'teacher'}


def admin_block(level):
    """The admin.json block kept for this level, if any."""
    key = {'main': 'main_admin', 'sub': 'teacher'}.get(level, LEGACY_LEVEL_KEYS.get(level, level))
    block = ADMIN_CONFIG.get(key)
    return block if isinstance(block, dict) else {}


def normalize_caps(values):
    """One capability per row, in the admin.db spelling, order kept."""
    out = []
    for value in values or []:
        if not str(value).strip():
            continue
        key = str(value).strip().lower().replace('-', '_')
        for canonical, spellings in CAPABILITY_ALIASES.items():
            if key in spellings or key == canonical.replace('_', ' '):
                key = canonical
                break
        if key not in out:
            out.append(key)
    return out


def caps_match(want, caps):
    """True when one admin.db row (either spelling) means this capability."""
    wanted = normalize_caps([want])
    return bool(wanted) and wanted[0] in normalize_caps(caps)


# How each capability is described to the main admin on the Staff page.
CAP_LABELS = {
    'manage_database': 'manage the database',
    'add_admins': 'add other admins',
    'create_quizzes': 'create quizzes',
    'create_summative_tests': 'create summative tests',
    'post_materials': 'post materials',
    'manage_teachers': 'manage teachers',
    'manage_students': 'manage students',
    'manage_classes': 'manage classes',
    'manage_teacher_assignment': 'assign teachers to classes',
    'view_assessment_results': 'view assessment results',
    'record_marks': 'record marks',
    'assign_teacher_to_admin': 'assign a teacher to an admin',
}


def cap_label(capability):
    """One capability, written the way the page reads it."""
    folded = normalize_caps([capability])
    if not folded:
        return ''
    return CAP_LABELS.get(folded[0], folded[0].replace('_', ' '))


def level_caps(level, as_written=False):
    """The capabilities written for one level in admin.json, or the school default.

    as_written keeps the school's own wording, which is what goes into admin.db;
    the default answer is folded onto the capability names app.py checks.
    """
    roles = admin_block(level).get('roles')
    if isinstance(roles, str):
        roles = [part for part in roles.split(',')]
    if not roles:
        roles = DEFAULT_ROLE_CAPS.get(level, [])
    roles = [str(r).strip() for r in roles if str(r).strip()]
    return roles if as_written else normalize_caps(roles)


def give_admin_db_columns():
    """Give an existing admin.db the column a new version of the app expects.

    The school's admin.db is edited by hand and outlives redeploys, so a column
    added here has to arrive on its own - CREATE TABLE IF NOT EXISTS would leave
    an old file exactly as it was and every read of the new column would fail.
    """
    present = {str(row.get('name') or '') for row in
               admin_sql('PRAGMA table_info(accounts)', as_rows=True)}
    if present and 'supervisor' not in present:
        admin_sql("ALTER TABLE accounts ADD COLUMN supervisor TEXT NOT NULL DEFAULT ''")


def ensure_admin_db():
    """Create and seed admin.db whenever it is missing - login must never be locked out."""
    fresh = not os.path.exists(ADMIN_DB_PATH)
    admin_sql('''CREATE TABLE IF NOT EXISTS roles (
                 level TEXT NOT NULL, capability TEXT NOT NULL,
                 PRIMARY KEY (level, capability))''')
    admin_sql('''CREATE TABLE IF NOT EXISTS accounts (
                 email TEXT PRIMARY KEY, password TEXT NOT NULL DEFAULT '',
                 level TEXT NOT NULL DEFAULT 'teacher',
                 supervisor TEXT NOT NULL DEFAULT '')''')
    give_admin_db_columns()
    if fresh or not admin_sql('SELECT level FROM roles', as_rows=True):
        for level in ADMIN_LEVELS:
            for cap in level_caps(level, as_written=True):
                admin_sql('INSERT OR IGNORE INTO roles (level, capability) VALUES (?, ?)',
                          (level, cap))
    for level in ADMIN_LEVELS:
        account = admin_block(level)
        email = str(account.get('email') or '').strip().lower()
        if level == 'main_admin' and not email:
            email = DEFAULT_ADMIN_EMAIL
        password = str(account.get('password') or '')
        if not password and email == DEFAULT_ADMIN_EMAIL:
            password = DEFAULT_ADMIN_PASSWORD
        if not email:
            continue
        if admin_sql('SELECT email FROM accounts WHERE lower(email) = ?',
                     (email,), one=True) is None:
            admin_sql('INSERT INTO accounts (email, password, level) VALUES (?, ?, ?)',
                      (email, password, level))
    _ADMIN_DB_CACHE.clear()


# --- ADMIN LEVELS AND ACCOUNTS (admin.db) ---
ensure_admin_db()


def admin_levels():
    """Every level admin.db lists, with the capabilities written under it."""
    def load():
        out = {level: [] for level in reversed(ADMIN_LEVELS)}
        for row in admin_sql('SELECT level, capability FROM roles ORDER BY level',
                             as_rows=True):
            out.setdefault(row['level'], []).append(row['capability'])
        return out
    return admin_db_cache('levels', load)


def roles_for(level):
    """What this level may do: admin.db first, then admin.json, then the school default.

    A Staff row is a teacher unless admin.db gives its email a level of its own,
    so nothing assigned on the Staff page loses the abilities it had before.
    """
    if not level:
        return []
    key = LEGACY_LEVEL_KEYS.get(level, level)
    caps = normalize_caps(admin_levels().get(key))
    return caps or level_caps(key)


def admin_account(email):
    """The admin.db row for this address, or None: {'email','password','level','supervisor'}."""
    address = str(email or '').strip().lower()
    if not address:
        return None
    return admin_db_cache(
        ('account', address),
        lambda: admin_sql('SELECT email, password, level, supervisor FROM accounts '
                          'WHERE lower(email) = ?', (address,), one=True))


def admin_accounts(level=None):
    """Every admin.db login, or only those at one level."""
    def load():
        return admin_sql('SELECT email, level, supervisor FROM accounts '
                         'ORDER BY level, email', as_rows=True)

    rows = admin_db_cache(('accounts', level), load)
    if level is None:
        return rows
    return [row for row in rows if str(row.get('level') or '') == level]


def admin_db_write(statement, args=()):
    """One statement that changes admin.db, then forget what was read from it."""
    wrote = admin_sql(statement, args)
    _ADMIN_DB_CACHE.clear()
    return wrote


def set_admin_account(email, password=None, level=None, supervisor=None):
    """Hand out (or refresh) one admin.db login: the Staff page writes here."""
    address = str(email or '').strip().lower()
    if not address:
        return False
    row = admin_account(address)
    if row is None:
        return admin_db_write(
            'INSERT INTO accounts (email, password, level, supervisor) VALUES (?, ?, ?, ?)',
            (address, str(password or ''),
             level if level in ADMIN_LEVELS else 'teacher',
             str(supervisor or '').strip().lower()))
    kept_level = level if level in ADMIN_LEVELS else str(row.get('level') or 'teacher')
    kept_supervisor = (str(supervisor).strip().lower() if supervisor is not None
                       else str(row.get('supervisor') or ''))
    admin_db_write('UPDATE accounts SET password = ?, level = ?, supervisor = ? '
                   'WHERE lower(email) = ?',
                   (str(password) if password is not None else str(row.get('password') or ''),
                    kept_level, kept_supervisor, address))
    return True


def supervisor_of(email):
    """The admin this login answers to, or '' for nobody but the main admin."""
    return str((admin_account(email) or {}).get('supervisor') or '').strip().lower()


def set_supervisor(email, admin_email):
    """Put a teacher under one admin, or back under the main admin with ''."""
    address = str(email or '').strip().lower()
    if not address:
        return False
    return admin_db_write('UPDATE accounts SET supervisor = ? WHERE lower(email) = ?',
                          (str(admin_email or '').strip().lower(), address)) is not None


def supervised_emails(admin_email):
    """Every login one admin is in charge of: their own teachers and the main admin's."""
    boss = str(admin_email or '').strip().lower()
    if not boss:
        return set()
    return {str(row.get('email') or '').strip().lower() for row in admin_accounts()
            if str(row.get('email') or '').strip().lower() != boss
            and str(row.get('supervisor') or '').strip().lower() == boss}


def remove_admin_account(email):
    """Take an admin.db login back; the level rows stay, they are the school's own list."""
    address = str(email or '').strip().lower()
    if not address:
        return False
    return admin_db_write('DELETE FROM accounts WHERE lower(email) = ?', (address,))


def main_admin_email():
    """admin.db's main_admin row, then admin.json, then the school owner."""
    for row in admin_sql("SELECT email FROM accounts WHERE level = 'main_admin'",
                         as_rows=True):
        address = str(row.get('email') or '').strip().lower()
        if address:
            return address
    return str(admin_block('main_admin').get('email') or DEFAULT_ADMIN_EMAIL).strip().lower()


ADMIN_EMAIL = main_admin_email()


def norm_section(value):
    """'crest', ' Crest ' and 'CREST' are one and the same section."""
    return ' '.join(str(value or '').split()).upper()


def norm_time(value):
    """'7:30', '07:30' and '7:30 AM' all save as 24-hour '07:30'.

    Returns '' for a blank box and None for something that is not a clock time,
    so the Classes page can tell the two apart instead of saving junk.
    """
    text = str(value or '').strip().upper().replace('.', '')
    if not text:
        return ''
    meridiem = text[-2:] if text.endswith(('AM', 'PM')) else ''
    if meridiem:
        text = text[:-2].strip()
    parts = text.split(':')
    if not 1 <= len(parts) <= 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) == 2 else 0
    except ValueError:
        return None
    if meridiem == 'PM' and hour < 12:
        hour += 12
    elif meridiem == 'AM' and hour == 12:
        hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return '%02d:%02d' % (hour, minute)


SLOT_LIMIT = 8


def serialize_slots(slots):
    """A saved schedule as stored text: one 'days|start|end' chunk per time slot,
    joined by ';'. Days stay in school order so a saved week reloads exactly as
    it was ticked, and a double period is simply two slots."""
    return ';'.join('%s|%s|%s' % (','.join(days), start or '', end or '')
                    for days, start, end in slots)


def parse_slots(text):
    """A stored schedule text back into [(days, start, end), ...]."""
    slots = []
    for chunk in str(text or '').split(';'):
        parts = chunk.split('|')
        if len(parts) != 3:
            continue
        days = [d for d in CLASS_DAYS if d in parts[0].split(',')]
        slots.append((days, parts[1].strip(), parts[2].strip()))
    return slots


def iter_slots(row):
    """The time slots of one saved schedule, newest spelling first.

    A class scheduled before slots existed reads as the single slot its old
    days-and-time columns describe.
    """
    text = str(getattr(row, 'schedule_slots', '') or '').strip()
    if text:
        return parse_slots(text)
    days = [d for d in CLASS_DAYS if d in str(row.schedule_days or '').split(',')]
    if not days and not (row.start_time or row.end_time):
        return []
    return [(days, row.start_time or '', row.end_time or '')]


def slot_label(days, start, end):
    label = ', '.join(days)
    if start and end:
        label = (label + ' ' if label else '') + '%s-%s' % (start, end)
    return label


def norm_room(value):
    """A room as stored: trimmed, one space between words, cut to the column."""
    return ' '.join(str(value or '').split())[:60]


def room_label(room):
    """How a room is printed: '5' becomes 'Room 5', and 'Room 5' stays 'Room 5'."""
    text = norm_room(room)
    if not text:
        return ''
    return text if text.lower().startswith('room') else 'Room %s' % text


def schedule_label(row):
    """What the class list shows for one section's saved schedule."""
    label = '; '.join(part for part in (slot_label(*slot) for slot in iter_slots(row))
                       if part)
    room = room_label(getattr(row, 'room', ''))
    if label and room:
        return '%s · %s' % (label, room)
    return label or room


def posted_room(request):
    """The room typed on one posted schedule form."""
    return norm_room(request.form.get('room'))


def posted_schedule(request):
    """The days and time slots one posted schedule form saves.

    Slot rows arrive named by index - days_N, start_N, end_N - with a hidden
    slot_count telling how many rows the page showed. Returns
    ([(days, start, end), ...], None) or (None, error text) so the Classes
    page can refuse junk instead of saving a broken week. A slot with no days
    ticked and no time typed is dropped; nothing left means the schedule is
    cleared. Two slots sharing a day may run back to back but never overlap.
    """
    try:
        count = int(request.form.get('slot_count') or 1)
    except ValueError:
        count = 1
    slots = []
    for index in range(max(count, 1)):
        picked = set(request.form.getlist('days_%d' % index))
        days = [day for day in CLASS_DAYS if day in picked]
        start = norm_time(request.form.get('start_%d' % index))
        end = norm_time(request.form.get('end_%d' % index))
        if start is None or end is None:
            return None, 'Slot %d: a time is written like 07:30 or 7:30 AM.' % (index + 1)
        if bool(start) != bool(end):
            return None, ('Slot %d: give both a start and an end time, '
                          'or leave both empty.' % (index + 1))
        if start and end <= start:
            return None, ('Slot %d: the end time must be later than the start '
                          'time.' % (index + 1))
        if days or start:
            slots.append((days, start, end))
    if len(slots) > SLOT_LIMIT:
        return None, 'A schedule can hold at most %d time slots.' % SLOT_LIMIT
    for pos, (days, start, end) in enumerate(slots):
        for other_days, other_start, other_end in slots[pos + 1:]:
            shared = [day for day in days if day in other_days]
            if shared and start and other_start and \
                    start < other_end and other_start < end:
                return None, ('Two slots meet on %s at overlapping times '
                              '(%s-%s and %s-%s).' % (
                                  ', '.join(shared), start, end,
                                  other_start, other_end))
    return slots, None


def save_schedule(row, slots, room=None):
    """Write parsed slots and the room onto one SectionLevel or TeacherClass row.

    The slot text is the live copy; the first slot also lands in the old
    days-and-time columns so the schedule still reads if the database is
    opened by an older version of the app. Passing no room leaves the one
    already on the row untouched.
    """
    row.schedule_slots = serialize_slots(slots)
    days, start, end = slots[0] if slots else ([], '', '')
    row.schedule_days = ','.join(days)
    row.start_time = start
    row.end_time = end
    if room is not None:
        row.room = room


def slot_minutes(value):
    """'07:30' into minutes past midnight, or None when there is no time yet."""
    parts = str(value or '').strip().split(':')
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def classes_week(classes):
    """Every class of one teacher plotted onto the weekday boxes, clashes found.

    A block is one meeting of one handed class: grade, section, subjects, start
    and end. Two blocks on the same day clash when their times overlap - the
    same teacher cannot stand in two rooms at once - so each carries the other
    in 'clash' and the profile turns those cells red.
    """
    week = {day: [] for day in CLASS_DAYS}
    for item in classes:
        for days, start, end in item.get('slots') or []:
            for day in days:
                if day in week:
                    week[day].append({'grade': item['grade'], 'section': item['section'],
                                      'subjects': item['subjects'],
                                      'room': room_label(item.get('room') or ''),
                                      'start': start, 'end': end})
    for blocks in week.values():
        blocks.sort(key=lambda b: (slot_minutes(b['start']) if b['start'] else 24 * 60,
                                   b['section']))
        for block in blocks:
            mine_start = slot_minutes(block['start'])
            mine_end = slot_minutes(block['end'])
            block['clash'] = []
            if mine_start is None or mine_end is None:
                continue
            for other in blocks:
                if other is block:
                    continue
                their_start = slot_minutes(other['start'])
                their_end = slot_minutes(other['end'])
                if their_start is None or their_end is None:
                    continue
                if mine_start < their_end and their_start < mine_end:
                    block['clash'].append(other)
    return week


def clash_notes(staff_id):
    """One line per pair of a teacher's classes that meet at the same time.

    Used after an assignment is saved: the Classes page cannot stop an admin
    handing the clash out, but it must say so in the message right away.
    """
    notes = []
    seen = set()
    for day, blocks in classes_week(member_classes(staff_id)).items():
        for block in blocks:
            for other in block['clash']:
                pair = (day,) + tuple(sorted([(block['grade'], block['section'], block['start']),
                                              (other['grade'], other['section'], other['start'])]))
                if pair in seen:
                    continue
                seen.add(pair)
                notes.append('%s %s %s-%s clashes with %s %s %s-%s on %s' % (
                    block['grade'], block['section'], block['start'], block['end'],
                    other['grade'], other['section'], other['start'], other['end'], day))
    return notes


def tidy_name(*parts):
    """EDGARDO, edgardo and Edgardo all end up shown as Edgardo."""
    words = []
    for part in parts:
        for word in str(part or '').split():
            words.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
    return ' '.join(words)


def section_choices_for(grade):
    """The sections the main admin created for one grade, in the order shown."""
    return [row.name for row in
            SectionLevel.query.filter_by(grade=grade or '').order_by(
                SectionLevel.name, SectionLevel.id).all()]


def grade_choices():
    """The grade levels the main admin created, in the order they were made."""
    return [row.name for row in GradeLevel.query.order_by(GradeLevel.id).all()]


def class_choices():
    """{grade: [section, ...]} for every grade level the main admin created.

    A grade with no section yet still belongs on the list, with an empty pick,
    so the Classes page is the only place a class is born. This is the only
    pickable list anywhere a learner or a material is filed under a section.
    """
    return {grade: section_choices_for(grade) for grade in grade_choices()}


def assigned_classes(staff_id):
    """{(grade, SECTION)} one teacher account was handed on the classes page."""
    if not staff_id:
        return set()
    return {(row.grade, norm_section(row.section)) for row in
            TeacherClass.query.filter_by(staff_id=staff_id).all()}


def open_classes():
    """The classes this signer may open: None means every class (the main admin)."""
    if at_least('admin'):
        return None
    member = current_staff()
    return assigned_classes(member.id) if member else set()


def may_open_class(grade, section):
    allowed = open_classes()
    return True if allowed is None else (grade, norm_section(section)) in allowed


def section_scope(grade):
    """The sections this signer may read within one grade; None means all of them.

    Picking a grade must not hand a teacher the whole grade: only the sections
    on the Classes page under their name are ever listed.
    """
    allowed = open_classes()
    if allowed is None:
        return None
    names = sorted({section for grade_key, section in allowed if grade_key == grade})
    # A list that cannot match anything keeps an unassigned grade empty rather
    # than falling back to the whole grade.
    return names or ['(none)']


def openable_learners():
    """[(id, label)] for every account this signer may open, by last name.

    The main admin gets the whole register; a teacher gets the learners whose
    grade and section sit on the Classes page under their name.
    """
    allowed = open_classes()
    learners = User.query.order_by(
        db.func.upper(User.last_name), db.func.upper(User.first_name)).all()
    out = []
    for student in learners:
        if allowed is not None and (student.grade, norm_section(student.section)) not in allowed:
            continue
        out.append((student.id, '%s - %s %s' % (
            student.full_name(), student.grade or '', norm_section(student.section))))
    return out


def pick_classes(groups):
    """Narrow a {grade: [sections]} picker down to the classes this teacher owns.

    The main admin keeps the whole list; a teacher only ever sees the classes the
    main admin put on the Classes page under their name.
    """
    allowed = open_classes()
    if allowed is None:
        return dict(groups)
    out = {}
    for grade, names in groups.items():
        keep = [name for name in names if (grade, norm_section(name)) in allowed]
        if keep:
            out[grade] = keep
    return out


def is_managed_class(grade, section):
    """True when the main admin created that grade and section."""
    return section in section_choices_for(grade)


def class_teachers(grade, section):
    """{'teacher','id','subjects','schedule','slots','room','row'} for the teachers
    handed one class."""
    return [{'teacher': member, 'id': row.id, 'subjects': split_subjects(row.subjects),
             'schedule': schedule_label(row), 'slots': iter_slots(row),
             'room': row.room, 'row': row}
            for member, row in
            (db.session.query(Staff, TeacherClass)
             .join(TeacherClass, TeacherClass.staff_id == Staff.id)
             .filter(TeacherClass.grade == grade,
                     db.func.upper(TeacherClass.section) == norm_section(section))
             .order_by(Staff.name)
             .all())]


def split_subjects(value):
    """The subjects saved on one assignment, back into a list."""
    return [part.strip() for part in str(value or '').split(',') if part.strip()]


def grade_subjects(grade):
    """The subjects the school's curriculum lists for one grade level."""
    return list((QUIZ_SPEC.get(grade) or {}).keys())


def tidy_subjects(grade, values):
    """Keep only the curriculum's own spelling for these subjects, in its order.

    A picker may post any number of them, but the names saved are the ones every
    other page already uses, so a class list cannot grow a 'science' next to a
    'Science'.
    """
    wanted = {str(value).strip().lower() for value in values if str(value).strip()}
    return [name for name in grade_subjects(grade) if name.lower() in wanted]


def teacher_subjects(staff_id):
    """The subjects one teacher was handed across their classes; empty means no rule.

    A teacher with assignments but no subject ticked yet is not shut out of the
    subject pickers - the school fills these in over time.
    """
    if not staff_id:
        return []
    rows = TeacherClass.query.filter_by(staff_id=staff_id).all()
    out = []
    for row in rows:
        for subject in split_subjects(row.subjects):
            if subject not in out:
                out.append(subject)
    return out


def staff_subject_scope():
    """The subjects the signed-in teacher may pick, lower-cased; None means all.

    This is the Classes page's assignment reaching the pickers: a teacher handed
    Science in one section cannot build a quiz out of Araling Panlipunan.
    """
    if at_least('admin'):
        return None
    member = current_staff()
    if not member:
        return None
    names = {name.lower() for name in teacher_subjects(member.id)}
    return names or None


def learners_in(grade, section=''):
    """How many accounts sit in a class - the reason a class cannot just go."""
    query = User.query.filter(User.grade == grade)
    if section:
        query = query.filter(db.func.upper(User.section) == norm_section(section))
    return query.count()


def materials_in(grade, section):
    return Resource.query.filter(
        Resource.grade == grade,
        db.func.upper(Resource.section) == norm_section(section)).count()


def rename_grade_rows(old, new):
    """Move every record that names a grade level the main admin just renamed."""
    for model, column in ((SectionLevel, SectionLevel.grade),
                          (TeacherClass, TeacherClass.grade),
                          (User, User.grade),
                          (UngradedAttempt, UngradedAttempt.grade),
                          (Resource, Resource.grade)):
        db.session.query(model).filter(column == old).update(
            {column: new}, synchronize_session=False)


def move_class_rows(grade, old, new):
    """Re-file the learners, scores and materials of one section under another.

    A section typed by hand in the past is stored in any capitals, so the match
    ignores them and every row ends up spelled the managed way.
    """
    for model, column in ((User, User.section),
                          (UngradedAttempt, UngradedAttempt.section),
                          (Resource, Resource.section)):
        db.session.query(model).filter(
            model.grade == grade,
            db.func.upper(column) == norm_section(old)).update(
            {column: norm_section(new)}, synchronize_session=False)


def move_class_teachers(grade, old, new):
    """Carry a rename or a merge onto the assignment table.

    A teacher already holding the target class needs no second row, so that
    assignment simply drops instead of breaking the one-row-per-class rule.
    """
    for row in TeacherClass.query.filter_by(grade=grade).all():
        if norm_section(row.section) != norm_section(old):
            continue
        holder = TeacherClass.query.filter_by(
            staff_id=row.staff_id, grade=grade, section=norm_section(new)).first()
        if holder and holder.id != row.id:
            db.session.delete(row)
        else:
            row.section = norm_section(new)


def rename_section_rows(grade, old, new):
    """Move every record of a section the main admin renamed."""
    move_class_rows(grade, old, new)
    move_class_teachers(grade, old, new)


# --- DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    middle_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80), nullable=False)
    suffix = db.Column(db.String(10))
    school = db.Column(db.String(200), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def full_name(self):
        name = tidy_name(self.first_name, self.middle_name, self.last_name)
        if self.suffix and self.suffix != 'N/A':
            name += ' ' + self.suffix
        return name


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    client_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    subject = db.Column(db.String(120), nullable=False)
    topic = db.Column(db.String(200))
    quiz_set_info = db.Column(db.Text)  # JSON: [{id, question, options, your_answer, correct, topic}]
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    date_taken = db.Column(db.DateTime, nullable=False)
    # 'quiz' was answered on this app; 'manual' is a score the teacher typed in
    # on the Assessment page, e.g. from a paper test.
    source = db.Column(db.String(20), nullable=False, default='quiz')
    # Who typed a recorded mark, so only that teacher (or the main admin) can take it back.
    recorded_by = db.Column(db.String(120))


class UngradedAttempt(db.Model):
    """A finished quiz whose student answered "No Thanks" to saving it.

    It lives in its own `ungraded` table so it can never appear in a student's
    results or change an average, while the school still keeps what the answers
    say about each item. Someone without an account is stored as "annonymous".
    """
    __tablename__ = 'ungraded'
    id = db.Column(db.Integer, primary_key=True)
    client_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    name = db.Column(db.String(120), nullable=False)
    school = db.Column(db.String(200))
    grade = db.Column(db.String(20))
    section = db.Column(db.String(80))
    subject = db.Column(db.String(120), nullable=False)
    topic = db.Column(db.String(200))
    quiz_set_info = db.Column(db.Text)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    date_taken = db.Column(db.DateTime, nullable=False)


class SyncSent(db.Model):
    """One record the live server has already accepted from this laptop.

    `kind` is 'users', 'attempts' or 'ungraded'; the key is the address or the
    client_uuid, which is the same on both copies. Recording it here means the
    Sync button can be pressed twice - or from two laptops - without posting
    the same result again.
    """
    __tablename__ = 'sync_sent'
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    key = db.Column(db.String(255), nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('kind', 'key', name='uq_sync_sent'),)


class SyncRun(db.Model):
    """The last time the Sync button finished, and what it said."""
    __tablename__ = 'sync_run'
    id = db.Column(db.Integer, primary_key=True)
    ran_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ok = db.Column(db.Boolean, nullable=False, default=False)
    message = db.Column(db.Text, nullable=False, default='')


class Resource(db.Model):
    """One material the admin hands out to a whole section.

    A section is the group, so everything stored for Grade 10 CREST is seen by
    every CREST student. Files (PDF, picture, slides) live on Google Drive and
    are shared so anyone can open them; a Google Doc, a Google Sheet or any
    other page is kept as the link the admin pasted.
    """
    __tablename__ = 'resource'
    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.String(20), nullable=False, index=True)
    section = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    drive_id = db.Column(db.String(80))
    note = db.Column(db.String(300))
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class PasswordReset(db.Model):
    """One forgot-password request, waiting for its emailed code.

    The code and the new password are both stored hashed, so a database dump
    shows neither. The random token in the address is what identifies the
    request while the student types the code in.
    """
    __tablename__ = 'password_reset'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    new_password_hash = db.Column(db.String(255), nullable=False)
    tries = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)


class Staff(db.Model):
    """A teacher the main admin lets in through the admin login.

    A sub-admin teaches and nothing more: they pull Assessment data, record a
    mark, hand out Materials and read the Results Dashboard. Students, stored
    rows and further teachers are the main admin's alone.
    """
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.String(120))


class GradeLevel(db.Model):
    """One grade level the main admin created. The pickers read this table."""
    __tablename__ = 'grade_level'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class SectionLevel(db.Model):
    """One section, filed under its grade. Both names come from the main admin.

    The schedule is the week the class actually meets: time slots kept as
    'days|start|end' text so a double period can be two slots, each with its
    own days and 24-hour HH:MM times. The old single days/start/end columns
    mirror the first slot. Empty means unscheduled. The room is where the class
    meets, one room for the whole week.
    """
    __tablename__ = 'class_section'
    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    room = db.Column(db.String(60), nullable=False, default='')
    schedule_days = db.Column(db.String(40), nullable=False, default='')
    start_time = db.Column(db.String(5), nullable=False, default='')
    end_time = db.Column(db.String(5), nullable=False, default='')
    schedule_slots = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('grade', 'name', name='uq_section_in_grade'),)


class TeacherClass(db.Model):
    """The class list a teacher is handed: one teacher, one grade and section.

    A teacher sees the records of these rows and nothing else, so this table is
    both the roster of who teaches what and the access rule for the dashboards.
    The subjects are the ones that teacher handles in that section, kept as a
    comma-separated list so one row still means one teacher in one class.
    The schedule is this teacher's own days and time slots in that class; when
    it is empty the section's schedule from class_section is shown instead. The
    room follows the same rule: the teacher's own room, or the section's.
    """
    __tablename__ = 'teacher_class'
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False, index=True)
    grade = db.Column(db.String(40), nullable=False, index=True)
    section = db.Column(db.String(80), nullable=False)
    subjects = db.Column(db.String(200), nullable=False, default='')
    room = db.Column(db.String(60), nullable=False, default='')
    schedule_days = db.Column(db.String(40), nullable=False, default='')
    start_time = db.Column(db.String(5), nullable=False, default='')
    end_time = db.Column(db.String(5), nullable=False, default='')
    schedule_slots = db.Column(db.Text, nullable=False, default='')
    assigned_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('staff_id', 'grade', 'section',
                                          name='uq_teacher_class'),)


class PushSubscription(db.Model):
    """One device that asked for schedule reminders.

    The endpoint is the address the browser's push service (Google, Firefox,
    Apple) delivers to; p256dh and auth are the keys that encrypt the message
    so only this device can read it. A learner fills user_id, staff fill
    staff_email - a phone handed to the school for both carries both.
    """
    __tablename__ = 'push_subscription'
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    staff_email = db.Column(db.String(120), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class PushSent(db.Model):
    """One reminder already delivered, so the loop never fires it twice.

    The key names the person, the day and the slot: 'remind|<sub>|2026-10-31|07:30'.
    A restart picks up where the school day left off.
    """
    __tablename__ = 'push_sent'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(200), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class NonClassDay(db.Model):
    """One whole-school no-class day, written on the Classes page.

    The date is 'YYYY-MM-DD' and the note says why - "no classes, it is a
    non-working holiday". While a note stands for today, class reminders and
    the morning digest are halted for everybody, and the note shows on the
    profiles instead of that day's classes.
    """
    __tablename__ = 'non_class_day'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), unique=True, nullable=False, index=True)
    note = db.Column(db.String(200), nullable=False, default='')
    created_by = db.Column(db.String(120), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# --- SCHEMA SELF-HEAL ---
# Hosted deployments can still be pointing at the pre-free rewrite database,
# whose `user` table has none of these columns and which has no quiz_attempt
# table at all. Without this every signup died with a bare 500.
LEGACY_USER_COLUMNS = {
    'first_name': "VARCHAR(80) DEFAULT ''",
    'middle_name': "VARCHAR(80)",
    'last_name': "VARCHAR(80) DEFAULT ''",
    'suffix': "VARCHAR(10) DEFAULT 'N/A'",
    'school': "VARCHAR(200) DEFAULT ''",
    'grade': "VARCHAR(20) DEFAULT ''",
    'section': "VARCHAR(80) DEFAULT ''",
    'password_hash': "VARCHAR(255)",
    'created_at': "DATETIME",
}


def add_missing_columns(table, model):
    """Give a table that already exists a column the model just gained.

    `create_all` never alters an existing table, so a deployment that has quiz
    rows from before this column would fail on every write until the school
    re-created its database by hand.
    """
    present = {row[1] for row in db.session.execute(db.text('PRAGMA table_info(%s)' % table))}
    for column in model.__table__.columns:
        if column.name in present:
            continue
        ddl = '%s %s' % (column.name, column.type.compile(db.engine.dialect))
        if not column.nullable:
            fallback = column.default.arg if column.default is not None and \
                hasattr(column.default, 'arg') else ''
            ddl += " NOT NULL DEFAULT '%s'" % fallback
        db.session.execute(db.text('ALTER TABLE %s ADD COLUMN %s' % (table, ddl)))
        app.logger.warning('Added %s.%s to an existing table', table, column.name)


def seed_class_registry():
    """Fill Grades & Sections once from the defaults and the learners on file.

    Only an empty registry is seeded, so a section the main admin deleted can
    never come back on the next start. Learners already signed up are adopted
    with them, which is what keeps a section with an odd old spelling visible
    until the admin cleans it up.
    """
    if db.session.query(GradeLevel.id).count() or db.session.query(SectionLevel.id).count():
        return

    grades = list(DEFAULT_GRADES)
    sections = {}
    for grade, members in DEFAULT_SECTIONS.items():
        sections.setdefault(grade, set()).update(members)
    for model, grade_col, section_col in (
            (User, User.grade, User.section),
            (Resource, Resource.grade, Resource.section),
            (UngradedAttempt, UngradedAttempt.grade, UngradedAttempt.section)):
        for grade, section in db.session.query(grade_col, section_col).distinct().all():
            grade = str(grade or '').strip()
            if not grade:
                continue
            if grade not in grades:
                grades.append(grade)
            if section:
                sections.setdefault(grade, set()).add(norm_section(section))

    for grade in grades:
        db.session.add(GradeLevel(name=grade))
    for grade, members in sections.items():
        if grade not in grades:
            continue
        for section in sorted(members):
            db.session.add(SectionLevel(grade=grade, name=section))
    db.session.commit()
    app.logger.info('Grades & Sections seeded: %s', ', '.join(grades))


def ensure_database():
    with app.app_context():
        db.create_all()
        add_missing_columns('quiz_attempt', QuizAttempt)
        add_missing_columns('class_section', SectionLevel)
        add_missing_columns('teacher_class', TeacherClass)
        model_cols = list(User.__table__.columns.keys())
        present = {row[1] for row in db.session.execute(db.text('PRAGMA table_info(user)'))}

        missing = [c for c in model_cols if c not in present]
        extra = [c for c in present if c not in model_cols]

        for column in missing:
            ddl = LEGACY_USER_COLUMNS.get(column, 'VARCHAR(255)')
            db.session.execute(db.text(f'ALTER TABLE user ADD COLUMN {column} {ddl}'))

        if missing or extra:
            # A rebuilt table is the only way to shed the dead economy columns,
            # which are NOT NULL and would reject every new signup.
            not_null = {c.name for c in User.__table__.columns if not c.nullable}
            pk = [c.name for c in User.__table__.primary_key.columns]
            cols_ddl = ', '.join(
                f'{c.name} {c.type.compile(db.engine.dialect)}'
                + ('' if c.nullable else ' NOT NULL')
                for c in User.__table__.columns
            )
            if pk:
                cols_ddl += ', PRIMARY KEY (' + ', '.join(pk) + ')'
            select_list = ', '.join(
                f"COALESCE({c}, '')" if c in not_null else c for c in model_cols
            )
            db.session.execute(db.text(
                f'CREATE TABLE user_migrated ({cols_ddl}, UNIQUE (email))'))
            db.session.execute(db.text(
                f'INSERT INTO user_migrated ({", ".join(model_cols)}) '
                f'SELECT {select_list} FROM user'))
            db.session.execute(db.text('DROP TABLE user'))
            db.session.execute(db.text('ALTER TABLE user_migrated RENAME TO user'))
            db.session.commit()
            app.logger.warning(
                'Upgraded the user table: added %s, dropped %s',
                ', '.join(missing) or 'nothing',
                ', '.join(extra) or 'nothing',
            )

        seed_class_registry()


ensure_database()


# --- ADMIN ACCOUNTS FROM admin.db ---
def sync_admin_accounts():
    """Write the passwords admin.db holds onto the rows the rest of the app checks.

    admin.db is the file to edit: the main admin's password is written onto that
    User row, and an admin or teacher row with both an email and a password of
    eight characters or more becomes (or refreshes) a Staff row, so the person
    can also be removed on the Staff page. A row with no email is only a list of
    capabilities, and admin.db accounts are always signed in straight from the
    database as well - this copy only keeps those pages working.
    """
    stored = admin_sql("SELECT password FROM accounts WHERE level = 'main_admin' "
                      "AND lower(email) = ?", (ADMIN_EMAIL,), one=True)
    main_password = str((stored or {}).get('password') or '') or \
        str(admin_block('main_admin').get('password') or '') or DEFAULT_ADMIN_PASSWORD
    if ADMIN_EMAIL and main_password:
        owner = User.query.filter(db.func.lower(User.email) == ADMIN_EMAIL).first()
        if owner is None:
            app.logger.info(
                'admin.db names %s as the main admin with no learner account behind '
                'it: /admin/login signs that row in on its own.', ADMIN_EMAIL)
        elif not check_password_hash(owner.password_hash or '', main_password):
            owner.password_hash = generate_password_hash(main_password)
            db.session.commit()

    for row in admin_sql('SELECT email, password, level FROM accounts', as_rows=True):
        account_email = str(row.get('email') or '').strip().lower()
        password = str(row.get('password') or '')
        if not account_email or len(password) < 8:
            continue
        member = Staff.query.filter(db.func.lower(Staff.email) == account_email).first()
        if member:
            if not check_password_hash(member.password_hash or '', password):
                member.password_hash = generate_password_hash(password)
        else:
            db.session.add(Staff(
                name=tidy_name(account_email.split('@')[0]), email=account_email,
                password_hash=generate_password_hash(password),
                created_by='admin.db'))
        db.session.commit()


with app.app_context():
    sync_admin_accounts()


# --- QUESTION BANK (loaded once at startup) ---
def parse_category_path(path):
    """'Grade 8 > Science > Quarter 2 > Topic' -> ('Quarter 2', 'Topic')."""
    parts = [p.strip() for p in path.split('>')] if path else []
    quarter = next((p for p in parts if p.lower().startswith('quarter')), '')
    topic = parts[-1] if parts else ''
    return quarter, (topic or 'General')


def load_question_bank():
    q_path = os.path.join(basedir, 'questions.json')
    if not os.path.exists(q_path):
        return []
    try:
        with open(q_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return []

    bank = []
    for q in raw:
        options = q.get('options') or q.get('option') or []
        if not isinstance(options, list):
            continue
        quarter, topic = parse_category_path(str(q.get('category_path', '') or ''))
        bank.append({
            'id': q.get('id'),
            'level': str(q.get('Grade_level', '') or '').strip(),
            'subject': str(q.get('major', '') or '').strip(),
            'quarter': quarter,
            'topic': topic,
            'question': q.get('question'),
            'options': [str(o) for o in options],
            'correct': q.get('CorrectAnswer'),
        })
    return bank


QUESTIONS = load_question_bank()


def load_quiz_spec():
    """Build the full Grade -> Subject -> Quarter -> Topic tree.

    Topics come from matatag_spec.json (mirrors the MNHS Question Maker);
    question counts come from the loaded bank so anything generated later
    shows up automatically.
    """
    tree = {}
    spec_path = os.path.join(basedir, 'matatag_spec.json')
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
    except Exception:
        spec = {}

    for level, subjects in spec.items():
        for subject, quarters in subjects.items():
            for quarter, topics in quarters.items():
                for topic in topics:
                    tree.setdefault(level, {}).setdefault(subject, {}).setdefault(quarter, {})[topic] = 0

    for q in QUESTIONS:
        node = tree.setdefault(q['level'], {}).setdefault(q['subject'], {}).setdefault(q['quarter'], {})
        node[q['topic']] = node.get(q['topic'], 0) + 1

    # Keep Grade 7-10 first, then any extra levels from the bank.
    ordered = {}
    for level in DEFAULT_GRADES + sorted(k for k in tree if k not in DEFAULT_GRADES):
        if level in tree:
            ordered[level] = tree[level]
    return ordered


QUIZ_SPEC = load_quiz_spec()


def spec_json():
    """The quiz tree as the signed-in staff may see it, ready for a page.

    A teacher handed subjects on the Classes page gets only those subjects in the
    picker. Serialized by hand because Flask's tojson sorts keys, which would
    scramble the Grade 7-10 and subject order the school teaches in.
    """
    scope = staff_subject_scope()
    spec = QUIZ_SPEC
    if scope is not None:
        spec = {grade: {subject: quarters for subject, quarters in subjects.items()
                        if subject.lower() in scope}
                for grade, subjects in QUIZ_SPEC.items()}
    return json.dumps(spec, ensure_ascii=False).replace('<', '\\u003c')


# --- HELPERS ---
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return db.session.get(User, uid)


def is_admin(user):
    return bool(user) and (user.email or '').strip().lower() == ADMIN_EMAIL


def current_staff():
    """The sub-admin row signed in through the admin login, or None."""
    sid = session.get('staff_id')
    if not sid:
        return None
    return db.session.get(Staff, sid)


def staff_level(member):
    """The admin.db level of a Staff row: teacher unless that address is listed higher."""
    if not member:
        return ''
    account = admin_account(member.email)
    level = str((account or {}).get('level') or '').strip().lower()
    return level if level in ADMIN_LEVELS else 'teacher'


def admin_kind(user=None):
    """'' for a learner or a visitor, else the admin.db level of the signed-in staff."""
    if user is None:
        user = current_user()
    if is_admin(user):
        return 'main_admin'
    member = current_staff()
    if member:
        # admin.db answers every time, so changing a row's level there reaches a
        # teacher who is already signed in.
        return staff_level(member)
    account = admin_account(session.get('staff_email'))
    level = str((account or {}).get('level') or '').strip().lower()
    return level if level in ADMIN_LEVELS else ''


def staff_email():
    """The address to stamp on a write, so a mark can be traced to its teacher."""
    user = current_user()
    if is_admin(user):
        return (user.email or '').strip().lower()
    member = current_staff()
    return (member.email or '').strip().lower() if member else ''


def staff_name(email=''):
    """Who an address belongs to, for a page that lists people by name."""
    address = str(email or '').strip().lower()
    if not address:
        return ''
    if address == ADMIN_EMAIL:
        return 'Main admin'
    member = Staff.query.filter(db.func.lower(Staff.email) == address).first()
    return member.name if member else address


def my_staff_email():
    """The signed-in staff's own address: main admin, admin, or teacher."""
    return staff_email() if admin_kind() else ''


def supervised_staff():
    """The Staff rows this signer is in charge of, in name order.

    The main admin owns every login, so they get the whole list. An admin gets
    the teachers written under them in admin.db plus anyone the main admin put
    under them, which is the small group their classes can be handed to.
    A teacher supervises nobody.
    """
    kind = admin_kind()
    if not kind:
        return []
    rows = Staff.query.order_by(db.func.upper(Staff.name)).all()
    if kind == 'main_admin':
        return rows
    owned = supervised_emails(my_staff_email())
    if not owned:
        return []
    return [row for row in rows
            if str(row.email or '').strip().lower() in owned
            and staff_level(row) == 'teacher']


def assignable_staff():
    """The teachers the Classes page may hand a class, subjects and schedule to.

    The main admin owns every login. An admin reaches only the teachers written
    under them - a class is handed to the signer's own teachers and nobody
    else's. Teacher level only - a class is never handed onto another admin
    or the owner.
    """
    rows = Staff.query.order_by(db.func.upper(Staff.name)).all()
    if at_least('main_admin'):
        return rows
    owned = supervised_emails(my_staff_email())
    return [row for row in rows
            if str(row.email or '').strip().lower() in owned
            and staff_level(row) == 'teacher']


def supervised_emails_of(address):
    """The teachers one address is in charge of, read straight from admin.db.

    The same rule the Staff page and the Classes pickers use, written for any
    address rather than the signed-in one, so a profile page can show somebody
    else's group.
    """
    level = str((admin_account(address) or {}).get('level') or '').strip().lower()
    rows = Staff.query.order_by(db.func.upper(Staff.name)).all()
    if level == 'main_admin':
        return [row for row in rows if staff_level(row) != 'main_admin']
    if level != 'admin':
        return []
    owned = supervised_emails(address)
    return [row for row in rows
            if str(row.email or '').strip().lower() in owned
            and staff_level(row) == 'teacher']


def member_classes(staff_id):
    """Every class handed to one Staff row, with its subjects and schedule.

    The schedule is the teacher's own days and time on the assignment. A class
    handed before assignments grew a schedule still shows the section's.
    """
    out = []
    for row in TeacherClass.query.filter_by(staff_id=staff_id) \
            .order_by(TeacherClass.grade, TeacherClass.section).all():
        section = SectionLevel.query.filter_by(
            grade=row.grade, name=norm_section(row.section)).first()
        own = schedule_label(row)
        out.append({'grade': row.grade, 'section': norm_section(row.section),
                    'subjects': split_subjects(row.subjects),
                    'room': row.room or (section.room if section else ''),
                    'schedule': own or (schedule_label(section) if section else ''),
                    'slots': (iter_slots(row) if own
                              else (iter_slots(section) if section else [])),
                    'assignment': row})
    return out


def staff_profile(address):
    """What a staff profile shows: the level, the powers, the people, the classes.

    One address in admin.db and one Staff row are the same person, so the page
    reads both: admin.db answers the level and the supervision, the Staff row
    answers the name and the classes handed on the Classes page.
    """
    address = str(address or '').strip().lower()
    member = Staff.query.filter(db.func.lower(Staff.email) == address).first()
    level = staff_level(member) if member else \
        str((admin_account(address) or {}).get('level') or '').strip().lower()
    if level not in ADMIN_LEVELS:
        level = 'teacher'
    classes = member_classes(member.id) if member else []
    return {
        'email': address,
        'name': member.name if member else staff_name(address),
        'level': level,
        'caps': [cap_label(cap) for cap in roles_for(level)],
        'boss': supervisor_of(address),
        'boss_name': staff_name(supervisor_of(address)),
        'teachers': [{'member': row, 'level': staff_level(row),
                      'classes': member_classes(row.id)}
                     for row in supervised_emails_of(address)],
        'classes': classes,
        'week': classes_week(classes),
        'joined': member.created_at if member and member.created_at else None,
    }


def role_can(capability, kind=None):
    """True when admin.db lists this capability for the signed-in staff level."""
    kind = admin_kind() if kind is None else kind
    return caps_match(capability, roles_for(kind))


@app.context_processor
def inject_admin_flag():
    user = current_user()
    kind = admin_kind(user)
    return {
        'is_admin': kind == 'main_admin',
        'is_staff': bool(kind),
        'admin_level': kind,
        'staff_user': current_staff(),
        'admin_roles': [cap_label(c) for c in roles_for(kind)],
        'can': lambda capability: role_can(capability, kind),
        'can_reach': at_least,
        'can_summative': role_can('create_summative_tests', kind),
    }


@app.template_filter('section_name')
def section_name(value):
    """A section is shown the same way wherever it appears: upper case, one space."""
    return norm_section(value)


def login_required_json(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'not_logged_in'}), 401
        return f(*args, **kwargs)
    return wrapper


def at_least(level):
    """True when the signed-in staff sits at this admin.db level or above."""
    def rank(kind):
        return ADMIN_LEVELS.index(kind) if kind in ADMIN_LEVELS else -1
    return rank(admin_kind()) >= rank(level)


def level_required(level):
    """A gate on one admin.db level: admin reaches what admin may, teacher what teacher may."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if at_least(level):
                return f(*args, **kwargs)
            return redirect(url_for('home') if session.get('user_id') else url_for('admin_login'))
        return wrapper
    return decorator


def staff_required(f):
    """Any staff level may reach this page: teacher, admin, or the owner."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if admin_kind():
            return f(*args, **kwargs)
        # A learner who typed the address goes home; an empty session goes to
        # the teacher door, not the student one.
        return redirect(url_for('home') if session.get('user_id') else url_for('admin_login'))
    return wrapper


def main_admin_required(f):
    """Only the main_admin row in admin.db: learner accounts and more staff."""
    return level_required('main_admin')(f)


# Kept as a name so the older pages read clearly: admin means the main admin here.
admin_required = main_admin_required


def parse_date(value):
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.utcnow()


# --- ROUTES ---
@app.route('/')
def index():
    return redirect(url_for('home'))


@app.route('/sw.js')
def serve_sw():
    resp = send_from_directory('.', 'sw.js')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/home')
def home():
    """The learner landing page. Staff get their own door at /staff/home."""
    if admin_kind():
        return redirect(url_for('staff_home'))
    return render_template('home.html', user=current_user())


@app.route('/staff/home')
def staff_home():
    """The staff landing page - main admin, admin or teacher.

    Kept apart from the learner home so a teacher never lands on quiz buttons
    and a student never sees the managing side of the app.
    """
    if not admin_kind():
        return redirect(url_for('home'))
    kind = admin_kind()
    member = current_staff()
    user = current_user()
    name = member.name if member else (
        user.full_name() if user else staff_name(my_staff_email()))
    today = datetime.now().strftime('%a')
    meetings = []
    if member or kind == 'main_admin':
        address = my_staff_email()
        rows = Staff.query.filter(db.func.lower(Staff.email) == address).all()
        for row in rows:
            for cls in member_classes(row.id):
                for days, start, end in cls['slots']:
                    if today in days and start:
                        meetings.append({
                            'grade': cls['grade'], 'section': cls['section'],
                            'subjects': ', '.join(cls['subjects']),
                            'room': room_label(cls['room']),
                            'start': start, 'end': end})
    meetings.sort(key=lambda m: m['start'])
    halt = non_class_note()
    if halt:
        meetings = []
    return render_template('staff_home.html', kind=kind, name=name,
                           meetings=meetings, halt=halt)


# --- PDF STUDIO (staff-only PDF and picture tools, run on the server) ---
# pdf_tools.py holds the same 17 jobs the desktop window in pdf_studio.py draws.
# A run gets its own folder under pdf_jobs/ (uploads in, results out) and the
# page is handed a download link. Nothing is kept for good: the sweep removes a
# folder after two hours, and the download route is behind the staff door too.
PDF_STUDIO_DIR = os.path.join(basedir, 'pdf_jobs')
PDF_STUDIO_KEEP_MINUTES = 120
PDF_STUDIO_MAX_FILES = 40
PDF_STUDIO_MAX_BYTES = 200_000_000
app.config['MAX_CONTENT_LENGTH'] = PDF_STUDIO_MAX_BYTES
PDF_STUDIO_TOKEN = re.compile(r'^[0-9a-f]{24}$')


def pdf_studio_catalogue():
    """The TOOLS list as plain data, so the page can draw its own form."""
    return [{
        'name': tool.name,
        'blurb': tool.blurb,
        'needs': tool.needs,
        'many': tool.many,
        'batch': tool.batch,
        'ordered': tool.ordered,
        'writes': tool.writes,
        'outExt': tool.out_ext,
        'fields': [{
            'key': field.key,
            'kind': field.kind,
            'label': field.label,
            'default': '' if field.default is None else str(field.default),
            'choices': list(field.choices or ()),
            'help': field.help_text,
        } for field in tool.fields],
    } for tool in PDF_STUDIO.TOOLS]


def pdf_studio_sweep():
    """Drop old workspaces so a shared host does not keep every run for ever."""
    cutoff = time.time() - PDF_STUDIO_KEEP_MINUTES * 60
    try:
        names = os.listdir(PDF_STUDIO_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(PDF_STUDIO_DIR, name)
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def pdf_studio_log(lines):
    """The last part of a job's running commentary, small enough to post back."""
    kept = [line for line in lines if line][-200:]
    return '\n'.join(kept)[-20000:]


def pdf_studio_public(text, out_dir, label):
    """Take the server's own folder out of a job's wording before it is shown."""
    if not text:
        return text
    return text.replace(out_dir + os.sep, '').replace(out_dir, label)


@app.route('/staff/pdf-studio')
@staff_required
def pdf_studio():
    """Every PDF job the staff can run, drawn from pdf_tools.TOOLS."""
    return render_template(
        'pdf_studio.html',
        ready=PDF_STUDIO_READY,
        tools=pdf_studio_catalogue() if PDF_STUDIO_READY else [],
        max_files=PDF_STUDIO_MAX_FILES,
        max_mb=PDF_STUDIO_MAX_BYTES // 1_000_000,
        keep_hours=PDF_STUDIO_KEEP_MINUTES // 60,
    )


@app.route('/staff/pdf-studio/run', methods=['POST'])
@staff_required
def pdf_studio_run():
    """Take the uploaded files and choices, run one tool, offer the result.

    Uploads and results live in PDF_STUDIO_DIR/<token>/; a single result is
    served as itself, several are zipped together, and the file report (which
    writes nothing) answers with its text instead.
    """
    if not PDF_STUDIO_READY:
        return jsonify(ok=False, error='PDF Studio is not installed on this '
                                       'server. Ask the main admin to install '
                                       'requirements.txt.'), 503

    tool = PDF_STUDIO.tool_named(request.form.get('tool', ''))
    if tool is None:
        return jsonify(ok=False, error='Pick a tool first.'), 400

    if request.content_length and request.content_length > PDF_STUDIO_MAX_BYTES:
        return jsonify(ok=False, error='That upload is over %d MB.'
                       % (PDF_STUDIO_MAX_BYTES // 1_000_000)), 413

    uploads = [item for item in request.files.getlist('files') if item and item.filename]
    if not uploads:
        return jsonify(ok=False, error='Add at least one file.'), 400
    if len(uploads) > PDF_STUDIO_MAX_FILES:
        return jsonify(ok=False, error='That is %d files; %d is the most one run '
                                       'takes.' % (len(uploads), PDF_STUDIO_MAX_FILES)), 400

    allowed = ('.pdf',) if tool.needs == 'pdf' else PDF_STUDIO.IMAGES
    wrong = [item.filename for item in uploads
             if os.path.splitext(item.filename)[1].lower() not in allowed]
    if wrong:
        wanted = 'PDFs' if tool.needs == 'pdf' else 'pictures (PNG, JPG, JFIF...)'
        return jsonify(ok=False, error='%s works on %s only. %s is not one.'
                       % (tool.name, wanted, os.path.basename(wrong[0]))), 400

    pdf_studio_sweep()
    token = secrets.token_hex(12)
    work = os.path.join(PDF_STUDIO_DIR, token)
    src_dir = os.path.join(work, 'in')
    out_dir = os.path.join(work, 'out')
    logs = []
    files = []

    try:
        os.makedirs(src_dir)
        os.makedirs(out_dir)
        total = 0
        for position, upload in enumerate(uploads, 1):
            ext = os.path.splitext(upload.filename)[1].lower()
            stem = secure_filename(os.path.splitext(upload.filename)[0])[:80] \
                or 'file-%d' % position
            path = os.path.join(src_dir, stem + ext)
            copy = 2
            while os.path.exists(path):
                path = os.path.join(src_dir, '%d-%s%s' % (copy, stem, ext))
                copy += 1
            upload.save(path)
            files.append(path)
            total += os.path.getsize(path)
        if total > PDF_STUDIO_MAX_BYTES:
            raise ValueError('Those files add up to over %d MB.'
                             % (PDF_STUDIO_MAX_BYTES // 1_000_000))

        # Only the tool's own boxes become options; "Save as" is never posted -
        # the server chooses the workspace, so a job cannot write anywhere else.
        opt = PDF_STUDIO.defaults(tool)
        for field in tool.fields:
            if field.key in request.form:
                opt[field.key] = request.form.get(field.key, '')
        opt['out'] = out_dir

        message = tool.run(files, opt, logs.append)
        shutil.rmtree(src_dir, ignore_errors=True)   # the results are all that is needed now

        made = []
        for root, _dirs, names in os.walk(out_dir):
            for name in sorted(names):
                made.append(os.path.join(root, name))

        if not made:
            shutil.rmtree(work, ignore_errors=True)
            return jsonify(ok=True, message=message,
                           log=pdf_studio_public(pdf_studio_log(logs), out_dir,
                                                 'the server'))

        if len(made) == 1:
            # One plain name at the top of the workspace keeps the link simple.
            flat = os.path.join(work, os.path.basename(made[0]))
            if os.path.abspath(made[0]) != os.path.abspath(flat):
                shutil.move(made[0], flat)
            name = os.path.basename(flat)
        else:
            name = '%s - pdf studio.zip' % (PDF_STUDIO.stem_of(files[0]) or 'results')

        log_text = pdf_studio_public(pdf_studio_log(logs), out_dir, 'the download')
        message = pdf_studio_public(message, out_dir, name)

        if len(made) > 1:
            with zipfile.ZipFile(os.path.join(work, name), 'w', zipfile.ZIP_DEFLATED) as bundle:
                for path in made:
                    bundle.write(path, os.path.relpath(path, out_dir))
                bundle.writestr('what happened.txt',
                                '%s\n%s\n\n%s\n' % (tool.name, message, log_text))
        shutil.rmtree(out_dir, ignore_errors=True)

        return jsonify(ok=True, message=message, log=log_text,
                       download=url_for('pdf_studio_file', token=token, name=name),
                       filename=name)
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        return jsonify(ok=False, error=str(exc) or exc.__class__.__name__,
                       log=pdf_studio_public(pdf_studio_log(logs), out_dir,
                                             'the download')), 400


@app.route('/staff/pdf-studio/files/<token>/<name>')
@staff_required
def pdf_studio_file(token, name):
    """One result from a run; the staff session is checked before it is served."""
    if not PDF_STUDIO_TOKEN.match(token):
        abort(404)
    base = os.path.join(PDF_STUDIO_DIR, token)
    path = os.path.join(base, name)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(base, name, as_attachment=True)


@app.errorhandler(413)
def upload_too_large(_error):
    """Flask's own ceiling, answered in the studio's language when it is the studio."""
    if request.path.startswith('/staff/pdf-studio'):
        return jsonify(ok=False, error='That upload is over %d MB.'
                       % (PDF_STUDIO_MAX_BYTES // 1_000_000)), 413
    return 'That upload is too large.', 413


@app.route('/quiz_setup')
def quiz_setup():
    user = current_user()
    return render_template('quiz_setup.html', spec_json=spec_json(), user=user)


@app.route('/quiz')
def quiz():
    level = request.args.get('level', '').strip()
    subject = request.args.get('subject', '').strip()
    quarter = request.args.get('quarter', '').strip()
    topic = request.args.get('topic', '').strip()
    if quarter == '__all__':
        quarter = ''

    user = current_user()
    user_json = {}
    if user:
        user_json = {
            'name': user.full_name(),
            'school': user.school,
            'grade': user.grade,
            'section': user.section,
        }
    return render_template(
        'quiz.html',
        user=user,
        user_json=user_json,
        level=level,
        subject=subject,
        quarter=quarter or 'All Quarters',
        topic=topic or 'All Topics',
    )


@app.route('/api/questions/<level>/<subject>')
def api_questions(level, subject):
    level = level.strip()
    subject = subject.strip()
    items = [
        q for q in QUESTIONS
        if q['level'].lower() == level.lower() and q['subject'].lower() == subject.lower()
    ]
    return jsonify(items)


# --- AUTH ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user_id'):
        return redirect(url_for('home'))

    errors = {}
    form = {}

    if request.method == 'POST':
        form = {
            'first_name': request.form.get('first_name', '').strip(),
            'middle_name': request.form.get('middle_name', '').strip(),
            'last_name': request.form.get('last_name', '').strip(),
            'suffix': request.form.get('suffix', 'N/A').strip() or 'N/A',
            'school': request.form.get('school', '').strip(),
            'grade': request.form.get('grade', '').strip(),
            'section': norm_section(request.form.get('section', '')),
            'email': request.form.get('email', '').strip().lower(),
            'password': request.form.get('password', ''),
            'confirm_password': request.form.get('confirm_password', ''),
        }

        if not form['first_name']:
            errors['first_name'] = 'First Name is required.'
        if not form['last_name']:
            errors['last_name'] = 'Last Name is required.'
        if form['suffix'] not in SUFFIX_CHOICES:
            errors['suffix'] = 'Invalid suffix.'
        if not form['school']:
            errors['school'] = 'School is required.'
        if form['grade'] not in grade_choices():
            errors['grade'] = 'Grade is required.'
        # A learner can only pick a section the main admin created, which is
        # what stops the section list from growing on its own.
        elif not form['section']:
            errors['section'] = 'Section is required.'
        elif form['section'] not in section_choices_for(form['grade']):
            errors['section'] = 'Pick your section from the list.'
        if not form['email'] or '@' not in form['email'] or '.' not in form['email'].split('@')[-1]:
            errors['email'] = 'A valid Email is required.'
        if len(form['password']) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif form['password'] != form['confirm_password']:
            errors['confirm_password'] = 'Passwords do not match.'

        # The same address typed with different capitals is the same person.
        existing = User.query.filter(db.func.lower(User.email) == form['email']).first()

        if not errors and existing and existing.password_hash:
            errors['email'] = 'That email is already registered. Try logging in instead.'

        if not errors:
            if existing:
                # Account row left by the old version, which stored no password.
                # The person registering now claims it and keeps its history.
                user = existing
            else:
                user = User(email=form['email'])
                db.session.add(user)
            user.first_name = tidy_name(form['first_name'])
            user.middle_name = tidy_name(form['middle_name']) or None
            user.last_name = tidy_name(form['last_name'])
            user.suffix = form['suffix']
            user.school = form['school']
            user.grade = form['grade']
            user.section = form['section']
            user.password_hash = generate_password_hash(form['password'])
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                app.logger.exception('Could not create account for %s', form['email'])
                errors['database'] = 'Could not save your account. Please try again.'
            else:
                session.clear()
                session['user_id'] = user.id
                session['user_email'] = user.email
                session.permanent = True
                return redirect(url_for('home'))

    return render_template(
        'signup.html',
        errors=errors,
        form=form,
        suffix_choices=SUFFIX_CHOICES,
        grade_choices=grade_choices(),
        section_choices=class_choices(),
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('home'))

    error = None
    notice = None
    email = ''
    if request.args.get('reset') == '1':
        notice = 'Password changed. Log in with your new one.'
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            session.clear()
            session['user_id'] = user.id
            session['user_email'] = user.email
            session.permanent = remember
            return redirect(url_for('home'))
        error = 'Invalid email or password.'

    return render_template('login.html', error=error, notice=notice, email=email)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# --- ADMIN LOGIN (teachers use this door, learners use /login) ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Sign in as any level admin.db lists: main_admin, admin or teacher.

    admin.db is enough on its own - a row there needs no matching sign-up first,
    so handing someone a login means one line in that file. The old doors still
    work: the User account angelesedgardo17@gmail.com signed up with, and every
    Staff row handed out on the Staff page.
    """
    if admin_kind():
        return redirect(url_for('staff_home'))

    error = None
    email = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        owner = User.query.filter(db.func.lower(User.email) == email).first()
        if is_admin(owner) and owner.password_hash and check_password_hash(owner.password_hash, password):
            session.clear()
            session['user_id'] = owner.id
            session['user_email'] = owner.email
            session.permanent = remember
            return redirect(url_for('staff_home'))

        account = admin_account(email)
        if account and str(account.get('password') or '') == password:
            member = Staff.query.filter(db.func.lower(Staff.email) == email).first()
            if member is None:
                member = Staff(
                    name=tidy_name(email.split('@')[0]), email=email,
                    password_hash=generate_password_hash(password),
                    created_by='admin.db')
                db.session.add(member)
                db.session.commit()
            elif not check_password_hash(member.password_hash or '', password):
                member.password_hash = generate_password_hash(password)
                db.session.commit()
            session.clear()
            session['staff_id'] = member.id
            session['staff_email'] = member.email
            session.permanent = remember
            return redirect(url_for('staff_home'))

        member = Staff.query.filter(db.func.lower(Staff.email) == email).first()
        if member and check_password_hash(member.password_hash, password):
            session.clear()
            session['staff_id'] = member.id
            session['staff_email'] = member.email
            session.permanent = remember
            return redirect(url_for('staff_home'))

        error = 'That email and password did not match a staff account.'

    return render_template('admin_login.html', error=error, email=email)


@app.route('/admin/staff', methods=['GET', 'POST'])
@level_required('admin')
def admin_staff():
    """The page that hands out staff logins - it writes straight into admin.db.

    Every row here is an `accounts` row in admin.db plus the `staff` row the rest
    of the app reads, so a person added here can sign in at /admin/login at the
    level chosen, and removing them takes both away.

    The main admin runs the whole list and decides who answers to whom. An admin
    sees only the teachers written under them and may give one of those teachers
    a login of their own or reset its password - never a higher level, and never
    somebody else's teacher.
    """
    owner = at_least('main_admin')
    boss = my_staff_email()
    errors = {}
    message = None
    form = {'name': '', 'email': '', 'level': 'teacher', 'supervisor': boss}

    def listed(member):
        """One row of this page's list, or None when this signer may not see it."""
        level = staff_level(member)
        if level == 'main_admin':
            return None
        if not owner and supervisor_of(member.email) != boss:
            return None
        return {'member': member, 'level': level,
                'boss': supervisor_of(member.email),
                'caps': ', '.join(cap_label(c) for c in roles_for(level))}

    if request.method == 'POST':
        action = (request.form.get('action') or 'add').strip()

        if action == 'add':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            level = (request.form.get('level') or 'teacher').strip().lower()
            supervisor = (request.form.get('supervisor') or '').strip().lower()
            # main_admin is not handed out here: a second owner is written in
            # admin.db by hand, so the Staff page can never list - or remove -
            # the row the whole school depends on. And an admin may only ever
            # hand out a teacher, who lands under them by default.
            if not owner:
                level, supervisor = 'teacher', boss
            else:
                level = level if level in HANDOUT_LEVELS else 'teacher'
            if level != 'teacher':
                # Only a teacher answers to somebody; an admin is the main admin's.
                supervisor = ''
            form = {'name': name, 'email': email, 'level': level, 'supervisor': supervisor}

            if not name:
                errors['name'] = 'Type the teacher\'s name.'
            if not email or '@' not in email or '.' not in email.split('@')[-1]:
                errors['email'] = 'A valid email is required.'
            if len(password) < 8:
                errors['password'] = 'A password needs at least 8 characters.'

            if not errors:
                if email == ADMIN_EMAIL:
                    errors['email'] = 'That is the main admin account, it needs no staff login.'
                elif Staff.query.filter(db.func.lower(Staff.email) == email).first():
                    errors['email'] = 'That teacher already has a staff login.'
                elif User.query.filter(db.func.lower(User.email) == email).first():
                    # One address must mean one person, or the admin login could
                    # not tell a teacher from a learner who signed up with it.
                    errors['email'] = 'A student account already uses that email.'
                elif supervisor and str((admin_account(supervisor) or {}).get('level')
                                        or '') != 'admin':
                    errors['supervisor'] = 'Pick an admin from the list, or leave it ' \
                                           'with the main admin.'

            if not errors:
                db.session.add(Staff(
                    name=tidy_name(name), email=email,
                    password_hash=generate_password_hash(password),
                    created_by=boss))
                db.session.commit()
                set_admin_account(email, password, level, supervisor)
                message = 'Gave %s an %s login. Use its password to sign in at /admin/login.' % (
                    tidy_name(name), level.replace('_', ' '))
                if supervisor:
                    message += ' %s answers to %s.' % (tidy_name(name), staff_name(supervisor))

        elif action == 'password':
            member = db.session.get(Staff, int(request.form.get('id') or 0))
            password = request.form.get('password', '')
            if not member or not listed(member):
                errors['password'] = 'That teacher is no longer on your list.'
            elif len(password) < 8:
                errors['password'] = 'A new password needs at least 8 characters.'
            else:
                member.password_hash = generate_password_hash(password)
                db.session.commit()
                set_admin_account(member.email, password)
                message = 'Set a new password for %s.' % member.name

        elif action == 'level':
            member = db.session.get(Staff, int(request.form.get('id') or 0))
            level = (request.form.get('level') or '').strip().lower()
            if not owner:
                errors['level'] = 'Only the main admin can change a role.'
            elif not member or staff_level(member) == 'main_admin':
                errors['level'] = 'That teacher is no longer on the list.'
            elif level not in HANDOUT_LEVELS:
                errors['level'] = 'Choose teacher or admin; a second main admin is written in admin.db.'
            else:
                # A teacher promoted to admin goes back to the main admin's own list.
                set_admin_account(member.email, level=level,
                                  supervisor='' if level != 'teacher' else None)
                message = '%s is now a %s.' % (member.name, level.replace('_', ' '))

        elif action == 'supervisor':
            member = db.session.get(Staff, int(request.form.get('id') or 0))
            supervisor = (request.form.get('supervisor') or '').strip().lower()
            if not owner:
                errors['supervisor'] = 'Only the main admin decides who a teacher answers to.'
            elif not member or staff_level(member) != 'teacher':
                errors['supervisor'] = 'Only a teacher is placed under somebody.'
            elif supervisor and (supervisor == str(member.email or '').strip().lower()
                                 or str((admin_account(supervisor) or {}).get('level')
                                        or '') != 'admin'):
                errors['supervisor'] = 'Pick an admin from the list, or leave it with the main admin.'
            else:
                set_supervisor(member.email, supervisor)
                message = '%s now answers to %s.' % (
                    member.name, staff_name(supervisor) if supervisor else 'the main admin')

        elif action == 'remove':
            member = db.session.get(Staff, int(request.form.get('id') or 0))
            if not owner:
                errors['remove'] = 'Only the main admin can take away a login.'
            elif not member or staff_level(member) == 'main_admin':
                errors['remove'] = 'That teacher is already gone.'
            elif not listed(member):
                errors['remove'] = 'That teacher is not on your list.'
            else:
                name, email = member.name, member.email
                db.session.delete(member)
                db.session.commit()
                remove_admin_account(email)
                message = 'Took away the login for %s. Signed-out devices still work until ' \
                          'they sign in again.' % name

    rows = [listed(m) for m in Staff.query.order_by(db.func.upper(Staff.name)).all()]
    members = [row for row in rows if row]
    groups = None
    if owner:
        # The main admin sees the ladder, not a flat pile: every admin under
        # them, the teachers answering to each of those admins, and last the
        # teachers the main admin holds personally.
        admin_rows = [row for row in members if row['level'] == 'admin']
        teacher_rows = [row for row in members if row['level'] != 'admin']
        boss_emails = {str(row['member'].email or '').strip().lower()
                       for row in admin_rows}
        groups = []
        for arow in admin_rows:
            boss = str(arow['member'].email or '').strip().lower()
            groups.append({'admin': arow, 'boss': boss,
                           'teachers': [t for t in teacher_rows if t['boss'] == boss]})
        held = [t for t in teacher_rows if t['boss'] not in boss_emails]
        if held:
            groups.append({'admin': None, 'boss': '', 'teachers': held})
    return render_template(
        'admin_staff.html',
        # A row admin.db lists as main_admin is the owner's own login, not a teacher's.
        members=members,
        groups=groups,
        # The names a teacher can be placed under: every admin.db login at admin.
        admins=[{'email': str(row.get('email') or ''),
                 'name': staff_name(row.get('email'))}
                for row in admin_accounts('admin')],
        owner=owner,
        levels=list(reversed(HANDOUT_LEVELS)) if owner else ['teacher'],
        errors=errors, message=message, form=form,
    )


@app.route('/admin/classes', methods=['GET', 'POST'])
@level_required('admin')
def admin_classes():
    """The school's class list: the grades, the sections under each, and the
    teachers handed them.

    Every picker in the app reads these two lists, so a learner can never type a
    new spelling of a section and a teacher can only open what is assigned here.

    An admin may hand one of their own teachers a class, its subjects and the
    schedule; the teachers under another admin are not theirs to move. The
    grade and section list itself stays the main admin's, so one class cannot
    grow two spellings, and so does the school-wide no-class day: a date with a
    note like "no classes, it is a non-working holiday" halts every class
    notification for that day.
    """
    owner = at_least('main_admin')
    errors = {}
    message = None

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action in REGISTRY_ACTIONS and not owner:
            errors['registry'] = 'The main admin owns the grade and section list. You may hand ' \
                                 'your own teachers a class, subject and schedule.'
            action = ''

        if action == 'add_grade':
            name = ' '.join((request.form.get('name') or '').split())
            if not name:
                errors['add_grade'] = 'Type the grade level, for example Grade 11.'
            elif len(name) > 40:
                errors['add_grade'] = 'A grade name is at most 40 characters.'
            elif GradeLevel.query.filter(db.func.upper(GradeLevel.name)
                                         == norm_section(name)).first():
                errors['add_grade'] = 'That grade level is already on the list.'
            else:
                db.session.add(GradeLevel(name=name))
                db.session.commit()
                message = 'Created %s. Add its sections, then assign a teacher.' % name

        elif action == 'rename_grade':
            row = db.session.get(GradeLevel, int(request.form.get('id') or 0))
            name = ' '.join((request.form.get('name') or '').split())
            if not row:
                errors['grade'] = 'That grade level is no longer on the list.'
            elif not name or len(name) > 40:
                errors['grade'] = 'A grade name is between 1 and 40 characters.'
            elif name == row.name:
                message = '%s stayed as it is.' % name
            else:
                old = row.name
                row.name = name
                rename_grade_rows(old, name)
                db.session.commit()
                message = 'Renamed %s to %s. Its learners, scores and materials moved with it.' % (old, name)

        elif action == 'delete_grade':
            row = db.session.get(GradeLevel, int(request.form.get('id') or 0))
            if not row:
                errors['grade'] = 'That grade level is already gone.'
            elif SectionLevel.query.filter_by(grade=row.name).count():
                errors['grade'] = 'Remove its sections first - a grade holds a class, not the other way round.'
            elif learners_in(row.name):
                errors['grade'] = 'Learners are still in %s. Move them to another grade first.' % row.name
            else:
                name = row.name
                db.session.delete(row)
                db.session.commit()
                message = 'Removed %s from the list.' % name

        elif action == 'add_section':
            grade = (request.form.get('grade') or '').strip()
            name = norm_section(request.form.get('name'))
            if grade not in grade_choices():
                errors['add_section'] = 'Create the grade level first, then add its section.'
            elif not name or len(name) > 40:
                errors['add_section'] = 'A section name is between 1 and 40 characters, like ORION.'
            elif SectionLevel.query.filter_by(grade=grade, name=name).first():
                errors['add_section'] = '%s already has a section named %s.' % (grade, name)
            else:
                db.session.add(SectionLevel(grade=grade, name=name))
                db.session.commit()
                message = 'Created %s %s. It is in every section picker now.' % (grade, name)

        elif action == 'rename_section':
            row = db.session.get(SectionLevel, int(request.form.get('id') or 0))
            name = norm_section(request.form.get('name'))
            if not row:
                errors['section'] = 'That section is no longer on the list.'
            elif not name or len(name) > 40:
                errors['section'] = 'A section name is between 1 and 40 characters.'
            elif name == row.name:
                message = '%s stayed as it is.' % name
            elif SectionLevel.query.filter_by(grade=row.grade, name=name).first():
                errors['section'] = '%s already has a section named %s.' % (row.grade, name)
            else:
                old = row.name
                row.name = name
                rename_section_rows(row.grade, old, name)
                db.session.commit()
                message = 'Renamed %s to %s in %s. Its learners and scores moved with it.' % (
                    old, name, row.grade)

        elif action == 'delete_section':
            row = db.session.get(SectionLevel, int(request.form.get('id') or 0))
            if not row:
                errors['section'] = 'That section is already gone.'
            elif learners_in(row.grade, row.name):
                errors['section'] = ('%s learners are still in %s %s. Edit them on the Assessment '
                                     'page and move them to another section first.' % (
                                         learners_in(row.grade, row.name), row.grade, row.name))
            elif materials_in(row.grade, row.name):
                errors['section'] = '%s still has materials posted to it. Remove those first.' % row.name
            else:
                name = row.name
                grade = row.grade
                TeacherClass.query.filter_by(grade=grade, section=name).delete()
                db.session.delete(row)
                db.session.commit()
                message = 'Removed %s %s. Teachers lost that class too.' % (grade, name)

        elif action == 'merge_section':
            row = db.session.get(SectionLevel, int(request.form.get('id') or 0))
            into = norm_section(request.form.get('into'))
            if not row:
                errors['merge'] = 'That section is no longer on the list.'
            elif not into or into == row.name or \
                    into not in section_choices_for(row.grade):
                errors['merge'] = 'Pick another section of the same grade to fold it into.'
            else:
                old = row.name
                grade = row.grade
                moved = learners_in(grade, old)
                move_class_rows(grade, old, into)
                move_class_teachers(grade, old, into)
                db.session.delete(row)
                db.session.commit()
                message = ('Folded %s %s into %s: %s learners with their scores and '
                           'materials now read as one class.' % (grade, old, into, moved))

        elif action == 'set_schedule':
            row = db.session.get(SectionLevel, int(request.form.get('id') or 0))
            saved, error = posted_schedule(request)
            if not row:
                errors['schedule'] = 'That section is no longer on the list.'
            elif error:
                errors['schedule'] = error
            else:
                save_schedule(row, saved, posted_room(request))
                db.session.commit()
                label = schedule_label(row)
                message = ('Saved %s %s as %s.' % (row.grade, row.name, label) if label
                           else 'Cleared the schedule of %s %s.' % (row.grade, row.name))

        elif action == 'set_assignment_schedule':
            row = db.session.get(TeacherClass, int(request.form.get('id') or 0))
            saved, error = posted_schedule(request)
            if not row:
                errors['schedule'] = 'That teacher assignment is no longer on the list.'
            elif error:
                errors['schedule'] = error
            else:
                save_schedule(row, saved, posted_room(request))
                db.session.commit()
                member = db.session.get(Staff, row.staff_id)
                label = schedule_label(row)
                message = ('Saved %s %s for %s as %s.' % (
                    row.grade, row.section, member.name if member else 'that teacher', label)
                    if label else 'Cleared the schedule of that teacher\'s class.')

        elif action == 'assign':
            member = db.session.get(Staff, int(request.form.get('staff_id') or 0))
            grade = (request.form.get('grade') or '').strip()
            # The section picker is a checklist now, so one submit can hand the
            # same subjects and time to several sections at once.
            sections = []
            for name in request.form.getlist('sections'):
                key = norm_section(name)
                if key and key not in sections:
                    sections.append(key)
            subjects = tidy_subjects(grade, request.form.getlist('subjects'))
            saved, error = posted_schedule(request)
            room = posted_room(request)
            owned = {row.id for row in assignable_staff()}
            if not member or member.id not in owned:
                errors['assign'] = 'Pick one of the teacher logins to assign.'
            elif not sections:
                errors['assign'] = 'Tick at least one section to assign.'
            elif any(name not in section_choices_for(grade) for name in sections):
                errors['assign'] = 'Pick classes that are on this page.'
            elif error:
                errors['assign'] = error
            else:
                added, kept = [], []
                for section in sections:
                    row = TeacherClass.query.filter_by(
                        staff_id=member.id, grade=grade, section=section).first()
                    if row:
                        row.subjects = ','.join(subjects)
                        save_schedule(row, saved, room)
                        kept.append(section)
                    else:
                        row = TeacherClass(
                            staff_id=member.id, grade=grade, section=section,
                            subjects=','.join(subjects), assigned_by=staff_email())
                        save_schedule(row, saved, room)
                        db.session.add(row)
                        added.append(section)
                db.session.commit()
                if added and kept:
                    message = 'Assigned %s %s to %s, and saved %s again.' % (
                        grade, ' / '.join(added), member.name, ', '.join(kept))
                elif added:
                    message = 'Assigned %s %s to %s.' % (
                        grade, ' / '.join(added), member.name)
                else:
                    message = 'Saved %s %s for %s.' % (
                        grade, ' / '.join(kept), member.name)
                if subjects:
                    message += ' They teach %s there.' % ', '.join(subjects)
                else:
                    # With no subject ticked the teacher still owns the classes,
                    # they simply keep the whole grade to pick from.
                    message += ' No subject ticked, so every subject is open.'
                if saved:
                    message += ' Their class meets %s.' % '; '.join(
                        slot_label(*slot) for slot in saved)
                if room_label(room):
                    message += ' In %s.' % room_label(room)
                notes = clash_notes(member.id)
                if notes:
                    message += ' WARNING - time clash: %s.' % '; '.join(notes)

        elif action == 'unassign':
            row = db.session.get(TeacherClass, int(request.form.get('id') or 0))
            if not row:
                errors['assign'] = 'That assignment is already gone.'
            elif not owner and staff_level(db.session.get(Staff, row.staff_id)) != 'teacher':
                errors['assign'] = 'Only a teacher\'s handed class can be taken back here.'
            else:
                member = db.session.get(Staff, row.staff_id)
                db.session.delete(row)
                db.session.commit()
                message = 'Took %s %s away from %s.' % (
                    row.grade, row.section, member.name if member else 'that teacher')

        elif action == 'no_class':
            if not owner:
                errors['no_class'] = 'Only the main admin declares a school-wide no-class day.'
            else:
                day = (request.form.get('date') or '').strip()
                note = ' '.join((request.form.get('note') or '').split())
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                    errors['no_class'] = 'Pick the date of the no-class day.'
                elif not note:
                    errors['no_class'] = 'Write the note, for example: no classes, ' \
                                         'it is a non-working holiday.'
                elif len(note) > 200:
                    errors['no_class'] = 'The note is at most 200 characters.'
                else:
                    row = NonClassDay.query.filter_by(date=day).first()
                    if row:
                        row.note = note
                        row.created_by = my_staff_email() or row.created_by
                    else:
                        db.session.add(NonClassDay(date=day, note=note,
                                                   created_by=my_staff_email() or ''))
                    db.session.commit()
                    message = 'Saved for %s: %s Class notifications for that day are halted.' \
                              % (day, note)

        elif action == 'no_class_delete':
            if not owner:
                errors['no_class'] = 'Only the main admin can take back a no-class day.'
            else:
                row = db.session.get(NonClassDay, int(request.form.get('id') or 0))
                if row:
                    day = row.date
                    db.session.delete(row)
                    db.session.commit()
                    message = 'Removed the note for %s; class notifications run again that day.' \
                              % day

    grades = []
    for grade in GradeLevel.query.order_by(GradeLevel.id).all():
        sections = []
        for row in SectionLevel.query.filter_by(grade=grade.name).order_by(
                SectionLevel.name, SectionLevel.id).all():
            sections.append({
                'row': row,
                'learners': learners_in(grade.name, row.name),
                'materials': materials_in(grade.name, row.name),
                'teachers': class_teachers(grade.name, row.name),
                'schedule': schedule_label(row),
                'slots': iter_slots(row),
            })
        grades.append({'grade': grade, 'sections': sections,
                       'learners': learners_in(grade.name)})

    return render_template(
        'admin_classes.html',
        grades=grades,
        days=CLASS_DAYS,
        members=assignable_staff(),
        subjects={grade.name: grade_subjects(grade.name) for grade in
                  GradeLevel.query.order_by(GradeLevel.id).all()},
        no_class_days=NonClassDay.query.order_by(NonClassDay.date).all(),
        halt_today=non_class_note(),
        today=datetime.now().strftime('%Y-%m-%d'),
        owner=owner,
        errors=errors, message=message,
    )


# --- FORGOT PASSWORD (a code is sent to the student's own email) ---
RESET_MINUTES = 10
RESET_TRIES = 5
RESET_COOLDOWN_SECONDS = 60


def user_by_email(email):
    """The same address in any capitals belongs to the same student."""
    want = str(email or '').strip().lower()
    if not want:
        return None
    return User.query.filter(db.func.lower(User.email) == want).first()


def pending_reset(token):
    row = PasswordReset.query.filter_by(token=token).first()
    if not row or row.used_at:
        return None
    if row.expires_at <= datetime.utcnow():
        db.session.delete(row)
        db.session.commit()
        return None
    return row


def reset_email_body(code):
    return (
        'Your Review Hub Ph reset code is:\n\n'
        '    %s\n\n'
        'It works for %d minutes and can be used once. Enter it on the page that '
        'asked for it to finish changing your password.\n\n'
        'If you did not ask for this, nothing has been changed - just ignore this email.\n'
        % (code, RESET_MINUTES)
    )


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    errors = {}
    email = ''

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        user = user_by_email(email)

        if not user:
            errors['email'] = ('That email is not registered. Check the spelling, or '
                               'make an account on the Sign Up page.')
        if len(password) < 8:
            errors['password'] = 'The new password must be at least 8 characters.'
        elif password != confirm:
            errors['confirm_password'] = 'The two new passwords do not match.'

        if not errors:
            last = PasswordReset.query.filter_by(email=user.email).order_by(
                PasswordReset.id.desc()).first()
            if last and not last.used_at and \
                    (datetime.utcnow() - last.created_at).total_seconds() < RESET_COOLDOWN_SECONDS:
                errors['email'] = ('A code was just sent. Wait about a minute before '
                                   'asking for another one.')

        if not errors:
            # Any older request for this address is dropped, so only the code the
            # student is about to receive can be used.
            for stale in PasswordReset.query.filter(
                    PasswordReset.email == user.email,
                    PasswordReset.used_at.is_(None)).all():
                db.session.delete(stale)

            code = '%06d' % secrets.randbelow(1_000_000)
            row = PasswordReset(
                token=secrets.token_urlsafe(24),
                email=user.email,
                code_hash=generate_password_hash(code),
                new_password_hash=generate_password_hash(password),
                expires_at=datetime.utcnow() + timedelta(minutes=RESET_MINUTES),
            )
            db.session.add(row)
            db.session.commit()

            if mail_send.send(user.email, 'Your Review Hub Ph reset code', reset_email_body(code)):
                return redirect(url_for('reset_password_code', token=row.token))

            # The code never arrived, so the request cannot be left waiting for it.
            db.session.delete(row)
            db.session.commit()
            errors['email'] = mail_send.error() or 'The code could not be emailed. Try again.'

    return render_template('reset_password.html', user=current_user(),
                           errors=errors, email=email,
                           minutes=RESET_MINUTES,
                           mail_ready=mail_send.configured())


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_code(token):
    row = pending_reset(token)
    if not row:
        return redirect(url_for('reset_password'))

    error = None
    if request.method == 'POST':
        if row.tries >= RESET_TRIES:
            db.session.delete(row)
            db.session.commit()
            return redirect(url_for('reset_password'))

        if not check_password_hash(row.code_hash, request.form.get('code', '').strip()):
            row.tries += 1
            db.session.commit()
            left = RESET_TRIES - row.tries
            error = ('That code is not right. ' +
                     ('It has been cancelled - ask for a new one.' if left <= 0
                      else 'You have %d tries left.' % left))
        else:
            user = user_by_email(row.email)
            if not user:
                error = 'That account is gone, so there is nothing to reset.'
            else:
                user.password_hash = row.new_password_hash
                row.used_at = datetime.utcnow()
                db.session.commit()
                if session.get('user_id') == user.id:
                    session.clear()
                return redirect(url_for('login') + '?reset=1')

    return render_template('reset_password_code.html', user=current_user(), row=row,
                           error=error, email=row.email,
                           deadline=row.expires_at.strftime('%I:%M %p').lstrip('0'))



# --- SYNC (offline attempts pushed once back online) ---
@app.route('/api/attempts/sync', methods=['POST'])
@login_required_json
def sync_attempts():
    data = request.get_json(silent=True) or {}
    attempts = data.get('attempts') or []
    if not isinstance(attempts, list):
        return jsonify({'error': 'invalid_payload'}), 400

    synced = 0
    skipped = 0
    for a in attempts[:50]:
        if not isinstance(a, dict):
            skipped += 1
            continue
        client_uuid = str(a.get('client_uuid') or '').strip()
        if not client_uuid:
            skipped += 1
            continue
        if QuizAttempt.query.filter_by(client_uuid=client_uuid[:64]).first():
            skipped += 1
            continue

        try:
            quiz_set_info = a.get('quiz_set_info') or []
            db.session.add(QuizAttempt(
                user_id=session['user_id'],
                client_uuid=client_uuid[:64],
                subject=str(a.get('subject', ''))[:120] or 'Unknown',
                topic=str(a.get('topic', ''))[:200] or None,
                quiz_set_info=json.dumps(quiz_set_info, ensure_ascii=False),
                score=int(a.get('score') or 0),
                total=int(a.get('total') or 0),
                date_taken=parse_date(a.get('date_taken')),
            ))
            synced += 1
        except (ValueError, TypeError):
            skipped += 1

    db.session.commit()
    return jsonify({'synced': synced, 'skipped': skipped})


@app.route('/api/attempts/ungraded', methods=['POST'])
def save_ungraded():
    """Keep a quiz the student chose not to save, as practice data only.

    No login is needed - that is the whole point: the ones without an account
    are recorded under the name "annonymous" so their answers still count
    towards how an item performs. This table is never read by My Results.
    """
    data = request.get_json(silent=True) or {}
    attempts = data.get('attempts') or []
    if not isinstance(attempts, list):
        return jsonify({'error': 'invalid_payload'}), 400

    user = current_user()
    saved = 0
    skipped = 0
    for a in attempts[:50]:
        if not isinstance(a, dict):
            skipped += 1
            continue
        client_uuid = str(a.get('client_uuid') or '').strip()
        if not client_uuid:
            skipped += 1
            continue
        if UngradedAttempt.query.filter_by(client_uuid=client_uuid[:64]).first():
            skipped += 1
            continue

        try:
            db.session.add(UngradedAttempt(
                client_uuid=client_uuid[:64],
                user_id=user.id if user else None,
                name=(user.full_name().strip() if user else '') or 'annonymous',
                school=(user.school if user else '')[:200] or None,
                grade=((user.grade if user else '') or str(a.get('level') or ''))[:20],
                section=norm_section(user.section if user else str(a.get('section') or ''))[:80],
                subject=str(a.get('subject', ''))[:120] or 'Unknown',
                topic=str(a.get('topic', ''))[:200] or None,
                quiz_set_info=json.dumps(a.get('quiz_set_info') or [], ensure_ascii=False),
                score=int(a.get('score') or 0),
                total=int(a.get('total') or 0),
                date_taken=parse_date(a.get('date_taken')),
            ))
            saved += 1
        except (ValueError, TypeError):
            skipped += 1

    db.session.commit()
    return jsonify({'saved': saved, 'skipped': skipped})


# --- RESOURCES ---
# Files a section shares live on Google Drive (drive_store.py) so the app needs
# no upload folder of its own and every student opens the same copy. A Google
# Doc, a Google Sheet or any other page is kept as the link the admin pasted.
KIND_NAMES = {
    'pdf': 'PDF',
    'png': 'Image',
    'ppt': 'Slides',
    'docs': 'Google Doc',
    'sheets': 'Google Sheet',
    'link': 'Link',
}
UPLOAD_KINDS = {
    '.pdf': 'pdf',
    '.png': 'png',
    '.jpg': 'png',
    '.jpeg': 'png',
    '.ppt': 'ppt',
    '.pptx': 'ppt',
}
MAX_UPLOAD_BYTES = 20_000_000


def link_kind(url):
    """Give the Google apps their own label; everything else is a plain link."""
    u = (url or '').strip().lower()
    if 'docs.google.com' in u:
        if '/document/' in u:
            return 'docs'
        if '/spreadsheets/' in u:
            return 'sheets'
        if '/presentation/' in u:
            return 'ppt'
    return 'link'


def known_grades():
    """The grade levels the main admin created - nothing else is offered."""
    return grade_choices()


def sections_map():
    """{grade: [section, ...]} of the classes that exist.

    A section gets its materials page as soon as the main admin creates it, so
    a teacher can post before its first learner signs up - and nothing can be
    filed under a section that was never made.
    """
    return class_choices()


def match_grade(raw):
    """'grade 10' in a URL still means Grade 10."""
    want = norm_section(raw)
    for grade in known_grades():
        if norm_section(grade) == want:
            return grade
    return ''


def resource_counts(grade, section):
    query = db.session.query(Resource.grade, Resource.section, db.func.count(Resource.id))
    if grade:
        query = query.filter(Resource.grade == grade)
    if section:
        query = query.filter(Resource.section == section)
    return {(g, s): n for g, s, n in query.group_by(Resource.grade, Resource.section).all()}


def own_section(user):
    """(grade, section) a student belongs to, or None when the account has no section."""
    if not user or not user.section:
        return None
    grade = match_grade(user.grade)
    if not grade:
        return None
    return grade, norm_section(user.section)


@app.route('/materials')
def materials():
    """The one Materials page. 'Resources' and 'Materials' were the same list twice.

    Materials are handed out to enrolled learners, so a visitor with no account
    is sent to sign in rather than shown the school's folders. A learner sees
    their own grade level and section with the items under it; staff get the
    class browser and open one section to read or post what its learners see.
    """
    user = current_user()
    kind = admin_kind(user)
    if not kind and not session.get('user_id'):
        return redirect(url_for('login'))
    if not kind:
        mine = own_section(user)
        return render_template('materials.html', user=user, groups={}, counts={},
                               own_grade=mine[0] if mine else '',
                               own_section=mine[1] if mine else '',
                               locked=not mine, learner=bool(mine),
                               items=resources_for(*(mine or ('', ''))),
                               kind_names=KIND_NAMES)
    groups = pick_classes(sections_map())
    counts = resource_counts(None, None)
    return render_template(
        'materials.html',
        user=user,
        groups=groups,
        counts=counts,
        own_grade=user.grade if user else '',
        own_section=norm_section(user.section) if user else '',
        can_post=role_can('post_materials', kind),
    )


@app.route('/materials/<grade>/<section>', methods=['GET', 'POST'])
def material_section(grade, section):
    """One section's materials, read and written on the same page.

    Everyone in the class sees the same set, because a material is filed against
    the section, not the student. Reading needs only a place in that section or a
    class assignment; adding or removing needs the post-materials role.
    """
    user = current_user()
    kind = admin_kind(user)
    grade_key = match_grade(grade)
    section_key = norm_section(section)
    if not grade_key or not section_key:
        return redirect(url_for('materials'))
    if not kind and not session.get('user_id'):
        return redirect(url_for('login'))
    if kind and not may_open_class(grade_key, section_key):
        # A teacher opens the materials of their own classes, no further.
        return redirect(url_for('materials'))
    if not kind and own_section(user) != (grade_key, section_key):
        # Another section's pile is not for this student to read.
        return redirect(url_for('profile'))

    can_post = bool(kind) and role_can('post_materials', kind)
    message = None
    problem = None

    if request.method == 'POST':
        if not can_post:
            problem = 'Only somebody who posts materials can change this list. ' \
                      'Ask the main admin, or read what is already here.'
        elif request.form.get('action') == 'delete':
            row = db.session.get(Resource, int(request.form.get('id') or 0))
            if row and not may_open_class(row.grade, row.section):
                problem = 'That class is not assigned to you.'
            elif row:
                file_id = row.drive_id
                db.session.delete(row)
                db.session.commit()
                # The Drive copy goes with it; a file nobody can reach is only
                # taking up room. The row is removed even if Drive says no.
                if file_id:
                    drive_store.delete(file_id)
                message = 'Removed that material from %s %s.' % (grade_key, section_key)
            else:
                problem = 'That material is already gone.'
        else:
            title = request.form.get('title', '').strip()
            link = request.form.get('link', '').strip()
            upload = request.files.get('file')
            drive_id = ''
            url = ''
            file_kind = ''
            name = title

            if upload and upload.filename:
                ext = os.path.splitext(upload.filename)[1].lower()
                data = upload.read()
                if ext not in UPLOAD_KINDS:
                    problem = 'Upload a pdf, png, jpg or ppt. A Google link goes in the link box.'
                elif len(data) > MAX_UPLOAD_BYTES:
                    problem = 'That file is over 20 MB. Put it on Drive yourself and paste its link.'
                else:
                    file_kind = UPLOAD_KINDS[ext]
                    file_id, shared, err = drive_store.upload(
                        data,
                        '%s %s - %s' % (grade_key, section_key, os.path.basename(upload.filename)),
                        upload.mimetype)
                    if not file_id:
                        problem = err or 'Google Drive did not take the file.'
                    else:
                        drive_id, url = file_id, shared
                        name = name or os.path.splitext(os.path.basename(upload.filename))[0]
            elif link.startswith('http://') or link.startswith('https://'):
                file_kind = link_kind(link)
                url = link
                name = name or link
            else:
                problem = 'Choose a file or paste a link that starts with http.'

            if not problem and name:
                db.session.add(Resource(
                    grade=grade_key,
                    section=section_key,
                    title=name[:200],
                    kind=file_kind,
                    url=url[:500],
                    drive_id=drive_id or None,
                    note=request.form.get('note', '').strip()[:300] or None,
                    # A material posted from a staff login has no learner account
                    # behind it; the stamp is the main admin's own row when there is one.
                    added_by=user.id if user else None,
                ))
                db.session.commit()
                message = 'Added to %s %s. Everyone in that section can open it.' % (
                    grade_key, section_key)

    items = Resource.query.filter_by(grade=grade_key, section=section_key).order_by(
        Resource.created_at.desc()).all()
    return render_template(
        'material_section.html',
        user=user,
        is_admin_user=bool(kind),
        can_post=can_post,
        grade=grade_key,
        section=section_key,
        items=items,
        kind_names=KIND_NAMES,
        message=message,
        problem=problem,
        drive_ready=drive_store.configured(),
        drive_note=drive_store.error(),
    )


@app.route('/resources')
def resources():
    """The old name for Materials: one page now, so the two links are one link."""
    return redirect(url_for('materials'))


@app.route('/resources/<grade>/<section>')
def section_resources(grade, section):
    return redirect(url_for('material_section', grade=grade, section=section))


@app.route('/admin/resources', methods=['GET', 'POST'])
@staff_required
def admin_resources():
    return redirect(url_for('materials'))


# --- MY RESULTS ---
@app.route('/my-results')
def my_results():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    attempts = QuizAttempt.query.filter_by(user_id=user.id).order_by(
        QuizAttempt.date_taken.desc()).limit(200).all()

    rows = []
    for a in attempts:
        try:
            info = json.loads(a.quiz_set_info or '[]')
        except (ValueError, TypeError):
            info = []
        rows.append({
            'id': a.id,
            'subject': a.subject,
            'topic': a.topic or '',
            'score': a.score,
            'total': a.total,
            'date_taken': a.date_taken.strftime('%b %d, %Y %I:%M %p') if a.date_taken else '',
            'quiz_set_info': info,
            'recorded': (a.source or 'quiz') == 'manual',
        })

    user_json = {
        'name': user.full_name(),
        'school': user.school,
        'grade': user.grade,
        'section': user.section,
    }
    return render_template('my_results.html', user=user, attempts=rows, user_json=user_json)


# --- STUDENT PROFILE ---
def resources_for(grade, section):
    """The materials kept for one section, whatever capitals were used."""
    if not (grade and section):
        return []
    return Resource.query.filter(
        db.func.upper(Resource.grade) == norm_section(grade),
        db.func.upper(Resource.section) == norm_section(section),
    ).order_by(Resource.created_at.desc()).all()


@app.route('/profile')
def profile():
    if admin_kind():
        return staff_profile_page(my_staff_email())

    user = current_user()
    if not user:
        return redirect(url_for('login'))

    attempts = QuizAttempt.query.filter_by(user_id=user.id).all()
    score_sum = sum(a.score for a in attempts)
    total_sum = sum(a.total for a in attempts)
    subjects = sorted({a.subject for a in attempts if a.subject})
    latest = max((a.date_taken for a in attempts if a.date_taken), default=None)

    # The learner's week is the schedule kept on their own section.
    section = SectionLevel.query.filter_by(
        grade=user.grade, name=norm_section(user.section)).first()

    return render_template(
        'profile.html',
        user=user,
        items=resources_for(user.grade, user.section),
        kind_names=KIND_NAMES,
        attempt_count=len(attempts),
        avg_pct=round(score_sum * 100 / total_sum) if total_sum else 0,
        subjects=subjects,
        latest=latest.strftime('%b %d, %Y') if latest else '',
        joined=user.created_at.strftime('%b %d, %Y') if user.created_at else '',
        slots=[{'days': ', '.join(days), 'start': start, 'end': end}
               for days, start, end in (iter_slots(section) if section else [])],
        room=section.room if section else '',
        halt=non_class_note(),
    )


def staff_profile_page(address):
    """Render one staff profile, when this signer is allowed to read it.

    A teacher reads their own. An admin reads their own and the pages of the
    teachers placed under them. The main admin reads anybody's. Everything on
    the page comes from admin.db and the Classes page, so a profile shows
    exactly what was handed out there.
    """
    kind = admin_kind()
    if not kind:
        return redirect(url_for('admin_login'))
    profile_data = staff_profile(address)
    if not profile_data['email']:
        return redirect(url_for('admin_staff'))
    mine = profile_data['email'] == my_staff_email()
    if not mine and kind != 'main_admin' and \
            profile_data['email'] not in supervised_emails(my_staff_email()):
        return redirect(url_for('admin_assessment'))
    # The browser alarm needs the meetings as plain data; '<' is escaped so a
    # stored name can never close the JSON script tag early.
    meetings = [{'day': day, 'grade': block['grade'], 'section': block['section'],
                 'subjects': block['subjects'], 'room': block['room'],
                 'start': block['start'], 'end': block['end']}
                for day, blocks in profile_data['week'].items() for block in blocks]
    halt = non_class_note()
    if halt:
        # A declared no-class day: the in-tab alarm gets nothing to ring for.
        meetings = []
    return render_template(
        'profile_staff.html', profile=profile_data, own=mine, days=CLASS_DAYS,
        halt=halt,
        meetings_json=json.dumps(meetings).replace('<', '\\u003c'),
    )


@app.route('/profile/account/<int:staff_id>')
@staff_required
def staff_profile_account(staff_id):
    """One teacher's or admin's profile, opened from the Staff and Classes pages."""
    member = db.session.get(Staff, staff_id)
    if not member:
        return redirect(url_for('admin_staff'))
    return staff_profile_page(member.email)


# --- ADMIN RESULTS (item analysis) ---
def difficulty_label(p):
    if p >= 0.75:
        return 'Easy', 'easy'
    if p >= 0.50:
        return 'Moderate', 'moderate'
    if p >= 0.25:
        return 'Difficult', 'difficult'
    return 'Very Difficult', 'very-difficult'


def build_admin_analysis(pairs):
    """Aggregate (attempt, identity) rows into per-item statistics.

    `identity` is a small dict made by the caller, so a saved attempt from an
    account holder and a declined attempt from an "annonymous" student can be
    counted in the same item analysis.
    """
    students = {}
    items = {}
    score_sum = 0
    total_sum = 0

    for attempt, who in pairs:
        st = students.setdefault(who['key'], {
            'name': who['name'],
            'section': who['section'],
            'ungraded': not who['graded'],
            'attempts': 0,
            'score_sum': 0,
            'total_sum': 0,
            'latest': attempt.date_taken,
        })
        st['attempts'] += 1
        st['score_sum'] += attempt.score
        st['total_sum'] += attempt.total
        if attempt.date_taken and (not st['latest'] or attempt.date_taken > st['latest']):
            st['latest'] = attempt.date_taken
        score_sum += attempt.score
        total_sum += attempt.total

        try:
            info = json.loads(attempt.quiz_set_info or '[]')
        except (ValueError, TypeError):
            info = []
        if not isinstance(info, list):
            info = []

        for it in info:
            if not isinstance(it, dict):
                continue
            qid = it.get('id')
            key = ('id', qid) if qid is not None else ('text', str(it.get('question', ''))[:200])
            stat = items.setdefault(key, {
                'question': str(it.get('question', '')),
                'options': [str(o) for o in it['options']] if isinstance(it.get('options'), list) else [],
                'correct': it.get('correct'),
                'topic': it.get('topic') or attempt.topic or '',
                'subject': it.get('subject') or attempt.subject,
                'quarter': it.get('quarter') or '',
                'shown': 0,
                'correct_count': 0,
                'unanswered': 0,
                'choices': {},
            })
            stat['shown'] += 1
            ans = it.get('your_answer')
            if ans is None or str(ans).strip() == '':
                stat['unanswered'] += 1
            else:
                ans = str(ans)
                stat['choices'][ans] = stat['choices'].get(ans, 0) + 1
                if ans == stat['correct']:
                    stat['correct_count'] += 1

    item_list = []
    for stat in items.values():
        stat['p'] = (stat['correct_count'] / stat['shown']) if stat['shown'] else 0.0
        stat['pct'] = round(stat['p'] * 100)
        label, cls = difficulty_label(stat['p'])
        stat['diff_label'] = label
        stat['diff_class'] = cls

        rows = []
        for opt in stat['options']:
            count = stat['choices'].get(opt, 0)
            rows.append({
                'text': opt,
                'count': count,
                'pct': round(count * 100 / stat['shown']) if stat['shown'] else 0,
                'is_correct': opt == stat['correct'],
            })
        known = set(stat['options'])
        for ans, count in sorted(stat['choices'].items()):
            if ans not in known:
                rows.append({
                    'text': ans,
                    'count': count,
                    'pct': round(count * 100 / stat['shown']) if stat['shown'] else 0,
                    'is_correct': ans == stat['correct'],
                })
        if stat['unanswered']:
            rows.append({
                'text': None,
                'count': stat['unanswered'],
                'pct': round(stat['unanswered'] * 100 / stat['shown']) if stat['shown'] else 0,
                'is_correct': False,
            })
        stat['option_rows'] = rows
        item_list.append(stat)

    # Group by subject; within a subject the most difficult items come first.
    item_list.sort(key=lambda s: (str(s['subject']), -s['p'], str(s['question'])))
    subjects = {}
    for stat in item_list:
        subjects.setdefault(stat['subject'], []).append(stat)

    most_difficult = sorted(item_list, key=lambda s: (s['p'], -s['shown']))[:5]

    student_list = sorted(students.values(), key=lambda s: s['name'].lower())
    for st in student_list:
        st['avg_pct'] = round(st['score_sum'] * 100 / st['total_sum']) if st['total_sum'] else 0
        st['latest_str'] = st['latest'].strftime('%b %d, %Y') if st['latest'] else ''

    return {
        'students': student_list,
        'student_count': len(student_list),
        'attempt_count': len(pairs),
        'ungraded_count': sum(1 for _, who in pairs if not who['graded']),
        'avg_pct': round(score_sum * 100 / total_sum) if total_sum else 0,
        'item_count': len(item_list),
        'subjects': subjects,
        'most_difficult': most_difficult,
    }


@app.route('/admin')
@staff_required
def admin_results():
    user = current_user()

    groups = pick_classes(sections_map())
    grade = request.args.get('grade', '').strip()
    if grade not in groups:
        grade = ''
    section = norm_section(request.args.get('section', ''))
    if grade and section and section not in groups[grade]:
        section = ''

    view = None
    classes = groups.get(grade, [])
    scope = section_scope(grade) if grade else None
    if grade and (not section or may_open_class(grade, section)):
        query = (db.session.query(QuizAttempt, User)
                 .join(User, QuizAttempt.user_id == User.id)
                 .filter(User.grade == grade))
        ungraded_query = UngradedAttempt.query.filter(UngradedAttempt.grade == grade)
        if section:
            query = query.filter(db.func.upper(User.section) == section)
            ungraded_query = ungraded_query.filter(db.func.upper(UngradedAttempt.section) == section)
        elif scope is not None:
            query = query.filter(db.func.upper(User.section).in_(scope))
            ungraded_query = ungraded_query.filter(
                db.func.upper(UngradedAttempt.section).in_(scope))

        pairs = [
            (attempt, {'key': ('saved', user_row.id), 'name': user_row.full_name(),
                       'section': norm_section(user_row.section), 'graded': True})
            for attempt, user_row in
            query.order_by(QuizAttempt.date_taken.desc()).limit(1000).all()
        ]
        for attempt in ungraded_query.order_by(
                UngradedAttempt.date_taken.desc()).limit(1000).all():
            # A student with no account shares the one "annonymous" name, so
            # grouping them into a single profile would pretend a hundred people
            # were one. Each of those quizzes stands on its own.
            who = attempt.name or 'annonymous'
            shown = who if who == 'annonymous' else (tidy_name(who) or who)
            key = ('ungraded', attempt.id) if attempt.user_id is None \
                else ('ungraded', attempt.user_id, norm_section(attempt.section))
            pairs.append((attempt, {
                'key': key,
                'name': shown,
                'section': norm_section(attempt.section),
                'graded': False,
            }))
        view = build_admin_analysis(pairs)

    return render_template(
        'admin_results.html',
        user=user,
        grade=grade,
        section=section,
        grade_choices=list(groups),
        sections=classes,
        class_map=groups,
        view=view,
    )


# --- ADMIN DATABASE (see what is stored and correct a row) ---
# The school asks for one table at a time, so this reads the real schema from
# SQLite instead of a hard-coded list. Table and column names are checked
# against that schema before they are used, and every value travels as a bound
# parameter, so nothing typed in a URL can become SQL.
ROW_PAGE_SIZE = 20
CELL_CHARS = 70

# Columns that name a learner without declaring the reference in the schema.
EXTRA_USER_LINKS = {'ungraded': {'user_id'}}
# Columns that name a learner by their sign-in address instead of their id.
ACCOUNT_USER_LINKS = {'games': {'account'}, 'jl_players': {'account'},
                      'ww_players': {'account'}}
DATE_FORMATS = ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d')


def quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def db_tables():
    rows = db.session.execute(db.text(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name")).all()
    return [row[0] for row in rows]


def db_columns(table):
    if table not in db_tables():
        return []
    cols = []
    for row in db.session.execute(db.text('PRAGMA table_info(%s)' % quote_ident(table))):
        cols.append({'name': row[1], 'type': row[2] or '',
                     'notnull': bool(row[3]), 'pk': int(row[5] or 0)})
    return cols


def db_pk(cols):
    """The one column this editor can point at, or None if the table has none."""
    keys = [c for c in cols if c['pk']]
    return keys[0] if len(keys) == 1 else None


def db_count(table, link=None, value=None):
    sql = 'SELECT COUNT(*) FROM %s' % quote_ident(table)
    params = {}
    if link:
        sql += ' WHERE %s = :only' % quote_ident(link)
        params['only'] = value
    return int(db.session.execute(db.text(sql), params).scalar() or 0)


def db_rows(table, page, link=None, value=None):
    cols = db_columns(table)
    key = db_pk(cols)
    names = ', '.join(quote_ident(c['name']) for c in cols)
    order = quote_ident(key['name']) if key else 'rowid'
    params = {'n': ROW_PAGE_SIZE, 'o': max(page - 1, 0) * ROW_PAGE_SIZE}
    where = ''
    if link:
        where = ' WHERE %s = :only' % quote_ident(link)
        params['only'] = value
    rows = db.session.execute(db.text(
        'SELECT %s FROM %s%s ORDER BY %s LIMIT :n OFFSET :o' % (
            names, quote_ident(table), where, order)), params).mappings().all()
    return rows


def db_row(table, identity):
    cols = db_columns(table)
    key = db_pk(cols)
    if not key:
        return None, cols
    value = int(identity) if 'INT' in (key['type'] or '').upper() else identity
    row = db.session.execute(db.text(
        'SELECT * FROM %s WHERE %s = :k LIMIT 1' % (quote_ident(table), quote_ident(key['name']))),
        {'k': value}).mappings().first()
    return row, cols


def looks_like_date(column):
    name = (column['type'] or '').upper()
    return 'DATE' in name or 'TIME' in name


def looks_like_int(column):
    return 'INT' in (column['type'] or '').upper()


def coerce_cell(column, raw):
    """Turn one box on the edit form into a value, or say what is wrong."""
    text = '' if raw is None else str(raw).strip()
    if not text:
        if column['notnull'] and not (looks_like_int(column) or looks_like_date(column)):
            return '', None
        return None, ('"%s" cannot be left empty.' % column['name']
                      if column['notnull'] else None)
    if looks_like_int(column):
        try:
            return int(float(text)) if '.' in text and float(text).is_integer() else int(text), None
        except ValueError:
            return None, '"%s" has to be a whole number.' % column['name']
    if looks_like_date(column):
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime('%Y-%m-%d %H:%M:%S.%f'), None
            except ValueError:
                continue
        return None, ('"%s" has to look like 2026-10-27 15:30:00.' % column['name'])
    return text, None


def user_link_columns(table):
    """{column: how it names a learner} for the columns of a table that point at an account.

    Most tables store the id, the game tables store the sign-in address, and the
    account table is its own list, so its key counts as a learner too. Nothing
    here is trusted from a request: a column may only be filtered on if this
    reads it out of the schema.
    """
    links = {}
    try:
        for row in db.session.execute(db.text(
                'PRAGMA foreign_key_list(%s)' % quote_ident(table))):
            if row[2] == 'user' and row[4] == 'id':
                links[row[3]] = 'id'
    except Exception:
        pass
    for name in EXTRA_USER_LINKS.get(table, set()):
        links[name] = 'id'
    for name in ACCOUNT_USER_LINKS.get(table, set()):
        links[name] = 'account'
    if table == 'user':
        links['id'] = 'id'
    return links


def user_picks(table):
    """{column: [(value, label)]} for the columns of a table that name a learner.

    quiz_attempt and resource declare the reference in their schema; the offline
    outbox keeps the same column without declaring it, so it is named here too.
    """
    links = user_link_columns(table)
    if not links:
        return {}
    learners = (User.query.order_by(db.func.upper(User.last_name),
                                    db.func.upper(User.first_name)).all())
    by_id, by_account = [], []
    for student in learners:
        label = '%s - %s %s' % (
            student.full_name(), student.grade or '', norm_section(student.section))
        by_id.append((student.id, label))
        by_account.append((student.email, '%s / %s' % (label, student.email)))
    options = {'id': by_id, 'account': by_account}
    return {name: options[kind] for name, kind in links.items()}


def db_form_fields(columns, row, typed=None, class_map=None, users=None):
    """Say how each box on the edit form is drawn and what it holds.

    A JSON column and a one-word grade are both text, but only one of them
    needs a tall box to be readable. A column that names a class or a learner
    becomes a pick from what the Classes page actually holds, so a row cannot
    be pointed at a section that was never created.
    """
    out = []
    for column in columns:
        name = column['name']
        if name == 'password_hash':
            out.append({'name': name, 'kind': 'hash', 'label': 'Password', 'multi': False})
            continue
        raw = row.get(name)
        text = '' if raw is None else str(raw)
        if typed is not None:
            text = str(typed.get(name, text))
        if class_map and name in ('grade', 'section'):
            if name == 'grade':
                names = list(class_map)
            else:
                held = '' if typed is None else str(typed.get('grade', '') or '')
                if not held:
                    raw_grade = row.get('grade')
                    held = '' if raw_grade is None else str(raw_grade)
                names = list(class_map.get(held) or [])
            out.append({'name': name, 'kind': name, 'label': name,
                        'type': 'class list', 'notnull': bool(column['notnull']),
                        'value': text, 'options': names,
                        'extra': text if text and text not in names else ''})
            continue
        if users and name in users:
            options = users[name]
            out.append({'name': name, 'kind': 'user', 'label': name,
                        'type': 'learner' if not column['notnull'] else 'learner (required)',
                        'notnull': bool(column['notnull']),
                        'value': text, 'options': options,
                        'extra': text if text and text not in {str(v) for v, _ in options} else ''})
            continue
        if 'INT' in (column['type'] or '').upper():
            kind = 'number'
        elif looks_like_date(column):
            kind = 'datetime'
        else:
            kind = 'text'
        out.append({'name': name, 'kind': kind, 'label': name,
                    'type': column['type'] or '', 'notnull': bool(column['notnull']),
                    'value': text,
                    'multi': kind == 'text' and (len(text) > 60 or text.lstrip().startswith(('{', '[')))})
    return out


@app.route('/admin/database')
@admin_required
def admin_database():
    tables = []
    for name in db_tables():
        cols = db_columns(name)
        tables.append({'name': name, 'count': db_count(name),
                       'columns': len(cols), 'editable': bool(db_pk(cols))})
    return render_template('admin_database.html', user=current_user(), tables=tables)


@app.route('/admin/database/<table>')
@admin_required
def admin_database_table(table):
    cols = db_columns(table)
    if not cols:
        return redirect(url_for('admin_database'))
    try:
        page = max(int(request.args.get('page', '1')), 1)
    except ValueError:
        page = 1

    # One learner picked from the whole register narrows the rows down to theirs.
    # The column is only honoured when the schema really names a learner there.
    links = user_link_columns(table)
    learner_col = request.args.get('col')
    if learner_col not in links:
        learner_col = sorted(links)[0] if links else ''
    only = (request.args.get('value') or '').strip()
    if learner_col and links[learner_col] == 'id':
        only = str(int(only)) if only.lstrip('-').isdigit() else ''
    # The picker always stands on the table; it only filters once a value arrives.
    filter_col = learner_col if only else ''

    total = db_count(table, filter_col, only) if filter_col else db_count(table)
    pages = max((total + ROW_PAGE_SIZE - 1) // ROW_PAGE_SIZE, 1)
    page = min(page, pages)
    return render_template(
        'admin_database_table.html',
        user=current_user(),
        table=table,
        columns=cols,
        rows=db_rows(table, page, filter_col, only),
        key=db_pk(cols),
        page=page,
        pages=pages,
        total=total,
        size=ROW_PAGE_SIZE,
        chars=CELL_CHARS,
        learner_col=learner_col,
        learner_options=user_picks(table).get(learner_col, []),
        learner_only=only,
    )


@app.route('/admin/database/<table>/<identity>', methods=['GET', 'POST'])
@admin_required
def admin_database_row(table, identity):
    row, cols = db_row(table, identity)
    key = db_pk(cols)
    if row is None or not key:
        return redirect(url_for('admin_database_table', table=table)
                        if table in db_tables() else url_for('admin_database'))

    editable = [c for c in cols if c['name'] != key['name']]
    message = None
    errors = {}
    typed = None
    class_map = class_choices()
    users = user_picks(table)

    if request.method == 'POST':
        values = {}
        for column in editable:
            if column['name'] == 'password_hash':
                continue  # only a fresh password typed below may rewrite it
            value, problem = coerce_cell(column, request.form.get(column['name']))
            if problem:
                errors[column['name']] = problem
            else:
                values[column['name']] = value

        new_password = (request.form.get('__new_password__') or '').strip()
        has_hash = any(c['name'] == 'password_hash' for c in cols)
        if has_hash and new_password:
            if len(new_password) < 8:
                errors['__new_password__'] = 'A password needs at least 8 characters.'
            else:
                values['password_hash'] = generate_password_hash(new_password)

        if errors:
            typed = {c['name']: request.form.get(c['name'], '') for c in editable}
        else:
            names = sorted(values)
            sets = ', '.join('%s = :v%d' % (quote_ident(n), i) for i, n in enumerate(names))
            params = {('v%d' % i): values[n] for i, n in enumerate(names)}
            params['k'] = int(identity) if 'INT' in (key['type'] or '').upper() else identity
            db.session.execute(db.text(
                'UPDATE %s SET %s WHERE %s = :k' % (
                    quote_ident(table), sets, quote_ident(key['name']))), params)
            db.session.commit()
            message = 'Saved row %s in %s.' % (identity, table)
            row, cols = db_row(table, identity)

    return render_template(
        'admin_database_row.html',
        user=current_user(),
        table=table,
        key=key,
        identity=identity,
        fields=db_form_fields(editable, row, typed, class_map, users),
        class_map=class_map,
        message=message,
        problem=' '.join(errors.values()) if errors else '',
    )


# --- ELEMENTALS GAME (mounted at /game, sharing this database) ---
GAME_DIR = os.path.join(basedir, 'ELEMENTALS')


def game_student_identity():
    """Hand the game the signed-in student, so nobody has to type their name."""
    user = current_user()
    if not user:
        return None
    # A row left by the old version has no name yet; the sheet still needs one.
    name = user.full_name().strip() or user.email.split('@')[0]
    return {'name': name, 'grade': user.grade or '',
            'section': user.section or '', 'account': user.email}


def mount_game():
    """Load ELEMENTALS out of its own folder and serve it under /game.

    The file is imported through importlib because it is named app.py: a plain
    "import app" would re-import this very module instead of the game.
    """
    import importlib.util

    path = os.path.join(GAME_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning('ELEMENTALS is not in %s, so /game stays disabled', GAME_DIR)
        return False

    app.config['ELEMENTALS_BACK_URL'] = '/home'
    if GAME_DIR not in sys.path:
        sys.path.append(GAME_DIR)          # the game imports periodic_data and clue_data
    spec = importlib.util.spec_from_file_location('elementals_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['elementals_game'] = game
    spec.loader.exec_module(game)

    # elements, clues, games and answers are created inside quiz_app.db.
    game.mount(app, url_prefix='/game', db_path=DB_PATH)
    game.student_defaults = game_student_identity
    game.is_admin = lambda: bool(admin_kind())   # staff-only worksheet pages
    return True


GAME_READY = mount_game()


# --- EDUCATIONAL GAMES (the hub page links every game in here) ---
JUMBLED_DIR = os.path.join(basedir, 'JUMBLED')


def mount_jumbled():
    """Load Jumbled Letters and serve it under /games/jumbled on this database.

    Its own tables (jl_rooms, jl_players, jl_answers) live inside quiz_app.db,
    and game scores stay in them, never in quiz_attempt.
    """
    import importlib.util

    path = os.path.join(JUMBLED_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning('Jumbled Letters is not in %s, so /games/jumbled stays disabled',
                           JUMBLED_DIR)
        return False

    app.config['JUMBLED_BACK_URL'] = '/games'
    if JUMBLED_DIR not in sys.path:
        sys.path.append(JUMBLED_DIR)        # the game imports its own words module
    spec = importlib.util.spec_from_file_location('jumbled_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['jumbled_game'] = game
    spec.loader.exec_module(game)

    game.mount(app, url_prefix='/games/jumbled', db_path=DB_PATH)
    game.identity = game_student_identity   # a signed-in student never types a name
    game.spec = QUIZ_SPEC                   # the very tree the quiz form uses
    game.is_admin = lambda: bool(admin_kind())   # staff-only worksheet pages
    return game


JUMBLED = mount_jumbled()
JUMBLED_READY = bool(JUMBLED)


# --- ADMIN ASSESSMENT (one section, one quiz set, every score) ---
# The teacher's own record book: pull a quiz set, see what each section got,
# add the scores taken on paper, and correct or remove a student.


def quiz_set_choices(grade):
    """Subjects and topics pickable for one grade.

    The MATATAG tree plus anything the students of this grade actually answered,
    so a set generated after matatag_spec.json was written still shows up here.
    A teacher handed subjects on the Classes page only sees those.
    """
    scope = staff_subject_scope()
    tree = {}
    for subject, quarters in (QUIZ_SPEC.get(grade) or {}).items():
        for topics in quarters.values():
            tree.setdefault(subject, set()).update(
                topics.keys() if isinstance(topics, dict) else topics)

    rows = (db.session.query(QuizAttempt.subject, QuizAttempt.topic)
            .join(User, QuizAttempt.user_id == User.id)
            .filter(User.grade == grade).distinct().all())
    rows += (db.session.query(UngradedAttempt.subject, UngradedAttempt.topic)
             .filter(UngradedAttempt.grade == grade).distinct().all())
    for subject, topic in rows:
        subject = str(subject or '').strip()
        if subject:
            tree.setdefault(subject, set()).add(str(topic or '').strip())

    return [{'subject': subject, 'topics': sorted(t for t in tree[subject] if t)}
            for subject in sorted(tree)
            if any(t for t in tree[subject])
            and (scope is None or subject.lower() in scope)]


def assessment_args(form):
    """Carry the four pickers through a redirect after a POST."""
    return {
        'grade': (form.get('grade') or '').strip(),
        'section': norm_section(form.get('section')),
        'subject': (form.get('subject') or '').strip(),
        'topic': (form.get('topic') or '').strip(),
    }


def assessment_date(value):
    """A paper quiz has a day on it, not a minute."""
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return datetime.utcnow()


# --- SYNCING THE LAPTOP TO THE LIVE SERVER ---
# The review center can run this same app on a laptop that the students reach
# through the modem's WiFi (start it with run_local.py). Quizzes and accounts
# then live in that laptop's quiz_app.db and work with no internet at all. When
# the connection is back, the main admin presses Sync on /admin/sync and this
# app posts the new rows to the live copy, which writes them into its own
# database. The laptop never touches PythonAnywhere's files or database.
#
# One result is known by its client_uuid and one account by its email, so a
# second press - or a sync from a second laptop - is ignored instead of being
# counted twice. Sending is add-only: a row edited on the laptop after it was
# sent is not re-sent, because the live copy would not know which version wins.

SYNC_CONFIG_PATH = os.path.join(basedir, 'sync_config.json')
SYNC_BATCH = 100
SYNC_ROUNDS = 50
SYNC_TOKEN_HEADER = 'X-Sync-Token'


def sync_settings():
    """Where to send, and the shared secret: environment first, then the file.

    On the laptop the two values sit in sync_config.json. On PythonAnywhere
    only the token matters and it goes in the WSGI file's environment, so no
    secret has to be uploaded with the code.
    """
    stored = {}
    try:
        with open(SYNC_CONFIG_PATH, encoding='utf-8') as handle:
            loaded = json.load(handle)
            if isinstance(loaded, dict):
                stored = loaded
    except (OSError, ValueError):
        pass
    return {
        'server_url': str(os.environ.get('MNHS_SYNC_URL')
                          or stored.get('server_url') or '').strip().rstrip('/'),
        'token': str(os.environ.get('MNHS_SYNC_TOKEN')
                     or stored.get('token') or '').strip(),
    }


def sync_sent(kind):
    """The keys of this kind that the live server already has."""
    return (db.session.query(SyncSent.key)
            .filter(SyncSent.kind == kind).scalar_subquery())


def sync_pending_users():
    return (User.query
            .filter(db.func.lower(User.email).notin_(sync_sent('users')))
            .order_by(User.id).limit(SYNC_BATCH).all())


def sync_pending_attempts():
    return (db.session.query(QuizAttempt, User)
            .join(User, QuizAttempt.user_id == User.id)
            .filter(QuizAttempt.client_uuid.notin_(sync_sent('attempts')))
            .order_by(QuizAttempt.id).limit(SYNC_BATCH).all())


def sync_pending_ungraded():
    return (db.session.query(UngradedAttempt, User)
            .outerjoin(User, UngradedAttempt.user_id == User.id)
            .filter(UngradedAttempt.client_uuid.notin_(sync_sent('ungraded')))
            .order_by(UngradedAttempt.id).limit(SYNC_BATCH).all())


def sync_pending_counts():
    return {
        'users': (User.query
                  .filter(db.func.lower(User.email).notin_(sync_sent('users'))).count()),
        'attempts': (QuizAttempt.query
                     .filter(QuizAttempt.client_uuid.notin_(sync_sent('attempts'))).count()),
        'ungraded': (UngradedAttempt.query
                     .filter(UngradedAttempt.client_uuid.notin_(sync_sent('ungraded'))).count()),
    }


def sync_datetime(value):
    try:
        return datetime.fromisoformat(str(value)) if value else datetime.utcnow()
    except (TypeError, ValueError):
        return datetime.utcnow()


def sync_payload():
    """One batch of new rows, plus the keys to mark sent once it is accepted."""
    users = sync_pending_users()
    attempts = sync_pending_attempts()
    ungraded = sync_pending_ungraded()
    payload = {
        'users': [{
            'email': (row.email or '').strip().lower(),
            'first_name': row.first_name or '',
            'middle_name': row.middle_name or '',
            'last_name': row.last_name or '',
            'suffix': row.suffix or '',
            'school': row.school or '',
            'grade': row.grade or '',
            'section': row.section or '',
            'password_hash': row.password_hash or '',
            'created_at': row.created_at.isoformat() if row.created_at else None,
        } for row in users if (row.email or '').strip()],
        'attempts': [{
            'client_uuid': row.client_uuid,
            'user_email': (owner.email or '').strip().lower(),
            'subject': row.subject or '',
            'topic': row.topic or '',
            'quiz_set_info': row.quiz_set_info or '',
            'score': int(row.score or 0),
            'total': int(row.total or 0),
            'date_taken': row.date_taken.isoformat() if row.date_taken else None,
            'source': row.source or 'quiz',
            'recorded_by': row.recorded_by or '',
        } for row, owner in attempts],
        'ungraded': [{
            'client_uuid': row.client_uuid,
            'user_email': (owner.email or '').strip().lower() if owner else '',
            'name': row.name or 'annonymous',
            'school': row.school or '',
            'grade': row.grade or '',
            'section': row.section or '',
            'subject': row.subject or '',
            'topic': row.topic or '',
            'quiz_set_info': row.quiz_set_info or '',
            'score': int(row.score or 0),
            'total': int(row.total or 0),
            'date_taken': row.date_taken.isoformat() if row.date_taken else None,
        } for row, owner in ungraded],
    }
    keys = {
        'users': [(row.email or '').strip().lower() for row in users
                  if (row.email or '').strip()],
        'attempts': [row.client_uuid for row, _owner in attempts],
        'ungraded': [row.client_uuid for row, _owner in ungraded],
    }
    return payload, keys


def sync_mark_sent(kind, keys):
    """Remember what the live server took, ignoring anything already written."""
    for key in keys:
        if not key:
            continue
        db.session.execute(db.text(
            'INSERT OR IGNORE INTO sync_sent (kind, key, sent_at) '
            'VALUES (:kind, :key, :at)'),
            {'kind': kind, 'key': key, 'at': datetime.utcnow()})
    db.session.commit()


def sync_post(url, token, payload):
    """Post one batch and read the answer; every failure becomes a message."""
    packed = json.dumps(payload).encode('utf-8')
    request_obj = urllib.request.Request(
        url, data=packed, method='POST',
        headers={'Content-Type': 'application/json',
                 'Accept': 'application/json',
                 SYNC_TOKEN_HEADER: token,
                 'User-Agent': 'MNHS-Review-Sync/1'})
    try:
        with urllib.request.urlopen(request_obj, timeout=60) as response:
            answer = json.loads(response.read().decode('utf-8') or '{}')
            return answer if isinstance(answer, dict) else {'ok': False}
    except urllib.error.HTTPError as error:
        detail = error.read().decode('utf-8', 'replace').strip()[:300]
        if error.code == 401:
            return {'ok': False,
                    'error': 'The live server did not accept the token. Check that '
                             'sync_config.json and the WSGI file hold the same one.'}
        return {'ok': False,
                'error': 'The live server refused the batch (HTTP %s). %s'
                         % (error.code, detail)}
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {'ok': False, 'error': 'Could not reach the live server: %s' % error}


@app.route('/api/sync/ingest', methods=['POST'])
def sync_ingest():
    """The live copy's door for a laptop's batch. Token only, no login."""
    settings = sync_settings()
    if not settings['token']:
        return jsonify({'ok': False, 'error': 'sync_not_configured'}), 503
    given = request.headers.get(SYNC_TOKEN_HEADER, '')
    if not hmac.compare_digest(given.encode('utf-8'), settings['token'].encode('utf-8')):
        return jsonify({'ok': False, 'error': 'bad_token'}), 401
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'ok': False, 'error': 'bad_body'}), 400

    accepted = {'users': [], 'attempts': [], 'ungraded': []}
    rejected = []

    def reject(kind, key, reason):
        rejected.append({'kind': kind, 'key': str(key or ''), 'reason': reason})

    for item in (body.get('users') or [])[:1000]:
        if not isinstance(item, dict):
            continue
        email = str(item.get('email') or '').strip().lower()[:120]
        if not email or '@' not in email:
            reject('user', email, 'bad_email')
            continue
        if User.query.filter(db.func.lower(User.email) == email).first() is not None:
            # The account is already here: the live password stays the one in use.
            accepted['users'].append(email)
            continue
        try:
            with db.session.begin_nested():
                db.session.add(User(
                    first_name=str(item.get('first_name') or '')[:80],
                    middle_name=str(item.get('middle_name') or '')[:80],
                    last_name=str(item.get('last_name') or '')[:80],
                    suffix=str(item.get('suffix') or '')[:10],
                    school=str(item.get('school') or '')[:200],
                    grade=str(item.get('grade') or '')[:20],
                    section=str(item.get('section') or '')[:80],
                    email=email,
                    password_hash=(str(item.get('password_hash') or '')[:255]
                                   or generate_password_hash(secrets.token_urlsafe(24))),
                    created_at=sync_datetime(item.get('created_at')),
                ))
        except Exception as error:  # one bad row must not sink the batch
            app.logger.warning('Sync could not add learner %s: %s', email, error)
            reject('user', email, 'could_not_add')
            continue
        accepted['users'].append(email)

    for item in (body.get('attempts') or [])[:1000]:
        if not isinstance(item, dict):
            continue
        client_uuid = str(item.get('client_uuid') or '').strip()[:64]
        if not client_uuid:
            reject('attempt', '', 'no_uuid')
            continue
        if QuizAttempt.query.filter_by(client_uuid=client_uuid).first() is not None:
            accepted['attempts'].append(client_uuid)
            continue
        email = str(item.get('user_email') or '').strip().lower()
        owner = (User.query.filter(db.func.lower(User.email) == email).first()
                 if email else None)
        if owner is None:
            reject('attempt', client_uuid, 'student_not_on_server')
            continue
        try:
            with db.session.begin_nested():
                db.session.add(QuizAttempt(
                    user_id=owner.id,
                    client_uuid=client_uuid,
                    subject=str(item.get('subject') or '')[:120],
                    topic=str(item.get('topic') or '')[:200],
                    quiz_set_info=str(item.get('quiz_set_info') or ''),
                    score=int(item.get('score') or 0),
                    total=int(item.get('total') or 0),
                    date_taken=sync_datetime(item.get('date_taken')),
                    source='manual' if str(item.get('source') or '') == 'manual' else 'quiz',
                    recorded_by=str(item.get('recorded_by') or '')[:120] or None,
                ))
        except Exception as error:
            app.logger.warning('Sync could not add result %s: %s', client_uuid, error)
            reject('attempt', client_uuid, 'could_not_add')
            continue
        accepted['attempts'].append(client_uuid)

    for item in (body.get('ungraded') or [])[:1000]:
        if not isinstance(item, dict):
            continue
        client_uuid = str(item.get('client_uuid') or '').strip()[:64]
        if not client_uuid:
            reject('ungraded', '', 'no_uuid')
            continue
        if UngradedAttempt.query.filter_by(client_uuid=client_uuid).first() is not None:
            accepted['ungraded'].append(client_uuid)
            continue
        email = str(item.get('user_email') or '').strip().lower()
        owner = (User.query.filter(db.func.lower(User.email) == email).first()
                 if email else None)
        try:
            with db.session.begin_nested():
                db.session.add(UngradedAttempt(
                    client_uuid=client_uuid,
                    user_id=owner.id if owner else None,
                    name=str(item.get('name') or 'annonymous')[:120] or 'annonymous',
                    school=str(item.get('school') or '')[:200],
                    grade=str(item.get('grade') or '')[:20],
                    section=str(item.get('section') or '')[:80],
                    subject=str(item.get('subject') or '')[:120],
                    topic=str(item.get('topic') or '')[:200],
                    quiz_set_info=str(item.get('quiz_set_info') or ''),
                    score=int(item.get('score') or 0),
                    total=int(item.get('total') or 0),
                    date_taken=sync_datetime(item.get('date_taken')),
                ))
        except Exception as error:
            app.logger.warning('Sync could not add ungraded %s: %s', client_uuid, error)
            reject('ungraded', client_uuid, 'could_not_add')
            continue
        accepted['ungraded'].append(client_uuid)

    try:
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        app.logger.exception('Sync ingest could not save the batch')
        return jsonify({'ok': False, 'error': 'could_not_save',
                        'detail': str(error)[:200]}), 500
    return jsonify({'ok': True, 'accepted': accepted, 'rejected': rejected})


SYNC_LOCK = threading.Lock()


def sync_all():
    """Push every pending batch to the live server. Returns (ok, message)."""
    settings = sync_settings()
    if not settings['server_url'] or not settings['token']:
        return False, ('Sync is not set up yet. Put the live address and the same '
                       'token in sync_config.json beside app.py, then try again.')
    if not SYNC_LOCK.acquire(blocking=False):
        return False, 'A sync is already running. Wait for it to finish.'
    try:
        url = settings['server_url'] + '/api/sync/ingest'
        totals = {'users': 0, 'attempts': 0, 'ungraded': 0}
        problems = []
        ok = True

        for _round in range(SYNC_ROUNDS):
            payload, keys = sync_payload()
            if not any(payload.values()):
                break
            answer = sync_post(url, settings['token'], payload)
            if not answer.get('ok'):
                ok = False
                problems.append(str(answer.get('error') or 'The live server did not answer.'))
                break

            taken = answer.get('accepted') or {}
            sent = {}
            for kind in totals:
                wanted = set(keys[kind])
                sent[kind] = [key for key in (taken.get(kind) or []) if key in wanted]
                totals[kind] += len(sent[kind])
                sync_mark_sent(kind, sent[kind])

            bad = answer.get('rejected') or []
            if bad:
                ok = False
                for item in bad[:5]:
                    problems.append('%s %s: %s' % (item.get('kind'), item.get('key'),
                                                   item.get('reason')))
                break
            if not any(sent.values()):
                # The server accepted nothing new, so sending the same batch
                # again would loop for ever. Leave the rows pending and say so.
                ok = False
                problems.append('The live server accepted nothing from that batch.')
                break

        summary = ('%s account(s), %s result(s) and %s ungraded quiz(zes) copied'
                   % (totals['users'], totals['attempts'], totals['ungraded']))
        if ok and not problems:
            message = ('Sync finished: %s to the live server.' % summary
                       if any(totals.values()) else 'Nothing new to send.')
        else:
            message = 'Sync stopped. %s. %s' % (summary, ' '.join(problems[:3]))

        db.session.add(SyncRun(ok=ok and not problems, message=message[:2000]))
        db.session.commit()
        return ok and not problems, message
    finally:
        SYNC_LOCK.release()


@app.route('/admin/sync')
@main_admin_required
def admin_sync():
    message = session.pop('sync_message', '')
    last = SyncRun.query.order_by(SyncRun.id.desc()).first()
    return render_template('admin_sync.html',
                           user=current_user(),
                           settings=sync_settings(),
                           counts=sync_pending_counts(),
                           last=last,
                           message=message)


@app.route('/admin/sync/run', methods=['POST'])
@main_admin_required
def admin_sync_run():
    _ok, message = sync_all()
    session['sync_message'] = message
    return redirect(url_for('admin_sync'))


@app.route('/admin/assessment')
@staff_required
def admin_assessment():
    user = current_user()
    me = staff_email()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    groups = pick_classes(sections_map())
    grade = request.args.get('grade', '').strip()
    if grade not in groups:
        grade = ''
    section = norm_section(request.args.get('section', ''))
    if grade and section not in groups[grade]:
        section = ''
    subject = request.args.get('subject', '').strip()
    topic = request.args.get('topic', '').strip()

    students = []
    scope = section_scope(grade) if grade else None
    if grade and (not section or may_open_class(grade, section)):
        query = User.query.filter(User.grade == grade)
        if section:
            query = query.filter(db.func.upper(User.section) == section)
        elif scope is not None:
            query = query.filter(db.func.upper(User.section).in_(scope))
        students = query.order_by(
            db.func.upper(User.first_name), db.func.upper(User.last_name)).all()

    rows = []
    by_id = {}
    for student in students:
        row = {'user': student, 'attempts': [], 'score_sum': 0, 'total_sum': 0, 'best': None}
        rows.append(row)
        by_id[student.id] = row

    if grade and subject:
        query = (db.session.query(QuizAttempt, User)
                 .join(User, QuizAttempt.user_id == User.id)
                 .filter(User.grade == grade)
                 .filter(db.func.lower(QuizAttempt.subject) == subject.lower()))
        if section:
            query = query.filter(db.func.upper(User.section) == section)
        elif scope is not None:
            query = query.filter(db.func.upper(User.section).in_(scope))
        if topic:
            query = query.filter(
                db.func.lower(db.func.coalesce(QuizAttempt.topic, '')) == topic.lower())
        for attempt, student in query.order_by(QuizAttempt.date_taken.desc()).all():
            row = by_id.get(student.id)
            if row is None:
                # A score left by an account that has since been removed still
                # belongs in the totals, so it must not vanish from the page.
                row = {'user': student, 'attempts': [], 'score_sum': 0, 'total_sum': 0,
                       'best': None}
                by_id[student.id] = row
                rows.append(row)
            pct = round(attempt.score * 100 / attempt.total) if attempt.total else None
            manual = (attempt.source or 'quiz') == 'manual'
            row['attempts'].append({
                'id': attempt.id,
                'score': attempt.score,
                'total': attempt.total,
                'pct': pct,
                'topic': attempt.topic or '',
                'manual': manual,
                'mine': manual and (attempt.recorded_by or '').strip().lower() == me,
                'date': attempt.date_taken.strftime('%b %d, %Y') if attempt.date_taken else '',
                'day': attempt.date_taken.strftime('%Y-%m-%d') if attempt.date_taken else today,
            })
            row['score_sum'] += attempt.score
            row['total_sum'] += attempt.total
            if pct is not None and (row['best'] is None or pct > row['best']):
                row['best'] = pct

    for row in rows:
        row['pct'] = round(row['score_sum'] * 100 / row['total_sum']) if row['total_sum'] else None

    rows.sort(key=lambda r: (-(r['best'] if r['best'] is not None else -1),
                             r['user'].first_name or '', r['user'].last_name or ''))

    shown_score = sum(r['score_sum'] for r in rows)
    shown_total = sum(r['total_sum'] for r in rows)

    return render_template(
        'admin_assessment.html',
        user=user,
        grade=grade,
        section=section,
        subject=subject,
        topic=topic,
        grade_choices=list(groups),
        sections=groups.get(grade, []),
        class_map=groups,
        classes=class_choices(),
        learners=openable_learners(),
        sets=quiz_set_choices(grade) if grade else [],
        spec_json=spec_json(),
        rows=rows,
        scored=sum(1 for r in rows if r['attempts']),
        waiting=sum(1 for r in rows if not r['attempts']),
        class_pct=round(shown_score * 100 / shown_total) if shown_total else None,
        today=today,
        notice=request.args.get('notice', ''),
        error=request.args.get('error', ''),
    )


@app.route('/admin/summative/questions')
@staff_required
def admin_summative_questions():
    """The bank behind a summative test: one grade, one subject, any number of topics.

    The pickers work exactly like the quiz setup, only the topic list is a set
    of check boxes, so the questions pulled here are the ones that selection
    would have drawn from. The correct answers are not sent to the page.
    """
    if not role_can('summative'):
        return jsonify({'error': 'forbidden'}), 403

    level = request.args.get('level', '').strip().lower()
    subject = request.args.get('subject', '').strip().lower()
    quarter = request.args.get('quarter', '').strip().lower()
    topics = {str(t).strip().lower() for t in request.args.getlist('topics') if str(t).strip()}
    scope = staff_subject_scope()
    if scope is not None and subject not in scope:
        # The picker already hides them; a typed-in subject cannot get past them.
        return jsonify({'items': []})
    if not level or not subject:
        return jsonify({'items': []})

    items = [
        {'id': q['id'], 'topic': q['topic'], 'question': q['question'], 'options': q['options']}
        for q in QUESTIONS
        if q['level'].lower() == level
        and q['subject'].lower() == subject
        and (not quarter or quarter == '__all__' or q['quarter'].lower() == quarter)
        and (not topics or q['topic'].lower() in topics)
    ]
    return jsonify({'items': items})


def score_bounds(form):
    """Read the two numbers on a mark and police them.

    Returns (score, total, error); error is '' when the pair is usable. Both
    recording and correcting go through here so the two pages can never argue
    about what a valid mark is.
    """
    try:
        score = int(str(form.get('score')).strip())
        total = int(str(form.get('total')).strip())
    except (TypeError, ValueError):
        return 0, 0, 'Type whole numbers for the score and the total.'
    if total < 1 or total > 200 or score < 0 or score > total:
        return 0, 0, 'The score must sit between 0 and the total, and a set holds at most 200 items.'
    return score, total, ''


@app.route('/admin/assessment/score', methods=['POST'])
@staff_required
def admin_assessment_score_add():
    form = request.form
    back = assessment_args(form)
    student = db.session.get(User, int(form.get('user_id') or 0))
    if not student:
        return redirect(url_for('admin_assessment', error='That student is no longer in the database.', **back))

    subject = (form.get('subject') or '').strip()
    topic = (form.get('topic') or '').strip()
    if not subject or not topic:
        return redirect(url_for('admin_assessment',
                                error='Pick a subject and a topic before recording a score.', **back))

    score, total, problem = score_bounds(form)
    if problem:
        return redirect(url_for('admin_assessment', error=problem, **back))

    db.session.add(QuizAttempt(
        user_id=student.id,
        client_uuid='manual-' + secrets.token_hex(10),
        subject=subject[:120],
        topic=topic[:200],
        quiz_set_info='[]',
        score=score,
        total=total,
        date_taken=assessment_date(form.get('date_taken')),
        source='manual',
        recorded_by=staff_email(),
    ))
    db.session.commit()
    return redirect(url_for(
        'admin_assessment',
        notice='Recorded %d/%d for %s in %s.' % (score, total, student.full_name(), topic),
        **back))


@app.route('/admin/assessment/score/<int:attempt_id>/edit', methods=['POST'])
@level_required('admin')
def admin_assessment_score_edit(attempt_id):
    """An admin-level account puts a saved quiz right: the mark, its total and its day.

    The questions answered stay exactly as they were answered, so the item
    analysis on the Results Dashboard still reports the real attempt.
    """
    form = request.form
    back = assessment_args(form)
    attempt = db.session.get(QuizAttempt, attempt_id)
    if attempt is None:
        return redirect(url_for('admin_assessment', error='That score is already gone.', **back))

    score, total, problem = score_bounds(form)
    if problem:
        return redirect(url_for('admin_assessment', error=problem, **back))

    attempt.score = score
    attempt.total = total
    attempt.date_taken = assessment_date(form.get('date_taken'))
    db.session.commit()
    student = db.session.get(User, attempt.user_id)
    return redirect(url_for(
        'admin_assessment',
        notice='Corrected the score of %s to %d/%d.' % (
            student.full_name() if student else 'that student', score, total),
        **back))


@app.route('/admin/assessment/score/<int:attempt_id>/delete', methods=['POST'])
@staff_required
def admin_assessment_score_delete(attempt_id):
    back = assessment_args(request.form)
    attempt = db.session.get(QuizAttempt, attempt_id)
    if attempt is None:
        return redirect(url_for('admin_assessment', error='That score is already gone.', **back))

    manual = (attempt.source or 'quiz') == 'manual'
    if not at_least('main_admin'):
        # A teacher may only take back the mark they themselves recorded.
        owner = (attempt.recorded_by or '').strip().lower()
        if not manual or owner != staff_email():
            return redirect(url_for(
                'admin_assessment',
                error='You can only remove a score you recorded here.', **back))

    student = db.session.get(User, attempt.user_id)
    name = student.full_name() if student else 'that student'
    db.session.delete(attempt)
    db.session.commit()
    return redirect(url_for(
        'admin_assessment',
        notice='Removed the %s score for %s.' % ('recorded' if manual else 'on-app quiz', name),
        **back))


def student_form_values(s):
    return {
        'first_name': s.first_name or '', 'middle_name': s.middle_name or '',
        'last_name': s.last_name or '', 'suffix': s.suffix or 'N/A',
        'school': s.school or '', 'grade': s.grade or '',
        # The section pickers hold upper-case names, so a legacy 'Vanguard' row
        # must arrive as 'VANGUARD' or the dropdown would silently change it.
        'section': norm_section(s.section), 'email': s.email or '',
    }


@app.route('/admin/assessment/student/<int:user_id>/class', methods=['POST'])
@staff_required
def admin_assessment_student_class(user_id):
    """Move a learner to another grade level and section, from the row itself.

    The assessment table pulls a learner in with whatever class was on their
    account, so this is where a wrong or out-of-date class gets corrected. The
    main admin may move anyone; a teacher may move the learners of a class
    assigned to them, which is also how a learner leaves that teacher's roster.
    """
    student = db.session.get(User, user_id)
    back = assessment_args(request.form)
    if not student:
        return redirect(url_for('admin_assessment',
                                error='That learner is no longer in the database.', **back))
    if not may_open_class(student.grade, student.section):
        return redirect(url_for('admin_assessment',
                                error='That class is not assigned to you.', **back))

    grade = (request.form.get('new_grade') or '').strip()
    section = norm_section(request.form.get('new_section'))
    if section not in section_choices_for(grade):
        return redirect(url_for('admin_assessment',
                                error='Pick a grade level and a section from the lists.', **back))

    if (grade, section) == (student.grade, norm_section(student.section)):
        message = '%s stayed in %s %s.' % (student.full_name(), grade, section)
    else:
        was = '%s %s' % (student.grade, norm_section(student.section) or '(no section)')
        student.grade = grade
        student.section = section
        db.session.commit()
        message = 'Moved %s from %s to %s %s.' % (student.full_name(), was, grade, section)

    return redirect(url_for('admin_assessment', notice=message, **back))


@app.route('/admin/assessment/student/<int:user_id>', methods=['GET', 'POST'])
@main_admin_required
def admin_assessment_student(user_id):
    """Correct one learner's details, move them, drop them from a section, or
    take them out of the database. The main admin alone, and every write is one
    deliberate click on this page."""
    user = current_user()
    student = db.session.get(User, user_id)
    if student is None:
        return redirect(url_for('admin_assessment'))

    back = assessment_args(request.args if request.method == 'GET' else request.form)
    values = student_form_values(student)
    errors = {}
    message = None

    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()

        if action == 'save':
            values = {
                'first_name': request.form.get('first_name', '').strip(),
                'middle_name': request.form.get('middle_name', '').strip(),
                'last_name': request.form.get('last_name', '').strip(),
                'suffix': request.form.get('suffix', 'N/A').strip() or 'N/A',
                'school': request.form.get('school', '').strip(),
                'grade': request.form.get('grade', '').strip(),
                'section': norm_section(request.form.get('section')),
                'email': request.form.get('email', '').strip().lower(),
            }
            if not values['first_name']:
                errors['first_name'] = 'First Name is required.'
            if not values['last_name']:
                errors['last_name'] = 'Last Name is required.'
            if values['suffix'] not in SUFFIX_CHOICES:
                errors['suffix'] = 'Invalid suffix.'
            if not values['school']:
                errors['school'] = 'School is required.'
            if values['grade'] not in grade_choices():
                errors['grade'] = 'Pick a grade level the school created.'
            if values['section'] and \
                    values['section'] not in section_choices_for(values['grade']):
                errors['section'] = 'Pick the section from that grade\'s list.'
            if not values['email'] or '@' not in values['email']:
                errors['email'] = 'A valid email is required.'
            else:
                taken = User.query.filter(db.func.lower(User.email) == values['email'],
                                          User.id != student.id).first()
                if taken:
                    errors['email'] = 'Another account already uses that email.'

            password = (request.form.get('__new_password__') or '').strip()
            if password and len(password) < 8:
                errors['password'] = 'A new password needs at least 8 characters.'

            if not errors:
                student.first_name = tidy_name(values['first_name'])
                student.middle_name = tidy_name(values['middle_name']) or None
                student.last_name = tidy_name(values['last_name'])
                student.suffix = values['suffix']
                student.school = values['school']
                student.grade = values['grade']
                student.section = values['section']
                student.email = values['email']
                if password:
                    student.password_hash = generate_password_hash(password)
                db.session.commit()
                message = 'Saved %s.' % student.full_name()

        elif action == 'drop':
            student.section = ''
            db.session.commit()
            message = '%s is no longer in any section. Their quiz history stayed.' % \
                student.full_name()
            values = student_form_values(student)

        elif action == 'delete':
            if student.id == user.id:
                errors['delete'] = 'You cannot delete the admin account you are signed in with.'
            elif (request.form.get('confirm_email') or '').strip().lower() != (student.email or '').lower():
                errors['delete'] = ('Type the student\'s email exactly to confirm. '
                                    'This deletes the account and every quiz saved under it.')
            else:
                name = tidy_name(student.first_name, student.last_name)
                QuizAttempt.query.filter_by(user_id=student.id).delete()
                # A declined quiz keeps teaching value as item data, so it stays
                # on file with the name it was recorded under and no account.
                UngradedAttempt.query.filter_by(user_id=student.id).update(
                    {'user_id': None}, synchronize_session=False)
                Resource.query.filter_by(added_by=student.id).update(
                    {'added_by': None}, synchronize_session=False)
                db.session.delete(student)
                db.session.commit()
                return redirect(url_for('admin_assessment',
                                        notice='Removed %s from the database.' % name,
                                        **back))

    attempts = QuizAttempt.query.filter_by(user_id=student.id).order_by(
        QuizAttempt.date_taken.desc()).all()
    ungraded = UngradedAttempt.query.filter_by(user_id=student.id).count()

    return render_template(
        'admin_assessment_student.html',
        user=user,
        student=student,
        values=values,
        errors=errors,
        message=message,
        suffix_choices=SUFFIX_CHOICES,
        grade_choices=grade_choices(),
        classes=class_choices(),
        attempt_count=len(attempts),
        manual_count=sum(1 for a in attempts if (a.source or 'quiz') == 'manual'),
        ungraded_count=ungraded,
        back=back,
    )


# --- WHO'S WHO (the teacher-written picture game, mounted at /games/whoswho) ---
WHOSWHO_DIR = os.path.join(basedir, 'WHOSWHO')
WHOSWHO_JSON = os.path.join(basedir, 'whoswho.json')


def mount_whoswho():
    """Load Who's Who and serve it under /games/whoswho on this database.

    Activities live in whoswho.json in this folder, pictures in Google Drive and
    a local mirror in whoswho_photos. The game's own tables (ww_rooms,
    ww_players, ww_answers) sit inside quiz_app.db and never touch quiz_attempt.
    """
    import importlib.util

    path = os.path.join(WHOSWHO_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning("Who's Who is not in %s, so /games/whoswho stays disabled",
                           WHOSWHO_DIR)
        return False

    app.config['WHOSWHO_BACK_URL'] = '/games'
    if WHOSWHO_DIR not in sys.path:
        sys.path.append(WHOSWHO_DIR)          # the game imports its own data and drive modules
    spec = importlib.util.spec_from_file_location('whoswho_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['whoswho_game'] = game
    spec.loader.exec_module(game)

    game.mount(app, url_prefix='/games/whoswho', db_path=DB_PATH, data_path=WHOSWHO_JSON)
    game.identity = game_student_identity     # a signed-in student never types a name
    game.is_admin = lambda: bool(admin_kind())
    return game


WHOSWHO = mount_whoswho()
WHOSWHO_READY = bool(WHOSWHO)


# --- ELEMENTAL TABLE GAME (five rows of the table, 25 cells emptied) ---
ETABLE_DIR = os.path.join(basedir, 'ETABLE')


def mount_elemental_table():
    """Load Elemental Table Game and serve it under /games/elemental-table.

    The game deals from the `elements` table ELEMENTALS already seeds into this
    database, so both games read one periodic table. Its own rows live in
    etg_games and never enter quiz_attempt.
    """
    import importlib.util

    path = os.path.join(ETABLE_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning('Elemental Table Game is not in %s, so '
                           '/games/elemental-table stays disabled', ETABLE_DIR)
        return False

    app.config['ETABLE_BACK_URL'] = '/games'
    if ETABLE_DIR not in sys.path:
        sys.path.append(ETABLE_DIR)         # the game imports its own etg_pdf module
    if GAME_READY:
        # ELEMENTALS is mounted at /game, and its /table page is the board of
        # element tiles the table game links to for a value nobody can work out.
        app.config['ETABLE_TILES_URL'] = '/game/table'
    spec = importlib.util.spec_from_file_location('etable_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['etable_game'] = game
    spec.loader.exec_module(game)

    game.mount(app, url_prefix='/games/elemental-table', db_path=DB_PATH)
    game.identity = game_student_identity     # a signed-in student never types a name
    game.is_admin = lambda: bool(admin_kind())  # staff-only worksheet pages
    return game


ETABLE = mount_elemental_table()
ETABLE_READY = bool(ETABLE)


# --- CROSSWORDS (teacher-built clue crosswords, ten words at a time) ---
CROSSWORDS_DIR = os.path.join(basedir, 'Crosswords')


def mount_crossword():
    """Load Crosswords and serve it under /games/crossword on this database.

    Its own tables (cw_puzzles, cw_attempts, cw_scores) sit inside quiz_app.db
    and game scores never enter quiz_attempt. A teacher lists ten words with
    clues, the app interlocks them into one grid, and every exact word clicked
    out on the tiles is worth three points, thirty at the most.
    """
    import importlib.util

    path = os.path.join(CROSSWORDS_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning('Crosswords is not in %s, so /games/crossword stays disabled',
                           CROSSWORDS_DIR)
        return False

    app.config['CROSSWORDS_BACK_URL'] = '/games'
    if CROSSWORDS_DIR not in sys.path:
        sys.path.append(CROSSWORDS_DIR)        # the game imports cw_gen and cw_pdf
    spec = importlib.util.spec_from_file_location('crossword_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['crossword_game'] = game
    spec.loader.exec_module(game)

    game.mount(app, url_prefix='/games/crossword', db_path=DB_PATH)
    game.identity = game_student_identity      # a signed-in student never types a name
    game.is_admin = lambda: bool(admin_kind()) # teacher, admin or main_admin
    game.is_officer = lambda: admin_kind() in ('admin', 'main_admin')
    game.staff_account = lambda: session.get('staff_email', '')
    return game


CROSSWORDS = mount_crossword()
CROSSWORDS_READY = bool(CROSSWORDS)


# --- QUANTUM ARCHITECT (the electron configuration board and worksheet studio) ---
# The player builds atoms on an orbital ladder while Aufbau, Pauli and Hund act as
# the physics that rejects a wrong move, and the same engine writes the teacher's
# worksheet papers and their answer keys as editable DOCX plus print PDF.
QUANTUM_DIR = os.path.join(basedir, 'Quantum Architect')


def mount_quantum_architect():
    """Load Quantum Architect and serve it under /games/quantum-architect.

    It adds no tables to quiz_app.db: a board run is scored in the browser and a
    worksheet is a document a teacher downloads, so the saved papers stay in
    Quantum Architect/data/worksheets.json. What the hub lends it instead is the
    session - a teacher, an admin or the main admin opens the answer keys, so the
    PIN screen the folder used on its own is gone.
    """
    import importlib.util

    path = os.path.join(QUANTUM_DIR, 'app.py')
    if not os.path.exists(path):
        app.logger.warning('Quantum Architect is not in %s, so /games/quantum-architect '
                           'stays disabled', QUANTUM_DIR)
        return False

    app.config['QA_BACK_URL'] = '/games'
    app.config['QA_LOGIN_URL'] = '/admin/login'   # the door teacher, admin and main admin use
    if QUANTUM_DIR not in sys.path:
        sys.path.append(QUANTUM_DIR)          # the game imports its own quantum package
    spec = importlib.util.spec_from_file_location('quantum_architect_game', path)
    game = importlib.util.module_from_spec(spec)
    sys.modules['quantum_architect_game'] = game
    spec.loader.exec_module(game)

    game.mount(app, url_prefix='/games/quantum-architect')
    game.identity = game_student_identity        # the paper header knows the class
    game.is_admin = lambda: bool(admin_kind())   # teacher, admin or main_admin
    game.teacher_label = lambda: staff_name(my_staff_email())
    return game


QUANTUM = mount_quantum_architect()
QUANTUM_READY = bool(QUANTUM)


@app.route('/games')
def games_hub():
    acts = WHOSWHO.D.activities() if WHOSWHO else []
    return render_template(
        'games.html',
        elementals=GAME_READY,
        jumbled=JUMBLED_READY,
        whoswho=WHOSWHO_READY,
        etable=ETABLE_READY,
        etable_points=ETABLE.MAX_POINTS if ETABLE else 25,
        etable_rows=ETABLE.ROWS if ETABLE else 5,
        etable_blanks=ETABLE.BLANKS if ETABLE else 5,
        acts=acts,
        act_count=len(acts),
        act_people=sum(len(a['persons']) for a in acts),
        word_seconds=JUMBLED.WORD_SECONDS if JUMBLED else 90,
        max_players=JUMBLED.MAX_PLAYERS if JUMBLED else 45,
        target_points=JUMBLED.W.TARGET_POINTS if JUMBLED else 5,
        valid_points=JUMBLED.W.VALID_POINTS if JUMBLED else 1,
        crossword=CROSSWORDS_READY,
        crossword_words=CROSSWORDS.WORDS_PER_PUZZLE if CROSSWORDS else 10,
        crossword_points=CROSSWORDS.POINTS_PER_WORD if CROSSWORDS else 3,
        crossword_max=CROSSWORDS.MAX_POINTS if CROSSWORDS else 30,
        quantum=QUANTUM_READY,
        quantum_max_z=QUANTUM.MAX_Z if QUANTUM else 118,
        quantum_types=QUANTUM.QUESTION_TYPES if QUANTUM else 10,
        quantum_tiers=' · '.join(QUANTUM.TIER_NAMES) if QUANTUM else '',
    )


# --- WEB PUSH: schedule reminders for learners and staff ---
# A student's phone or a teacher's laptop gets a real notification even when
# this app is closed: the browser's own push service carries the message to the
# device and shows it in its notification tray. VAPID keys are this app's ID
# card at those services - generated once into vapid.json beside admin.db.
# Times are read on the computer's own clock: run the app on a Philippine-time
# machine and the reminders land at Philippine time.
try:
    from pywebpush import webpush as _webpush, WebPushException as _WebPushException
except ImportError:  # reminders simply stay off until the package is installed
    _webpush = None
    _WebPushException = Exception

VAPID_PATH = os.path.join(basedir, 'vapid.json')
REMINDER_LEAD_MINUTES = 3
DIGEST_HOUR = 6

# The one-time "turn on class reminders" bar keeps its answer here, per signed
# in account. "ask" is the untouched default; "shown" means the bar has been
# seen once and must not come back on its own; "enabled" and "dismissed" are
# what the person chose. Nothing in this file is a notification address - the
# push subscriptions stay in the database.
REMINDER_CHOICE_PATH = os.path.join(basedir, 'reminder_choice.json')
REMINDER_CHOICE_DEFAULT = 'ask'
REMINDER_CHOICES = ('ask', 'shown', 'enabled', 'dismissed')
_REMINDER_CHOICE_LOCK = threading.Lock()


def ensure_vapid():
    """The VAPID key pair, created on first use and kept in vapid.json."""
    try:
        with open(VAPID_PATH) as handle:
            saved = json.load(handle)
        if saved.get('private_pem') and saved.get('public_key'):
            return saved
    except (OSError, ValueError):
        pass
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()
    raw_public = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint)
    saved = {'private_pem': private_pem,
             'public_key': base64.urlsafe_b64encode(raw_public).decode()}
    tmp = VAPID_PATH + '.tmp'
    with open(tmp, 'w') as handle:
        json.dump(saved, handle)
    os.replace(tmp, VAPID_PATH)
    return saved


def today_day_label():
    """'Mon'..'Sun' for the machine's own calendar, in school order."""
    return CLASS_DAYS[datetime.now().weekday()]


def non_class_note(day=None):
    """The note halting the whole school on one date, or '' for a normal day."""
    day = day or datetime.now().strftime('%Y-%m-%d')
    row = NonClassDay.query.filter_by(date=day).first()
    return str(row.note or '') if row else ''


def learner_meetings(user, day=None):
    """One learner's class times today, from their section's schedule."""
    day = day or today_day_label()
    section = SectionLevel.query.filter_by(
        grade=user.grade, name=norm_section(user.section)).first()
    if not section:
        return []
    label = '%s %s' % (user.grade, norm_section(user.section))
    if room_label(section.room):
        label += ' - %s' % room_label(section.room)
    return [(start, end, label)
            for days, start, end in iter_slots(section)
            if day in days and start]


def staff_meetings(email, day=None):
    """One teacher's class times today, from the assignments on the Classes page."""
    day = day or today_day_label()
    member = Staff.query.filter(
        db.func.lower(Staff.email) == str(email or '').strip().lower()).first()
    if not member:
        return []
    out = []
    for cls in member_classes(member.id):
        label = '%s %s' % (cls['grade'], cls['section'])
        if cls['subjects']:
            label += ' (' + ', '.join(cls['subjects']) + ')'
        if room_label(cls['room']):
            label += ' - %s' % room_label(cls['room'])
        for days, start, end in cls['slots']:
            if day in days and start:
                out.append((start, end, label))
    out.sort()
    return out


def push_message(sub, title, body, url):
    """Send one push to a device; a dead endpoint is dropped from the table."""
    keys = ensure_vapid()
    try:
        _webpush(
            {'endpoint': sub.endpoint,
             'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
            data=json.dumps({'title': title, 'body': body, 'url': url}),
            vapid_private_key=keys['private_pem'],
            vapid_claims={'sub': 'mailto:' + ADMIN_EMAIL,
                          'exp': int(time.time()) + 86400},
            ttl=3600, timeout=15)
        return True
    except _WebPushException as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', 0)
        if status in (404, 410):
            # The browser threw this endpoint away: stop carrying it.
            db.session.delete(sub)
            db.session.commit()
        else:
            app.logger.warning('Push failed for one device: %s', exc)
        return False
    except Exception:
        app.logger.exception('Push could not be sent')
        return False


def push_already_sent(key):
    """True when this reminder went out today already; claims the key if not."""
    if PushSent.query.filter_by(key=key).first():
        return True
    try:
        db.session.add(PushSent(key=key))
        db.session.commit()
    except Exception:
        db.session.rollback()
        return True  # another worker just claimed the same reminder
    return False


def push_tick(now=None):
    """One pass of the reminder clock: class-soon alerts and the morning digest."""
    now = now or datetime.now()
    today = now.strftime('%Y-%m-%d')
    if non_class_note(today):
        # The main admin wrote "no classes" for this date, so no class
        # notification goes out to anybody today.
        return
    minutes = now.hour * 60 + now.minute
    for sub in PushSubscription.query.all():
        meetings = []
        url = '/home'
        if sub.staff_email:
            meetings = staff_meetings(sub.staff_email)
            url = '/staff/home'
        learner = db.session.get(User, sub.user_id) if sub.user_id else None
        if learner:
            meetings = meetings + learner_meetings(learner)
        for start, end, label in meetings:
            start_min = slot_minutes(start)
            if start_min is None:
                continue
            lead = start_min - minutes
            if 0 < lead <= REMINDER_LEAD_MINUTES and not push_already_sent(
                    'remind|%d|%s|%s|%s' % (sub.id, today, start, label)):
                push_message(sub, 'Class starts soon',
                             '%s begins at %s (in about %d min).' % (label, start, lead),
                             url)
        if now.hour == DIGEST_HOUR and meetings and not push_already_sent(
                'digest|%d|%s' % (sub.id, today)):
            summary = '; '.join('%s - %s' % (start, label)
                                for start, end, label in meetings)
            push_message(sub, "Today's classes",
                         'You have %d class%s today: %s' % (
                             len(meetings), 'es' if len(meetings) != 1 else ' ',
                             summary),
                         url)


def _push_loop():
    while True:
        try:
            with app.app_context():
                push_tick()
        except Exception:
            app.logger.exception('Reminder loop hit a problem')
        time.sleep(30)


_PUSH_THREAD = None


def start_push_loop():
    """Bring the reminder clock up once per process."""
    global _PUSH_THREAD
    if _PUSH_THREAD is not None or _webpush is None:
        return
    _PUSH_THREAD = threading.Thread(target=_push_loop, daemon=True,
                                    name='push-reminders')
    _PUSH_THREAD.start()


def reminder_choice_key():
    """Whose answer this is: the staff login first, else the learner account."""
    staff = my_staff_email()
    if staff:
        return 'staff:%s' % str(staff).strip().lower()
    user_id = session.get('user_id')
    return 'user:%s' % user_id if user_id else ''


def reminder_choice_file():
    """The saved file, keeping its shape even when it is missing or damaged."""
    try:
        with open(REMINDER_CHOICE_PATH) as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            accounts = saved.get('accounts')
            default = str(saved.get('default') or '').strip().lower()
            return {
                'default': (default if default in REMINDER_CHOICES
                            else REMINDER_CHOICE_DEFAULT),
                'accounts': accounts if isinstance(accounts, dict) else {},
            }
    except (OSError, ValueError):
        pass
    return {'default': REMINDER_CHOICE_DEFAULT, 'accounts': {}}


def reminder_choice():
    """This account's answer, or the file's default while it has none."""
    saved = reminder_choice_file()
    key = reminder_choice_key()
    entry = saved['accounts'].get(key) if key else None
    choice = str((entry or {}).get('choice') or '').strip().lower()
    if choice in REMINDER_CHOICES:
        return choice
    fallback = str(saved.get('default') or '').strip().lower()
    return fallback if fallback in REMINDER_CHOICES else REMINDER_CHOICE_DEFAULT


def reminder_choice_save(choice, only_while_asking=False):
    """Write one account's answer, leaving every other account alone.

    only_while_asking is how the bar records that it was shown: if an answer
    was written a moment earlier, that answer wins instead of being replaced
    by "shown".
    """
    key = reminder_choice_key()
    if not key:
        return False
    with _REMINDER_CHOICE_LOCK:
        saved = reminder_choice_file()
        current = str(((saved['accounts'].get(key) or {}).get('choice'))
                      or '').strip().lower()
        if (only_while_asking and current in REMINDER_CHOICES
                and current != REMINDER_CHOICE_DEFAULT):
            return True
        saved['accounts'][key] = {
            'choice': choice,
            'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        tmp = REMINDER_CHOICE_PATH + '.tmp'
        try:
            with open(tmp, 'w') as handle:
                json.dump(saved, handle, indent=2, sort_keys=True)
            os.replace(tmp, REMINDER_CHOICE_PATH)
        except OSError:
            return False
    return True


@app.route('/push/choice', methods=['GET', 'POST'])
def push_choice():
    """The saved answer to the one-time reminder bar.

    GET is what the page reads before drawing the bar; POST records an
    answer. The file keeps it until that account changes it, on the Profile
    page or by answering the bar.
    """
    if not reminder_choice_key():
        return jsonify({'error': 'not_logged_in'}), 401
    if request.method == 'GET':
        return jsonify({'choice': reminder_choice()})
    body = request.get_json(silent=True) or {}
    choice = str(body.get('choice') or '').strip().lower()
    if choice not in REMINDER_CHOICES:
        return jsonify({'error': 'bad_choice'}), 400
    if not reminder_choice_save(choice, only_while_asking=(choice == 'shown')):
        return jsonify({'error': 'could_not_save'}), 500
    return jsonify({'ok': True, 'choice': reminder_choice()})


@app.route('/push/vapid')
def push_public_key():
    if _webpush is None:
        return jsonify({'error': 'push_not_installed'}), 501
    return jsonify({'publicKey': ensure_vapid()['public_key']})


@app.route('/push/subscribe', methods=['POST'])
def push_subscribe():
    """A device tells us its push address; it is remembered as the signed-in person."""
    user_id = session.get('user_id')
    staff = my_staff_email()
    if not user_id and not staff:
        return jsonify({'error': 'not_logged_in'}), 401
    body = request.get_json(silent=True) or {}
    endpoint = str(body.get('endpoint') or '').strip()
    keys = body.get('keys') or {}
    if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
        return jsonify({'error': 'bad_subscription'}), 400
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub is None:
        sub = PushSubscription(endpoint=endpoint)
        db.session.add(sub)
    sub.p256dh = str(keys['p256dh'])
    sub.auth = str(keys['auth'])
    if user_id:
        sub.user_id = user_id
    if staff:
        sub.staff_email = str(staff).strip().lower()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'could_not_save'}), 500
    return jsonify({'ok': True})


@app.route('/push/unsubscribe', methods=['POST'])
def push_unsubscribe():
    body = request.get_json(silent=True) or {}
    endpoint = str(body.get('endpoint') or '').strip()
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({'ok': True})


# The debug reloader runs this file in two processes; only the child (and a
# hosted server importing the app) should carry the reminder clock.
if os.environ.get('MNHS_LOCAL') != '1' and (
        __name__ != '__main__' or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
    start_push_loop()

if __name__ == '__main__':
    app.run(debug=True)
