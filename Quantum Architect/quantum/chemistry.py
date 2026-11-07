"""Electron-configuration engine for Quantum Architect.

Pure Python, no framework, no I/O. Both the worksheet generator and the browser
board trust these numbers, so keep this module the single source of truth.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Fill order (Madelung / n+l rule; ties broken by lower n first)
# --------------------------------------------------------------------------- #

FILL_ORDER = [
    "1s", "2s", "2p", "3s", "3p", "4s", "3d", "4p", "5s", "4d", "5p", "6s",
    "4f", "5d", "6p", "7s", "5f", "6d", "7p",
]

# Sublevel -> (magnetic quantum numbers of the orbitals, max electrons)
SUBLEVEL_L = {"s": 0, "p": 1, "d": 2, "f": 3}
ORBITALS = {"s": 1, "p": 3, "d": 5, "f": 7}
SUBLEVEL_MAX = {t: 2 * ORBITALS[t] for t in ORBITALS}

NOBLE_CORES = [(2, "He"), (10, "Ne"), (18, "Ar"), (36, "Kr"), (54, "Xe"), (86, "Rn")]

# --------------------------------------------------------------------------- #
# Element table: Z 1-118
# --------------------------------------------------------------------------- #

ELEMENT_NAMES = [
    "Hydrogen", "Helium", "Lithium", "Beryllium", "Boron", "Carbon", "Nitrogen",
    "Oxygen", "Fluorine", "Neon", "Sodium", "Magnesium", "Aluminium", "Silicon",
    "Phosphorus", "Sulfur", "Chlorine", "Argon", "Potassium", "Calcium",
    "Scandium", "Titanium", "Vanadium", "Chromium", "Manganese", "Iron",
    "Cobalt", "Nickel", "Copper", "Zinc", "Gallium", "Germanium", "Arsenic",
    "Selenium", "Bromine", "Krypton", "Rubidium", "Strontium", "Yttrium",
    "Zirconium", "Niobium", "Molybdenum", "Technetium", "Ruthenium", "Rhodium",
    "Palladium", "Silver", "Cadmium", "Indium", "Tin", "Antimony", "Tellurium",
    "Iodine", "Xenon", "Caesium", "Barium", "Lanthanum", "Cerium",
    "Praseodymium", "Neodymium", "Promethium", "Samarium", "Europium",
    "Gadolinium", "Terbium", "Dysprosium", "Holmium", "Erbium", "Thulium",
    "Ytterbium", "Lutetium", "Hafnium", "Tantalum", "Tungsten", "Rhenium",
    "Osmium", "Iridium", "Platinum", "Gold", "Mercury", "Thallium", "Lead",
    "Bismuth", "Polonium", "Astatine", "Radon", "Francium", "Radium",
    "Actinium", "Thorium", "Protactinium", "Uranium", "Neptunium", "Plutonium",
    "Americium", "Curium", "Berkelium", "Californium", "Einsteinium",
    "Fermium", "Mendelevium", "Nobelium", "Lawrencium", "Rutherfordium",
    "Dubnium", "Seaborgium", "Bohrium", "Hassium", "Meitnerium", "Darmstadtium",
    "Roentgenium", "Copernicium", "Nihonium", "Flerovium", "Moscovium",
    "Livermorium", "Tennessine", "Oganesson",
]

ELEMENT_SYMBOLS = [
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si",
    "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co",
    "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I",
    "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy",
    "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au",
    "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U",
    "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db",
    "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
]

MAX_Z = 118

# --------------------------------------------------------------------------- #
# Ground-state exceptions. Keys override the Madelung result for that sublevel.
# Source: NIST Atomic Spectra Database ground configurations.
# --------------------------------------------------------------------------- #

EXCEPTIONS: dict[int, dict[str, int]] = {
    24: {"3d": 5, "4s": 1},      # Cr  half-filled d
    29: {"3d": 10, "4s": 1},     # Cu  filled d
    41: {"4d": 4, "5s": 1},      # Nb
    42: {"4d": 5, "5s": 1},      # Mo
    44: {"4d": 7, "5s": 1},      # Ru
    45: {"4d": 8, "5s": 1},      # Rh
    46: {"4d": 10, "5s": 0},     # Pd  empty 5s
    47: {"4d": 10, "5s": 1},     # Ag
    57: {"4f": 0, "5d": 1},      # La
    58: {"4f": 1, "5d": 1},      # Ce
    64: {"4f": 7, "5d": 1},      # Gd
    78: {"5d": 9, "6s": 1},      # Pt
    79: {"5d": 10, "6s": 1},     # Au
    89: {"5f": 0, "6d": 1},      # Ac
    90: {"5f": 0, "6d": 2},      # Th
    91: {"5f": 2, "6d": 1},      # Pa
    92: {"5f": 3, "6d": 1},      # U
    93: {"5f": 4, "6d": 1},      # Np
    96: {"5f": 7, "6d": 1},      # Cm
    103: {"6d": 0, "7p": 1},     # Lr
}

# Elements worth teaching as exceptions, by world in the GDD.
CLASSROOM_EXCEPTIONS = [24, 29]
EXTENDED_EXCEPTIONS = [41, 42, 44, 45, 46, 47, 57, 58, 64, 78, 79, 89, 90, 91, 92, 93, 96, 103]

EXCEPTION_REASON = {
    24: "A half-filled 3d⁵ sublevel gains exchange energy, so one 4s electron moves up: [Ar] 3d⁵ 4s¹.",
    29: "A filled 3d¹⁰ sublevel is lower in energy than 3d⁹ 4s², so 4s gives up one electron: [Ar] 3d¹⁰ 4s¹.",
    41: "4d⁴ 5s¹ is lower than 4d³ 5s².",
    42: "Half-filled 4d⁵ with a single 5s electron.",
    44: "4d⁷ 5s¹ is lower than 4d⁶ 5s².",
    45: "4d⁸ 5s¹ is lower than 4d⁷ 5s².",
    46: "A filled 4d¹⁰ leaves 5s empty entirely.",
    47: "Filled 4d¹⁰ with a single 5s electron.",
    57: "The first electron after xenon enters 5d, not 4f.",
    58: "One electron sits in 4f and one in 5d.",
    64: "Half-filled 4f⁷ plus one 5d electron.",
    78: "5d⁹ 6s¹ is lower than 5d⁸ 6s².",
    79: "Filled 5d¹⁰ with a single 6s electron — the classic gold exception.",
    89: "The first electron after radon enters 6d, not 5f.",
    90: "Thorium puts two electrons in 6d and none in 5f.",
    91: "5f² 6d¹ rather than 5f³.",
    92: "5f³ 6d¹ rather than 5f⁴.",
    93: "5f⁴ 6d¹ rather than 5f⁵.",
    96: "Half-filled 5f⁷ plus one 6d electron.",
    103: "The last electron enters 7p, completing [Rn] 5f¹⁴ 7s² 7p¹.",
}

# Well-known ions used by the worksheet generator.
COMMON_IONS = {
    1: [-1], 3: [1], 4: [2], 5: [3], 6: [-4], 7: [-3], 8: [-2], 9: [-1],
    11: [1], 12: [2], 13: [3], 14: [-4], 15: [-3], 16: [-2], 17: [-1],
    19: [1], 20: [2], 21: [3], 22: [4], 23: [5, 2], 24: [3, 6], 25: [2, 4],
    26: [2, 3], 27: [2, 3], 28: [2], 29: [1, 2], 30: [2], 31: [3], 32: [4, -4],
    33: [-3], 34: [-2], 35: [-1], 37: [1], 38: [2], 47: [1], 48: [2],
    49: [3], 50: [2, 4], 51: [3, 5], 52: [-2], 53: [-1], 55: [1], 56: [2],
    80: [1, 2], 81: [1, 3], 82: [2, 4], 83: [3, 5],
}

ISOELECTRONIC_SETS = [
    ([8, 9, 10, 11, 12, 13], "1s² 2s² 2p⁶"),
    ([16, 17, 18, 19, 20], "1s² 2s² 2p⁶ 3s² 3p⁶"),
]

SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def sup(n: int) -> str:
    """10 -> '¹⁰'"""
    return str(n).translate(SUPERSCRIPT)


def sublevel_type(name: str) -> str:
    return name[-1]


def sublevel_n(name: str) -> int:
    return int(name[0])


def capacity(name: str) -> int:
    return SUBLEVEL_MAX[sublevel_type(name)]


def orbitals(name: str) -> int:
    return ORBITALS[sublevel_type(name)]


def fill_index(name: str) -> int:
    return FILL_ORDER.index(name)


def element_symbol(z: int) -> str:
    return ELEMENT_SYMBOLS[z - 1]


def element_name(z: int) -> str:
    return ELEMENT_NAMES[z - 1]


def element_label(z: int) -> str:
    return f"{element_name(z)}, {element_symbol(z)} (Z = {z})"


def parse_config(text: str) -> dict[str, int]:
    """'1s2 2s2 2p6' or '1s² 2s² 2p⁶' or '[Ar] 4s1' -> {sublevel: count}."""
    core_match = re.match(r"^\[([A-Za-z]{1,2})\]\s*", text)
    config: dict[str, int] = {}
    body = text
    if core_match:
        core = core_match.group(1)
        z = ELEMENT_SYMBOLS.index(core) + 1
        config.update(ground_config(z))
        body = text[core_match.end():]
    body = body.translate({ord(c): None for c in SUPERSCRIPT})
    for token in body.replace(",", " ").split():
        m = re.match(r"^(\d)([spdf])(\d*)$", token)
        if not m:
            raise ValueError(f"cannot parse configuration token {token!r}")
        name = f"{m.group(1)}{m.group(2)}"
        config[name] = config.get(name, 0) + (int(m.group(3)) if m.group(3) else 0)
    return {k: v for k, v in config.items() if v}


# --------------------------------------------------------------------------- #
# Core build
# --------------------------------------------------------------------------- #

def madelung_config(z: int) -> dict[str, int]:
    """Textbook Aufbau result with no exceptions applied."""
    config: dict[str, int] = {}
    left = z
    for name in FILL_ORDER:
        if left <= 0:
            break
        take = min(left, capacity(name))
        if take:
            config[name] = take
        left -= take
    return config


def ground_config(z: int) -> dict[str, int]:
    """Exception-corrected ground-state configuration, kept in fill order."""
    config = madelung_config(z)
    for name, count in EXCEPTIONS.get(z, {}).items():
        if count:
            config[name] = count
        else:
            config.pop(name, None)
    return {name: config[name] for name in FILL_ORDER if name in config}


def is_exception(z: int) -> bool:
    return z in EXCEPTIONS


def expected_but_wrong(z: int) -> str:
    """The Aufbau sequence a student would write before learning the exception,
    shown in filling (energy) order."""
    return format_config(madelung_config(z), order="fill")


def sort_by_shell(config: dict[str, int]) -> dict[str, int]:
    return dict(sorted(config.items(), key=lambda kv: (sublevel_n(kv[0]), SUBLEVEL_L[sublevel_type(kv[0])])))


def format_config(config: dict[str, int], order: str = "shell", unicode: bool = True) -> str:
    """order: 'shell' (grouped by n, what teachers mark) or 'fill' (energy order)."""
    items = sort_by_shell(config) if order == "shell" else {k: config[k] for k in FILL_ORDER if k in config}
    out = []
    for name, count in items.items():
        out.append(name + (sup(count) if unicode else str(count)))
    return " ".join(out)


def shorthand_config(z: int, order: str = "shell", unicode: bool = True) -> str:
    """Noble-gas bracket form. Falls back to the full configuration for light
    elements, where a bracket would hide more than it saves."""
    full = ground_config(z)
    core = noble_core_of(z)
    if core is None or z - core[1] < 3:
        return format_config(full, order, unicode)
    core_config = madelung_config(core[1])
    rest = {k: v for k, v in full.items() if core_config.get(k, 0) != v}
    return f"[{core[0]}] {format_config(rest, order, unicode)}".strip()


def noble_core_of(z: int) -> tuple[str, int] | None:
    core = None
    for cn, cs in NOBLE_CORES:
        if cn < z:
            core = (cs, cn)
    return core


# --------------------------------------------------------------------------- #
# Orbital box diagrams (Hund + Pauli applied by construction)
# --------------------------------------------------------------------------- #

def sublevel_boxes(name: str, count: int) -> list[str]:
    """Boxes for one sublevel as arrow strings: '', '↑', '↑↓', '↓'.

    Hund: one electron per orbital, parallel spin, before any pairing.
    Pauli: a pair is always ↑↓, and a lone electron is always ↑, never ↓.
    """
    m = orbitals(name)
    boxes = [""] * m
    if count > 2 * m:
        raise ValueError(f"{name} cannot hold {count} electrons (max {2 * m}) — Pauli violation")
    for i in range(min(count, m)):
        boxes[i] = "↑"
    for i in range(m, count):
        boxes[i - m] = "↑↓"
    return boxes


def orbital_diagram(config: dict[str, int], order: str = "fill") -> list[dict]:
    items = config if order == "fill" else sort_by_shell(config)
    rows = []
    for name, count in items.items():
        rows.append({
            "sublevel": name,
            "count": count,
            "capacity": capacity(name),
            "type": sublevel_type(name),
            "boxes": sublevel_boxes(name, count),
        })
    return rows


def diagram_to_text(rows: list[dict], sep: str = "  ") -> str:
    parts = []
    for row in rows:
        cells = " ".join(f"[{box.center(2)}]" for box in row["boxes"])
        parts.append(f"{row['sublevel']:>3} {cells}")
    return sep.join(parts)


def diagram_with_error(name: str, count: int, error: str) -> list[str]:
    """Boxes for an intentionally WRONG diagram, used by find-the-error items."""
    m = orbitals(name)
    boxes = [""] * m
    if error == "hund_early_pair":
        if count < 2 or m < 2:
            raise ValueError("cannot build a Hund error here")
        boxes[0] = "↑↓"
        for i in range(1, count - 1):
            boxes[i] = "↑"
        return boxes
    if error == "pauli_same_spin":
        if count < 2:
            raise ValueError("cannot build a spin error here")
        boxes[0] = "↑↑"
        for i in range(1, count - 1):
            boxes[min(i, m - 1)] = "↑" if boxes[min(i, m - 1)] == "" else "↑↑"
        return boxes
    raise ValueError(error)


# --------------------------------------------------------------------------- #
# Shells, block, group, period
# --------------------------------------------------------------------------- #

def shell_distribution(z: int) -> list[int]:
    """Electrons per principal shell n (K, L, M, ...). This is the real count:
    a transition metal's M shell goes past 8 because 3d belongs to n = 3."""
    totals: dict[int, int] = {}
    for name, count in ground_config(z).items():
        n = sublevel_n(name)
        totals[n] = totals.get(n, 0) + count
    return [totals[n] for n in sorted(totals)]


def shell_text(z: int) -> str:
    return ", ".join(str(x) for x in shell_distribution(z))


def period_of(z: int) -> int:
    for p, hi in [(1, 2), (2, 10), (3, 18), (4, 36), (5, 54), (6, 86), (7, MAX_Z)]:
        if z <= hi:
            return p
    raise ValueError(z)


def block_of(z: int) -> str:
    """Block by series, not just by the last sublevel written — Ce's last written
    sublevel is 5d but it belongs to the f-block."""
    if z == 2:
        return "s"
    if 58 <= z <= 71 or 90 <= z <= 103:
        return "f"
    return sublevel_type(last_differentiating_sublevel(z))


def group_of(z: int) -> int | None:
    """Derived from the exception-corrected configuration, so Cr lands in 6 and
    Pd (5s⁰ 4d¹⁰) lands in 10."""
    config = ground_config(z)
    if z == 2:
        return 18
    block = block_of(z)
    if block == "f":
        return None
    if block == "s":
        n = period_of(z)
        return config.get(f"{n}s", 1)
    if block == "p":
        n = period_of(z)
        return 12 + config.get(f"{n}p", 0)
    n = period_of(z)
    return config.get(f"{n}s", 0) + config.get(f"{n - 1}d", 0)


def series_of(z: int) -> str:
    if 58 <= z <= 71:
        return "lanthanide series"
    if 90 <= z <= 103:
        return "actinide series"
    if 21 <= z <= 30 or 39 <= z <= 48 or 72 <= z <= 80 or 104 <= z <= 112:
        return "transition metal"
    return ""


# The desktop periodic table is an 18-column grid. Periods occupy rows 1-7;
# the two f-block series are pulled out into rows 9 and 10, with row 8 left
# blank as the usual gap. Columns are groups 1-18, and both f-block rows start
# under group 3 (La/Ac).
PERIODIC_F_ROWS = ((57, 71, 9), (89, 103, 10))
PERIODIC_COLUMNS = 18


def periodic_layout() -> dict[int, tuple[int, int]]:
    """(row, column) for every element in the 18-column table."""
    positions: dict[int, tuple[int, int]] = {}
    for z in range(1, MAX_Z + 1):
        row = None
        for first, last, f_row in PERIODIC_F_ROWS:
            if first <= z <= last:
                row = (f_row, 3 + z - first)
                break
        if row is None:
            group = group_of(z)
            row = (period_of(z), group if group else 3)
        positions[z] = row
    return positions


def last_differentiating_sublevel(z: int) -> str:
    """The sublevel receiving the final electron in energy order."""
    config = ground_config(z)
    for name in reversed(FILL_ORDER):
        if config.get(name):
            return name
    raise ValueError(z)


def valence_sublevels(z: int) -> list[str]:
    """The sublevels that hold the valence electrons, in fill order. Same rule as
    valence_electrons(), so the board can highlight them and the counts agree."""
    config = ground_config(z)
    n = period_of(z)
    block = block_of(z)
    if block == "s":
        names = [f"{n}s"]
    elif block == "p":
        names = [f"{n}s", f"{n}p"]
    elif block == "d":
        names = [f"{n}s", f"{n - 1}d"]
    else:
        names = [f"{n}s", f"{n - 1}d", f"{n - 2}f"]
    return [name for name in FILL_ORDER if name in names and config.get(name)]


def valence_electrons(z: int) -> int:
    return sum(ground_config(z).get(name, 0) for name in valence_sublevels(z))


# --------------------------------------------------------------------------- #
# Quantum numbers of the differentiating electron
# --------------------------------------------------------------------------- #

@dataclass
class QuantumNumbers:
    n: int
    l: int
    ml: int
    ms: str
    sublevel: str
    box_index: int
    convention: str = (
        "Boxes are numbered left to right as mℓ = −ℓ … +ℓ; the first pass puts in ↑, "
        "the second pass pairs with ↓. The left-to-right choice is a convention — any "
        "order of the degenerate boxes is acceptable."
    )

    def label(self) -> str:
        return f"n = {self.n}, ℓ = {self.l}, mℓ = {self.ml:+d}, mₛ = {self.ms}"


L_LABEL = {0: "s", 1: "p", 2: "d", 3: "f"}


def last_quantum_numbers(z: int) -> QuantumNumbers:
    name = last_differentiating_sublevel(z)
    config = ground_config(z)
    n = sublevel_n(name)
    l = SUBLEVEL_L[sublevel_type(name)]
    m = ORBITALS[sublevel_type(name)]
    count = config[name]
    index = (count - 1) % m
    pairing = count > m
    return QuantumNumbers(n=n, l=l, ml=-l + index, ms="−½" if pairing else "+½",
                          sublevel=name, box_index=index)


# --------------------------------------------------------------------------- #
# Ions
# --------------------------------------------------------------------------- #

def ion_config(z: int, charge: int) -> dict[str, int]:
    """charge > 0 removes electrons (cation), charge < 0 adds them (anion)."""
    config = dict(ground_config(z))
    if charge > 0:
        electrons = sum(config.values())
        if charge >= electrons:
            raise ValueError(f"cannot remove {charge} electrons from a {electrons}-electron atom")
        # Highest principal shell first; within a shell, highest ℓ first.
        order = sorted(config, key=lambda k: (sublevel_n(k), SUBLEVEL_L[sublevel_type(k)]), reverse=True)
        left = charge
        for name in order:
            while left and config[name]:
                config[name] -= 1
                left -= 1
            if not left:
                break
        return {k: v for k, v in config.items() if v}
    if charge < 0:
        left = -charge
        target = None
        for name in FILL_ORDER:
            have = config.get(name, 0)
            if have < capacity(name):
                target = name
                break
        if target is None:
            raise ValueError("no room left in the sublevel ladder")
        config[target] = config.get(target, 0) + left
        if config[target] > capacity(target):
            raise ValueError(f"adding {left} electrons overfills {target}")
        return {k: config[k] for k in FILL_ORDER if config.get(k)}
    return config


def ion_label(z: int, charge: int, unicode: bool = True) -> str:
    if charge > 0:
        magnitude = "" if charge == 1 else (sup(charge) if unicode else str(charge))
        sign = "⁺" if unicode else "+"
    else:
        magnitude = "" if charge == -1 else (sup(-charge) if unicode else str(-charge))
        sign = "⁻" if unicode else "-"
    return f"{element_symbol(z)}{magnitude}{sign}"


def ion_formation_text(z: int, charge: int) -> str:
    config = ground_config(z)
    name = ion_label(z, charge)
    neutral = format_config(config, order="shell")
    after = format_config(ion_config(z, charge), order="shell")
    if charge > 0:
        removed = []
        remaining = charge
        order = sorted(config, key=lambda k: (sublevel_n(k), SUBLEVEL_L[sublevel_type(k)]), reverse=True)
        for sub in order:
            take = min(remaining, config[sub])
            if take:
                removed.append(f"{take} from {sub}")
            remaining -= take
            if not remaining:
                break
        note = f"Lost {' + '.join(removed)}. Electrons leave the highest shell (largest n) first, so {period_of(z)}s empties before {period_of(z) - 1}d."
    else:
        target = None
        for sub in FILL_ORDER:
            if config.get(sub, 0) < capacity(sub):
                target = sub
                break
        note = f"Gained {-charge} into {target}. The anion reaches the next noble-gas configuration."
    return (
        f"{ion_label(z, charge)}: neutral {element_name(z)} is {neutral}. {note} "
        f"Ion configuration: {after}."
    )


def ion_is_stable_note(z: int, charge: int) -> str:
    cfg = ion_config(z, charge)
    d = cfg.get(f"{period_of(z) - 1}d", 0)
    core = noble_core_of(z)
    full_core = core and sum(cfg.values()) == core[1]
    if block_of(z) == "d" and d in (5, 10) and charge > 0:
        return "Half-filled (d⁵) or filled (d¹⁰) d sublevel — extra stability."
    if full_core:
        return f"Isoelectronic with {core[0]} — a noble-gas configuration."
    return ""


# --------------------------------------------------------------------------- #
# Rule validation (also the basis of the browser engine)
# --------------------------------------------------------------------------- #

@dataclass
class Violation:
    rule: str
    code: str
    message: str
    severity: str = "bounce"
    correct_sublevel: str | None = None
    correct_box: int | None = None

    def as_dict(self) -> dict:
        return {
            "rule": self.rule, "code": self.code, "message": self.message,
            "severity": self.severity, "correctSublevel": self.correct_sublevel,
            "correctBox": self.correct_box,
        }


# Exact classroom wording. Edit here, nowhere else.
MESSAGES = {
    "aufbau": "Energy Rejection — {target} is higher in energy than {next}. Fill {next} first.",
    "aufbau_exception": "Stability Exception — {symbol} takes {actual}. {reason}",
    "pauli_third": "Pauli Exclusion — one orbital holds at most 2 electrons.",
    "pauli_spin": "Pauli Exclusion — paired electrons must have opposite spins. ↑↓ only.",
    "hund": "Hund's Rule — spread out first. Place 1 electron in each {type} orbital before pairing.",
    "hund_spin": "Hund's Rule — a lone electron is always drawn ↑ first, and every lone "
                 "electron in the same sublevel spins the same way. ↓ goes in only when pairing.",
    "capacity": "Too many electrons — a {type} sublevel holds {max}.",
    "count_over": "Neutral {symbol} has {z} electrons. You have {have}.",
    "count_under": "Incomplete — {have} of {z} electrons placed.",
    "ion_order": "Ion Order — remove {outer} before {inner} when forming {ion}.",
}


def next_needed_sublevel(config: dict[str, int], state_counts: dict[str, int]) -> str | None:
    for name in FILL_ORDER:
        want = config.get(name, 0)
        if want and state_counts.get(name, 0) < want:
            return name
    return None


def validate_placement(state_counts: dict[str, int], z: int, target: str, box: int,
                       spin: str = "↑") -> Violation | None:
    """Occupancy before the attempt is in `state_counts`. Mirrored in JS by
    board.js so the browser can validate offline against the same numbers."""
    config = ground_config(z)
    have = sum(state_counts.values())
    if have >= z:
        return Violation("COUNT", "count_over",
                         MESSAGES["count_over"].format(symbol=element_symbol(z), z=z, have=have + 1))
    cap = capacity(target)
    occupied = state_counts.get(target, 0)
    if occupied >= cap:
        return Violation("CAPACITY", "capacity",
                         MESSAGES["capacity"].format(type=sublevel_type(target), max=cap),
                         severity="block")

    needed = next_needed_sublevel(config, state_counts)
    if needed is not None and target != needed:
        if is_exception(z) and target == next_needed_sublevel(madelung_config(z), state_counts):
            return Violation("EXCEPTION", "aufbau_exception",
                             MESSAGES["aufbau_exception"].format(
                                 symbol=element_symbol(z),
                                 actual=format_config(config, order="fill"),
                                 reason=EXCEPTION_REASON.get(z, "")),
                             severity="warn", correct_sublevel=needed, correct_box=0)
        return Violation("AUFBAU", "aufbau",
                         MESSAGES["aufbau"].format(target=target, next=needed),
                         correct_sublevel=needed, correct_box=0)

    m = orbitals(target)
    boxes = sublevel_boxes(target, occupied)
    current = boxes[box] if 0 <= box < m else "↑↓"
    first_empty = occupied if occupied < m else None

    if current == "↑↓":
        return Violation("PAULI", "pauli_third", MESSAGES["pauli_third"], severity="block",
                         correct_sublevel=target, correct_box=first_empty_box(target, occupied))
    if current == "↑" and first_empty is not None:
        return Violation("HUND", "hund", MESSAGES["hund"].format(type=sublevel_type(target)),
                         correct_sublevel=target, correct_box=first_empty)
    if current == "↑" and spin == "↑":
        return Violation("PAULI", "pauli_spin", MESSAGES["pauli_spin"], severity="warn",
                         correct_sublevel=target, correct_box=box)
    if current == "" and spin == "↓" and occupied < m:
        return Violation("HUND", "hund_spin", MESSAGES["hund_spin"], severity="warn",
                         correct_sublevel=target, correct_box=box)
    return None


def first_empty_box(name: str, occupied: int) -> int | None:
    """Next box that can legally take an ↑, or the next box that can pair."""
    m = orbitals(name)
    if occupied < m:
        return occupied
    if occupied < 2 * m:
        return occupied - m
    return None


def engine_payload(z: int) -> dict:
    """Everything the browser needs to validate a board for one element without
    re-implementing the tables."""
    config = ground_config(z)
    return {
        "z": z,
        "symbol": element_symbol(z),
        "name": element_name(z),
        "block": block_of(z),
        "period": period_of(z),
        "group": group_of(z),
        "isException": is_exception(z),
        "exceptionReason": EXCEPTION_REASON.get(z, ""),
        "expected": expected_but_wrong(z),
        "valenceSublevels": valence_sublevels(z),
        "valenceCount": valence_electrons(z),
        "sublevels": [
            {
                "name": name,
                "n": sublevel_n(name),
                "type": sublevel_type(name),
                "count": count,
                "capacity": capacity(name),
                "orbitals": orbitals(name),
                "fillIndex": fill_index(name),
                "boxes": sublevel_boxes(name, count),
            }
            for name, count in config.items()
        ],
        "lockedSublevels": [name for name in FILL_ORDER if name not in config],
        "full": format_config(config, order="shell"),
        "fillOrder": format_config(config, order="fill"),
        "shorthand": shorthand_config(z),
        "shells": shell_text(z),
        "diagram": orbital_diagram(config),
        "quantum": last_quantum_numbers(z).__dict__,
        "commonIons": COMMON_IONS.get(z, []),
    }


def engine_shared() -> dict:
    """Table-level data shared by every board (mirrored in JS)."""
    return {
        "fillOrder": FILL_ORDER,
        "capacity": {f"{t}": SUBLEVEL_MAX[t] for t in SUBLEVEL_MAX},
        "orbitals": ORBITALS,
        "nobleCores": NOBLE_CORES,
        "messages": MESSAGES,
        "scoring": {
            "place": 100, "hundSweep": 250, "closure": {"s": 200, "p": 600, "d": 1000, "f": 1400},
            "lockBase": 1000, "blockFactor": {"s": 1.0, "p": 1.2, "d": 1.5, "f": 2.0},
            "exceptionInsight": 200, "perfectMultiplier": 1.5,
            "stability": {"start": 100, "place": 2, "bounce": -12, "block": -8, "warn": -4,
                          "recovery": 10, "decay": 0},
            "penalty": {"bounce": -150, "block": -100, "warn": -75, "undo": -25, "hint": -100},
            "multiplier": {"step": 0.25, "max": 3.0},
            "timerBaseSeconds": 45, "timerPerElectron": 3,
            "starThresholds": [0.55, 0.75, 0.90],
        },
    }


def all_engine_payloads() -> dict[int, dict]:
    return {z: engine_payload(z) for z in range(1, MAX_Z + 1)}


# --------------------------------------------------------------------------- #
# Find-the-error generator
# --------------------------------------------------------------------------- #

def build_aufbau_error(z: int, rng: random.Random | None = None) -> dict | None:
    """Move an electron from a lower-energy sublevel into a higher one."""
    rng = rng or random.Random()
    config = ground_config(z)
    names = [k for k in FILL_ORDER if k in config]
    candidates = []
    for i, low in enumerate(names):
        for high in names[i + 1:]:
            if config[low] > 1 and config[high] < capacity(high):
                candidates.append((low, high))
    if not candidates:
        return None
    low, high = rng.choice(candidates)
    wrong = dict(config)
    wrong[low] -= 1
    wrong[high] += 1
    return {
        "text": format_config(wrong, order="fill"),
        "rule": "Aufbau principle",
        "explanation": f"{high} was filled before {low} was finished. Electrons enter the lowest available energy first.",
        "corrected": format_config(config, order="shell"),
        "z": z,
    }


def build_pauli_error(z: int, rng: random.Random | None = None) -> dict | None:
    """Overfill one sublevel past its orbital capacity."""
    config = ground_config(z)
    for name in [k for k in FILL_ORDER if k in config]:
        if config[name] < capacity(name):
            wrong = dict(config)
            wrong[name] += 1
            return {
                "text": format_config(wrong, order="fill"),
                "rule": "Pauli exclusion principle",
                "explanation": f"{name} now holds {wrong[name]} electrons, but a {sublevel_type(name)} sublevel has only {orbitals(name)} orbital(s) — maximum {capacity(name)}.",
                "corrected": format_config(config, order="shell"),
                "z": z,
            }
    return None


def build_hund_error(z: int, rng: random.Random | None = None) -> dict | None:
    """Premature pairing in a degenerate sublevel, shown as a box diagram."""
    rng = rng or random.Random()
    config = ground_config(z)
    options = [name for name, count in config.items()
               if orbitals(name) >= 3 and 2 <= count <= orbitals(name)]
    if not options:
        return None
    name = rng.choice(options)
    count = config[name]
    return {
        "text": None,
        "diagram_sublevel": name,
        "diagram_count": count,
        "boxes": diagram_with_error(name, count, "hund_early_pair"),
        "rule": "Hund's rule",
        "explanation": f"In {name}, electrons occupy every orbital singly before any pair forms. Pairing first costs extra electron-electron repulsion.",
        "corrected_boxes": sublevel_boxes(name, count),
        "z": z,
    }


def build_spin_error(z: int, rng: random.Random | None = None) -> dict | None:
    """A box containing two parallel spins."""
    rng = rng or random.Random()
    config = ground_config(z)
    options = [name for name, count in config.items() if count > orbitals(name)]
    if not options:
        return None
    name = rng.choice(options)
    count = config[name]
    return {
        "text": None,
        "diagram_sublevel": name,
        "diagram_count": count,
        "boxes": diagram_with_error(name, count, "pauli_same_spin"),
        "rule": "Pauli exclusion principle",
        "explanation": "Two electrons sharing one orbital must have opposite spins (↑↓). Two ↑ in a box is impossible.",
        "corrected_boxes": sublevel_boxes(name, count),
        "z": z,
    }


ERROR_BUILDERS = {
    "aufbau": build_aufbau_error,
    "pauli": build_pauli_error,
    "hund": build_hund_error,
    "spin": build_spin_error,
}


def build_random_error(z: int, kinds: list[str], rng: random.Random) -> dict | None:
    rng.shuffle(kinds)
    for kind in kinds:
        result = ERROR_BUILDERS[kind](z, rng)
        if result:
            result["kind"] = kind
            return result
    return None
