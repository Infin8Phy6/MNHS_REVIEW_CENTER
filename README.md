# Review Hub Ph (Flask)

A completely free Flask web app that lets users prepare for exams through an
interactive quiz system. Works offline. It also serves the ELEMENTALS
periodic-table game at `/game`, on the same app and the same database.

## What the app does

### Quizzes (no account needed)
- Pick a Grade (7–10), a Subject (English, Filipino, Mathematics, MAPEH,
  SocSci, Science, TLE), a Quarter (1–4, or All Quarters), and optionally a
  Topic — following the MATATAG Budget of Work structure.
- 10 randomly-shuffled questions per quiz from `questions.json`.
- At the end of every quiz the user is asked: **"Save your result?"**

### Accounts (only needed to save scores)
After finishing a quiz, the user can choose to save the result. If they have
no account, they are taken through a simple free sign-up:

- First Name (required)
- Middle Name (optional)
- Last Name (required)
- Suffix (dropdown: N/A, Sr, Jr, I, II, III, IV, V)
- School (required)
- Grade (required, dropdown: Grade 7–10)
- Section (required) — **Grade 8 picks from ORION / MILKYWAY and Grade 10 from
  CREST / PRIME / SOVEREIGN / VANGUARD**; Grade 7 and Grade 9 still type theirs,
  because the school has not fixed those lists.
- Email (required, unique)
- Password (required, min 8 characters)

Login uses email + password with an optional **Remember me on this device**
checkbox (31-day session).

**Capitalization never splits a student in two.** The address is compared
case-insensitively, so `Juan@Example.com` and `juan@example.com` are the same
account. A section is stored and matched in one tidy shape (`crest`, ` Crest `
and `CREST` are all `CREST`), and names are shown word by word
(`EDGARDO`, `edgardo` and `Edgardo` all display as `Edgardo`). The results
dashboard therefore groups and sorts one section as one group and one student
as one student, whatever was typed at sign-up.

### Forgot password (an emailed code)
**Reset Password** is on the home page and under the login box
(`/reset_password`). The student types their email, and the app says so if that
address is not registered. They then type the new password twice, and a 6-digit
code is emailed to that address (`smtp.gmail.com:587`, see **Setup**). The code
page takes the code, and the new password is written to the account.

- The code and the new password are both stored hashed in `password_reset`, so a
  database dump shows neither; the random token in the address is only a pointer
  to that one request.
- A code works for **10 minutes**, can be used **once**, and allows **5 wrong
  tries** before the request is cancelled. Asking again inside a minute is held
  back, and a new request throws away any older code for that address.
- If the mail cannot be sent, the student is told why on the form and the
  request is deleted, so nobody is left waiting for a code that will never come.

### Student profile (`/profile`)
**Profile** in the navbar (signed-in students only) shows the account exactly as
the app holds it — name, email, school, grade, section, the day it was made —
plus how many quizzes are saved, the average score, the subjects covered and the
latest quiz. Under that, the materials filed for **that student's section** are
listed on the same page, with the same Open buttons as the section page, so a
student never has to hunt for their own group. A student with no section yet is
told there is nothing to show rather than seeing an empty box.

### Class reminders and the one-time bar
A signed-in student or staff member sees a small **Class reminders** card once,
at the bottom of the page, offering class-start notifications for that device.
It does not come back: the answer is written to `reminder_choice.json` beside
the app, under the account's own key (`user:<id>` for a student,
`staff:<email>` for a teacher), and stays exactly as saved until that person
changes it. **Profile** has a **Class reminders** switch that turns the saved
setting off or on again for that device.

Answering "Not now", or simply leaving the card, records that it has been shown,
so a reload or a new page cannot ask a second time. The file never holds a push
address or a password — the subscriptions stay in `push_subscription`. Deleting
the file asks everybody once more; its top-level `default` can be set to
`ask` (show once), `shown`/`dismissed` (stay quiet) or `enabled` (treat as
turned on) for accounts that have no entry of their own.

### Saved results
Each saved quiz attempt records:
- Subject
- Topic
- `quiz_set_info` — the quiz set (question IDs, the participant's answers,
  correct answers)
- Score
- Date taken

Saved attempts are listed under **My Results**, where any attempt can be
downloaded as an **A4 report** in either format — a **single multi-page PDF**, or
**one PNG per page** — showing the student's info, score, every question, and
their answers vs. the correct answers. The same two buttons are on the quiz
result screen, whether or not the student has an account.

Pages are rendered one at a time and each is released before the next is drawn,
so a long quiz does not run a phone out of memory; if a device still cannot
build the file, the button says so instead of doing nothing. The PDF is written
in the browser itself (`static/export.js` holds a small PDF 1.4 writer that
places each A4 sheet as one JPEG), so no library and no internet is needed.

### Materials (`/materials`)
**Resources** and **Materials** were the same list twice, so they are one page
now. Every section has its own page, made automatically — there is nothing to
create first, and **an account is needed to open any of them**. A signed-out
visitor who types `/materials` is sent to the log-in page, and the **Materials**
link is not in the navbar until someone signs in. A student does not browse the
index: `/materials` shows their own section (Grade 10 VANGUARD never sees the
CREST pile), and any other section address bounces them to their profile. The
index of every section, with how many items each holds, is only for staff — the
main admin or one assigned on the
[Staff](#staff--admin-and-teacher-logins-adminstaff) page.

The student's own materials are also printed on their profile (`/profile`), so
there is exactly one place a student looks. `/materials/Grade 10/CREST` is one
section's page, and the page both reads and writes it:

| Kind | How it gets there |
| --- | --- |
| PDF, PNG/JPG, PPT/PPTX | upload, and the file is stored in Google Drive |
| Google Doc / Google Sheet / Slides | paste the link (labelled by itself) |
| Any other page | paste the link |

- **A section is the group.** Everything filed for Grade 10 CREST is seen by
  every CREST student, and only by them.
- **Anyone can view a file once it is shared.** An uploaded file goes into the
  Drive folder `MNHSREVIEWCENTER` and is shared with `type=anyone, role=reader`,
  so a student with no Google account still opens it. The link handed out is
  `https://drive.google.com/file/d/<id>/view`. Reaching the page that lists them
  still takes an account.
- **One upload cap:** 20 MB (`MAX_UPLOAD_BYTES`), and only `.pdf`, `.png`,
  `.jpg`, `.jpeg`, `.ppt`, `.pptx`. Bigger or other types: put it on Drive
  yourself and paste the link.
- **Deleting a material deletes its Drive file too** — the row goes first, so a
  Drive hiccup can never leave a dead link on the student's page.
- **Posting needs the `can post materials` capability** (the main admin's own
  row in admin.db lists it). A teacher who can only read still opens their
  classes here; the add and remove controls simply are not on their page.
- Grades and sections in the address are matched loosely: `/materials/grade%2010/crest`
  and `/materials/Grade 10/CREST` are the same page.
- The old addresses `/resources`, `/resources/<grade>/<section>` and
  `/admin/resources` redirect, so a bookmarked or cached link still lands.

### Names stay private
A school tablet is passed around, so no page shows a student a list of names
that are not theirs:

- ELEMENTALS no longer offers the **Pick up a name** chips. They listed whoever
  had played last on that machine, and the next student could take their name.
  A player types their own name, or plays under the account they signed in with.
- `/game/results` for a signed-out player lists only the rounds that player
  started in that browser; a signed-in one lists only their own account's rounds.
- The Jumbled Letters and Who's Who score pages report a room, its topic, its
  player count and its top score — never the champion's name. Names stay inside
  a room, where everybody in it already sees them.
- A single-player Jumbled Letters sheet carries only the player's own name and
  is never written to the offline cache.

### Ungraded attempts
A student who finishes a quiz and does not save it still counts. The **No
Thanks** button, and leaving through **Take Another Quiz** or **Back to Home**
without choosing Save or No Thanks, stores that finished quiz in its own
`ungraded` table through `/api/attempts/ungraded`:

- It never appears in My Results and never changes an average, but the admin
  dashboard folds it into the per-item analysis.
- A student with an account is stored under their own name; a student without
  one is stored as **annonymous**, which is what makes the ones with no account
  still measurable.
- Offline first: the attempt goes to the `rh_ungraded_outbox` in localStorage
  and uploads itself on the next page the student opens online.

### Offline support
- The app shell and visited pages are cached by a service worker (`sw.js`).
  The games run on the same origin, some with their own workers and their own
  caches, so each one only ever clears its own (`reviewhub-*`, `elementals-*`,
  `jumbled-*`, `whoswho-*`) — a quiz-app update can no longer delete a game's
  saved copy.
- Navigations are network-first. When the device is offline, the saved copy of
  **that page** is shown; only `/` and `/home` may fall back to the home page.
  A game or materials link that was never opened offline gets an honest "You are
  offline" notice instead of silently rendering the home page, which looked like
  the app bounced the student back out of the game.
- Question sets (`/api/questions/...`) are cached with a
  stale-while-revalidate strategy, so any subject opened once online can be
  quizzed again offline.
- **A school tablet is shared, so one person's own pages are never kept on it.**
  `/admin/...`, `/profile`, `/my-results`, `/resources`, `/logout`, any
  `/reset_password/<code-link>`, any `/games/jumbled/result/<code>`, any
  `/games/elemental-table/play/<token>`, the whole
  `/games/quantum-architect/worksheets…` studio (papers, exports and answer
  keys) and any staff `/game/worksheet…`,
  `/games/elemental-table/worksheet…` or `/games/jumbled/worksheet…` are not
  written to the offline cache, and any such copy left by an older version is
  deleted when the worker activates. Open one of those offline and the device
  says so instead of showing whoever was signed in last.
- Quantum Architect's board is shell-cached (`/games/quantum-architect/`, its
  `/play`, `/api/engine`, CSS and JS), so an atom can be built on a tablet with
  no internet once the page has been opened. Its `/api/…` JSON is served
  stale-while-revalidate like the question sets.
- A quiz taken offline is stored on the device (localStorage outbox) and is
  automatically synced to the account database once the user is online again.
- Results saved while logged out are kept on the device and uploaded right
  after the user signs up or logs in.

### Admin results dashboard
The account listed as `main_admin` in `admin.db` (`angelesedgardo17@gmail.com` today) is the main
admin. When a
teacher is signed in, a **Results Dashboard** link appears in the navbar
(`/admin`). One can pick a Grade Level and (optionally) a Section and see:

- Student summary — attempts and average score per student
- **Per-item analysis** — for every question: how many students answered, how
  many got it correct (difficulty index with Easy/Moderate/Difficult/Very
  Difficult labels), and how answers were distributed across the options
- **Most Difficult Questions** — the items with the lowest correct rate

**MNHS REVIEW CENTER** (the home link), **Take a Quiz** and **Educational
Games** leave the navbar on the staff pages — `/admin/assessment` and its
learner pages, `/materials` and every section page, `/admin/classes`,
`/admin/database`, `/admin/staff` and `/profile` — but only while a staff
account is the one signed in. A learner on `/materials` or `/profile` still
sees all three, and `/home` and `/games` are untouched.

**Assessment** and **Results Dashboard** are for every level in `admin.db`.
**Classes** needs `can manage classes` (an admin or the main admin), **Materials**
is read by every level and needs `can post materials` to add or remove, and
**Database** and **Staff** answer to their own rules (the Staff page is open to an
admin for the teachers under them; Database is the main admin's alone). Anyone
else is turned away from all of them: a signed-in student goes to `/home`, a
visitor who is not signed in goes to `/admin/login`.

### Staff — admin and teacher logins (`/admin/staff`)
Staff do not sign in with a student account. **Admin Log In**
(`/admin/login`) is a separate door with its own page:

- Any row in `admin.db`'s `accounts` table signs in there with its own email and
  password — no learner account has to exist first, and no second login is made
  for the same person.
- The Staff page is the friendly way to write that table: it adds, levels,
  re-passwords and removes rows, says which admin each teacher answers to, and
  keeps the matching `staff` row the rest of the app reads in step.
- **The page is a ladder, and each rung only sees its own.** The main admin's
  list is grouped: one block per admin — "Admin — *name* (*email*) · N
  teacher(s) under them" — with exactly that admin's teachers underneath, then a
  final block for the teachers the main admin holds directly; an empty block is
  never printed. An admin opens the same page and sees only the teachers whose
  `supervisor` is their own address, and may add a teacher or reset the password
  of those teachers — not change their role, move them, or remove them. The
  Classes page follows the same rule: the teacher picker for an admin lists only
  their own teachers, so a class can never be handed to somebody under another
  admin.
- A learner who types their own email at `/admin/login` is refused: the address
  has to be in `admin.db` or have a staff row of its own.
- **Staff worksheets in the games** (`/game/worksheet`,
  `/games/elemental-table/worksheet`, `/games/jumbled/worksheet`) are open to
  every staff level — a teacher prepares their own class's copy; see
  [Educational Games](#educational-games-games).
- **PDF Studio** (`/staff/pdf-studio`) is open to every staff level too: the 17
  PDF and picture jobs from the desktop `pdf_studio.py` now run on the server, so
  a teacher can use them from a phone or the PythonAnywhere copy without
  installing anything; see [PDF Studio](#pdf-studio-staffpdf-studio).

### `admin.db` — the levels and what each may do
`admin.db` sits next to `app.py` and is a plain SQLite file with two tables:

```
accounts(email, password, level, supervisor)  -- who may sign in, as what, and to
                                                whom a teacher answers
roles(level, capability)                      -- what each level may do
```

It is built and seeded the first time the app runs without it — or after it is
deleted — so login can never be lost, and the main admin row is always written
with the school's own address (`angelesedgardo17@gmail.com`) and the password in
`admin.json`. Levels run `teacher` → `admin` → `main_admin`; a browser can open
`admin.db` directly to edit either table, and the change reaches the next request
without a restart.

- `accounts.level` decides the powers, read from the `roles` table for that level.
  A row the Staff page made is a `teacher` until its level is changed there, and a
  level change lands even for someone already signed in.
- `accounts.supervisor` is the email of the admin a teacher answers to; empty
  means the main admin holds them. Only the main admin sets it, and it follows a
  teacher, not an admin: promoting a teacher to `admin` puts them back under the
  main admin. An admin may hand out a login for a teacher of their own — the
  level is forced to `teacher` and the supervisor is themselves — and may set a
  new password for those teachers. Changing a role, moving a teacher to another
  admin and removing a login stay the main admin's.
- `roles.capability` is matched after folding, so `can manage classes`,
  `manage classes` and `manage_classes` are the same row. Unknown wording is kept
  but unlocks nothing, and a level with no row at all falls back to the school
  default in `DEFAULT_ROLE_CAPS` (`app.py`).
- The words that matter: `manage database` (Database page), `manage teachers`
  (Staff page), `can add other admin`, `manage students` (a learner's
  **Details**, drop, delete), `can manage classes` and `manage teacher assignment`
  (Classes page), `can view assessment results` (Assessment and Results
  Dashboard), `record marks` (**Record a score**), `record marks for the teacher`
  and the **Adjust** control, `can create quizzes`, `can create summative tests`
  (the **Create a Summative Test** panel and `/admin/summative/questions`) and
  `can post materials` (Materials).
- `admin.json` still works as the seed and as the fallback for any level
  `admin.db` says nothing about. Both files hold a real password: keep them out
  of any public repository.

What each level may do as shipped:

| Level | May | May not |
| --- | --- | --- |
| `teacher` | Create a quiz or summative test, record a score, read the Materials of their own classes | Open Classes, Staff or Database; correct or remove anyone else's score |
| `admin` | The teacher's own list, plus Classes, teacher assignment, assessment results and **Adjust**; hand out a login for a teacher of their own and reset its password | Reach Database, post Materials, change a learner's details, change a role, or touch a teacher who does not answer to them |
| `main_admin` | Everything, including Staff, Database and a learner's **Details** | — |

Removing a teacher's row takes their access away on the next request; a device
left signed in loses it as soon as the page reloads.

### Staff profile (`/profile`, `/profile/account/<staff id>`)
Staff get a profile of their own, and it is a read-out of admin.db and the
Classes page rather than a second place to set anything:

- **Account** — name, email, level, who they answer to, the day the login was made.
- **What I may do** — the capabilities the `roles` table lists for that level.
- **Classes** — every grade and section handed to them, the subjects they teach
  in each, and that section's saved schedule. These are the only classes their
  Assessment pickers will open.
- **Teachers under me** — for an admin, the teachers placed under them with each
  one's classes; for the main admin, every staff login.

A teacher sees their own. An admin sees their own and the teachers under them.
The main admin sees anybody's, and the Staff and Classes pages link to each
profile by name.

### PDF Studio (`/staff/pdf-studio`)
Every staff level gets the whole desktop studio in the browser: pick a tool on
the left, add the files, fill in the few boxes, press **Run**, and the result
downloads. Files are uploaded to the server for that one run only.

- **The 17 tools.** Merge PDFs · Split into parts · Extract pages · Remove pages ·
  Rearrange pages · Rotate pages · Watermark · Page numbers · Pages to images ·
  Images to PDF · JFIF to PNG · Extract text · Compress · Protect with a
  password · Remove the password · File report · Edit title and author.
- **The same engine as the desktop app.** The jobs and their form descriptions
  live in `pdf_tools.py`, which has no window; `pdf_studio.py` (the Tkinter
  window) and this page both read that one `TOOLS` list, so a fix or a new tool
  reaches both. The desktop file is not imported by `app.py` — a server has no
  display — only `pdf_tools.py` is.
- **What comes back.** One result downloads as itself; a tool that writes
  several files (split, pages to images, JFIF to PNG, one `.txt` per PDF, …)
  comes back as a ZIP with a `what happened.txt` beside the results. **File
  report** writes nothing, so its findings are shown on the page instead.
- **The order is the order.** The file list can be moved up and down, and Merge
  and Images to PDF use that order. Files can be dropped onto the page or picked
  with **Choose files**; the picker and the drop both refuse the wrong kind of
  file for the chosen tool.
- **Where it works and for how long.** Each run gets its own folder under
  `pdf_jobs/`; the download link is behind the same staff login, and a sweep
  deletes folders older than two hours. One run takes up to 40 files and 200 MB.
  The 20 MB materials limit is unchanged.
- **What it needs on the host.** `pypdf` (page surgery), `PyMuPDF` (rendering,
  watermarking, AES-256), `Pillow` (pictures and page numbers) and
  `cryptography` (reading AES-locked inputs) — all four are in `requirements.txt`.
  If one is missing, only the tools that use it stop, and the page says which.
- **Passwords are never stored.** A password typed for a locked PDF or for
  **Protect** is used for that run only; it is not logged, and the uploaded file
  and the result are deleted by the sweep.

### Classes: who teaches what (`/admin/classes`)
The school's class list, and the only place a grade or a section is born. A
teacher can open the records of what is written here under their name and
nothing else, so this page is both the roster and the access rule.

- **Grade level and section** are the main admin's: create, rename, fold a
  duplicate, remove. An admin reaches the page but not these controls.
- **Assign a teacher** hands one class to one of the signer's own teachers —
  the main admin's whole staff list, or an admin's supervised teachers only.
  Assigning the same class again edits it instead of failing.
- **Subjects** are ticked per teacher per class from that grade's own curriculum
  list, so one row still means one teacher in one class. Those subjects then
  narrow that teacher's Subject picker on the Assessment page and the summative
  question bank. A class with none ticked leaves the whole grade open, which is
  how a school that has not filled the subjects in yet keeps working.
- **Schedule & time** is the section's: the weekdays it meets and a start and end
  time. It shows on the class list and on everyone's profile.
- **No-class days (school-wide)** are the main admin's, in a panel under the
  assign form. One dated note — `YYYY-MM-DD` and free text like *"no classes, it
  is a non-working holiday"* — lands in the `non_class_day` table (one row per
  date). **While a note stands for today, every class reminder and the morning
  digest are halted for the whole school** (`push_tick()` returns before it sends
  anything), the in-tab class alarm is silenced, and the staff home page, both
  profiles and the learner's profile print *"No classes today — 〈note〉"* where
  that day's classes would have been. A day already lifted simply resumes. Each
  stored day is listed with its note and who wrote it, and **Lift** (main admin
  only) deletes it; declaring is `action=no_class`, lifting `action=no_class_delete`.

### Admin assessment (`/admin/assessment`)
The record book for one section at a time. Four pickers — Grade Level, Section,
Subject, Quiz set (topic) — and **Pull the data** loads it. The topic list is the
MATATAG tree for that grade plus any set its students have actually answered, so a
newer topic is still pickable, and choosing **All Topics in the subject** shows the
whole subject at once.

- The roster is every account in that section, each with their scores on that set:
  best, overall percent, and the section average pooled from every row. A learner
  with no score is still listed, marked *no score yet*, so it is obvious who is
  missing.
- **Record a score** files a mark the student did not earn on the app — a paper
  test, a recitation. Score, out of and the date taken; the date is a day, not a
  minute. It lands in `quiz_attempt` with `source = 'manual'`, a
  `manual-<random>` id so it can never collide with a synced quiz, and
  `recorded_by` set to the teacher who typed it.
- A recorded score is labelled **recorded** here and **recorded by your teacher**
  in the student's own **My Results**, where its download buttons are hidden (there
  is no answer sheet to print). The teacher who typed it can **Remove** it; nobody
  else can.
- **Adjust** (an admin or the main admin) corrects a saved quiz in place — score, out of and
  the day. It is offered for a quiz answered on the app as well as a recorded
  mark, and it leaves `quiz_set_info` exactly as the student answered it, so the
  item analysis on the Results Dashboard still reports the real attempt. The
  **Remove** button here also takes away an app quiz for good; that is the one
  thing on this page that cannot be undone from the page itself.
- **Details** (main admin only) opens one learner: first/middle/last name, suffix, school, grade,
  section, email and an optional new password. Names are stored tidied
  (`ANA delos REYES` → `Ana Delos Reyes`), a section is stored upper case, and an
  email another account already uses is refused.
- **Drop from `<section>`** clears only the section. The account and every quiz it
  saved stay; the student simply sees the "no section yet" note on Resources until
  they are placed again.
- **Delete from the database** needs the student's own email typed in, and never
  the admin account in use. It removes the account and its saved quizzes, and keeps
  what is not theirs to lose: a declined practice quiz stays as item data with no
  account attached, and a material they filed stays with no owner.
- Like every other admin page, this writes straight into the live database with no
  undo. Copy `quiz_app.db` before deleting anyone.

### Create a Summative Test (bottom of `/admin/assessment`)
The panel under the record book builds a paper test out of the question bank. It is
shown to any level whose `admin.db` roles mention *summative*, and it never writes
to the database — its only output is the PDF the browser downloads.

- The pickers are the quiz setup, one step at a time: **Grade Level → Subject →
  Quarter** (a quarter, or *All Quarters*). Each box carries its question count, so
  a topic with nothing in it is greyed out and cannot be checked.
- Unlike a quiz, **topics are check boxes**: tick as many as the test should cover,
  or use *Check every topic*. **Pull the questions** asks
  `/admin/summative/questions` for that grade, subject, quarter and every checked
  topic at once, and lists what it returns.
- Every question arrives with its own check box and is checked from the start, so
  unticking is how a distractor gets dropped. **Check all** / **Clear checks** work
  on the whole list, and the counter beside them is how many items are in the draft.
- **Export to PDF** prints only the checked questions — numbered, with their choices
  lettered A., B., C., D. — onto A4 pages under a test header (title, grade and
  subject, the topics covered, a *Name / Section / Date* line, *Score ___ / n* and
  the directions), and downloads it as `SummativeTest_<title>_<subject>.pdf`. The
  correct answers are never sent to the page, so they cannot print by accident.
- The paper is drawn and written by `static/export.js` in the browser, the same
  hand-built A4/PDF code the quiz reports use, so the export needs no internet and
  no extra Python package.

### Admin database editor (`/admin/database`)
Only the main admin opens this page. It reads the database itself and corrects a
row — for a misspelled name, a student in the wrong section, a date that needs
fixing, or to let a student back in who cannot reach their email.

- **Database** lists every table SQLite actually has, with its row count, so the
  tables the games make (`elements`, `jl_rooms`, `ww_players`, …) appear on their
  own.
- Opening a table pages its rows 20 at a time; long values are shortened to read
  and `password_hash` is never shown.
- Opening a row gives one box per column, sized for the type: whole numbers,
  dates (`2026-10-27 15:30:00`), a tall monospace box for a JSON column such as
  `quiz_set_info`. **Save changes** writes that row.
- A box that cannot be understood (a score of `many`, a date of
  `sometime last year`) is reported and the row is left exactly as it was.
  Surrounding spaces are trimmed, and an empty box saves no value.
- On the `user` table the stored password is hidden; the admin types a new
  password in its own box to set the student back up, and leaving it empty keeps
  the password as it is.
- Table and column names are checked against SQLite's own schema before use, and
  every value travels as a bound parameter, so nothing typed into a URL can turn
  into SQL.
- There is no undo, and no delete — the page says so and asks the admin to copy
  `quiz_app.db` first.

## Educational Games (`/games`)
The navbar item is **Educational Games**, and `/games` is the page that lists
them. All six games are mounted inside this same app on the same database, and
each keeps its scores to itself — a game can never appear in **My Results** or in
the admin **Results Dashboard**. `templates/games.html` shows a card for each
game that is actually installed and disables the ones that are not.

The home page deliberately keeps the games out — **Take a Quiz**, **My Saved
Results** / **Create a Free Account**, and the buttons that go to the student's
own section materials are all it shows. `/games` (and the navbar) is the only
entrance to the games.

**Staff worksheets.** Four games — ELEMENTALS, the Elemental Table Game,
Jumbled Letters and Quantum Architect — each carry a **Prepare worksheets**
button on their card for a
signed-in staff account (any level in `admin.db`, including a teacher). It opens
that game's own worksheet page, which deals a fresh puzzle, stores it, and
hands out the blank worksheet for the class and
the answer key for the teacher. Every worksheet route is closed to students with
the game's own "staff only" page; the gate is the `is_admin` hook `app.py` injects
when it mounts each blueprint (`game.is_admin = lambda: bool(admin_kind())`), so
standalone runs of a game keep the pages open for the person sitting at the machine.
Quantum Architect is the exception on format: its studio generates a paper from the
element pools and question types, keeps it in `Quantum Architect/data/worksheets.json`
instead of a table, and exports editable **DOCX** as well as print **PDF**, A4
landscape, for both the student paper and the key.

### ELEMENTALS (`/game`)
`ELEMENTALS/` is the periodic-table symbol sprint: ten elements, three clues
each, answered from six choices or typed out on the Hard level, with a printable
A4 PNG result sheet.

- **One server.** `ELEMENTALS/app.py` is a Flask blueprint. `app.py` here
  imports it with `importlib` (a plain `import app` would re-import the review
  app itself) and calls `game.mount(app, url_prefix='/game', db_path=DB_PATH)`.
  Nothing else needs to run — visit `http://127.0.0.1:5000/game/`.
- **Links.** "Educational Games" in the navbar → `/games` → "Play ELEMENTALS".
  The game's own header has a "Review Hub" link back to `/games`.
- **Same database.** Tables `elements`, `clues`, `games`, `answers` are created
  inside `quiz_app.db` next to `user` and `quiz_attempt` (SQLite busy timeout so
  both writers share the file).
- **No retyping the name.** A logged-in student is identified by the account,
  not a form field: the play page shows "Playing as <name> · Grade 8 · Rizal"
  and only asks for the level, and `/game/start` takes the name, grade, section
  and account email from the session and ignores anything posted. Nobody has to
  type their name. A logged-out visitor (a shared lab device, or standalone
  mode) still gets the name field, because the sheet needs something to print.
- **Scores stay separate.** A sprint writes only to `games`/`answers`. It never
  touches `QuizAttempt`, so it cannot appear in **My Results** or in the admin
  **Results Dashboard**. The game says so on its start and Scores pages.
- **Private scores.** `games.account` holds the signed-in email, so `/game`
  Scores lists only your own rounds when you are logged in. Rounds played
  without an account have an empty `account` and only show in the anonymous and
  standalone listings.
- **Offline.** The game registers its own service worker at `/game/sw.js`, so
  the two caches (review app + game) stay independent.
- **Standalone still works.** `cd ELEMENTALS && python app.py 8000` mounts the
  same blueprint at `/` and keeps using its own `ELEMENTALS/elements.db`.
- **Staff worksheet.** `/game/worksheet` (staff only, closed with
  `ws_closed.html`) deals a fresh ten-element sprint, stores the picks in
  `ws_sheets`, and offers two PDFs of that one sprint: **worksheet** (three
  clues per item and a `Symbol: ____` line to fill) and **answer key** (the
  same sheet with every symbol printed). Drawn by `ELEMENTALS/sheet_pdf.py`
  with reportlab, portrait A4, the same Name/Grade/Section/Score header as the
  in-browser PNG.
- If `ELEMENTALS/` is missing on the server, the review app logs a warning and
  `/game` simply stays disabled.
- **Deploying:** upload the whole `ELEMENTALS/` folder together with the updated
  `app.py`, `sw.js`, `templates/` and `static/style.css`.

### Elemental Table Game (`/games/elemental-table`)
`ETABLE/` deals a table of the periodic table with cells emptied: five elements
at a time across **Element, Symbol, Mass Number, Proton Number, Neutron Number,
Electron Count, Valence Electron, Period, Group**, with five cells in every row
left blank — 5 × 5 = the **25 points** on the sheet, one point per cell.

- **The clues are the laws.** A blank is only dealt when the four cells still
  standing in its own row pin that row to exactly one element: protons =
  electrons in a neutral atom, mass number = protons + neutrons, the group gives
  the valence count (1, 2, then 3–8; helium 2), and one element per Period and
  Group. `possible()` is the same candidate elimination a student does on paper,
  so `solvable()` is checked before a pattern is ever served — there is no cell
  on the table that the clues cannot answer.
- **Only the main groups are dealt** (groups 1, 2 and 13–18 of periods 1–4, so
  26 elements) because that is where those laws hold without exceptions. The
  scope is printed on the How-to-play page, and the same rule is what makes a
  group-and-period clue unique.
- **One element per table** comes from the `elements` table ELEMENTALS already
  seeds into `quiz_app.db`, so both games read one periodic table. Standalone,
  the game falls back to `ELEMENTALS/elements.db`.
- **Typed answers, checked by the server.** The page renders the clues and one
  text box per empty cell (`/play/<token>`); **Check and score** posts the cells
  to `/api/check/<token>`, which grades them from the dealt grid, not from
  anything the browser claims. Names accept either spelling (Sulfur/Sulphur,
  Aluminium/Aluminum), symbols and numbers ignore case and stray spaces, and
  a wrong cell is marked with the value it should have held. Re-opening the
  table puts the saved answers, marks and score back on the page.
- **Landscape download.** The **Download the table** button paints one A4
  landscape sheet (1123 × 794 px at 96 dpi, drawn at 2× and saved as a PNG) with
  the student's name, the date, every column, the clue cells, the typed answers
  with their ✓/✗, and the score — `ETABLE/static/etg_export.js`, separate from
  the portrait quiz sheet in `static/export.js`.
- **Scores stay separate.** A round is written to `etg_games` (token, student,
  grade, section, account, the dealt grid, the marks and the score) inside
  `quiz_app.db`, never to `QuizAttempt`, so it cannot show up in **My Results**
  or the admin **Results Dashboard**.
- **No retyping the name.** `app.py` hands the blueprint `game_student_identity`,
  so a signed-in student's name, grade, section and account are taken from the
  session and only a logged-out visitor types a name.
- **Offline.** `/games/elemental-table/` and its three files are in the app
  shell in `sw.js`, and `/games/elemental-table/play/…` is listed as private so
  one student's answered table is never kept on a shared tablet.
- **Standalone still works.** `cd ETABLE && python app.py 8040` mounts the same
  blueprint at `/` on its own `ETABLE/etable.db`.
- **Staff worksheet.** `/games/elemental-table/worksheet` (staff only, closed
  with `etg_closed.html`) deals a fresh 5 × 5 table, stores the grid in
  `etg_sheets`, and hands out two PDFs of that one table drawn by
  `ETABLE/etg_pdf.py` (landscape A4, reportlab): the **worksheet** shows the
  clue cells with each blank as an empty square and the Name/Grade/Section/
  Date/Score header, and the **answer key** prints every value in the blanks.
- If `ETABLE/` is missing on the server, the review app logs a warning and
  `/games/elemental-table` stays disabled; its card says so.

### Jumbled Letters (`/games/jumbled`)
`JUMBLED/` is the multiplayer topic-word sprint. One person opens a room and
shares the link; everyone in it sees the same jumble at the same moment.

- **Same choices as a quiz paper.** The setup page walks the very
  Grade → Subject → Quarter → Topic tree the quiz form uses, because `app.py`
  hands the blueprint its `QUIZ_SPEC` (`game.spec = QUIZ_SPEC`). Words come from
  `JUMBLED/word_bank.json`, which holds its own list for all 478 topic names that
  tree can show — every topic in `matatag_spec.json` plus the two Grade 10
  Science topics that only exist in `questions.json`. Regenerate it with
  `cd JUMBLED && python build_bank.py` after editing the keyword rules.
- **Random selection, same rule as the quiz.** `words.pick()` samples five words
  at random from that topic's words; a topic with too few of its own falls back
  to the subject's general pool.
- **Scoring.** The topic word is 5 points. Any other real word built from the
  same letters is 1 point, up to three bonus words per jumble, and letters the
  jumble does not hold are rejected. "Real word" is decided by
  `JUMBLED/wordlist.txt` (349,766 words, loaded lazily once) unioned with the
  bank so Tagalog answers count too — no internet needed.
- **The clock lives on the server.** A word is shown for 90 seconds
  (`WORD_SECONDS`). Nothing runs in the background: every poll calls `advance()`,
  which moves the room to the next word once the deadline has passed. That is
  what keeps it safe on a shared host such as PythonAnywhere, where a WSGI
  process cannot keep timers running.
- **Up to 45 players** (`MAX_PLAYERS`). A signed-in student joins under the
  account name and the same account never occupies two seats; a visitor without
  an account types their own name, which is remembered in a `jl_nick` cookie for
  the next round. The device remembers its seat in a `jl_p_<code>` cookie, so a
  refresh returns to the same player.
- **Three winners.** Champion, First Place and Second Place, ranked by points,
  then by the clincher, then by who got there first. If those three places are
  not settled, one extra **clincher** word appears and only the tied players may
  answer it.
- **Scores stay inside the game.** `jl_rooms`, `jl_players` and `jl_answers`
  are the only tables it writes, so `quiz_attempt` is untouched.
- **Standalone still works.** `cd JUMBLED && python app.py 8030` mounts the same
  blueprint at `/` with its own `jumbled.db`, reads `../matatag_spec.json` for
  the topic tree and asks for a nickname because nobody is signed in.
- **Staff worksheet.** `/games/jumbled/worksheet` (staff only, closed with
  `jl_closed.html`) walks the same Grade → Subject → Quarter → Topic tree as the
  setup page, picks 5–20 topic words (10 by default) with the game's own
  `words.pick()`, stores them in `jl_sheets`, and hands out two PDFs drawn by
  `JUMBLED/jl_sheet_pdf.py` (portrait A4): the **worksheet** prints each word
  as a row of letter boxes with an `Answer: ____` line under it and the
  "Words taken from: Grade – Subject – Quarter – Topic" path, and the **answer
  key** prints the real word beside every jumble. A topic with too few words
  simply bounces back with a note instead of saving a short sheet.
- **Deploying:** upload the whole `JUMBLED/` folder — including
  `word_bank.json` and the 3.7 MB `wordlist.txt` — next to `app.py`. If the
  folder is missing, `/games` shows the card as not installed and the review app
  keeps running.
- **Two modes on the setup page.** *Single player* is the default: the round
  starts straight away (no lobby, no invite link) and the same 90-second clock
  and 5-point/1-point scoring apply. A solo room belongs to whoever started it,
  so `/games/jumbled/join/<code>` sends anybody else back to the setup page, and
  the finish screen shows a personal total out of `words × 5` instead of a
  podium. *Multiplayer room* is unchanged. The flag is the `solo` column on
  `jl_rooms`; `init_db()` adds it with `ALTER TABLE` to a database created
  before single-player existed.
- **The solo result is a downloadable A4 PNG.** When a single-player round
  finishes, the board offers **Download the result (PNG)**, which opens
  `/games/jumbled/result/<code>?p=<player token>` — the player's own seat token
  is the only way onto that page, and a multiplayer room has no sheet at all.
  The page hands one page of data to `JUMBLED/static/jl_export.js`, which draws
  it on a 794×1123 canvas at 2× (a PNG of 1588×2246, true A4 portrait) with the
  student's name at the top, the score, and every jumble with the words that
  player sent. Signed-in students get their account name; a player with no
  account gets the name they typed on the setup page. Nothing is uploaded: the
  picture is made in the browser, so it works offline.

### Who's Who (`/games/whoswho`)
`WHOSWHO/` is the picture-and-clues guessing game. The admin builds activities
with a fill-up form; each activity is a round of people to identify.

- **The admin form** (`/games/whoswho/new`, admin only — `angelesedgardo17@gmail.com`)
  asks for the **title of the activity**, then one block per person: their
  **picture**, **name** and **three major clues**. "Add new person" clones a
  blank block, so there is no limit on how many people an activity holds.
  `/games/whoswho/edit/<slug>` reopens the same form with the stored rows, and
  `/games/whoswho/delete/<slug>` removes an activity. Only `POST` writes; the
  page is closed to everybody else with `ww_closed.html`.
- **Every person needs a picture**, because the picture is the clue the whole
  round is built on. `save_activity()` refuses a saved person with no picture and
  bounces back to `?error=photo&missing=<row numbers>`, and `ww_write.js` stops
  the submit before the browser posts, reddens the block (`.person.bad`) and
  names the rows that still need one. The file label reads "(required)".
- **The board is picture-first, not picture-huge.** The photo sits **upper left at
  roughly 2 to 4 inches wide** (`clamp(192px, 26vw, 384px)`), the **jumbled letters
  fall straight under it**, and the **clues, the Reveal buttons and the points line
  run down the right**. The frame follows the photo's own ratio — `height: auto`
  with a 384 px ceiling — so a landscape picture is neither cropped nor banded.
  Under 620 px the columns stack and the picture is capped at 260 px, because a
  6-inch phone has no room beside it. Where an older activity has a person with no
  picture, the same slot shows a dashed `#noPhoto` note instead of the game logo,
  and every picture strip renders a `?` tile for them, so a missing file never
  reads as a person.
  Rows post index-matched lists (`name`, `clue1`–`clue3`, `person_id`) plus a
  per-row `photo<i>` and `keep_photo<i>`. Both per-row names are indexed for a
  reason: an unchecked box posts nothing, and "Remove this person" renumbers the
  blocks left behind, so a picture can never be read onto the wrong name.
- **Pictures appear before the round starts too** — as spoiler-free faces on the
  activity list (`.faces`, first six then `+N`), on the join page and in the room
  lobby (`.strip`). No names are shown there; they only appear when the round ends.
- **The free clue is the jumbled name, and it holds still.** `jumble(name, seed)`
  in `WHOSWHO/app.py` shuffles through a seeded `random.Random`, and `state_json`
  seeds it with `<room code>-<item index>`, so the letters are one steady
  arrangement for the whole person even though the board is re-read every 1.5 s.
  The client re-deals those same letters **by itself every 10 seconds**
  (`start_clock()` in `whoswho.js`, restarted whenever a new person is dealt or
  the player presses **Shuffle the letters**), so the clue keeps moving without
  ever becoming a new clue. `whoswho.js` keys its reset to the *turn*
  (`status + slug + index`), not to the letters text, which is what lets a
  half-typed name survive the polling — before, every poll re-shuffled and wiped
  the answer field. The player finishes the name and presses **Submit answer**;
  the guess is checked without caring about spacing, punctuation or a middle
  initial (`same_name()`), and three wrong tries hand the player clue 3 so a stuck
  seat cannot hold the room up. A correct name answers with **"Bravo! <name> — <n>
  points."**, held on screen ~3.5 s so a solo round moving straight on cannot
  erase it before it is read.
- **The point ladder.** Answering straight from the picture and the jumble is
  **5 points**. Each "Reveal Clue" costs one: clue 1 → worth 4, clue 2 → worth
  3, clue 3 → worth 2 (`item_points(reveals) = max(5 − reveals, 2)`). Once the
  third clue is out, a **10-second countdown** starts; when it runs out without a
  correct answer the seat gets **1 point** and the round moves to the next
  person. Reveals, lock and deadline are stored per player in `ww_players`, so
  two players in one room each pay for their own clues.
- **Totals.** At the end of the round the points are added up: solo says
  "You scored <em>n</em> points over <em>total</em> people", a room shows the
  podium and every seat's score, and both show the whole list of people with
  their names, clues and pictures so a class can see who they were.
- **Both ways to play**, chosen on the activity page: *Play alone* (one seat,
  the whole activity, no link to share) or *Open a multiplayer room* (up to
  `MAX_PLAYERS` = 45 seats, joined by link and nickname or account name).
- **Server-authoritative clock,** the same lazy trick as Jumbled Letters: no
  background timers, every 1.5 s poll calls `advance()`, which settles any
  expired 10-second count and moves everyone on once each seat is locked. Safe
  on WSGI hosts such as PythonAnywhere.
- **Where the data lives.** The activities are plain JSON in
  **`whoswho.json` in this project's root folder** — `WHOSWHO/ww_data.py` reads
  and writes it atomically (`.tmp` then `os.replace`, guarded by a lock), and the
  pages are ordinary HTML rendered from it. Pictures go to **Google Drive** in a
  folder named `MNHSREVIEWCENTER`, created on the first upload if it is not
  there, and are mirrored to **`whoswho_photos/`** so a round still renders with
  no internet or before Drive is configured. `/games/whoswho/photo/<slug>/<id>`
  serves the local copy, or pulls it back from Drive and caches it.
- **Scores stay inside the game.** Only `ww_rooms`, `ww_players` and
  `ww_answers` are written, so `quiz_attempt`, **My Results** and the admin
  **Results Dashboard** never see a Who's Who round. `/games/whoswho/scores`
  lists finished rooms.
- **Standalone still works.** `cd WHOSWHO && python app.py 8040` mounts the same
  blueprint at `/` with its own `whoswho.db` and `WHOSWHO/whoswho.json`.
- **Deploying:** upload `WHOSWHO/`, `whoswho.json` and `whoswho_photos/`. Never
  upload a credentials file — see the Google Drive setup below.

### Quantum Architect (`/games/quantum-architect`)
`Quantum Architect/` is the electron-configuration board and the worksheet studio
that goes with it. A student drops electrons into the orbital ladder and the three
quantum rules do the teaching: Aufbau bounces the wrong energy, Pauli refuses the
third electron in a box, Hund refuses the early pair. Everything the rules say, and
every answer on every key, comes from `Quantum Architect/quantum/chemistry.py` —
one source of truth for the board, the API and the exports.

- **One server.** `Quantum Architect/app.py` is a Flask blueprint. `app.py` here
  loads it with `importlib` (a plain import would fight the review app's own
  `app.py`) and calls `game.mount(app, url_prefix='/games/quantum-architect')`,
  then hands it the three hooks: `game.identity`, `game.is_admin` and
  `game.teacher_label`. Nothing else runs — visit `http://127.0.0.1:5000/games/quantum-architect/`.
- **No PIN, no second login.** The folder used to gate its answer keys with a
  teacher PIN. That screen is gone: teacher, admin and main admin open the keys
  with the staff session they already have at `/admin/login`, and a learner sees
  the board only — the studio links disappear from the page and every
  `/games/quantum-architect/worksheets…` route answers 403 with a page that says
  the studio is for teachers. Mounted with no hub at all (`python app.py` in the
  folder, port 8050), `is_admin` is `None` and everything stays open for the
  person at the machine.
- **The teacher line is already filled.** `header_defaults()` reads
  `teacher_label` for the paper's teacher box and the signed-in student's grade
  and section for the class and section boxes, so a paper printed from the hub
  needs no retyping.
- **Templates are `qa_*`.** `render_template()` inside a blueprint still searches
  the host app's `templates/` first, so `index.html` or `play.html` here would
  have rendered the review app's own pages. Every file in
  `Quantum Architect/templates/` carries the `qa_` prefix, like the other games'
  `etg_`, `jl_`, `cw_`, `ww_`.
- **The board knows its own address.** `qa_play.html` injects
  `window.QA_BASE = "/games/quantum-architect/"` and `static/js/game.js` builds
  every `fetch()` and `history.replaceState()` from it, so the prefix does not
  break the element lookups or the URL.
- **No tables.** `mount()` takes `db_path` only so every game is mounted with the
  same call. The board is scored in the browser and a paper is a file a teacher
  downloads, so `quiz_app.db` gains nothing and `quiz_attempt` is untouched —
  no Quantum Architect round can appear in **My Results** or the admin
  **Results Dashboard**. Saved papers live in
  `Quantum Architect/data/worksheets.json`.
- **Staff papers, both formats.** `/games/quantum-architect/worksheets/new`
  generates from a tier (**Grades 7-8**, **Standard**, **Advanced**, **Custom**),
  an element pool (preset, Z range, typed list) and up to ten question types
  (configuration, shorthand, orbital diagram, ion, quantum numbers, find-the-error…),
  deterministically per seed. **Download DOCX** and **Download PDF** give the
  class paper; **Answer key**, **Key DOCX** and **Key PDF** give the marking copy.
  All A4 landscape, everything in tables, so a teacher can edit the paper in Word
  instead of re-typing it.
  `python-docx` and `reportlab` are already in `requirements.txt`.
- **Offline.** `/games/quantum-architect/`, `/play`, `/api/engine`, its CSS and
  JS are in the `sw.js` app shell, its `/api/…` JSON is cached
  stale-while-revalidate, and the whole `/worksheets…` studio is listed as
  private so a teacher's papers and keys are never kept on a shared tablet.
- **Checks.** From this folder:
  `venv\Scripts\python.exe "Quantum Architect/checks/check_chemistry.py"`,
  `…check_app.py` (the folder on its own) and `…check_hub_mount.py`, which
  imports **this** `app.py` and proves the mount, the prefix, the staff gate and
  the hub's own pages still answer.
- If `Quantum Architect/` is missing on the server, the review app logs a warning,
  `QUANTUM_READY` stays false, and the card says the game is not installed.
- **Deploying:** upload the whole `Quantum Architect/` folder together with the
  updated `app.py`, `templates/games.html` and `sw.js`.

#### Google Drive (section materials and Who's Who pictures)
Everything below is **one setup for both kinds of upload** — the section
materials in **Materials** (`drive_store.py`) and the Who's Who pictures
(`WHOSWHO/ww_drive.py`) read the same file. Uploads work without Drive: a
picture is kept in `whoswho_photos/`, a material keeps its local copy, and the
pages play normally. To store originals in Drive instead of only on this
machine:

1. Install the Drive libraries **into the same Python the app runs under**. On
   this machine that is the virtual environment, so plain `pip install` into
   system Python is not enough — `drive_store.configured()` will still say false
   while the app is started with `venv\Scripts\python.exe`:

   ```
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   It lists `google-api-python-client`, `google-auth`, `google-auth-httplib2`
   and `google-auth-oauthlib`.
2. Put the **OAuth client secret** you downloaded from Google Cloud → APIs &
   Services → Credentials → *OAuth client ID (Desktop app)* at
   **`~/.mnhs/client_secret.json`** — never in this folder. On this machine
   **that file is already written**, so there is nothing to download or paste.
3. `python gdrive_authorize.py` opens Google once. Sign in with the account that
   owns the Drive; it writes the authorized-user token to
   **`~/.mnhs/google_credentials.json`** (mode 0600) with the `drive.file` scope,
   so the app only sees files it uploaded itself, never the rest of the Drive.
   Use the venv's Python for this too: `venv\Scripts\python.exe
   gdrive_authorize.py`.
4. That one file is all of Drive: the section materials (`drive_store.py`) and the
   Who's Who pictures (`WHOSWHO/ww_drive.py`) both read it. To point at a different
   path instead — a hosted deployment, for instance — set `MNHS_DRIVE_CREDENTIALS`
   or `WHOSWHO_DRIVE_CREDENTIALS=/path/to/google_credentials.json`. On
   PythonAnywhere that is `/home/<user>/.mnhs/google_credentials.json`.
5. On the first upload the app finds or creates the Drive folder
   **`MNHSREVIEWCENTER`** and files the upload inside it.

If the file at that path is missing, `drive_store.configured()` and
`ww_drive.configured()` return false, the admin page shows a note that uploads
stay local, and nothing fails.

**A refresh token dies after 7 days while the OAuth consent screen is still in
"Testing"**, so Drive starts returning `invalid_grant: Token has been expired or
revoked` about a week after it was set up. Publish the consent screen (or re-add
the account as a test user) and run `python gdrive_authorize.py` again — the app
cannot refresh a token Google has already killed.

Every Drive failure in `drive_store.py` is passed through `_note()`, which adds
that instruction to Google's terse message, so the admin page shows
"the saved Google sign-in has expired. Run 'python gdrive_authorize.py' once in
this folder to get a fresh one." instead of a bare `invalid_grant`.

`matatag_spec.json` holds the full Grade 7–10 → Subject → Quarter → Topic
tree (483 topics, MATATAG Budget of Work). It mirrors the `subjectData`
structure in the MNHS Question Maker (`MNHS Question Maker/templates/index.html`),
so the two apps always match. The quiz setup dropdown is generated from this
spec; question counts per topic come from `questions.json` (exported from the
Question Maker), so newly generated questions appear automatically.

## Database
SQLite: `quiz_app.db`

- `User` — account info
- `Staff` — one teacher the main admin assigned: name, email, hashed password,
  when it was made and which address made it. Nothing else about a teacher is
  stored here, and a student row in `user` is never a staff row.
- `QuizAttempt` — one row per saved quiz (unique `client_uuid` makes offline
  sync idempotent — no duplicate rows). `source` says where it came from:
  `quiz` for an answer sheet from this app, `manual` for a mark recorded on the
  Assessment page. `recorded_by` holds the email of the teacher who typed a
  recorded mark, which is how only they (or the main admin) can take it back.
  An older database gains these columns by itself on start-up
  (`ALTER TABLE quiz_attempt ADD COLUMN …`), with existing rows kept as `quiz`.
- `ungraded` (`UngradedAttempt`) — one row per finished quiz the student
  declined to save; never read by **My Results**
- `resource` (`Resource`) — one material per row: grade, section, title, kind
  (`pdf`/`png`/`ppt`/`docs`/`sheets`/`link`), url, `drive_id` when the file was
  uploaded, note, who added it and when
- `password_reset` (`PasswordReset`) — one forgot-password request per row: the
  random token in the address, the email, the **hashed** code, the **hashed** new
  password, tries used, expiry, and `used_at` once it has been spent
- `elements`, `clues`, `games`, `answers` — created by ELEMENTALS in the same
  file; see the game section above. `ws_sheets` (token, the ten picked `z`s,
  created) holds the staff symbol-sprint worksheets.
- `etg_games`, `etg_sheets` — created by the Elemental Table Game in the same
  file; `etg_games` is a played table (token, student, dealt grid, marks,
  score) and `etg_sheets` is a dealt worksheet grid waiting for its two PDFs.
- `jl_rooms`, `jl_players`, `jl_answers` — created by Jumbled Letters in the
  same file; see the game section above (`jl_rooms.solo` flags a single-player
  round and is added with `ALTER TABLE` to an older database). `jl_sheets`
  (token, grade, subject, quarter, topic, the picked words, created) holds the
  staff letter-box worksheets.
- `ww_rooms`, `ww_players`, `ww_answers` — created by Who's Who in the same
  file; the activities themselves are the plain JSON in `whoswho.json`
- `non_class_day` (`NonClassDay`) — one school-wide no-class day per row:
  `date` (unique `YYYY-MM-DD`), `note` (≤ 200 chars, e.g. "no classes, it is a
  non-working holiday"), `created_by`, `created_at`. Written only from the
  Classes page by the main admin; read by `non_class_note()` to halt class
  reminders, the morning digest, the in-tab alarm and the schedule banners.

## Routes
- `GET /`, `/home`
- `GET /staff/home` — the staff landing page (Staff Home)
- `GET /staff/pdf-studio` (staff) — PDF Studio: all 17 tools on one page
- `POST /staff/pdf-studio/run` (staff) — upload the files and the boxes, run one
  tool; answers with the closing message, the log and, when the tool writes
  something, a download link
- `GET /staff/pdf-studio/files/<token>/<name>` (staff) — one run's result, with
  the staff login checked again; a single result is itself, several are a ZIP
- `GET /quiz_setup`
- `GET /quiz?level=&subject=&quarter=&topic=`
- `GET /api/questions/<level>/<subject>`
- `GET/POST /signup`, `GET/POST /login`, `GET /logout`
- `GET/POST /admin/login` — the staff door: any email with a row in `admin.db`, or
  a staff row. A learner's email is refused here.
- `GET/POST /admin/staff` — assign a login, choose its level, say which admin
  supervises a teacher, re-password, change the level or remove it. An admin sees
  only the teachers under them and may add or re-password those. This is where
  `admin.db` is written.
- `GET/POST /reset_password` — email + new password, then the code is emailed
- `GET/POST /reset_password/<token>` — the page that takes the emailed code
- `GET /profile` — a student's own details and section materials, or the staff
  profile (level, powers, supervision, classes) for a signed-in teacher or admin
- `GET /profile/account/<staff id>` — one staff member's profile: the main admin
  opens anybody's, an admin only a teacher under them
- `GET /push/choice` — the saved answer to the one-time Class reminders bar
  (`ask`, `shown`, `enabled` or `dismissed`) for the signed-in account
- `POST /push/choice` — record that answer in `reminder_choice.json`
- `GET /push/vapid`, `POST /push/subscribe`, `POST /push/unsubscribe` — the
  device's push address for class-start and morning-digest reminders
- `POST /api/attempts/sync`
- `POST /api/attempts/ungraded` — the "No Thanks" / left-without-deciding quiz
- `GET /my-results`
- `GET /materials` — needs an account: a signed-in student is sent to their own
  section, a teacher sees the index of every section, a visitor is sent to `/login`
- `GET/POST /materials/<grade>/<section>` — that section's materials, and the page
  that posts or removes one; needs an account, and a student only reaches their own
- `GET /resources`, `GET /resources/<grade>/<section>`, `GET/POST /admin/resources`
  — the old names, each redirected to its `/materials` page
- `GET /admin/assessment?grade=&section=&subject=&topic=` — one section's scores
  for one quiz set (any teacher)
- `POST /admin/assessment/score` — record a score for a student (any teacher);
  `POST /admin/assessment/score/<id>/delete` — remove one (its own teacher, or the
  main admin for any row);
  `POST /admin/assessment/score/<id>/edit` — correct score, total or day (an admin
  or the main admin)
- `GET/POST /admin/assessment/student/<id>` — edit, drop or delete one learner
  (main admin only)
- `GET /admin/summative/questions?level=&subject=&quarter=&topics=` — the questions a
  summative draft may pick from; `topics` is repeated once per checked topic, and no
  answer key is included (any level whose `admin.db` roles mention *summative*)
- `GET /admin?grade=&section=` (any teacher)
- `GET /admin/database` — every table with its row count (main admin only)
- `GET /admin/database/<table>?page=` — that table's rows, 20 a page (main admin only)
- `GET/POST /admin/database/<table>/<id>` — read and save one row (main admin only)
- `GET /sw.js`
- `GET /games` — the Educational Games hub
- `GET /game/`, `/game/table`, `/game/results`, `/game/install`, `/game/download`
- `POST /game/start`, `GET /game/play/<token>`
- `GET /game/api/state/<token>`, `POST /game/api/answer/<token>`,
  `POST /game/api/sheet/<token>`, `GET /game/sheets/<name>`
- `GET /game/worksheet` (staff), `POST /game/worksheet/new`,
  `GET /game/worksheet/<token>/worksheet.pdf` and `…/answer-key.pdf`
- `GET /games/elemental-table/` (how to play), `POST /games/elemental-table/deal`
  (deal a table), `GET /games/elemental-table/play/<token>` (the table itself),
  `POST /games/elemental-table/api/check/<token>` (grade the 25 cells)
- `GET /games/elemental-table/worksheet` (staff), `POST …/worksheet/new`,
  `GET …/worksheet/<token>`, `…/worksheet/<token>/worksheet.pdf`,
  `…/worksheet/<token>/answer-key.pdf`
- `GET /games/jumbled/` (setup), `POST /games/jumbled/create` (new room)
- `GET/POST /games/jumbled/join/<code>` (a seat), `GET /games/jumbled/room/<code>`
- `GET /games/jumbled/api/state/<code>` (the 1.5 s poll),
  `POST /games/jumbled/api/start/<code>`, `POST /games/jumbled/api/answer/<code>`
- `GET /games/jumbled/result/<code>` (the solo player's A4 sheet),
  `GET /games/jumbled/scores`, `/games/jumbled/manifest.webmanifest`,
  `/games/jumbled/sw.js`, `/games/jumbled/icon/<size>`
- `GET /games/jumbled/worksheet` (staff), `POST …/worksheet/new`,
  `GET …/worksheet/<token>`, `…/worksheet/<token>/worksheet.pdf`,
  `…/worksheet/<token>/answer-key.pdf`
- `GET /games/whoswho/` (the activity list), `GET /games/whoswho/a/<slug>`
  (one activity), `GET /games/whoswho/photo/<slug>/<person id>`
- `GET/POST /games/whoswho/new`, `GET/POST /games/whoswho/edit/<slug>` and
  `POST /games/whoswho/delete/<slug>` — admin only
- `POST /games/whoswho/play/<slug>` (start a solo round or a room),
  `GET/POST /games/whoswho/join/<code>`, `GET /games/whoswho/room/<code>`
- `GET /games/whoswho/api/state/<code>` (the 1.5 s poll),
  `POST /games/whoswho/api/reveal/<code>` (pay for a clue),
  `POST /games/whoswho/api/answer/<code>`,
  `POST /games/whoswho/api/reserve/<code>` (give this person up for 1 point),
  `POST /games/whoswho/api/next/<code>` (the host moves on),
  `POST /games/whoswho/api/start/<code>`
- `GET /games/whoswho/scores`, `/games/whoswho/manifest.webmanifest`,
  `/games/whoswho/sw.js`, `/games/whoswho/icon/<size>`
- `GET /games/quantum-architect/` (the game's own home), `GET /games/quantum-architect/play`,
  `GET /games/quantum-architect/play/<z>` (the board for one element)
- `GET /games/quantum-architect/api/table`, `/api/engine`, `/api/element/<z>`
  (the engine's fill order, wording and per-element payload)
- `GET /games/quantum-architect/worksheets`, `GET …/worksheets/new`,
  `POST …/worksheets/create`, `GET …/worksheets/<id>`,
  `POST …/worksheets/<id>/regenerate`, `POST …/worksheets/<id>/delete`,
  `GET …/worksheets/<id>/export/<docx|pdf>` — the studio, staff only
- `GET …/worksheets/<id>/answer-key`, `GET …/worksheets/<id>/answer-key/export/<docx|pdf>`
  — staff only

## Setup
1) `pip install -r requirements.txt`
2) `python app.py`

The app runs on `http://127.0.0.1:5000`, and the games ride along with it:
`http://127.0.0.1:5000/games` is the hub, `…/game/` is ELEMENTALS,
`…/games/elemental-table/` is the Elemental Table Game,
`…/games/jumbled/` is Jumbled Letters and `…/games/whoswho/` is Who's Who.
Nothing extra needs to be started. **PDF Studio** is at
`http://127.0.0.1:5000/staff/pdf-studio` for any staff login; it keeps each
run's files in `pdf_jobs/`, which the app creates and sweeps by itself.

**Uploading materials** is the only part that needs a Google key, and it is the
same `drive.file` token described in the Who's Who setup above: `drive_store.py`
reads `MNHS_DRIVE_CREDENTIALS`, falls back to `WHOSWHO_DRIVE_CREDENTIALS`, then
to `~/.mnhs/google_credentials.json`. The key is only ever read, never written
into this folder. With no key present, `drive_store.configured()` is false, the
Materials page says so in one line, pasted links keep working, and nothing else
in the app changes.

**Emailing a reset code** needs one Gmail **App Password** (not the ordinary
Gmail password; it comes from `myaccount.google.com/apppasswords`, which asks
for 2-Step Verification first). Run `python mail_authorize.py` once — it asks
for the App Password, checks it against Gmail, and saves it to
`~/.mnhs/mail.json`. That file is outside this folder on purpose: the app reads
`MNHS_MAIL_PASSWORD` or `MNHS_MAIL_CREDENTIALS` first, then that file, and the
password is never written into the project, copied, zipped or pushed.

```
Mail server  smtp.gmail.com   port 587   STARTTLS
Username     angelesedgardo17@gmail.com  (overridable with MNHS_MAIL_USERNAME)
Password     the Gmail App Password      (MNHS_MAIL_PASSWORD or ~/.mnhs/mail.json)
```

`mail_send.py` uses only Python's own `smtplib`, so there is nothing to install
for this. With no password set, `mail_send.configured()` is false, the Reset
Password page says email is not set up yet and names the command to fix it, and
the rest of the app is unchanged.

## Notes
- The economy (watch-video credits), referral, and PayPal payment features
  were removed — the app is completely free now. Old templates are kept in
  `old/removed_templates_2026-10-22/` for reference, and the old database is
  backed up as `quiz_app_old_economy.db.bak`.
- Delete `quiz_app.db` to reset all accounts and results.
- On startup, `ensure_database()` creates any missing tables and upgrades an
   old economy-schema `user` table in place (adds the name/school/grade/
   section/password columns, drops the dead `credits`/`status` columns). This
   runs whenever `app.py` is imported, so hosted deployments such as
   PythonAnywhere self-heal after a reload — no manual SQL needed.
   Accounts from the old version have no password yet, so signing up with one
   of those emails fills in that existing row instead of rejecting it.
- The local `quiz_app.db` now holds only the admin account and one saved
  attempt; the old "Test Student A–F" seed rows are gone. ELEMENTALS adds its
  reference data on first run (118 elements, 243 clues), Jumbled Letters
  creates the three `jl_` tables and Who's Who the three `ww_` tables on first
  request, and `whoswho.json` starts as `{"activities": []}` until the admin
  fills in the first activity.
- `_quiz_app_before_recover.db`, `_quiz_app_before_jumbled.db` and
  `_quiz_app_before_ww_cleanup.db` are local safety copies taken before schema
  work. Keep them on this computer — never upload them to the server.
- Deploying the games means uploading `ELEMENTALS/`, `JUMBLED/`, `WHOSWHO/`,
  `whoswho.json` and `whoswho_photos/` together with `app.py`, `templates/` and
  `static/`. Anything missing only disables its own card on `/games`; the quiz
  app keeps running. No credentials file, token or backup `.db` belongs on the
  server.
- For production hosting, set a real `secret_key` via an environment
  variable and serve over HTTPS (also required for the offline
  service worker on non-localhost origins).
