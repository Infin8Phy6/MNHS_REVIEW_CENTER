"""Worksheet generator: turns teacher settings into a list of exam-style items.

Every item carries a student-facing prompt and a teacher-facing answer plus a
teaching note, so one data structure feeds the preview page, the student export
and the answer-key export.
"""

from __future__ import annotations

import random
import re
import unicodedata
from datetime import datetime

from quantum import chemistry as qa

TIERS = {
    "grade8": ["shell_notation", "full_config", "identify_element", "block_group"],
    "standard": ["full_config", "shorthand", "orbital_diagram", "identify_element",
                 "shell_notation", "block_group"],
    "advanced": ["full_config", "shorthand", "orbital_diagram", "quantum_numbers",
                 "ion", "find_error", "exception_explain", "identify_element",
                 "shell_notation", "block_group"],
    "custom": None,
}

TIER_LABELS = {
    "grade8": "Grades 7-8 — shells and simple configurations (Z 1-20)",
    "standard": "Standard — full spdf, shorthand, orbital diagrams",
    "advanced": "Advanced — ions, quantum numbers, error analysis, exceptions",
    "custom": "Custom — I choose the question types",
}

TYPE_LABELS = {
    "full_config": "Full electron configuration",
    "shorthand": "Noble-gas shorthand",
    "orbital_diagram": "Orbital diagram (box form)",
    "quantum_numbers": "Quantum numbers",
    "ion": "Ion configuration",
    "find_error": "Find the error",
    "exception_explain": "Stability exception",
    "identify_element": "Identify the element",
    "shell_notation": "Shell distribution",
    "block_group": "Block, group and period",
}

PRESETS = {
    "first20": (range(1, 21), "First 20 elements (Z 1-20)"),
    "period1_3": (range(1, 19), "Periods 1-3 (Z 1-18)"),
    "period4": (range(19, 37), "Period 4 (Z 19-36)"),
    "periods1_4": (range(1, 37), "Periods 1-4 (Z 1-36)"),
    "transition": (range(21, 31), "First transition series (Z 21-30)"),
    "main_group": ([z for z in range(1, 55) if not 21 <= z <= 30], "Main-group elements (Z 1-54)"),
    "exception_prone": ([24, 29, 41, 42, 44, 45, 46, 47, 57, 58, 64, 78, 79], "Exception-prone elements"),
    "ion_formers": (sorted(qa.COMMON_IONS), "Common ion formers"),
    "noble_and_halides": ([9, 11, 17, 19, 35, 37, 53], "Halide / alkali ion pairs"),
    "full_table": (range(1, qa.MAX_Z + 1), "Whole periodic table (Z 1-118)"),
}

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII"}


def slugify(text: str) -> str:
    text = unicodedata.normalize("kd5", text) if False else text
    text = re.sub(r"[" + "'']", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "worksheet"


def ion_name(z: int, charge: int) -> str:
    """Stock notation for variable-charge metals, plain name otherwise."""
    base = qa.element_name(z)
    if charge > 0:
        fixed = qa.block_of(z) == "s" or z in (13, 31, 49, 81)
        if fixed:
            return f"the {base} ion"
        return f"{base}({ROMAN.get(charge, charge)}) ion"
    anion = {"F": "fluoride", "Cl": "chloride", "Br": "bromide", "I": "at", "S": "sulfide",
             "O": "oxide", "N": "nitride", "Se": "selenide", "P": "phosphide", "H": "hydride",
             "Te": "telluride", "As": "arsenide"}
    return f"the {anion.get(qa.element_symbol(z), base.lower() + 'ide')} ion"


def _item(z, type_key, prompt, answer, *, note="", lines=None, diagram=None,
          error=None, marks=2, workspace=2, answer_shorthand=None):
    return {
        "z": z,
        "type": type_key,
        "type_label": TYPE_LABELS[type_key],
        "prompt": prompt,
        "answer": answer,
        "answer_lines": lines or [],
        "answer_shorthand": answer_shorthand,
        "diagram": diagram,
        "error": error,
        "note": note,
        "marks": marks,
        "workspace": workspace,
    }


# --------------------------------------------------------------------------- #
# Item builders. Each returns None when the combination makes no sense, so the
# generator can quietly skip impossible pairings.
# --------------------------------------------------------------------------- #

def build_full_config(z, s, rng):
    config = qa.ground_config(z)
    answer = qa.format_config(config, order=s["notation_order"])
    prompt = f"Write the full electron configuration of {qa.element_label(z)}."
    note = ""
    if qa.is_exception(z):
        note = f"Watch for this one: Aufbau predicts {qa.expected_but_wrong(z)}. {qa.EXCEPTION_REASON.get(z, '')}"
    return _item(z, "full_config", prompt, answer, note=note,
                 answer_shorthand=qa.shorthand_config(z, s["notation_order"]),
                 marks=s["marks"], workspace=2)


def build_shorthand(z, s, rng):
    core = qa.noble_core_of(z)
    if core is None or z - core[1] < 3:
        return None
    answer = qa.shorthand_config(z, s["notation_order"])
    prompt = (f"Write the noble-gas (shorthand) electron configuration of "
              f"{qa.element_label(z)}.")
    return _item(z, "shorthand", prompt, answer, marks=s["marks"], workspace=1,
                 note=f"Full form: {qa.format_config(qa.ground_config(z), order=s['notation_order'])}. "
                      f"Core is {core[0]} (Z = {core[1]}).")


def build_orbital_diagram(z, s, rng):
    config = qa.ground_config(z)
    if s["diagram_scope"] == "valence":
        n = qa.period_of(z)
        keep = [name for name in config
                if (qa.sublevel_n(name) == n or qa.sublevel_type(name) == "d"
                    and qa.sublevel_n(name) == n - 1)]
        config = {k: config[k] for k in qa.FILL_ORDER if k in keep}
        head = f"the valence electrons of {qa.element_label(z)}"
    else:
        head = f"{qa.element_label(z)}"
    rows = qa.orbital_diagram(config, order=s["notation_order"])
    answer = qa.diagram_to_text(rows)
    prompt = f"Draw the orbital diagram (boxes with ↑ and ↓ arrows) for {head}."
    return _item(z, "orbital_diagram", prompt, answer, diagram=rows, marks=s["marks"] + 1,
                 workspace=1,
                 note="Hund's rule: single occupancy across the degenerate boxes before any pair. "
                      "Pauli: a pair is always ↑↓.")


def build_quantum_numbers(z, s, rng):
    q = qa.last_quantum_numbers(z)
    name = qa.last_differentiating_sublevel(z)
    prompt = (f"Give the four quantum numbers (n, ℓ, mℓ, mₛ) of the last "
              f"(differentiating) electron of {qa.element_label(z)}.")
    answer = q.label()
    return _item(z, "quantum_numbers", prompt, answer, marks=s["marks"], workspace=1,
                 note=f"Last electron enters {name}. {q.convention}")


def build_ion(z, s, rng):
    charges = qa.COMMON_IONS.get(z)
    if not charges:
        return None
    charge = rng.choice(charges)
    try:
        config = qa.ion_config(z, charge)
    except ValueError:
        return None
    label = qa.ion_label(z, charge)
    name = ion_name(z, charge)
    answer = qa.format_config(config, order=s["notation_order"])
    prompt = f"Write the electron configuration of {name}, {label} (Z = {z})."
    note = qa.ion_formation_text(z, charge)
    stable = qa.ion_is_stable_note(z, charge)
    if stable:
        note = f"{note} {stable}"
    return _item(z, "ion", prompt, answer, marks=s["marks"] + 1, workspace=2, note=note,
                 answer_shorthand=_shorthand_of_config(config, z))


def _shorthand_of_config(config, z):
    core = qa.noble_core_of(z)
    if not core or core[1] > sum(config.values()):
        return None
    core_config = qa.madelung_config(core[1])
    rest = {k: v for k, v in config.items() if core_config.get(k, 0) != v}
    if not rest:
        return f"[{core[0]}]"
    return f"[{core[0]}] {qa.format_config(rest)}"


def build_find_error(z, s, rng):
    kinds = list(s["error_kinds"]) if s.get("error_kinds") else ["aufbau", "pauli", "hund", "spin"]
    err = qa.build_random_error(z, kinds, rng)
    if not err:
        return None
    if err.get("text"):
        shown = err["text"]
        prompt = (f"The following configuration of {qa.element_label(z)} breaks exactly one rule. "
                  f"Name the rule and say what is wrong:\n{shown}")
        answer = f"{err['rule']}."
        lines = [f"What is wrong: {err['explanation']}", f"Corrected: {err['corrected']}"]
    else:
        prompt = (f"The orbital diagram below for the {err['diagram_sublevel']} sublevel of "
                  f"{qa.element_label(z)} breaks exactly one rule. Name the rule and say what is "
                  f"wrong:\n{err['diagram_sublevel']}  " +
                  " ".join(f"[{b.center(2)}]" for b in err["boxes"]))
        answer = f"{err['rule']}."
        lines = [f"What is wrong: {err['explanation']}",
                 "Corrected: " + " ".join(f"[{b.center(2)}]" for b in err["corrected_boxes"])]
    return _item(z, "find_error", prompt, answer, lines=lines, marks=s["marks"] + 1,
                 workspace=2, error=err,
                 note="Accept the rule name only if the student also states the specific fault.")


def build_exception_explain(z, s, rng):
    if not qa.is_exception(z):
        return None
    actual = qa.format_config(qa.ground_config(z), order=s["notation_order"])
    expected = qa.expected_but_wrong(z)
    prompt = (f"{qa.element_name(z)} is usually predicted as {expected}, but its ground state is "
              f"{actual}. Explain the reason for this deviation.")
    answer = qa.EXCEPTION_REASON.get(z, "")
    return _item(z, "exception_explain", prompt, answer, marks=s["marks"] + 2, workspace=3,
                 note="Award full marks only for the half-filled / fully-filled sublevel argument.")


def build_identify_element(z, s, rng):
    config = qa.ground_config(z)
    text = qa.format_config(config, order=s["notation_order"])
    prompt = f"Identify the element described by this configuration: {text}\nGive its symbol, name and atomic number."
    answer = f"{qa.element_symbol(z)}, {qa.element_name(z)}, Z = {z}"
    return _item(z, "identify_element", prompt, answer, marks=s["marks"], workspace=1,
                 note=f"Shorthand: {qa.shorthand_config(z, s['notation_order'])}. "
                      f"Shells: {qa.shell_text(z)}.")


def build_shell_notation(z, s, rng):
    prompt = f"Write the shell (Bohr) distribution, in K, L, M … order, for {qa.element_label(z)}."
    answer = qa.shell_text(z)
    note = ""
    if qa.block_of(z) == "d" and max(qa.shell_distribution(z)) > 8:
        note = ("The M shell passes 8 here because 3d electrons still belong to n = 3. "
                "Students who learned the 2-8-8 rule will get this wrong — good discussion item.")
    return _item(z, "shell_notation", prompt, answer, note=note, marks=max(1, s["marks"] - 1),
                 workspace=1)


def build_block_group(z, s, rng):
    prompt = (f"From the electron configuration alone, state the block, the group and the period of "
              f"{qa.element_label(z)}.")
    group = qa.group_of(z)
    series = qa.series_of(z)
    answer = (f"{qa.block_of(z)}-block, group {group if group else '—'}, period {qa.period_of(z)}"
              + (f", {series}" if series else ""))
    return _item(z, "block_group", prompt, answer, marks=max(1, s["marks"] - 1), workspace=1,
                 note=f"Configuration: {qa.shorthand_config(z, s['notation_order'])}. "
                      f"Valence electrons: {qa.valence_electrons(z)}.")


BUILDERS = {
    "full_config": build_full_config,
    "shorthand": build_shorthand,
    "orbital_diagram": build_orbital_diagram,
    "quantum_numbers": build_quantum_numbers,
    "ion": build_ion,
    "find_error": build_find_error,
    "exception_explain": build_exception_explain,
    "identify_element": build_identify_element,
    "shell_notation": build_shell_notation,
    "block_group": build_block_group,
}


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def resolve_pool(settings: dict) -> list[int]:
    mode = settings.get("pool_mode", "preset")
    if mode == "custom":
        raw = settings.get("custom_pool", "")
        numbers = [int(x) for x in re.findall(r"\d+", str(raw))]
        pool = [z for z in numbers if 1 <= z <= qa.MAX_Z]
    elif mode == "range":
        lo = max(1, int(settings.get("z_min", 1)))
        hi = min(qa.MAX_Z, int(settings.get("z_max", 20)))
        pool = list(range(lo, hi + 1))
    else:
        pool = list(PRESETS.get(settings.get("preset", "periods1_4"), PRESETS["periods1_4"])[0])
    if settings.get("avoid_heavy", True):
        pool = [z for z in pool if z <= 54 or len(pool) < 6]
    return pool or list(range(1, 21))


def resolve_types(settings: dict) -> list[str]:
    tier = settings.get("tier", "standard")
    allowed = TIERS[tier] if TIERS.get(tier) else list(TYPE_LABELS)
    chosen = settings.get("types") or []
    types = [t for t in chosen if t in TYPE_LABELS and (allowed is None or t in allowed)]
    return types or (allowed or ["full_config"])[:4]


def default_settings(**overrides) -> dict:
    settings = {
        "title": "Electron Configuration Practice",
        "class_name": "",
        "section": "",
        "teacher": "",
        "date": datetime.now().strftime("%B %d, %Y"),
        "tier": "standard",
        "pool_mode": "preset",
        "preset": "periods1_4",
        "z_min": 1,
        "z_max": 20,
        "custom_pool": "",
        "types": [],
        "item_count": 12,
        "marks": 5,
        "notation_order": "shell",
        "diagram_scope": "full",
        "error_kinds": ["aufbau", "pauli", "hund", "spin"],
        "allow_shorthand": True,
        "show_element_names": True,
        "shuffle": True,
        "no_repeat": True,
        "seed": random.randint(100000, 999999),
        "avoid_heavy": True,
        "instructions": ("Answer each item in the space provided. Use the notation "
                         "discussed in class. Show your work for any orbital diagram."),
    }
    settings.update(overrides)
    return settings


def generate(settings: dict) -> dict:
    """Build a worksheet from settings. Deterministic for a given seed."""
    settings = default_settings(**settings)
    rng = random.Random(settings["seed"])
    pool = resolve_pool(settings)
    types = resolve_types(settings)

    if settings["tier"] == "grade8":
        pool = [z for z in pool if z <= 20] or [z for z in pool if z <= 36] or pool

    wanted = int(settings["item_count"])
    items: list[dict] = []
    seen: set[tuple[int, str]] = set()
    working_pool = list(pool)
    rng.shuffle(working_pool)

    # Prefer coverage: walk the pool type-by-type before repeating anything.
    attempts = 0
    max_attempts = wanted * 12 + 200
    while len(items) < wanted and attempts < max_attempts:
        attempts += 1
        if not working_pool:
            working_pool = list(pool)
            rng.shuffle(working_pool)
            if settings["no_repeat"]:
                types = types[1:] + types[:1]
                if not types:
                    break
        z = working_pool.pop(rng.randrange(len(working_pool)) if len(working_pool) > 1 else 0)
        type_key = types[len(items) % len(types)]
        if settings["no_repeat"] and (z, type_key) in seen:
            continue
        builder = BUILDERS[type_key]
        item = builder(z, settings, rng)
        if item is None:
            working_pool.append(z)
            continue
        seen.add((z, type_key))
        items.append(item)

    if not settings["shuffle"]:
        items.sort(key=lambda it: (it["z"], it["type"]))
    for number, item in enumerate(items, start=1):
        item["number"] = number
    # Every item is worth the same five points, whatever the type mix.
    for item in items:
        item["marks"] = 5

    total_marks = sum(item["marks"] for item in items)
    slug = slugify(settings["title"])
    return {
        "settings": settings,
        "items": items,
        "total_marks": total_marks,
        "slug": slug,
        "type_summary": {t: sum(1 for i in items if i["type"] == t) for t in types},
        "element_count": len({i["z"] for i in items}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
