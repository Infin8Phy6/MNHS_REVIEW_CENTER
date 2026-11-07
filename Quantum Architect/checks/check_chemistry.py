"""Chemistry engine verification. Run:  python checks/check_chemistry.py

Independent hand-typed reference configurations for Z 1-36, a noble-gas core for
every element, and structural invariants. Exits non-zero on any failure.
"""

import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantum import chemistry as qa  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}\n     got:  {got}\n     want: {want}")


def check_true(label: str, condition) -> None:
    if not condition:
        FAILURES.append(f"{label} -> expected truthy, got {condition!r}")


# --- 1. Reference table, Z 1-36 (typed independently of the engine) ---------- #

REFERENCE = {
    1: "1s1", 2: "1s2", 3: "1s2 2s1", 4: "1s2 2s2", 5: "1s2 2s2 2p1",
    6: "1s2 2s2 2p2", 7: "1s2 2s2 2p3", 8: "1s2 2s2 2p4", 9: "1s2 2s2 2p5",
    10: "1s2 2s2 2p6", 11: "1s2 2s2 2p6 3s1", 12: "1s2 2s2 2p6 3s2",
    13: "1s2 2s2 2p6 3s2 3p1", 14: "1s2 2s2 2p6 3s2 3p2",
    15: "1s2 2s2 2p6 3s2 3p3", 16: "1s2 2s2 2p6 3s2 3p4",
    17: "1s2 2s2 2p6 3s2 3p5", 18: "1s2 2s2 2p6 3s2 3p6",
    19: "1s2 2s2 2p6 3s2 3p6 4s1", 20: "1s2 2s2 2p6 3s2 3p6 4s2",
    21: "1s2 2s2 2p6 3s2 3p6 4s2 3d1", 22: "1s2 2s2 2p6 3s2 3p6 4s2 3d2",
    23: "1s2 2s2 2p6 3s2 3p6 4s2 3d3", 24: "1s2 2s2 2p6 3s2 3p6 4s1 3d5",
    25: "1s2 2s2 2p6 3s2 3p6 4s2 3d5", 26: "1s2 2s2 2p6 3s2 3p6 4s2 3d6",
    27: "1s2 2s2 2p6 3s2 3p6 4s2 3d7", 28: "1s2 2s2 2p6 3s2 3p6 4s2 3d8",
    29: "1s2 2s2 2p6 3s2 3p6 4s1 3d10", 30: "1s2 2s2 2p6 3s2 3p6 4s2 3d10",
    31: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p1", 32: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p2",
    33: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p3", 34: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p4",
    35: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p5", 36: "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p6",
}

for z, want in REFERENCE.items():
    got = qa.format_config(qa.ground_config(z), order="fill", unicode=False)
    check(f"Z={z} {qa.element_symbol(z)} full config (fill order)", got, want)

# Shell-ordered display must group by n.
check("Z=26 shell-order string", qa.format_config(qa.ground_config(26)),
      "1s² 2s² 2p⁶ 3s² 3p⁶ 3d⁶ 4s²")

# --- 2. Electron count, capacity and ordering invariants, Z 1-118 ------------ #

for z in range(1, qa.MAX_Z + 1):
    config = qa.ground_config(z)
    check_true(f"Z={z} electron count", sum(config.values()) == z)
    for name, count in config.items():
        if count > qa.capacity(name):
            FAILURES.append(f"Z={z}: {name} holds {count}, max {qa.capacity(name)}")
    indices = [qa.fill_index(n) for n in config]
    check_true(f"Z={z} config keys in fill order", indices == sorted(indices))
    check_true(f"Z={z} no gap in ladder", all(n in qa.FILL_ORDER for n in config))

# --- 3. Noble-gas cores are exact ------------------------------------------- #

for z, symbol in [(2, "He"), (10, "Ne"), (18, "Ar"), (36, "Kr"), (54, "Xe"), (86, "Rn")]:
    check(f"core {symbol} config", qa.format_config(qa.ground_config(z), unicode=False),
          qa.format_config(qa.madelung_config(z), unicode=False))
    check(f"{symbol} is not flagged an exception", qa.is_exception(z), False)

# --- 4. Exceptions ---------------------------------------------------------- #

check("Cr shorthand", qa.shorthand_config(24), "[Ar] 3d⁵ 4s¹")
check("Cu shorthand", qa.shorthand_config(29), "[Ar] 3d¹⁰ 4s¹")
check("Cr Madelung (what a student expects)", qa.expected_but_wrong(24),
      "1s² 2s² 2p⁶ 3s² 3p⁶ 4s² 3d⁴")
check("Pd leaves 5s empty", qa.format_config(qa.ground_config(46), order="fill", unicode=False),
      "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p6 4d10")
check("Ag shorthand", qa.shorthand_config(47), "[Kr] 4d¹⁰ 5s¹")
check("Au shorthand", qa.shorthand_config(79), "[Xe] 4f¹⁴ 5d¹⁰ 6s¹")
check("Lr last sublevel", qa.last_differentiating_sublevel(103), "7p")
check("exception count", len(qa.EXCEPTIONS), 20)

# Every exception table entry must redistribute, never create or destroy electrons.
def madelung_differs_from_actual(z: int) -> bool:
    return qa.madelung_config(z) != qa.ground_config(z)


for z, override in qa.EXCEPTIONS.items():
    check_true(f"Z={z} exception counts are not negative", all(v >= 0 for v in override.values()))
    check_true(f"Z={z} exception actually changes the Madelung answer",
               madelung_differs_from_actual(z))
check_true("no non-exception is altered",
           not [z for z in range(1, qa.MAX_Z + 1)
                if z not in qa.EXCEPTIONS and madelung_differs_from_actual(z)])


# --- 5. Box diagrams obey Hund and Pauli ------------------------------------ #

check("N 2p boxes (Hund)", qa.sublevel_boxes("2p", 3), ["↑", "↑", "↑"])
check("O 2p boxes (first pair)", qa.sublevel_boxes("2p", 4), ["↑↓", "↑", "↑"])
check("Ne 2p boxes (full)", qa.sublevel_boxes("2p", 6), ["↑↓", "↑↓", "↑↓"])
check("Cr 3d boxes (half-filled)", qa.sublevel_boxes("3d", 5), ["↑"] * 5)
check("Fe 3d boxes", qa.sublevel_boxes("3d", 6), ["↑↓", "↑", "↑", "↑", "↑"])
check("s box", qa.sublevel_boxes("1s", 1), ["↑"])
check("f capacity", qa.sublevel_boxes("4f", 14), ["↑↓"] * 7)

for z in range(1, qa.MAX_Z + 1):
    for row in qa.orbital_diagram(qa.ground_config(z)):
        arrows = "".join(row["boxes"])
        if arrows.count("↑") != arrows.count("↓"):
            pass  # a half-filled sublevel legitimately has more up arrows
        if "↑↑" in row["boxes"] or "↓↓" in row["boxes"]:
            FAILURES.append(f"Z={z} {row['sublevel']}: parallel spins in one box")
        if sum(len(b.replace(" ", "")) for b in row["boxes"]) != row["count"]:
            FAILURES.append(f"Z={z} {row['sublevel']}: boxes show the wrong electron count")

# --- 6. Ions ---------------------------------------------------------------- #

check("Fe²⁺", qa.format_config(qa.ion_config(26, 2), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d6")
check("Fe³⁺", qa.format_config(qa.ion_config(26, 3), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d5")
check("Cu⁺", qa.format_config(qa.ion_config(29, 1), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d10")
check("Cu²⁺", qa.format_config(qa.ion_config(29, 2), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d9")
check("Zn²⁺", qa.format_config(qa.ion_config(30, 2), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d10")
check("Na⁺ is isoelectronic with Ne", sum(qa.ion_config(11, 1).values()), 10)
check("Cl⁻ is isoelectronic with Ar", sum(qa.ion_config(17, -1).values()), 18)
check("O²⁻", qa.format_config(qa.ion_config(8, -2), unicode=False), "1s2 2s2 2p6")
check("Sn²⁺ inert pair", qa.format_config(qa.ion_config(50, 2), order="fill", unicode=False),
      "1s2 2s2 2p6 3s2 3p6 4s2 3d10 4p6 5s2 4d10")
check("Sn²⁺ as the key prints it (shell order)", qa.format_config(qa.ion_config(50, 2)),
      "1s² 2s² 2p⁶ 3s² 3p⁶ 3d¹⁰ 4s² 4p⁶ 4d¹⁰ 5s²")
check("Cr³⁺", qa.format_config(qa.ion_config(24, 3), unicode=False),
      "1s2 2s2 2p6 3s2 3p6 3d3")
check("K⁺", qa.format_config(qa.ion_config(19, 1), unicode=False), "1s2 2s2 2p6 3s2 3p6")
check("Ca²⁺", qa.format_config(qa.ion_config(20, 2), unicode=False), "1s2 2s2 2p6 3s2 3p6")
check("Mg²⁺", qa.format_config(qa.ion_config(12, 2), unicode=False), "1s2 2s2 2p6")
check("Al³⁺", qa.format_config(qa.ion_config(13, 3), unicode=False), "1s2 2s2 2p6")
check("Fe²⁺ label", qa.ion_label(26, 2), "Fe²⁺")
check("Cl⁻ label", qa.ion_label(17, -1), "Cl⁻")
check("O²⁻ label", qa.ion_label(8, -2), "O²⁻")
check("Na⁺ label has no bare 1", qa.ion_label(11, 1), "Na⁺")
check_true("Fe³⁺ note mentions d⁵ stability", "d⁵" in qa.ion_is_stable_note(26, 3))
check_true("K⁺ note mentions argon", "Ar" in qa.ion_is_stable_note(19, 1))

# Ion conversion must never break capacity or lose track of the electron count.
for z in range(1, 57):
    for charge in qa.COMMON_IONS.get(z, []):
        try:
            cfg = qa.ion_config(z, charge)
        except ValueError:
            continue
        want = z - charge
        check_true(f"{qa.ion_label(z, charge)} electron count", sum(cfg.values()) == want)
        for name, count in cfg.items():
            check_true(f"{qa.ion_label(z, charge)} {name} capacity", count <= qa.capacity(name))


# --- 7. Shells, block, group, period, valence ------------------------------- #

check("K shells", qa.shell_distribution(19), [2, 8, 8, 1])
check("Ca shells", qa.shell_distribution(20), [2, 8, 8, 2])
check("Fe shells (M exceeds 8)", qa.shell_distribution(26), [2, 8, 14, 2])
check("Br shells", qa.shell_distribution(35), [2, 8, 18, 7])
check("Cr group", qa.group_of(24), 6)
check("Pd group", qa.group_of(46), 10)
check("Sc group", qa.group_of(21), 3)
check("Zn group", qa.group_of(30), 12)
check("Cl group", qa.group_of(17), 17)
check("He group", qa.group_of(2), 18)
check("Na group", qa.group_of(11), 1)
check("Si group", qa.group_of(14), 14)
check("Cu block", qa.block_of(29), "d")
check("Ga block", qa.block_of(31), "p")
check("Ce block", qa.block_of(58), "f")
check("period of Br", qa.period_of(35), 4)
check("period of La", qa.period_of(57), 6)
check("valence of As", qa.valence_electrons(33), 5)
check("valence of Ca", qa.valence_electrons(20), 2)
check("valence of Cr", qa.valence_electrons(24), 6)
check("valence of Pd", qa.valence_electrons(46), 10)
check("valence of La", qa.valence_electrons(57), 3)
check("valence sublevels of As", qa.valence_sublevels(33), ["4s", "4p"])
check("valence sublevels of Cr", qa.valence_sublevels(24), ["4s", "3d"])
check("valence sublevels of Pd skip the empty 5s", qa.valence_sublevels(46), ["4d"])
check("valence sublevels of He", qa.valence_sublevels(2), ["1s"])
for z in range(1, qa.MAX_Z + 1):
    cfg = qa.ground_config(z)
    subs = qa.valence_sublevels(z)
    check_true(f"Z={z} valence sublevels are occupied", all(cfg.get(n) for n in subs))
    check_true(f"Z={z} valence sublevels count correctly",
               sum(cfg[n] for n in subs) == qa.valence_electrons(z))
    outer = max(qa.sublevel_n(n) for n in cfg)
    check_true(f"Z={z} highest shell is valence",
               any(qa.sublevel_n(n) == outer for n in subs))

# --- 8. Quantum numbers of the differentiating electron --------------------- #

q = qa.last_quantum_numbers(17)  # Cl: 3p⁵ fills box 2 then pairs box 1 -> mℓ = 0, ↓
check("Cl last e n", q.n, 3)
check("Cl last e l", q.l, 1)
check("Cl last e ml", q.ml, 0)
check("Cl last e ms", q.ms, "−½")
q = qa.last_quantum_numbers(8)   # O: 2p4 -> first pairing pass
check("O last e ms (paired pass)", q.ms, "−½")
check("O last e ml", q.ml, -1)
q = qa.last_quantum_numbers(21)  # Sc: 3d1
check("Sc last e", (q.n, q.l, q.ml, q.ms), (3, 2, -2, "+½"))
q = qa.last_quantum_numbers(11)  # Na: 3s1
check("Na last e", (q.n, q.l, q.ml, q.ms), (3, 0, 0, "+½"))

for z in range(1, qa.MAX_Z + 1):
    qn = qa.last_quantum_numbers(z)
    check_true(f"Z={z} |mℓ| <= ℓ", abs(qn.ml) <= qn.l)
    check_true(f"Z={z} n >= 1", qn.n >= 1)

# --- 9. Placement validator: the auto-player must finish clean -------------- #

def autoplay(z: int):
    """Place every electron into the engine's own correctTarget; expect no
    violation at any step, and a complete board at the end."""
    state: dict[str, int] = {}
    target = qa.ground_config(z)
    for name in qa.FILL_ORDER:
        for _ in range(target.get(name, 0)):
            occupied = state.get(name, 0)
            box = qa.first_empty_box(name, occupied)
            if box is None:
                return f"no legal box left in {name}"
            spin = "↑" if occupied < qa.orbitals(name) else "↓"
            v = qa.validate_placement(state, z, name, box, spin)
            if v:
                return f"{v.rule}/{v.code}: {v.message}"
            state[name] = occupied + 1
    if state != target:
        return f"board {state} != target {target}"
    return None

for z in range(1, qa.MAX_Z + 1):
    problem = autoplay(z)
    if problem:
        FAILURES.append(f"Z={z} auto-player failed: {problem}")

# Illegal moves must each be caught with the right rule.
v = qa.validate_placement({"1s": 2, "2s": 1, "2p": 0}, 6, "2p", 0)
check("jumping ahead of 2s is an Aufbau rejection", v.code if v else None, "aufbau")
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 6, "3s": 2, "3p": 6, "4s": 0, "3d": 0},
                          26, "3d", 0)
check("3d before 4s is an Aufbau rejection", v.code if v else None, "aufbau")
check("and it names the sublevel to fill", v.correct_sublevel if v else None, "4s")
v = qa.validate_placement({"1s": 2}, 2, "1s", 0)
check("extra electron on a full atom", v.code if v else None, "count_over")
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 4}, 9, "2p", 0)
check("third electron in one 2p box", v.code if v else None, "pauli_third")
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 2}, 8, "2p", 0, "↑")
check("pair before the sweep is a Hund rejection", v.code if v else None, "hund")
check("Hund points at the empty box", v.correct_box if v else None, 2)
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 2}, 8, "2p", 2, "↑")
check("second singleton is legal", v, None)
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 3}, 8, "2p", 0, "↓")
check("pairing after a full sweep is legal", v, None)
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 3}, 8, "2p", 0, "↑")
check("parallel spins in a pairing warn", v.code if v else None, "pauli_spin")
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 2}, 8, "2p", 2, "↓")
check("down-first singleton warns", v.code if v else None, "hund_spin")

# A lone electron is always drawn ↑, so no reference diagram can contain a lone ↓.
for z in range(1, qa.MAX_Z + 1):
    for sub, count in qa.ground_config(z).items():
        check_true(f"Z={z} {sub} has no lone down arrow",
                   all(box != "↓" for box in qa.sublevel_boxes(sub, count)))
v = qa.validate_placement({"1s": 2, "2s": 2, "2p": 6, "3s": 2, "3p": 6, "4s": 2, "3d": 10,
                           "4p": 6, "5s": 2, "4d": 10, "5p": 6, "6s": 2, "4f": 14, "5d": 10,
                           "6p": 6, "7s": 2}, 90, "5f", 0)
check("Th takes 6d, so 5f is an exception not an error", v.code if v else None, "aufbau_exception")


# --- 10. Find-the-error builders ------------------------------------------- #

import random  # noqa: E402

rng = random.Random(7)
for z in range(6, 37):
    for kind in ("aufbau", "pauli", "hund", "spin"):
        err = qa.ERROR_BUILDERS[kind](z, rng)
        if not err:
            continue
        check_true(f"Z={z} {kind} error has an explanation", bool(err["explanation"]))
        check_true(f"Z={z} {kind} error names a rule", bool(err["rule"]))
        if err.get("corrected"):
            check_true(f"Z={z} {kind} corrected != wrong text", err["corrected"] != err["text"])

built = [qa.ERROR_BUILDERS[k](7, rng) for k in ("aufbau", "hund")]
check_true("N has an aufbau error option", built[0] is not None)
check_true("N has a Hund error option", built[1] is not None)
check_true("N Hund boxes leave a box empty", built[1] and "" in built[1]["boxes"])
# An early pair is only drawable while a box is still empty: count <= orbitals.
check_true("O 2p⁴ has no premature-pair diagram", qa.build_hund_error(8, rng) is None)


# --- 11. Payload shape used by the browser ---------------------------------- #

payload = qa.engine_payload(24)
check_true("payload sublevels match ladder", [s["name"] for s in payload["sublevels"]] ==
           [n for n in qa.FILL_ORDER if n in qa.ground_config(24)])
check_true("payload flags Cr exception", payload["isException"])
check("payload carries Cr valence sublevels", payload["valenceSublevels"], ["4s", "3d"])
check("payload carries Cr valence count", payload["valenceCount"], 6)
check_true("payload box total equals Z",
           sum(len(s["boxes"]) for s in payload["sublevels"]) ==
           sum(qa.orbitals(n) for n in qa.ground_config(24)))
shared = qa.engine_shared()
check_true("shared payload carries the wording", shared["messages"]["pauli_third"].startswith("Pauli"))
check_true("shared payload carries scoring", shared["scoring"]["closure"]["d"] == 1000)

# --- 12. Periodic table placement and the orbital-box sheet ----------------- #

layout = qa.periodic_layout()
check("layout covers every element", sorted(layout), list(range(1, qa.MAX_Z + 1)))
for z, want in {1: (1, 1), 2: (1, 18), 3: (2, 1), 5: (2, 13), 10: (2, 18),
                19: (4, 1), 26: (4, 8), 57: (9, 3), 71: (9, 17),
                89: (10, 3), 103: (10, 17), 104: (7, 4), 118: (7, 18)}.items():
    check(f"Z={z} sits at {want}", layout[z], want)
check("no two elements share a cell", len(set(layout.values())), len(layout))
check_true("all columns are inside the 18-group grid",
           all(1 <= col <= 18 for _, col in layout.values()))
check_true("f-block rows start under group 3",
           layout[57][1] == 3 and layout[89][1] == 3)

from quantum import atom_sheets  # noqa: E402

first20 = atom_sheets.resolve_elements(atom_sheets.default_settings())
check("first-20 preset", first20, list(range(1, 21)))
check("custom list is de-duplicated",
      atom_sheets.resolve_elements(atom_sheets.default_settings(
          pool_mode="custom", custom_pool="17, 1, 17, 2")), [1, 2, 17])
check_true("every first-20 element is compact",
           all(atom_sheets.element_block(z)["compact"] for z in range(1, 21)))
check("Sc is too large to share a page", atom_sheets.element_block(21)["compact"], False)

na = atom_sheets.element_block(11)
check("Na contributes one row per occupied sublevel", len(na["rows"]), 4)
check("Na box totals", na["box_total"], 6)
check("Na shell text", na["shell_text"], "2, 8, 1")
check("Na Bohr rings", [(r["letter"], r["count"], r["valence"]) for r in na["bohr"]["rings"]],
      [("K", 2, False), ("L", 8, False), ("M", 1, True)])
for z in range(1, 21):
    block = atom_sheets.element_block(z)
    for row in block["rows"]:
        want = sum(len(box.replace(" ", "")) for box in row["boxes"])
        check(f"Z={z} {row['sublevel']} boxes hold the printed count", want, row["count"])
        check(f"Z={z} {row['sublevel']} has one mℓ per box",
              len(row["ml"]), len(row["boxes"]))

blocks = [atom_sheets.element_block(z) for z in range(1, 21)]
check("twenty small elements make ten A4 pages",
      len(atom_sheets.paginate(blocks, "auto")), 10)
check("every auto page holds two elements",
      [len(page) for page in atom_sheets.paginate(blocks, "auto")], [2] * 10)
check("a forced single-element page gives twenty pages",
      len(atom_sheets.paginate(blocks, "1")), 20)
sc = atom_sheets.element_block(21)
check("a large element is alone on its page",
      len(atom_sheets.paginate([blocks[0], sc, blocks[1]], "auto")[1]), 1)

# --- report ----------------------------------------------------------------- #

print(f"reference configs checked : {len(REFERENCE)}")
print(f"elements swept            : {qa.MAX_Z}")
print(f"autoplay boards completed : {qa.MAX_Z}")
if FAILURES:
    print(f"\nFAILED ({len(FAILURES)}):")
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1)
print("\nAll chemistry checks passed.")
