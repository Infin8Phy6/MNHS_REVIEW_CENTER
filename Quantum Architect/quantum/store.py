"""JSON-file persistence for saved worksheets.

No database: the folder is a single self-contained app and a plain file is easier
to back up, email or drop on a shared drive. Writes go through a temp file so a
crash cannot leave a half-written catalogue.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CATALOGUE = DATA_DIR / "worksheets.json"
ATOM_CATALOGUE = DATA_DIR / "atom_sheets.json"


def _read(path: Path = CATALOGUE) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return []


def _write(records: list[dict], path: Path = CATALOGUE) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=DATA_DIR, prefix=".catalogue-", suffix=".tmp", delete=False)
    try:
        json.dump(records, handle, ensure_ascii=False, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


def summary(record: dict) -> dict:
    settings = record["settings"]
    return {
        "id": record["id"],
        "title": settings["title"],
        "class_name": settings["class_name"],
        "section": settings["section"],
        "tier": settings["tier"],
        "item_count": len(record["items"]),
        "elements": record["element_count"],
        "total_marks": record["total_marks"],
        "saved_at": record["saved_at"],
        "seed": settings["seed"],
    }


def list_all() -> list[dict]:
    records = _read()
    records.sort(key=lambda r: r.get("saved_at", ""), reverse=True)
    return [summary(r) for r in records]


def get(worksheet_id: str) -> dict | None:
    for record in _read():
        if record.get("id") == worksheet_id:
            return record
    return None


def save(worksheet: dict, worksheet_id: str | None = None) -> dict:
    records = _read()
    record = dict(worksheet)
    record["id"] = worksheet_id or uuid.uuid4().hex[:12]
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")
    existing = [i for i, r in enumerate(records) if r.get("id") == record["id"]]
    if existing:
        records[existing[0]] = record
    else:
        records.append(record)
    _write(records)
    return record


def delete(worksheet_id: str) -> bool:
    records = _read()
    kept = [r for r in records if r.get("id") != worksheet_id]
    if len(kept) == len(records):
        return False
    _write(kept)
    return True


# --------------------------------------------------------------------------- #
# Orbital-box sheets (the atom sheet studio) live in their own catalogue.
# --------------------------------------------------------------------------- #

def list_atoms() -> list[dict]:
    from quantum import atom_sheets

    records = _read(ATOM_CATALOGUE)
    records.sort(key=lambda r: r.get("saved_at", ""), reverse=True)
    return [atom_sheets.summary(r) for r in records]


def get_atom(sheet_id: str) -> dict | None:
    for record in _read(ATOM_CATALOGUE):
        if record.get("id") == sheet_id:
            return record
    return None


def save_atom(sheet: dict, sheet_id: str | None = None) -> dict:
    records = _read(ATOM_CATALOGUE)
    record = dict(sheet)
    record["id"] = sheet_id or uuid.uuid4().hex[:12]
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")
    existing = [i for i, r in enumerate(records) if r.get("id") == record["id"]]
    if existing:
        records[existing[0]] = record
    else:
        records.append(record)
    _write(records, ATOM_CATALOGUE)
    return record


def delete_atom(sheet_id: str) -> bool:
    records = _read(ATOM_CATALOGUE)
    kept = [r for r in records if r.get("id") != sheet_id]
    if len(kept) == len(records):
        return False
    _write(kept, ATOM_CATALOGUE)
    return True
