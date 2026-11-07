"""Word bank, jumbling and answer checking for Jumbled Letters.

The bank is plain JSON so a teacher can add topics:
    {"Science": {"general": ["ATOM", ...],
                 "topics": {"Newton's Laws of Motion": ["FORCE", "MASS", ...]}}}
An entry may also be {"w": "OSMOSIS", "grades": ["Grade 9", "Grade 10"]} to keep a
word inside certain grades only.
"""
import json
import os
import random
import re
import threading
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(BASE, "word_bank.json")
LIST_PATH = os.path.join(BASE, "wordlist.txt")

WORDS_PER_ROUND = 5      # one round is five jumbles
TARGET_POINTS = 5        # the topic word itself
VALID_POINTS = 1         # any other real word built from the same letters
MAX_VALID_PER_WORD = 3   # only three bonus words count per jumble
MIN_VALID_TO_PASS = 2    # the topic word plus two bonus words ends the jumble early
MIN_LENGTH = 3           # shortest word the bank may deal
MIN_GIVEN = 2            # a two-letter submission counts if it is a real word

# The wordlist starts at three letters, so the common two-letter words live here.
TWO_LETTER_WORDS = frozenset("""
AM AN AS AT BE BY DO GO HE HI HO ID IF IN IS IT ME MY NO OF ON OR SO TA TO UM UP US WE
""".split())

_bank = None
_dictionary = None
_lock = threading.Lock()


def bank():
    global _bank
    if _bank is None:
        with open(BANK_PATH, encoding="utf-8") as f:
            _bank = json.load(f)
    return _bank


def _clean(entry):
    """Bank rows are either bare words or {'w': ..., 'grades': ...}."""
    if isinstance(entry, str):
        return entry.strip().upper(), None
    return str(entry.get("w", "")).strip().upper(), entry.get("grades")


def bank_words(subject, grade=None):
    out = []
    entry = bank().get(subject, {})
    for group in (entry.get("general", []), ):
        out += [w for w, g in [_clean(e) for e in group] if w and (g is None or grade in g)]
    return out


def topic_words(subject, topic, grade=None):
    out = []
    for name, rows in bank().get(subject, {}).get("topics", {}).items():
        if name.strip().lower() != (topic or "").strip().lower():
            continue
        for word, g in [clean for clean in map(_clean, rows)]:
            if word and (g is None or grade in g):
                out.append(word)
    return out


def words_for(grade, subject, topic, count=WORDS_PER_ROUND):
    """Every pick from the quiz-specification form can start a round.

    Topic words first; if the topic has too few of its own the subject pool fills
    in, and after that the whole subject bank, so the round still has `count`.
    """
    found, seen = [], set()

    def take(words):
        for w in words:
            if w not in seen and len(w) >= MIN_LENGTH:
                seen.add(w)
                found.append(w)

    take(topic_words(subject, topic, grade))
    if len(found) < count:
        take(bank_words(subject, grade))
    if len(found) < count:
        take(sorted({w for name, rows in bank().get(subject, {}).get("topics", {}).items()
                      for w, g in map(_clean, rows) if w and len(w) >= MIN_LENGTH}))
    return found


def pick(grade, subject, topic, count=WORDS_PER_ROUND):
    """Random selection, the same rule the quiz paper uses for its items."""
    words = words_for(grade, subject, topic, count)
    chosen = random.sample(words, min(count, len(words)))
    return [{"word": w, "jumble": jumble(w)} for w in chosen]


def jumble(word, tries=12):
    letters = list(word)
    for _ in range(tries):
        random.shuffle(letters)
        scrambled = "".join(letters)
        if scrambled != word and len(word) > 2:
            return scrambled
    return word[::-1] if len(word) > 2 else word


def dictionary():
    """350k words, loaded once and only when an answer has to be judged."""
    global _dictionary
    if _dictionary is None:
        with _lock:
            if _dictionary is None:
                words = set()
                with open(LIST_PATH, encoding="utf-8") as f:
                    for line in f:
                        w = line.strip().lower()
                        if w:
                            words.add(w)
                for subject in bank():
                    words.update(w.lower() for w in bank_words(subject))
                    for rows in bank().get(subject, {}).get("topics", {}).values():
                        words.update(w.lower() for w, _ in map(_clean, rows))
                _dictionary = frozenset(words)
    return _dictionary


def normal(raw):
    text = re.sub(r"[^A-Za-z]", "", str(raw or ""))
    return text.upper()


def uses_letters(given, target):
    """Only letters from the jumble, and no more of each than it holds."""
    need, have = Counter(given), Counter(target)
    return all(have[letter] >= count for letter, count in need.items())


def check(raw, target, already_valid, solved, bonus_count):
    """Return {'points', 'kind', 'reason'} for one submission."""
    given = normal(raw)
    if not given:
        return {"points": 0, "kind": "none", "reason": "Type a word first."}
    if len(given) < MIN_GIVEN:
        return {"points": 0, "kind": "none", "reason": "Type at least %d letters." % MIN_GIVEN}
    if not uses_letters(given, target):
        return {"points": 0, "kind": "none", "reason": "Those letters are not in the jumble."}

    if given == target:
        if solved:
            return {"points": 0, "kind": "none", "reason": "You already gave the topic word."}
        return {"points": TARGET_POINTS, "kind": "topic", "reason": "The topic word!"}

    key = given.lower()
    if key not in dictionary() and given not in TWO_LETTER_WORDS:
        return {"points": 0, "kind": "none", "reason": "Not a word we accept."}
    if key in already_valid:
        return {"points": 0, "kind": "none", "reason": "That word already counted."}
    if bonus_count >= MAX_VALID_PER_WORD:
        return {"points": 0, "kind": "none",
                "reason": "Only %d bonus words count per jumble." % MAX_VALID_PER_WORD}
    return {"points": VALID_POINTS, "kind": "valid", "reason": "A real word."}
