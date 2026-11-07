# Quantum Architect — Game Design Document (GDD)

**Version:** 1.1 (stack revised to Python + Flask at the owner's direction; §16 and the build notes now
describe the app that is actually in the folder)
**Date:** 2026-11-03
**Companion file:** [quantum_architect_todo_list.md](file:///C:/Users/ADMIN/Documents/Quantum%20Architect/quantum_architect_todo_list.md)
**Status:** Phase 1 GDD + a first working build of Phase 2/3 (engine, board, worksheet studio, exports).
Sections marked `DECISION NEEDED` still require the owner's wording/scope call.

---

## 1. High Concept

**Quantum Architect** is a browser game where the player builds atoms by dragging electrons into
orbital boxes in the correct quantum order. Each element is a level. Correct placements raise a
**Stability Meter**; rule violations (wrong energy order, two same-spin electrons in a box, pairing
too early) trigger an **Energy Rejection Bounce** and drain stability. The goal is a complete, stable
electron configuration shown in standard notation.

- **One-line pitch:** *Tetris-style placement pressure meets real chemistry rules.*
- **Genre:** Educational puzzle-arcade / drag-and-drop construction.
- **Platform:** Web (desktop browser + touch/tablet/Chromebook), no install.
- **Session length:** 60–120 seconds per element; a class period fits 8–15 elements.
- **Fantasy:** The player is an engineer assembling matter, level by level, from the smallest atom up.

### 1.1 Design pillars

| # | Pillar | What it means in practice | Fails when |
|---|--------|---------------------------|------------|
| P1 | **The rules are the gameplay** | Aufbau, Pauli and Hund are not explained in a tutorial slide — they are the physics that rejects your move. | Errors feel arbitrary or unexplained. |
| P2 | **Science-accurate, always** | Every displayed configuration matches an authoritative reference (NIST/CRC). Exceptions are real, not invented. | The game teaches a wrong configuration. |
| P3 | **Two views, one truth** | The Bohr model and the real cloud model are live mirrors of the same orbital-stack state. | The three representations can ever disagree. |
| P4 | **Learnable without a teacher present** | Every rejection names the rule violated and shows the correct target. | A stuck student has no next move. |
| P5 | **Runs on a school Chromebook** | Static build, no install, low CPU, works offline. | Load time > 3s or frame drops with 118 electrons. |

---

## 2. Audience & Curriculum Fit

| Attribute | Value |
|---|---|
| Primary | Junior high / senior high students, age 13–17, first exposure to electron configuration |
| Secondary | Review-center students prepping for chemistry exams |
| Prior knowledge required | Atomic number, protons/electrons, shells K-L-M-N; **not** quantum numbers |
| Class context | Teacher-led lab/computer session, 1 device per student or per pair |
| Language | English UI; `DECISION NEEDED` — add Filipino/Bisaya toggle? |
| Teacher role | Owns a Teacher Mode dashboard (see §14) |

**Learning objectives** (what a player can do after finishing World 5):
1. Write the full spdf configuration for any element Z = 1–36.
2. Write the noble-gas shorthand for Z = 19–56.
3. State which rule was broken in a given wrong configuration.
4. Explain why Cr and Cu break the expected order.
5. Form cations and anions and remove/add electrons in the correct order (highest *n* first).
6. Relate a line spectrum to an electron falling back down an energy gap.

---

## 3. Play Modes

| Mode | Description | Unlocks |
|---|---|---|
| **Build Mode** (default) | Standard per-element level with timer, stability, scoring. | Start |
| **Practice Mode** | Same board, infinite stability, no timer, hints always on, no score saved. | Start |
| **Shorthand Mode** | Board starts pre-filled to the bracketed noble core; only the valence sublevels are playable. | World 6 |
| **Ion Mode** | Player first builds the neutral atom, then adds/removes the requested electrons to form the ion. | World 3 |
| **Exam Mode** | No hints, no bounce-back explanations, results recorded to the class log, one attempt per element. | Teacher Mode |
| **Spectra Mode** | Bonus mini-game: excite electrons with photons and match emitted line spectra (§13). | Complete World 5 |
| **Sandbox** | Any element Z = 1–118, free build, no scoring, both views side by side. | Complete World 1 |

---

## 4. Core Game Loop

```
Element Brief  ->  Place electrons  ->  Rule validation  ->  Feedback  ->  Sublevel closes
      |                                        |                              |
      |                                        v                              v
 preview Z, target ion,          Energy Rejection Bounce           Stability bonus + score
 shorthand hint                  + stability drain + hint popup    multiplier step-up
                                                                             |
   Retry from checkpoint  <-  Stability = 0  <-  Atom decays  <-              v
                                                                   All Z electrons placed
                                                                            |
                                                                   Stability Lock -> Result Modal
                                                                            |
                                                        World Map (next element / star rating)
```

**Moment-to-moment (2–5s):** pick electron → aim at a box → place → see glow + spin arrow + live
notation update.
**Element (60–120s):** fill sublevels in order, close each sublevel for a bonus, survive the timer.
**World (1 class):** 6–17 elements with one new mechanic introduced per world (§11).

---

## 5. The Two Representations

Both views render from a single source of truth: the `ElectronPlacement[]` state (§16.2). They are
never independently editable.

### 5.1 Orbital Stack / Bohr view (primary play surface)

- Rows = sublevels, stacked in **energy order (Madelung)**, not by shell, and read **top to bottom**:
  `1s` sits at the top and energy increases downward. Each box carries an
  `n` tag so the shell is still readable.
- Sublevel label on the left: `1s`, `2s`, `2p`, `3s`, `3p`, `4s`, `3d`, `4p`, `5s`, `4d`, `5p`, `6s`, `4f`, `5d`, `6p`, `7s`, `5f`, `6d`, `7p`.
- Boxes per sublevel: s = 1, p = 3, d = 5, f = 7.
- Each box = one orbital; holds 0–2 electrons drawn as ↑ / ↓ arrows.
- Degenerate boxes in the same sublevel are visually linked (shared bracket + label `3p`).
- Locked/unreachable sublevels (beyond current Z) render dimmed with a padlock and energy label, so
  the ladder is always visible and the player learns its shape.
- **Valence marking:** the valence sublevels (the set behind `valence_electrons()` — outer `s`/`p`,
  plus `(n−1)d` and `(n−2)f` for the transition and inner-transition metals) are drawn in red, and so
  are their arrows, their terms in the live notation and their ring in the Bohr model. The row label
  also prints the word *valence* and the pool tokens read "valence electron", so colour is never the
  only signal (§15 colour-blind rule).
- Shell rings (Bohr) are drawn as a background arc layer behind each `n` group: K n=1, L n=2, M n=3,
  N n=4, O n=5, P n=6, Q n=7.

> **Design note (P3 risk):** the classic Bohr "2-8-18-32" shell table conflicts with energy ordering
> (`4s` fills before `3d`). The game resolves this by ordering the *play surface* by energy while the
> *Bohr model* groups by `n`. The Element Brief shows both counts so the student sees that shell M
> holds 8 while 3s/3p fill and gains 10 more when 3d fills. **Never** show a shell total that the
> board cannot produce.

### 5.2 Bohr model and real cloud model (two canvases)

The old single "cloud view" is now two pictures stacked in the readout, because they answer two
different questions — *which shell?* and *what shape is the orbital?*

**Bohr model (upper canvas).** Nucleus, one ring per occupied `n` (K–Q), electron dots spread evenly
on their ring, valence ring and dots in red, ring labels `K2`, `L8`, `M1`. This is the shell picture
the student is meant to internalise; it is deliberately the simple model.

**Real cloud model (lower canvas).** Electrons are not dots. Every occupied orbital is drawn as the
shape its `ℓ` and `mℓ` give it, all overlaid on one nucleus:

- `s` (`ℓ = 0`, one box, `mℓ = 0`) — a sphere.
- `p` (`ℓ = 1`, three boxes) — a dumbbell; `mℓ = −1` lies across the page, `mℓ = 0` stands upright,
  `mℓ = +1` points diagonally and is stroked dashed to read as "into the page".
- `d` (`ℓ = 2`, five boxes) — a four-lobed cloverleaf, rotated by `mℓ`; `mℓ = 0` is the
  dumbbell-with-ring `d_z²`.
- `f` (`ℓ = 3`, seven boxes) — a stylised multi-lobed shape, rotated by `mℓ`.

Each box contributes one orbital; a paired box is drawn brighter than a singly occupied one, and any
orbital in a valence sublevel is drawn red. Larger `n` draws a larger shape, and the nucleus symbol
sits on top. Z 1–20 is covered completely by `s` and `p`; `d` and `f` are implemented so the board
does not stop teaching at calcium. Hovering a box in the ladder highlights that single orbital in the
cloud and prints `sublevel · mℓ = … · shape` under the canvas.

The cloud is decorative-but-consistent: the number of shapes equals the number of occupied orbitals,
and it never shows an occupancy the board could not produce (§1.1 P3).

### 5.3 Spin

- Spin is first-class state, not cosmetic: ↑ and ↓.
- **Spin is pre-assigned by position:** the first electron in an orbital is always ↑, and ↓ appears
  only as the second arrow of an ↑↓ pair. Placing ↓ into an empty box is auto-corrected to ↑ with the
  Hund message, so a lone ↓ can never exist on the board or in an answer key.
- Encoding is **shape + arrow direction**, never colour alone (colour-blind safety, §15).
- Players can flip spin before or after placing (`S` key / spin toggle button).

---

## 6. Input Controls

| Action | Mouse | Touch | Keyboard | Screen reader announcement |
|---|---|---|---|---|
| Grab electron | click-drag from Electron Pool | long-press + drag | `Enter` on pool, then `Arrow` to target, `Enter` to drop | "Electron ready, spin up" |
| Quick place | — | — | `Enter`/`Space` on focused box | "3p box 2, now one electron, spin up" |
| Pulse-click (no drag) | single click on a box places the next electron in the *next legal slot* | same | `P` | "Auto-placed into 3d box 4" |
| Flip spin | right-click / spin button | tap spin chip | `S` | "Spin now down" |
| Undo | toolbar | toolbar | `Ctrl+Z` | "Removed electron from 4s" |
| Redo | toolbar | toolbar | `Ctrl+Y` | — |
| Reset element | toolbar (confirm) | toolbar | `R` | "Board cleared" |
| Jump to next legal slot | — | — | `Tab` / `]` | "Next valid target: 4s box 1" |
| Inspect orbital shape | hover a box | tap a box | — | "3p box 2, mℓ = 0, dumbbell upright" |
| Pause | — | — | `Esc` | "Paused" |

**Drag-and-drop requirements**
1. Pointer-based (click a box, or drag an electron token from the pool) so mouse, touch and pen share
   one code path.
2. Drop target = the orbital box, with a ≥ 44 × 44 px hit area on touch regardless of visual size.
3. Ghost preview shows legality *before* release: green ring = legal, red ring + rule name = illegal.
4. Illegal drop is not silently ignored — it plays the Energy Rejection Bounce (§9.4).
5. Full keyboard path exists for every placement (accessibility, §15).
6. Auto-scroll when dragging near the edge of the ladder (period 6–7 boards exceed one screen).

---

## 7. Chemistry Data Model

### 7.1 Sublevel capacities

| Sublevel | Orbitals | Max electrons | First appears at Z |
|---|---|---|---|
| s | 1 | 2 | 1 (H) |
| p | 3 | 6 | 5 (B) |
| d | 5 | 10 | 21 (Sc) |
| f | 7 | 14 | 58 (Ce)* |

\* f-block conventionally starts at La (Z=57) / Ce (Z=58) depending on the textbook. **`DECISION NEEDED`**
— which convention the game states on screen. Recommended: show La as `[Xe] 5d¹ 6s²` and label Lu (Z=71)
as the first 4d¹⁰5d¹ completion, with a footnote — but keep the visual f-block cut at Ce, matching most
senior-high textbooks.

### 7.2 Madelung (n + ℓ) fill order — the master sequence

| # | Sublevel | e⁻ | cumulative Z | n+ℓ | Block |
|---|---|---|---|---|---|
| 1 | 1s | 2 | 2 | 1 | s |
| 2 | 2s | 2 | 4 | 2 | s |
| 3 | 2p | 6 | 10 | 3 | p |
| 4 | 3s | 2 | 12 | 4 | s |
| 5 | 3p | 6 | 18 | 5 | p |
| 6 | 4s | 2 | 20 | 4 | s |
| 7 | 3d | 10 | 30 | 5 | d |
| 8 | 4p | 6 | 36 | 6 | p |
| 9 | 5s | 2 | 38 | 6 | s |
| 10 | 4d | 10 | 48 | 7 | d |
| 11 | 5p | 6 | 54 | 8 | p |
| 12 | 6s | 2 | 56 | 7 | s |
| 13 | 4f | 14 | 70 | 8 | f |
| 14 | 5d | 10 | 80 | 9 | d |
| 15 | 6p | 6 | 86 | 10 | p |
| 16 | 7s | 2 | 88 | 8 | s |
| 17 | 5f | 14 | 102 | 9 | f |
| 18 | 6d | 10 | 112 | 10 | d |
| 19 | 7p | 6 | 118 | 11 | p |

Tie-break rule inside equal `n+ℓ`: lower `n` fills first (explains 4s before 3d, 5s before 4d).

### 7.3 Ground-state exceptions (real, reference-backed)

Taught exceptions (must implement):

| Z | Element | Expected by Madelung | Actual ground state | Reason shown in-game |
|---|---|---|---|---|
| 24 | Cr | `[Ar] 3d⁴ 4s²` | `[Ar] 3d⁵ 4s¹` | half-filled d gains exchange stability |
| 29 | Cu | `[Ar] 3d⁹ 4s²` | `[Ar] 3d¹⁰ 4s¹` | fully-filled d is lower energy |

Extended exception set (unlock in World 7+ / toggle in Teacher Mode):

| Z | Element | Actual |
|---|---|---|
| 41 | Nb | `[Kr] 4d⁴ 5s¹` |
| 42 | Mo | `[Kr] 4d⁵ 5s¹` |
| 44 | Ru | `[Kr] 4d⁷ 5s¹` |
| 45 | Rh | `[Kr] 4d⁸ 5s¹` |
| 46 | Pd | `[Kr] 4d¹⁰` |
| 47 | Ag | `[Kr] 4d¹⁰ 5s¹` |
| 57 | La | `[Xe] 5d¹ 6s²` |
| 58 | Ce | `[Xe] 4f¹ 5d¹ 6s²` |
| 64 | Gd | `[Xe] 4f⁷ 5d¹ 6s²` |
| 78 | Pt | `[Xe] 4f¹⁴ 5d⁹ 6s¹` |
| 79 | Au | `[Xe] 4f¹⁴ 5d¹⁰ 6s¹` |
| 89 | Ac | `[Rn] 6d¹ 7s²` |
| 90 | Th | `[Rn] 6d² 7s²` |
| 91 | Pa | `[Rn] 5f² 6d¹ 7s²` |
| 92 | U | `[Rn] 5f³ 6d¹ 7s²` |
| 93 | Np | `[Rn] 5f⁴ 6d¹ 7s²` |
| 96 | Cm | `[Rn] 5f⁷ 6d¹ 7s²` |

**Validation behaviour:** when an element has an entry in `exceptions.json`, the Aufbau handler accepts
the exception path and the *Madelung path is rejected with a special "Stability Exception" message*
(not an error sound). See §9.5.

### 7.4 Ion rules

Ion Mode always builds neutral first, then converts. Electron bookkeeping:

| Case | Rule | Worked example |
|---|---|---|
| Main-group cation | remove from the highest-`n` sublevel | `Mg [Ne]3s²` → `Mg²⁺ [Ne]` |
| Transition cation | remove **ns before (n−1)d** — the d electrons stay | `Fe [Ar]3d⁶4s²` → `Fe²⁺ [Ar]3d⁶` → `Fe³⁺ [Ar]3d⁵` |
| Anion | add to the partially filled highest-energy sublevel (usually np) | `Cl [Ne]3s²3p⁵` → `Cl⁻ [Ne]3s²3p⁶ = [Ar]` |
| p-block metal cation | ns and np leave, (n−1)d core stays | `Sn [Kr]4d¹⁰5s²5p²` → `Sn²⁺ [Kr]4d¹⁰5s²` (inert pair) |

High-value teaching moments to feature explicitly:
- `Fe²⁺` vs `Fe³⁺` — 3d⁵ half-filled makes Fe³⁺ unusually stable.
- `Cu⁺ [Ar]3d¹⁰` vs `Cu²⁺ [Ar]3d⁹` — the closed d wins on stability, hydration wins on chemistry.
- `Cr³⁺ [Ar]3d³`, `Mn²⁺ [Ar]3d⁵`, `Zn²⁺ [Ar]3d¹⁰` (the only d¹⁰ ion; Zn is not a variable-charge metal).
- Isoelectronic series: `O²⁻`, `F⁻`, `Ne`, `Na⁺`, `Mg²⁺`, `Al³⁺` all `1s²2s²2p⁶` — bonus challenge in Ion Mode.

**Ion scope by world:** monoatomic only (no polyatomic ions such as `SO₄²⁻` or `NH₄⁺` — out of scope;
`DECISION NEEDED` for a later expansion pack).

### 7.5 Notation formats displayed

1. Full spdf: `1s² 2s² 2p⁶ 3s² 3p⁶ 4s¹`
2. Noble-gas shorthand: `[Ar] 4s¹`
3. Orbital diagram: box/arrow form (what the board *is*)
4. Shell (Bohr) distribution: `2, 8, 8, 1` for K — **labelled "shells by principal quantum number"**
   to avoid clashing with the energy-ordered board.
5. Subshell occupancy bar: `s² p⁶ d⁵ f¹⁴`
6. Quantum numbers of the last differentiating electron: `n, ℓ, mℓ, ms` (advanced tooltip, Teacher Mode
   can force this into Exam Mode)

---

## 8. Level Structure

Each level = one element card with a target.

```json
{
  "id": "level_24_cr",
  "z": 24,
  "symbol": "Cr",
  "name": "Chromium",
  "world": 5,
  "targetType": "neutral-exception",
  "electronCount": 24,
  "timeLimitSeconds": 150,
  "allowedSublevels": ["1s","2s","2p","3s","3p","4s","3d"],
  "exceptionId": "Cr-3d5-4s1",
  "hintsEnabled": true,
  "shorthand": "[Ar] 3d5 4s1",
  "starThresholds": [0.55, 0.75, 0.90],
  "teachingNote": "Half-filled 3d buys exchange energy — the exception the exam always asks about."
}
```

**Element brief screen (pre-level, 1 tap to start):** symbol, name, Z, mass, block badge, neutral vs
ion target, the sublevels that will be involved (hidden if "surprise" flag set), new-mechanic card
(first time only), and a Start / Practice / Back choice.

---

## 9. Quantum Rule Validation Engine

Pure, synchronous, deterministic module — no React, no timers, no randomness. This is the highest-
risk, highest-value code in the project and is unit-tested against a reference table of all 118
ground states (§19).

### 9.1 Public surface

```
validatePlacement(state, placement) -> { ok: true } | Violation
Violation = {
  rule: 'AUFBAU' | 'PAULI' | 'HUND' | 'SPIN' | 'CAPACITY' | 'COUNT' | 'ION_ORDER',
  messageKey: string,        // maps to exact on-screen wording
  correctTarget: SublevelBox | null,
  severity: 'bounce' | 'block' | 'warn',
  stabilityDelta: number,
  scoreDelta: number
}
```

### 9.2 Aufbau Principle handler

**Check:** target sublevel's index in the Madelung sequence must be the *current* next-fillable index,
or a sublevel already opened at that index. Reject placing into sublevel *k* while any sublevel *j < k*
that the element needs is not yet at its required occupancy for this target configuration.

**Failure feedback:** Energy Rejection Bounce — the electron springs back to the pool, the offending
sublevel flashes amber, the earlier unfilled sublevel pulses with a "fill me first" chevron.
Message: `Energy Rejection — 3d is higher in energy than 4s. Fill 4s first.`
Score/stability: −150 / −12. Severity `bounce`.

**Special case:** for exception elements, the Madelung-expected placement is rejected with the §9.5
exception message, not the Aufbau message.

### 9.3 Pauli Exclusion handler

**Check:** box occupancy ≤ 2; if 2, their spins must be opposite.

- Third electron attempted → blocked entirely (no drop), message `Pauli Exclusion — one orbital holds
  at most 2 electrons.` Severity `block`, −100 / −8.
- Two electrons with the **same spin** in one box → the placement lands, then a forced spin-flip
  animation corrects it with a warning, message `Pauli Exclusion — paired electrons must have opposite
  spins. ↑↓ only.` Severity `warn`, −75 / −4. The game never lets an illegal ↑↑ state persist.

### 9.4 Hund's Rule handler

**Check:** within a degenerate sublevel, a pairing is legal only once every box of that sublevel
already holds 1 electron, **and** all singletons share the same spin.

- Pairing early → bounce, message `Hund's Rule — spread out first. Place 1 electron in each 3p orbital
  before pairing.` Correct target box is highlighted. Severity `bounce`, −150 / −12.
- Singleton with opposite spin to existing singletons → warn + auto-correct (like §9.3):
  `Hund's Rule — unpaired electrons in the same sublevel spin the same way.` −75 / −4.

### 9.5 Stability Exception handler (Cr, Cu, …)

When a target sublevel is an exception sublevel:
- The rejected-expected placement triggers a distinct **gold** effect, not the red error effect:
  sound = chime, message `Stability Exception — Chromium takes 3d⁵ 4s¹. Half-filled d is more stable
  than 3d⁴ 4s².`
- Reward instead of penalty: `+200 Exception Insight` the first time per element, and an
  "Exceptions Codex" entry is unlocked in the Player Codex.
- Teacher Mode toggle: `Strict exceptions` (must discover unaided) vs `Guided exceptions` (popup
  first). Default per world (§11).

### 9.6 Capacity & count guards

| Check | Message | Severity |
|---|---|---|
| Sublevel over capacity (`2p⁷`) | `Too many electrons — a p sublevel holds 6.` | block |
| Total electrons > Z (neutral) | `Neutral potassium has 19 electrons. You have 20.` | block |
| Placed < Z at timer expiry | `Incomplete — 16 of 19 electrons placed.` | timeout |
| Ion removal from wrong sublevel | `Ion Order — remove 4s before 3d when forming Fe²⁺.` | bounce |

### 9.7 Validation order (per attempt)

```
1. COUNT/CAPACITY   (is a slot even available?)      -> block
2. AUFBAU           (is this the next energy level?) -> bounce
3. HUND             (degenerate singletons first?)   -> bounce / warn
4. PAULI            (spin pairing)                   -> block / warn
5. EXCEPTION        (overrides 2 for listed Z)       -> gold accept
6. commit + recompute notation + mirror to cloud
```

### 9.8 Validation test matrix (must exist before Phase 2 exit)

- Golden file: all 118 ground-state configurations, built by an auto-player that always picks
  `correctTarget`; assert it completes with 0 violations and matches the reference exactly.
- Mutation tests: 200 hand-written illegal placements, one per rule × sublevel × element type.
- Property tests: for every Z and every sublevel, `placed > capacity` is unreachable; ↑↑ is
  unreachable; no configuration with fewer than Z electrons can be declared stable.

---

## 10. Scoring System

### 10.1 Earning

| Event | Points | Notes |
|---|---|---|
| Correct electron placement | 100 | × current multiplier |
| Hund sweep (all boxes in a sublevel single-occupied before any pair) | 250 | per sublevel |
| Sublevel closure | s 200 · p 600 · d 1000 · f 1400 | full and correct |
| Element completion (Stability Lock) | 1000 × block factor | block factor s 1.0 · p 1.2 · d 1.5 · f 2.0 |
| Time remaining bonus | +2 per second left | capped at 50% of base |
| Exception insight (§9.5) | +200 | first time per element |
| Flawless element (0 violations) | ×1.5 on element total | the "Architect" badge |
| Shorthand-mode correct bracket core | +400 | skips 18 placements deliberately |
| Ion conversion correct | 150 per electron added/removed in the right sublevel | |

### 10.2 Streak multiplier

Starts ×1.00. Each consecutive correct placement +0.25, max ×3.00. Any `bounce`/`block` resets to
×1.00; a `warn` halves it (rounded to 0.25). Displayed as a flame/orbit gauge next to the score.

### 10.3 Penalties (triggers, exact)

| Trigger | Score | Stability | Also |
|---|---|---|---|
| Aufbau bounce | −150 | −12 | 1 error logged |
| Hund bounce | −150 | −12 | 1 error logged |
| Pauli third-electron block | −100 | −8 | 1 error logged |
| Spin auto-correct warn | −75 | −4 | warn, not an error for grading |
| Undo | −25 | 0 | capped at −200 per element |
| Hint used | −100 | 0 | Practice/Exam: 0 / blocked |
| Idle > 8s | 0 | −3 over time | nudges `correctTarget` pulse |
| Atom decay (stability 0) | restart element from checkpoint | reset to 100 | attempt count +1 |

Penalties can drive a running score negative for one element; the level total is floored at 0 so the
star bar never moves backwards (avoids punishing a comeback).

### 10.4 Stability Meter & timers

- **Stability** = 0–100, starts 100. +2 per correct placement, values above per §10.3.
- 100–70 = calm blue glow · 69–40 = amber flicker · 39–15 = red shaking nucleus · 14–1 = crack
  overlay + alarm pulse · 0 = **Atom Decays** → restart from checkpoint.
- **Recovery:** 4 consecutive correct placements restores +10 once (a comeback mechanic so a single
  mistake does not spiral).
- **Countdown timer** per element: `45s + 3s × Z`, ×0.7 in World 6+, ×1.5 in Practice, off in Teacher
  demo mode. Period-6/7 elements get a floor of 180s and the Shorthand power-up strongly encouraged.
- **Stability timer (lock phase):** after the last electron, a 3.0s "settling" window runs — if the
  configuration is complete and legal, the atom locks with a cascade animation; incompleteness during
  this window plays the decay warning instead. This is the level's climax beat.

### 10.5 Stars & grading

| Stars | Score vs par (par = 100 × Z + closure bonuses) | Errors allowed |
|---|---|---|
| ★☆☆ | ≥ 55% | any |
| ★★☆ | ≥ 75% | ≤ 3 |
| ★★★ | ≥ 90% | ≤ 1, timer > 25% remaining |

Teacher Mode can export: element, attempts, score, % par, star, error breakdown by rule, time. That
breakdown is the pedagogically useful output — it says *which rule* the student does not own.

---

## 11. Progression Curve (full periodic table)

| World | Elements | New mechanic | Validation strictness | Exception handling |
|---|---|---|---|---|
| **W0 Tutorial — First Light** | H, He | drag/place, Pauli (2 in 1s) | full forgiving, no score | n/a |
| **W1 Shell Two** | Li–Ne (3–10) | 2s/2p, **Hund introduced**, spin | warn-only (no stability drain) | n/a |
| **W2 Third Way** | Na–Ar (11–18) | 3s/3p, octet highlight, **Ion Mode** (Na⁺, Cl⁻) | full bounce, 1 hint free | n/a |
| **W3 The 4s Detour** | K, Ca (19–20) | **Aufbau vs shell order conflict** — the core reveal; shorthand power-up preview | full, extended timer | n/a |
| **W4 d-Block Forge** | Sc–Zn (21–30) | 3d ladder row, sublevel closure bonuses, **Cr & Cu exceptions** | full, `Guided exceptions` default | Cr, Cu |
| **W5 p-Block Rise** | Ga–Kr (31–36) | **Noble Gas Shorthand unlocked** (mandatory from here), Spectra Mode unlocks | full, `Guided` | none new |
| **W6 Fifth Shell** | Rb–Xe (37–54) | 4d, shorthand-only boards, 5s/4d ordering | full, `Strict exceptions` | none new |
| **W7 Inner Transition** | Cs–Rn (55–86) | **4f ladder**, 6s/4f/5d order, Exceptions Codex | full, strict | Nb–Ag, La, Ce, Gd, Pt, Au |
| **W8 Actinide Deep** | Fr–Og (87–118) | 5f/6d/7p, superheavy time-pressure, exam gate | full, strict | Ac–Cm |
| **W9 Architect** | mixed Z 1–118 gauntlet | random draws, no hints, streak pressure, leaderboard | full | all |

Curve intent: the *first conflict* a student meets is Hund (W1), the *second* is energy-vs-shell
(“why does 4s fill before 3d?” — W3), and the *third* is exceptions (W4). Each world's difficulty
spike is one concept, never three at once.

**Par time per world** ≈ one 40–50 minute class session (W4 and W7 may need two).

---

## 12. Power-Ups & Progression Systems

| Power-up | Effect | Unlocked | Cost | Cooldown |
|---|---|---|---|---|
| **Noble Gas Shorthand Bracket** | Collapses the core into `[Ar]`/`[Kr]`/`[Xe]`/`[Rn]`; those electrons are pre-placed and unplayable | W5 preview, mandatory W6+ | 1 hint charge | 1 per element |
| **Spin Flipper** | Flip any placed electron's spin without penalty (once) | W1 | 1 charge | 1 per element |
| **Energy Lens** | Reveals the next legal sublevel + box, no penalty | W2 | −100 score | 30s |
| **Stability Cell** | +30 stability | W4 | 1 charge | once per element |
| **Time Dilation** | +20% timer | W3 | 1 charge | once per element |
| **Exception Shield** | Absorbs the next Aufbau bounce without stability loss | W4 | 1 charge | once per element |
| **Hund's Sweep** | Auto-distributes singletons across an empty degenerate sublevel (scores normally, no streak) | W5 | 2 charges | per sublevel |

Earned currency: **Quanta** (from stars + flawless runs) buys cosmetic orbitals, themes, and Codex
entries — never hints in Exam Mode. `DECISION NEEDED` — confirm no paid currency.

**Meta progression:** Exceptions Codex, Element Gallery (collected atoms), Themes (Neon Lab, Deep
Space, Chalkboard, Colour-blind Safe), Teacher leaderboard per class.

---

## 13. Spectra Mode (bonus mini-game)

**Premise:** the atom you built is now a light source. Excite it, watch the electron jump, catch the
emitted line.

Loop:
1. Choose an atom (built elements only, H first — hydrogen is the only one with analytically exact lines).
2. Fire photons of selectable energy (drag a wavelength slider: 100 nm UV → 1 mm microwave).
3. Absorption only succeeds when photon energy matches an allowed gap: electron hops `nᵢ → n_f`,
   orbital box glows, notation shows the excited state (`1s² 2s¹ 2p¹` for excited Be — **clearly
   labelled "EXCITED — not the ground state"**).
4. Electron falls back → an emission line appears at the correct wavelength/colour on a spectrum strip.
5. Match the emitted line pattern against a mystery sample's line spectrum = the round's objective.
6. Failure states: energy too low (transparent, no absorption), too high (ionisation, electron leaves,
   atom becomes cation — a nice callback to Ion Mode).

Scoring: per correct identification; streaks across 3 unknown samples. Kept deliberately separate from
Build Mode scoring so it never competes with the core rule-validation learning.

Content ladder: H (Balmer/Lyman/Paschen), He, then stylised multi-electron lines for Na (the yellow
doublet — flame test tie-in), K, Li, Cu (the green one). Data source must be real wavelengths
(NIST Atomic Spectra Database).

---

## 14. UI / UX Specification

### 14.1 Screen map

```
Title -> Mode Select -> World Map -> Element Brief -> [PLAY] -> Result Modal -> World Map
                                   ^                    |            |
                                   |                    v            v
Settings / Accessibility <---- HUD menus          Practice variant  Codex / Gallery
Teacher Mode (staff session) -> Class Roster -> Section -> Live Board -> Export
```

### 14.2 Play screen — layout mockup (desktop, 1280×720)

```
+--------------------------------------------------------------------------------------+
| ELEMENT 24  Cr  Chromium  [d-block]   TIME 01:52   SCORE 2,480  x2.25   LEFT 5       |  HUD 56px
| STABILITY [##########------] 62     red anywhere = the valence electrons and their    |
|                                     sublevel / shell                                 |
+--------------------------------+------------------+----------------------------------+
| PERIODIC PICKER                | ELECTRON POOL    | LIVE NOTATION                      |
| 18 groups, 7 periods, the      | (unplaced: 5)    |  1s² 2s² 2p⁶ 3s² 3p⁶ 3d⁵ 4s¹     |
| f-block pulled out below;      |  ↑ ↑ ↑ ↑ ↑       |   3d⁵ and 4s¹ are red = valence    |
| clicking a cell switches Z     |  ↑ ↑ ↑ ↑         |  energy order: 1s² 2s² 2p⁶ …       |
+--------------------------------+------------------+  [Ar] 3d⁵ 4s¹  (shorthand target)  |
| ORBITAL LADDER (energy order,  |  [flip spin S]   |  shells: 2, 8, 13(red), 1(red)     |
| 1s on top; energy grows        |                  |----------------------------------|
| downward)                      |  drag from here, | BOHR MODEL                         |
| 1s ▸ [_↑↓_]            closed  |  or click a      |  rings K–Q, valence ring in red     |
| 2s ▸ [_↑↓_]            closed  |  box, or Tab +   |----------------------------------|
| 2p ▸ [_↑↓_][_↑↓_][_↑↓_]        |  Enter           | REAL CLOUD MODEL                   |
| 3s ▸ [_↑↓_]                    |                  |  occupied orbitals as shapes:       |
| 3p ▸ [_↑↓_][_↑↓_][_↑↓_]        |                  |  sphere · dumbbell (mℓ axis) ·      |
| 4s ▸ [_↑_]    ← red row        |                  |  cloverleaf · multi-lobed f         |
| 3d ▸ [_↑_][_↑_][_↑_][_↑_][___] |                  |----------------------------------|
| 4p ▸ 🔒      5s ▸ 🔒            |                  | RULE FEEDBACK (last 6)              |
+--------------------------------+------------------+------------------------------------+
```

Touch layout (≤ 980px): the three columns stack in reading order — picker, ladder, electron pool, then
the notation, Bohr model, real cloud model and feedback; the HUD collapses to 2 rows and the pool stops
sticking while scrolling. Above 1180px the ladder gets the widest share and the pool stays pinned
beside it. The picker is a real 18-column table — group numbers across the top, period numbers down
the left, the two f-block rows detached under the main body with La/Ac placeholders in period 6/7 —
so a student can read period and group position, not just a row of tiles.

### 14.3 HUD elements

Element chip (Z, symbol, name, block badge) · live notation (updates on every placement, full and
shorthand simultaneously) · Stability Meter · Countdown Timer · Score + multiplier gauge · error
ticker (last 3 violations, rule-named) · Bohr model and real cloud model canvases (always on, stacked;
no toggle) · Undo / Redo / Reset · Hint (Energy Lens) · pause.

### 14.4 Result modal (level completion summary)

- Configuration in **4 notations** (§7.5), each individually copyable.
- Orbital diagram screenshot-style graphic (for students to paste into notes).
- Star rating, score vs par, time, largest multiplier reached.
- **Rule report:** per-rule counts — Aufbau 0, Pauli 1, Hund 2, Spin 0 — plus one sentence of coaching
  for the worst offender.
- Teaching note for that element (e.g. K: "one electron over a full argon core — that single 4s¹ is
  why potassium is explosive in water").
- Codex unlock banner, Quanta earned, Next / Retry / World Map buttons.

### 14.5 Orbital box worksheet (teacher studio)

A second, separate printable — not the question paper in §14.6. It teaches the same configuration by
hand and eye:

- **A4 portrait**, one element block per half page: a small element occupies the top half and the next
  occupies the bottom half, with a dashed **cut here** line between them. An element whose
  configuration needs more than six sublevel rows or thirteen orbital boxes (period 4 onward) is
  treated as a large element and takes the whole A4. A `per_page` setting can force two-to-a-page or
  one-to-a-page.
- **Boxes, not answers.** Every occupied sublevel prints its orbital boxes empty, with the `mℓ` value
  under each box, so the student writes `↑` and `↓` in the right boxes.
- **Bohr model in the upper right** of every block — rings, dots, ring labels, valence in red — so the
  shell picture is rehearsed while the boxes are filled.
- **Answer key:** the same sheet with the arrows filled in vector strokes, plus the configuration,
  energy order, shell distribution and valence count under the diagram. Student PDF, key PDF, and a
  combined **PDF + key in one file** (student pages first, key after) all come from
  `quantum/atom_exports.py`.
- The HTML preview mirrors the PDF and toggles between `student copy` and `?key=1`.
- **Teachers only:** the list, form, preview, delete and all three exports sit behind the same
  `staff_required` gate as the question studio. Records live in `data/atom_sheets.json`, so no table
  is added to `quiz_app.db`.
- Default pool is the **first twenty elements**, where `s` and `p` boxes and the Bohr model cover every
  electron. Any preset, Z range or typed list is accepted; heavy elements simply print smaller boxes.

### 14.6 Teacher Mode (staff session)

Signed in through the Review Center at `/admin/login` — teacher, admin or main admin, no separate
Quantum Architect login and no PIN. The top bar shows whose session is driving
(`teacher mode · <name>`), and the answer-key routes are the only pages the gate closes.

Class/section roster · assign worlds or specific elements · live board showing who is on what ·
strictness presets (`Guided` / `Strict exceptions`) · disable power-ups · disable timer (demo mode for
projector use) · show-shell-vs-energy footnote toggle · export CSV of per-rule error breakdown ·
**Answer-only mode** (project the correct board for a class walkthrough).

### 14.7 Art direction

Retro sci-fi / neon cyberpunk: near-black navy base, cyan-magenta accents, monospace numerals for
notation, thin glowing orbit rings, soft bloom on closures. Particle FX reserved for: pickup trail,
placement impact, sublevel closure cascade, Stability Lock shockwave, atom-decay shatter. Every FX has
a reduced-motion alternative.

---

## 15. Accessibility & School Compatibility

**Target: WCAG 2.1 AA.**

| Requirement | Implementation |
|---|---|
| Colour-blind safe | spin = arrow shape/direction, not colour; block/exception states use icon + text; no red/green-only signals; palette checked against deuteranopia + protanopia simulations |
| Keyboard-only | every placement, spin flip, undo, mode change reachable (§6); visible focus ring on each orbital box; logical tab order follows the energy ladder |
| Screen reader | ARIA grid role on each sublevel, `aria-label` per box "3p orbital 2, 1 of 2 electrons, spin up"; `aria-live=polite` announcements for placement, rejection and rule name; notation region updated on completion only (avoid spam) |
| Motion | reduced-motion mode: no bloom/particles/shake, bounce becomes a 150ms opacity blink; `prefers-reduced-motion` respected by default |
| Text | 16px body minimum, UI text scalable to 200%, no information in images alone |
| Touch | ≥44px targets; drag threshold; tap-to-place alternative always available |
| Cognitive | hint-only practice loop; no fail-states in W0–W1; per-element "one new rule" rule; optional plain-language mode for rule messages |
| Language | English first; Filipino/Bisaya strings stubbed in the i18n layer — `DECISION NEEDED` |
| Hardware | school Chromebook class target: 4 GB RAM, Celeron/i3, 1366×768, low-bandwidth school wifi |
| Network | **PWA + service worker**: full offline play after first load; assets ≤ 8 MB total; results queue locally and sync when back online |
| Input fallback | if drag fails (some trackpads / styluses), tap-pool → tap-box always completes the action |

---

## 16. Technical Architecture

### 16.1 Stack (decided by the owner: Python + Flask)

| Concern | Choice | Why |
|---|---|---|
| App | **Flask 3** — `app.py` exposes a `Blueprint` plus `mount(host_app, url_prefix)`. The MNHS Review Center imports it and calls `mount()` | the board *and* the worksheet studio live in the hub's one process, beside the other games |
| Pages | **Jinja2** templates in `templates/`, every file named `qa_*.html` | no build step, no bundler, edit-and-reload; the prefix is what stops the hub's own `index.html`/`play.html` from rendering instead of this game's |
| Chemistry | **`quantum/chemistry.py`** — pure Python, framework-free | single source of truth for both the board and the answer keys |
| Board front-end | **vanilla JS** (`static/js/game.js`) + CSS | served straight from disk; Chromebook-safe; no toolchain for a school lab |
| Electron cloud | **HTML5 Canvas 2D** | 2D only, no WebGL requirement |
| Rule mirror in browser | `/api/engine` + `/api/element/<z>` payloads | the wording and the tables come from Python, so JS can't drift |
| Worksheets | **`quantum/worksheets.py`** | deterministic per seed; 10 question types × tiers |
| Exports | **`python-docx`** + **`reportlab`** | editable DOCX *and* print PDF, both A4 landscape, everything in tables |
| Persistence | **`data/worksheets.json`** (temp file + `os.replace`) | no database to provision on shared hosting |
| Staff gate | the hub's own staff session, handed in as `game.is_admin` and read by `@staff_required` | teacher, admin and main admin open the key with the sign-in they already have — **no PIN, no second login** |
| Tests | `checks/check_chemistry.py`, `checks/check_app.py`, `checks/check_hub_mount.py` | stdlib-only, runnable on the owner's machine; the hub check imports the real review app |
| Deployment | deployed with the Review Center (PythonAnywhere or any WSGI host) | one process, no background timer, **two extra pip installs** beyond what the hub already needs |

**Phaser.js and React remain deliberately unused.** The board is a grid of accessible controls, not a
canvas scene, and every screen is a template.

### 16.2 Module layout (as built)

```
app.py                     a Flask Blueprint + mount(host_app, url_prefix, db_path=None).
                           routes: /, /play[/<z>], /api/*, /worksheets/*,
                           /atom-worksheets/*, exports. hub hooks: identity · is_admin · teacher_label
quantum/
  chemistry.py             Madelung order · capacities · exceptions · ions · quantum numbers ·
                           periodic_layout() (18-column grid) · validate_placement() ·
                           engine_payload() · engine_shared() · MESSAGES
  worksheets.py            tiers, presets (incl. first20), 10 builders, generate(settings)
  exports.py               student_docx / teacher_docx / student_pdf / teacher_pdf -> bytes
  atom_sheets.py           orbital-box sheet model: element_block(), compact/full, paginate(),
                           bohr_model(), PRESETS resolution
  atom_exports.py          A4 portrait PDFs: student_pdf / key_pdf / both_pdf
  store.py                 JSON catalogue of saved worksheets and orbital sheets
templates/                 qa_base, qa_index, qa_play, qa_error, qa_worksheets,
                           qa_worksheet_new, qa_worksheet_view, qa_worksheet_key,
                           qa_atom_sheets, qa_atom_sheet_new, qa_atom_sheet_view
static/css/app.css         studio (light) + board (dark), print rules, reduced motion
static/css/atom_sheet.css  A4 portrait preview and its own @page rule
static/js/game.js          ladder rendering, placement, validation mirror, scoring, timer,
                           Bohr and orbital-cloud painters
                           (fetches relative to window.QA_BASE, injected by qa_play.html)
checks/                    check_chemistry.py (engine + layout + sheet model),
                           check_app.py (app + store + exports), check_hub_mount.py
data/worksheets.json       saved papers      data/atom_sheets.json   saved orbital sheets
samples/                   exported examples for opening in Word / a PDF viewer
```

**Key invariant:** `quantum/chemistry.py` imports nothing from Flask or from the browser. The board,
the answer keys and the error-adding generators all read the same tables, so a rule can only be
taught one way.

### 16.3 Rule engine sketch

```python
def validate_placement(state_counts: dict[str, int], z: int, target: str,
                       box: int, spin: str) -> Violation | None:
    if total(state_counts) >= z:        return Violation("count",  "block", ...)
    if occupancy(state_counts, target) >= capacity(target):
                                         return Violation("pauli",  "block", "pauli_third")
    if target != next_needed_sublevel(config, state_counts) and not exception_gold(...):
                                         return Violation("aufbau", "bounce", "aufbau")
    if would_pair_before_sweep(...):     return Violation("hund",   "bounce", "hund")
    if pairs_with_same_spin(...):        return Violation("pauli",  "warn",   "pauli_spin")
    return None
```

Severity drives the reaction: `bounce` = Energy Rejection (the electron returns, stability drops),
`block` = the move is refused outright, `warn` = accepted but flagged in the coaching report.

### 16.4 Performance budget (hard gates for Phase 4 exit)

| Metric | Budget |
|---|---|
| Initial JS (gzip) | ≤ 300 KB |
| Total payload (first load) | ≤ 8 MB incl. audio/atlas |
| Time-to-interactive, cold, throttled Fast-3G | ≤ 3.0 s |
| Sustained FPS, period-7 board (118 electrons) | ≥ 45 fps on Celeron Chromebook |
| Validation latency per placement | ≤ 4 ms (main-thread, no perceptible lag) |
| Memory ceiling | ≤ 200 MB per tab |
| Offline replay | full, after first load |

---

## 17. Audio Design

| Cue | Feel | Trigger |
|---|---|---|
| Pickup | soft blip | electron leaves pool |
| Place | click + short rising tone | legal placement |
| Spin flip | two-pitch tick | ↑ ↔ ↓ |
| Aufbau/Hund bounce | dull thud + descending warble | rejection (never harsh) |
| Pauli block | muted clunk | capacity hit |
| Sublevel closure | rising arpeggio, length ∝ sublevel size | s short → f long and grand |
| Exception insight | gold chime, bell-like | §9.5 |
| Stability low | slow pulsing drone, ≤ 2 dB above music | stability < 25 |
| Atom decay | glass shatter + reverb tail | stability 0 |
| Stability Lock | 3s cascade, 8-note motif | element complete |
| Ambient bed | synthwave loop, ducked 6 dB under cues, per-world variation | loop |

Master mute + separate SFX/music sliders; all cues suppressed in reduced-motion mode (paired with
silent-fail risk, so keep the low-stability drone as a *visual* pulse too).

---

## 18. Content & Data Pipeline

All content tables live in [quantum/chemistry.py](file:///C:/Users/ADMIN/Documents/Quantum%20Architect/quantum/chemistry.py)
as Python data, not as separate JSON files — one file to diff, one place the game and the answer keys
both read:

| Table | Contents |
|---|---|
| `ELEMENT_NAMES` / `ELEMENT_SYMBOLS` | Z 1–118, IUPAC spellings |
| `FILL_ORDER`, `SUBLEVEL_L`, `ORBITALS`, `SUBLEVEL_MAX` | Madelung sequence, capacities, orbital counts |
| `EXCEPTIONS` | Z → the sublevels that differ from the Madelung prediction (Cr, Cu + 18 extended) |
| `EXCEPTION_REASON` | the teaching note printed on the board and in the answer key |
| `COMMON_IONS`, `ISOELECTRONIC_SETS` | element × charge, stable-partner lists |
| `NOBLE_CORES` | shorthand cores He → Rn |
| `MESSAGES` | **every rule message in one dict** — this is the table to edit when wording changes |
| `engine_shared().scoring` | points, penalties, stability deltas, star thresholds, timer formula |

Worksheets add their own tables in `quantum/worksheets.py`: `TIERS`, `TYPE_LABELS`, `PRESETS`.
`data/worksheets.json` is the saved-paper catalogue; `spectra/lines.json` (real wavelengths) is still
to come with Spectra Mode.

Verification is a script, not a human eye — `python checks/check_chemistry.py` compares generated
configurations with 36 hand-typed reference rows, sweeps invariants over all 118 elements, auto-plays
every board and asserts each illegal placement is rejected with the right message.

---

## 19. Testing & Pedagogical Validation

**Automated:** engine unit tests (§9.8), golden 118-element config test, a11y audit (axe) per screen,
keyboard-only e2e playthrough, Playwright perf trace on CPU 4× throttle.

**Playtest protocol** (Phase 5):
1. Cohort: 12–20 students of the target section, plus 2 chemistry teachers.
2. Instrument: 5-minute pre-quiz (write 3 configurations), then 20 min unassisted play, then same-shape
   post-quiz, then a 6-question exit interview.
3. Watch for, specifically: (a) does the student *verbalise the rule* after a bounce, (b) do they
   confuse 4s/3d order, (c) do they attempt to pair before sweeping, (d) do they find the drag or the
   tap fallback, (e) how long to first successful element.
4. Success bar: ≥ 70% post-quiz correct on Z ≤ 20 configurations; ≥ 80% of players can state which rule
   rejected them; 0 players stuck > 60s on W0; teacher agreement that on-screen wording is usable in a
   lecture.
5. Iterate on: timer length, hint visibility, Hund strictness in W1, message wording.

**Teacher review gates** (owner to confirm wording at each): W1 messages · W3 energy-vs-shell footnote ·
W4 exception popup · Ion Mode removal rule text · notation formats shown by default.

---

## 20. Deployment

| Target | Notes |
|---|---|
| **The Review Center** (primary) | `app.py` there imports this folder and calls `mount(app, url_prefix='/games/quantum-architect')`, so the game ships with the hub — one process, one database file, no extra service, no background timer. Two pip installs beyond Flask: **`python-docx`** and **`reportlab`** — they are already in the hub's `requirements.txt`. Nothing is configured by hand: staff identity comes from the hub's session, not from an env var. |
| **PythonAnywhere** (or any WSGI host) | deployed as part of the Review Center; upload this whole folder beside `app.py`. `QA_SECRET_KEY` and `QA_TEACHER_PIN` no longer exist — there is no login screen in this folder |
| Lab machine, offline | the standalone runner (`python app.py`, port 8050, `--lan`) needs no hub and no sign-in: with no `is_admin` hook the folder keeps every page open for the person sitting there. Worksheets stay in `data/worksheets.json` on that machine |
| Static-only mirror (GitHub Pages, itch.io) | **not possible for the whole app** — the worksheet studio and the exports need Python. Only the game board could be split out as a static build if that ever matters |
| **LMS / SCORM** | Phase 5 optional. Wrap the build in an SCORM 1.2 (or xAPI) shim; emit `completion`, `score`, `element attempted`, and **per-rule error counts** as the meaningful learner data. Budget ~1 week and accept that the shim is the least-tested part; a simpler CSV export covers most classroom needs first |

Versioning: every rule-table or wording change gets a data version stamped into the saved worksheet and
the results log, so old class data stays interpretable.

---

## 21. Analytics (in-game, aggregated)

Per element: attempts, time, score, stars, every violation keyed by rule, hints and power-ups used,
first-target chosen, drop-off point. Purpose: reveal *which rule* the cohort struggles with, and which
timer length is right. Privacy: student data stays in the Teacher Mode export, never in a public
leaderboard; no personal data leaves the device without a teacher-initiated sync.

---

## 22. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Bohr shell order vs energy order confuses students | core learning goal fails | one source of truth, shell-vs-energy footnote in Element Brief, W3 built specifically around the conflict |
| Drag-and-drop unreliable on cheap touchscreens | students blocked | tap-pool → tap-box fallback is mandatory, tested on a real low-end device |
| Exception spam (17 exceptions) overwhelms learners | frustration | only Cr + Cu before W7; rest in the Codex behind a toggle |
| Cloud model scope creep into fake 3D physics | schedule blown | cloud is a *density mirror*, decorative-but-consistent; no orbital solver |
| Timer turns a chemistry lesson into panic | teaching value lost | Practice mode, teacher "demo/no-timer" switch, star thresholds that don't require speed |
| Accessibility is retrofitted | rebuild risk | keyboard placement + ARIA grid built into the board from the first build, not added later |
| Web audio blocked until user gesture | silent first level | resume audio context on the first tap in Title screen |
| Wording churn from teacher review | rework | all copy in `strings/*.json`, zero code edits to change wording |

---

## 23. Milestones (mapped to the 5-phase roadmap)

**Phase 1 — Design & Architecture** ✅ this document +
- [ ] Owner sign-off on §24 decisions (exact on-screen wording — `MESSAGES` in `quantum/chemistry.py` is where it gets locked)
- [x] App scaffold: `app.py`, `templates/`, `static/`, `requirements.txt`, no build step
- [x] Data model: sublevels, orbital boxes, spin, `Violation`, `QuantumNumbers`, per-element engine payload for Z 1–118
- [x] Play screen built to the §14.2 mock-up

**Phase 2 — Mechanics & Engine**
- [x] Aufbau, Pauli, Hund, capacity, exceptions and ion transform in `quantum/chemistry.py`
- [x] Golden 118 test green — `python checks/check_chemistry.py`
- [x] Orbital ladder renders for Z 1–118; click, drag and keyboard placement
- [x] Ladder reads top to bottom (1s first), electron pool pinned in its own column on the right,
      Bohr model and real cloud model stacked in the readout above the live notation
- [x] Valence sublevels, their arrows, notation terms and cloud ring highlighted in red
      (`valenceSublevels` + `valenceCount` in the engine payload)
- [x] Live notation derived from the board (full, energy order, shorthand, shells, quantum numbers)
- [x] Bounce/shake/glow feedback wired to the three violation severities
- [x] Cr + Cu path, plus the 18 extended exceptions
- [x] Practice mode (untimed) stands in for W0–W3
- [ ] World map with W0–W9 gating

**Phase 3 — Gamification**
- [x] Stability meter, countdown, decay + attempt counter, recovery streak
- [x] Score, multiplier, closure/lock/Hund-sweep bonuses, star thresholds
- [x] Result modal with the per-rule coaching report
- [x] Worksheet studio: tiers, element pools, 10 question types, saved papers, DOCX + PDF export,
      teacher-only answer key
- [ ] Shorthand bracket power-up and the rest of §12 (Codex, Quanta)
- [ ] Spectra Mode MVP (hydrogen lines only)

**Phase 4 — Audio, Polish, Accessibility**
- [ ] Full FX/sound set, per-world audio identity
- [ ] Axe audit clean, keyboard-only playthrough, reduced-motion, colour-blind themes
- [ ] Chromebook performance budget met (§16.4)
- [ ] PWA offline build + local result queue

**Phase 5 — Testing & Deployment**
- [ ] Playtest round 1 → tuning → round 2 (§19)
- [ ] Teacher sign-off on wording and difficulty curve
- [ ] Vercel production + GitHub Pages mirror + offline bundle
- [ ] Teacher Mode export CSV; SCORM/xAPI wrapper as an explicit stretch item

**Definition of done for the MVP (classroom-usable):** worlds W0–W5 (Z 1–36) complete, Cr/Cu
exceptions working, Ion Mode for Na⁺/Cl⁻/Fe²⁺/Fe³⁺, both views consistent, keyboard-only path proven,
runs offline on a school Chromebook.

---

## 24. Open Decisions — owner input required

1. **Exact on-screen wording** of the five rule messages and the exception popup (I used placeholders;
   these must match how you say it in class).
2. **Grade/year target** — Grade 8 MATATAG, Grade 9/10, or review-center only? Changes W0–W5 scope
   and all copy reading level.
3. **Top of the ladder** — ship at Z = 36 (Kr), 54 (Xe), or the full 118?
4. **f-block cut** — La vs Ce as the first 4f element on screen (§7.1).
5. **Polyatomic ions** — confirm out of scope for v1.
6. **Shell distribution (`2,8,8,1`)** shown by default, or hidden behind a toggle?
7. **Quantum numbers (n, ℓ, mℓ, ms)** tooltip — v1 or later?
8. **Filipino/Bisaya localisation** now or later?
9. **Timer on by default** in classroom builds, or off and teacher-enabled?
10. **Paid currency / monetisation** — confirm none.
11. ~~**Class sync** — is there an existing MNHS app this should report into, or standalone?~~
    **Decided:** it is mounted inside the MNHS Review Center at `/games/quantum-architect` and takes
    the hub's identity and staff session. A board round is still *not* reported into `quiz_attempt`, so
    it cannot appear in **My Results** or the admin **Results Dashboard**; only the teacher's papers
    leave the app, as DOCX/PDF downloads. If lesson-log usage ever needs board plays recorded, that is
    a separate decision and a new table.

---

## Appendix A — Quick reference: capacities and energies

| Sublevel | ℓ | Orbitals | Max e⁻ | Shape in the real cloud model |
|---|---|---|---|---|
| s | 0 | 1 | 2 | sphere |
| p | 1 | 3 | 6 | dumbbell (x, y, z) |
| d | 2 | 5 | 10 | cloverleaf ×4 + dz² |
| f | 3 | 7 | 14 | multi-lobed (stylised) |

Shell ring labels: K n=1 · L n=2 · M n=3 · N n=4 · O n=5 · P n=6 · Q n=7 (max 2n² as a limit; the game
shows the *actually occupied* count, which is what makes the energy order visible).

## Appendix B — Glossary (for on-screen text and for the team)

**Aufbau principle** — electrons enter the lowest-energy sublevel available first.
**Pauli exclusion principle** — one orbital holds at most two electrons, and only with opposite spins.
**Hund's rule** — electrons occupy equal-energy orbitals singly, with parallel spins, before pairing.
**Madelung (n+ℓ) rule** — the ordering rule behind the energy ladder the board is built on.
**Stability Exception** — a real element whose ground state breaks the expected order for a lower
energy (Cr, Cu).
**Energy Rejection Bounce** — the in-game rejection animation for an illegal placement.
**Stability Lock** — the 3-second settle-and-confirm sequence at the end of an element.
**Shorthand core** — the bracketed noble-gas part of a configuration.
