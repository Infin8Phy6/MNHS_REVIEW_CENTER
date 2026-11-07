# ELEMENTALS — Periodic Table Symbol Sprint

A Flask activity for class use. Ten elements are drawn at random from a local
SQLite database; the student reads the clues and gives the chemical symbol.
The score is marked on the computer and the result sheet downloads as a PNG.

Two levels are chosen on the name slip:

* **With choices** — the clues plus six symbol buttons at the side. The student
  may press one or type it, and any letter case counts (`fe`, `FE`, `Fe`).
* **Hard - spell the symbol** — only the clues. There are no buttons, so the
  student types the symbol, and the capitalisation is part of the answer:
  `Fe` is correct while `fe` and `FE` are marked wrong. The number of letters
  is shown as the only hint, and right letters in the wrong case get their own
  feedback line.

Nothing needs the internet. The tiles, clues and scores live in `elements.db`
in this folder.

## Run it

Windows: double-click **run.bat**
Mac: double-click **run.command**
Any computer:

    pip install -r requirements.txt
    python app.py

The browser opens on <http://localhost:8000/>. Use another port with
`python app.py 8020`, and let the whole class connect to one machine with
`python app.py --lan` (it prints the network address).

## Install it as an app

Open the running app in Chrome or Edge and press the **Install** icon at the
end of the address bar. ELEMENTALS then gets its own window, taskbar icon and
Start-menu entry, and the pages plus all 118 tiles are cached for offline use.

## Give it to a student

Press **Install → Download the app (ELEMENTALS.zip)** on the running server, or
copy this folder. The student unzips it, installs Python once, and double-clicks
`run.bat`.

## Pages

| Address | What it is |
| --- | --- |
| `/` | Name slip, the level choice and how the activity scores |
| `/play/<token>` | The game: tile, clues, choices on the standard level, typed answer on the hard level, score |
| `/table` | All 118 element tiles with configuration, oxidation states, state and class |
| `/results` | Every attempt stored in the database |
| `/install` | These instructions in the browser |

## Files

    app.py            Flask server, database schema and routes
    periodic_data.py  tile data for the 118 elements + electron configuration builder
    clue_data.py      three classroom clues for the 81 elements the game may draw
    templates/        page templates
    static/           style, tile renderer, game script, offline service worker, icons
    elements.db       created on first run; delete it to rebuild from the data files

## The next activities

`devnotes` in this folder lists the planned games that reuse the same database
and the same 10-item, scored, PNG-export format: ionisation, isotopes, mole
calculations, stoichiometry, balancing equations and limiting reactant.
