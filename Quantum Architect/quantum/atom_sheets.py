"""The orbital-box worksheet: elements laid out as boxes, arrows, and a Bohr model.

A sheet is a list of elements, not a list of questions. Two small elements share
one A4 portrait page - one in the top half, one in the bottom half - and an
element whose configuration needs many rows takes the whole page. Each block
prints the sublevel boxes for a student to put arrows in, with the Bohr model in
the upper right so the shell picture and the box diagram teach each other.
"""

from __future__ import annotations

import math
import re
from datetime import datetime

from quantum import chemistry as qa
from quantum.worksheets import PRESETS

SHELL_LETTERS = "KLMNOPQ"

# A block is small enough to share a page when it has at most this many
# sublevel rows and orbital boxes. Z 1-20 qualifies; the first transition
# series (seven rows) does not, which matches the classroom rule of thumb.
COMPACT_ROWS = 6
COMPACT_BOXES = 13

PER_PAGE_LABELS = {
    "auto": "Automatic — two small elements per page, one large element per page",
    "2": "Always two elements per A4 page (top and bottom half)",
    "1": "One element per A4 page",
}


def default_settings(**overrides) -> dict:
    settings = {
        "title": "Orbital Box Worksheet",
        "class_name": "",
        "section": "",
        "teacher": "",
        "date": datetime.now().strftime("%B %d, %Y"),
        "pool_mode": "preset",
        "preset": "first20",
        "z_min": 1,
        "z_max": 20,
        "custom_pool": "",
        "per_page": "auto",
        "show_bohr": True,
        "instructions": ("Write \u2191 or \u2193 in each box, one arrow per electron. "
                         "Use \u2191\u2193 only when the orbital already holds one electron."),
    }
    settings.update(overrides)
    return settings


def resolve_elements(settings: dict) -> list[int]:
    """The atomic numbers on this sheet, de-duplicated and in atomic order."""
    mode = settings.get("pool_mode", "preset")
    if mode == "custom":
        numbers = [int(x) for x in re.findall(r"\d+", str(settings.get("custom_pool", "")))]
        pool = [z for z in numbers if 1 <= z <= qa.MAX_Z]
    elif mode == "range":
        lo = max(1, int(settings.get("z_min", 1)))
        hi = min(qa.MAX_Z, int(settings.get("z_max", 20)))
        if hi < lo:
            lo, hi = hi, lo
        pool = list(range(lo, hi + 1))
    else:
        preset = PRESETS.get(settings.get("preset", "first20"), PRESETS["first20"])
        pool = list(preset[0])
    return sorted({int(z) for z in pool})


def bohr_model(z: int) -> dict:
    """Rings and electron positions for the little Bohr picture (viewBox 200)."""
    shells = qa.shell_distribution(z)
    valence_shells = {qa.sublevel_n(name) for name in qa.valence_sublevels(z)}
    rings = []
    for index, electrons in enumerate(shells):
        n = index + 1
        radius = 34.0 if len(shells) == 1 else 30.0 + 58.0 * index / (len(shells) - 1)
        dots = []
        for i in range(electrons):
            angle = (2 * math.pi * i) / electrons - math.pi / 2
            dots.append({"x": round(100 + radius * math.cos(angle), 2),
                         "y": round(100 + radius * math.sin(angle), 2)})
        rings.append({
            "n": n,
            "letter": SHELL_LETTERS[n - 1],
            "count": electrons,
            "r": round(radius, 2),
            "dots": dots,
            "valence": n in valence_shells,
        })
    return {"rings": rings, "electrons": z, "symbol": qa.element_symbol(z)}


def element_block(z: int) -> dict:
    """Everything one printed element block needs, student and key alike."""
    config = qa.ground_config(z)
    rows = []
    box_total = 0
    for name in qa.FILL_ORDER:
        count = config.get(name)
        if not count:
            continue
        l = qa.SUBLEVEL_L[qa.sublevel_type(name)]
        orbital_count = qa.orbitals(name)
        box_total += orbital_count
        rows.append({
            "sublevel": name,
            "type": qa.sublevel_type(name),
            "n": qa.sublevel_n(name),
            "l": l,
            "count": count,
            "boxes": qa.sublevel_boxes(name, count),
            "ml": [-l + i for i in range(orbital_count)],
        })
    group = qa.group_of(z)
    shells = qa.shell_distribution(z)
    return {
        "z": z,
        "symbol": qa.element_symbol(z),
        "name": qa.element_name(z),
        "block": qa.block_of(z),
        "period": qa.period_of(z),
        "group": group,
        "group_label": str(group) if group else "f-block",
        "rows": rows,
        "box_total": box_total,
        "compact": len(rows) <= COMPACT_ROWS and box_total <= COMPACT_BOXES,
        "config": qa.format_config(config, order="shell"),
        "config_fill": qa.format_config(config, order="fill"),
        "shorthand": qa.shorthand_config(z),
        "shells": shells,
        "shell_text": ", ".join(str(x) for x in shells),
        "valence": qa.valence_electrons(z),
        "bohr": bohr_model(z),
    }


def paginate(blocks: list[dict], per_page: str = "auto") -> list[list[dict]]:
    """Split blocks into A4 pages.

    auto  - pair compact elements, give a large element its own page.
    2/1   - the teacher forces the pair count.
    """
    if not blocks:
        return []
    if per_page == "1":
        return [[block] for block in blocks]

    pages: list[list[dict]] = []
    current: list[dict] = []
    for block in blocks:
        fits = per_page == "2" or block["compact"]
        if fits:
            current.append(block)
            if len(current) == 2:
                pages.append(current)
                current = []
        else:
            if current:
                pages.append(current)
                current = []
            pages.append([block])
    if current:
        pages.append(current)
    return pages


def build_sheet(record: dict) -> dict:
    settings = record["settings"]
    blocks = [element_block(z) for z in record["elements"]]
    pages = paginate(blocks, settings.get("per_page", "auto"))
    return {
        "settings": settings,
        "blocks": blocks,
        "pages": pages,
        "page_count": len(pages),
        "element_count": len(blocks),
    }


def summary(record: dict) -> dict:
    settings = record["settings"]
    elements = record["elements"]
    page_count = len(paginate([element_block(z) for z in elements],
                              settings.get("per_page", "auto")))
    first = qa.element_symbol(elements[0]) if elements else "—"
    last = qa.element_symbol(elements[-1]) if elements else "—"
    return {
        "id": record["id"],
        "title": settings["title"],
        "class_name": settings["class_name"],
        "section": settings["section"],
        "teacher": settings["teacher"],
        "element_count": len(elements),
        "page_count": page_count,
        "per_page": settings.get("per_page", "auto"),
        "range_label": first if first == last else f"{first} – {last}",
        "saved_at": record.get("saved_at", ""),
    }
