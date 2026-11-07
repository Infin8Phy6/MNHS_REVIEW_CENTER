"""The Who's Who activities, kept in whoswho.json in the Review Center root folder.

An activity is one round of the game:

    {"activities": [{
        "slug": "filipino-heroes", "title": "Filipino Heroes", "created": "...",
        "persons": [{"id": "...", "name": "Jose Rizal",
                     "clues": ["...", "...", "..."],
                     "photo": {"drive_id": "...", "file": "abc123.jpg"}}
    }]}

The JSON is the whole point of the design: the admin writes it with the form, and
the pages only ever read it, so an activity survives a restart and copies to the
server as one small text file.
"""
import json
import os
import re
import secrets
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA_PATH = os.path.join(ROOT, "whoswho.json")
PHOTO_DIR = os.path.join(ROOT, "whoswho_photos")

_lock = threading.Lock()


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:60] or "activity"


def document():
    with _lock:
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            doc = {}
        doc.setdefault("activities", [])
        if not isinstance(doc["activities"], list):
            doc["activities"] = []
        return doc


def save(doc):
    with _lock:
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        tmp = DATA_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, DATA_PATH)


def activities():
    """Newest first, and never broken by one bad entry."""
    rows = [clean(a) for a in document()["activities"]]
    return [a for a in rows if a]


def get(slug):
    for row in activities():
        if row["slug"] == (slug or "").strip():
            return row
    return None


def put(activity):
    """Insert, or replace the activity that already holds this slug."""
    doc = document()
    people = [clean_person(p) for p in activity.get("persons", [])]
    row = {"slug": activity["slug"], "title": activity["title"].strip(),
           "created": activity.get("created") or now_text(),
           "persons": [p for p in people if p]}
    for i, existing in enumerate(doc["activities"]):
        if existing.get("slug") == row["slug"]:
            doc["activities"][i] = row
            save(doc)
            return row
    doc["activities"].insert(0, row)
    save(doc)
    return row


def remove(slug):
    doc = document()
    kept = [a for a in doc["activities"] if a.get("slug") != slug]
    if len(kept) == len(doc["activities"]):
        return False
    doc["activities"] = kept
    save(doc)
    return True


def new_person_id():
    return secrets.token_hex(6)


def now_text():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean(activity):
    """One activity as the pages need it, with anything unusable dropped."""
    if not isinstance(activity, dict):
        return None
    title = str(activity.get("title") or "").strip()
    slug = str(activity.get("slug") or "").strip() or slugify(title)
    if not title or not slug:
        return None
    people = [clean_person(p) for p in activity.get("persons", [])]
    return {"slug": slug, "title": title, "created": activity.get("created") or "",
            "persons": [p for p in people if p]}


def clean_person(person):
    if not isinstance(person, dict):
        return None
    name = re.sub(r"\s+", " ", str(person.get("name") or "")).strip()
    if not name:
        return None
    clues = [re.sub(r"\s+", " ", str(c or "")).strip()[:300]
             for c in list(person.get("clues") or [])[:3]]
    while len(clues) < 3:
        clues.append("")
    photo = person.get("photo") if isinstance(person.get("photo"), dict) else {}
    return {"id": str(person.get("id") or new_person_id()), "name": name[:80],
            "clues": clues,
            "photo": {"drive_id": str(photo.get("drive_id") or ""),
                      "file": os.path.basename(str(photo.get("file") or ""))}}


def photo_path(name):
    return os.path.join(PHOTO_DIR, name) if name else None


def save_photo(data, mime, name=None):
    """Keep a local copy of every picture so the round renders offline too.

    Google Drive is still the copy of record — this is the device-side mirror.
    """
    if not data:
        return ""
    os.makedirs(PHOTO_DIR, exist_ok=True)
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
           "image/webp": ".webp"}.get((mime or "").split(";")[0].strip(), ".jpg")
    fname = name or (secrets.token_hex(8) + ext)
    fname = os.path.basename(fname)
    with open(photo_path(fname), "wb") as f:
        f.write(data)
    return fname
