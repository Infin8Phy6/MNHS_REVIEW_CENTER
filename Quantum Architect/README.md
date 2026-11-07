# Quantum Architect

Electron configuration taught two ways: students build atoms on a game board where Aufbau, Pauli and
Hund behave like physics, and teachers generate printable worksheets with answer keys.

It is one of the **Educational Games** in the MNHS Review Center. The Review Center imports this
folder as a Flask blueprint and mounts it at **`/games/quantum-architect`**, so the hub is the normal
way to run it — open `http://127.0.0.1:5000/games` and the Quantum Architect card is there.

## Run it inside the Review Center

Nothing to start here. From the Review Center folder:

```
venv\Scripts\python.exe app.py
```

Then **http://127.0.0.1:5000/games/quantum-architect/**. The hub installs `python-docx` and
`reportlab` from its own `requirements.txt`; `requirements.txt` in this folder is only for the
standalone run below.

Mounted inside the hub the game gets three hooks from `app.py`:

| Hook | What it gives this folder |
|---|---|
| `identity` | the signed-in student (name, grade, section, account), so nobody types their name on the board |
| `is_admin` | whether the visitor is a teacher, admin or main admin — this is what opens the worksheet studio and every answer key |
| `teacher_label` | the signed-in staff member's display name, printed on the paper header and in the top bar |

There is **no PIN and no second login**. Staff use the Review Center's own `/admin/login`; a learner
who is not signed in as staff sees only the board, and the studio links disappear from the page.
Running this folder on its own (no hub, no hooks) keeps every page open for the person at the machine.

## Run it standalone

Useful for checking the folder by itself. Open a terminal in this folder and:

```
pip install -r requirements.txt
python app.py            # http://127.0.0.1:8050, add --lan for the lab, --no-browser to keep it quiet
```

## What to click

The top bar has **Play**, and for a staff session also **Worksheets**, **Create worksheet** and a
`teacher mode · <name>` badge. The last item is **‹ Educational Games**, back to the hub's games page.

- **Play** (home card: *Open the board*) — pick any element from the 18-column periodic table, or
  type a Z and press Enter, or use **Random element**. Click an orbital box to drop the next electron,
  drag one out of the electron pool, or use the keyboard: `S` flip spin (the **flip (S)** button does
  the same), `U` undo, `H` hint, `R` / **Clear board** to start the atom again, `1`–`7` jump to a shell.
  Tick **Practice mode** to switch off the timer, the stability drain and the point penalties while you
  demonstrate on the projector.
  The ladder reads **downward from 1s** (energy grows as you go down), the **electron pool sits in its
  own column on the right**, and the readout carries two pictures of the same atom: the **Bohr model**
  (rings K–Q with electron dots) and, below it, the **real cloud model**, where each occupied orbital is
  drawn with its own shape — sphere for s, dumbbell for p (with mℓ deciding the axis), cloverleaf for d
  and the many-lobed f — rather than a dot. Hovering a box in the ladder isolates that orbital and
  prints its `mℓ` under the cloud. Anything in **red** is a **valence** sublevel or shell. The lone
  electron in an orbital is always drawn `↑`; `↓` only appears when a box already holds one.
- **Create worksheet** (home card: *Create a worksheet*) — fill in title / class / section / teacher and
  the date — the teacher line and the class come from the signed-in staff account and the student's own
  section, so there is nothing to retype — choose a tier (**Grades 7-8**, **Standard**, **Advanced**,
  **Custom — I choose the question types**), choose the elements with a preset, a Z range, or a typed
  list such as `11 12 13 26`, tick the question types, set the number of items and the marks per item,
  pick the notation order (grouped by shell, or energy/Aufbau order) and the diagram scope, then press
  **Generate worksheet**.
- On the worksheet page — **Download DOCX** (editable in Word), **Download PDF** (print as it is),
  **Print this page**, **Regenerate with the next seed** (same settings, different paper), **Delete
  worksheet**, and the three answer-key buttons (**Answer key**, **Key DOCX**, **Key PDF**). The whole
  studio, keys included, is behind the hub's staff session.
- **Orbital sheets** (home cards: *Orbital box worksheet* / *New orbital sheet*) — the A4 portrait
  sheet. Pick the first twenty elements (or a preset, a Z range or a typed list) and the layout:
  **two small elements to a page** — one in the top half, one in the bottom half, cut along the dashed
  line — or **one element to a page** for configurations with many sublevels. Every sublevel prints
  its empty boxes with the `mℓ` value under each, and the **Bohr model** sits in the upper right of the
  block. **Student PDF** leaves the boxes blank; **Answer key PDF** fills the arrows and prints the
  configuration, energy order and shell counts; **PDF + key in one file** puts the student pages first
  and the key after. Teachers only, like the rest of the studio.

## Checks

Run these from the Review Center folder — no pytest or other test framework needed:

```
venv\Scripts\python.exe "Quantum Architect/checks/check_chemistry.py"   # 36 reference configs, 118-element sweep, auto-play, illegal moves, grid layout, orbital-sheet pagination
venv\Scripts\python.exe "Quantum Architect/checks/check_app.py"          # pages, APIs, both studios, all PDFs, staff-only keys, cleanup
venv\Scripts\python.exe "Quantum Architect/checks/check_hub_mount.py"    # the game mounted inside the real hub app
```

All three should end with `All ... checks passed.` `check_app.py` also writes example files into
`samples/` — student and key papers for both studios — so you can open a PDF or Word file without
generating one first.

## Files

| Path | What it holds |
|---|---|
| `app.py` | the blueprint: board, APIs, worksheet studio, exports, and `mount()` for the Review Center |
| `quantum/chemistry.py` | the chemistry: fill order, capacities, exceptions, ions, quantum numbers, rule validation, and **`MESSAGES`** — every on-screen rule wording lives in that one dict |
| `quantum/worksheets.py` | tiers, element pools, the ten question builders, the deterministic generator |
| `quantum/exports.py` | A4 landscape DOCX (python-docx) and PDF (reportlab), student and teacher versions |
| `quantum/atom_sheets.py` | the orbital-box sheet: element blocks, compact/full classification, pagination, Bohr rings |
| `quantum/atom_exports.py` | A4 **portrait** PDF for the orbital-box sheet — student, key, and both in one file |
| `quantum/store.py` | saved worksheets in `data/worksheets.json`, orbital sheets in `data/atom_sheets.json` — no database, and no tables in `quiz_app.db` |
| `templates/` | the pages, all named `qa_*.html` so they cannot collide with the hub's own templates |
| `static/` | the stylesheets (`app.css`, `atom_sheet.css`) and `js/game.js`, which fetches under `window.QA_BASE` so it works at `/games/quantum-architect/` |
| `QUANTUM_ARCHITECT_GDD.md` | the design document, including the §24 wording decisions still open |
