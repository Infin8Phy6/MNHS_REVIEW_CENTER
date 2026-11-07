"""Deterministic crossword builder - standard library only.

Ports the placement ideas of crossword_generator.py, but instead of scattering
words anywhere it interlocks them like a real crossword, numbers every word's
displayed start cell and fills the leftover cells with random letters so a
printed or on-screen grid never shows where a word ends.
"""
import random

GRID_MAX = 15          # the prototype's board size
MIN_LEN = 3
MAX_LEN = 15
REFLOWS = 12           # whole-board retries before the words are rejected
REVERSE_CHANCE = 0.5   # the prototype hid half its words back-to-front

ACROSS, DOWN = "H", "V"


class GenerationError(Exception):
    """The words cannot interlock, even after every reflow."""


def clean(word):
    return "".join(ch for ch in (word or "").upper() if "A" <= ch <= "Z")


def build(pairs, seed):
    """(word, clue) pairs -> {rows, cols, grid, placements}.

    A placement is {word, clue, dir, rev, cells, n, at}:
      cells  coordinates in word-reading order (a reversed word reads right
             to left or bottom to top, so the step direction flips);
      at     the cell that carries the printed number - the top-left end of
             the run, exactly where a solver begins reading across or down.
    """
    entries = _checked(pairs)
    rng = random.Random(seed)
    for _ in range(REFLOWS):
        board = _try_build(entries, random.Random(rng.randrange(1 << 40)))
        if board:
            return _finish(board, rng)
    raise GenerationError(
        'These words refuse to interlock into one grid. Replace the longest '
        'word, or pick words that share more letters.')


def _checked(pairs):
    entries, seen = [], set()
    for word, clue in pairs:
        w = clean(word)
        if len(w) < MIN_LEN or len(w) > MAX_LEN:
            raise GenerationError('"%s" must be a plain word of %d to %d '
                                  'letters.' % ((word or "").strip(), MIN_LEN, MAX_LEN))
        if w in seen:
            raise GenerationError('"%s" is on the list twice - each word must '
                                  'be different.' % w)
        seen.add(w)
        entries.append({"word": w, "clue": (clue or "").strip()})
    return entries


def _try_build(entries, rng):
    """Place every word on a GRID_MAX board, or return None for a reflow."""
    grid = {}
    placed = []
    # longest first: late words then have many letters to hang crossings on
    for entry in sorted(entries, key=lambda e: -len(e["word"])):
        word = entry["word"]
        if not placed:
            row = GRID_MAX // 2
            col = rng.randint(0, GRID_MAX - len(word))
            run = [(row, col + i) for i in range(len(word))]
            _park(grid, word, run)
            placed.append({"word": word, "clue": entry["clue"], "dir": ACROSS,
                           "rev": False, "cells": run})
            continue
        spot = _best_spot(grid, word, rng)
        if spot is None:
            return None
        run, direction, rev = spot
        _park(grid, word, run)
        placed.append({"word": word, "clue": entry["clue"], "dir": direction,
                       "rev": rev, "cells": run})
    return {"grid": grid, "placed": placed}


def _park(grid, word, run):
    for coord, letter in zip(run, word):
        grid[coord] = letter


def _best_spot(grid, word, rng):
    """A candidate crossing with the most overlaps; ties broken at random."""
    by_score = {}
    for index, letter in enumerate(word):
        for cross, filled in grid.items():
            if filled != letter:
                continue
            for direction in (ACROSS, DOWN):
                for rev in (False, True):
                    if rev and rng.random() > REVERSE_CHANCE:
                        continue
                    run = _run_through(cross, index, direction, rev, word)
                    if run is not None and _valid(grid, word, run):
                        score = sum(coord in grid for coord in run)
                        by_score.setdefault(score, []).append(
                            (run, direction, rev))
    if not by_score:
        return None
    return rng.choice(by_score[max(by_score)])


def _run_through(cross, index, direction, rev, word):
    """A run whose letter at `index` sits on `cross`, reading forward or back.

    rev means the word reads against the natural direction: an Across word
    running right to left, a Down word running bottom to top. The returned
    coordinates stay in word-reading order either way.
    """
    r, c = cross
    step = (-1 if rev else 1)
    if direction == ACROSS:
        run = [(r, c + step * (i - index)) for i in range(len(word))]
    else:
        run = [(r + step * (i - index), c) for i in range(len(word))]
    if any(rr < 0 or cc < 0 or rr >= GRID_MAX or cc >= GRID_MAX for rr, cc in run):
        return None
    return run


def _valid(grid, word, run):
    if _occupied(grid, _outside(run, run[0], run[1])):
        return False
    if _occupied(grid, _outside(run, run[-1], run[-2])):
        return False
    for i, coord in enumerate(run):
        letter = word[i]
        if coord in grid:
            if grid[coord] != letter:
                return False
            continue
        # a fresh cell may not touch another letter on its flanks, or two
        # parallel words would grow where no clue points
        for side in _sides(run, coord):
            if side in grid:
                return False
    return True


def _outside(run, end, towards):
    """The cell one step beyond `end`, opposite to `towards`."""
    dr, dc = end[0] - towards[0], end[1] - towards[1]
    return (end[0] + dr, end[1] + dc)


def _occupied(grid, coord):
    r, c = coord
    in_bounds = 0 <= r < GRID_MAX and 0 <= c < GRID_MAX
    return in_bounds and coord in grid


def _sides(run, coord):
    r, c = coord
    horizontal = len(run) > 1 and run[1][0] == run[0][0]
    if horizontal:
        return [(r - 1, c), (r + 1, c)]
    return [(r, c - 1), (r, c + 1)]


def _finish(board, rng):
    """Trim, number, and fill the baffles; placements come back sorted by n."""
    grid, placed = board["grid"], board["placed"]
    rows_used = [r for r, _ in grid]
    cols_used = [c for _, c in grid]
    top, left = min(rows_used), min(cols_used)
    height = max(rows_used) - top + 1
    width = max(cols_used) - left + 1

    def shift(coord):
        return (coord[0] - top, coord[1] - left)

    taken = {shift(coord): letter for coord, letter in grid.items()}
    cells = [[taken.get((r, c)) for c in range(width)] for r in range(height)]

    # numbers walk the board the way a reader does, top left to bottom right;
    # one cell starting both an Across and a Down word carries one number
    starts = {}
    for placement in placed:
        run = [shift(coord) for coord in placement["cells"]]
        at = run[-1] if placement["rev"] else run[0]
        starts.setdefault(at, []).append((placement, run))
    for number, at in enumerate(sorted(starts), start=1):
        for placement, run in starts[at]:
            placement["n"] = number
            placement["at"] = at

    for r in range(height):
        for c in range(width):
            if cells[r][c] is None:
                cells[r][c] = chr(rng.randint(65, 90))

    return {
        "rows": height,
        "cols": width,
        "grid": cells,
        "placements": [
            {"n": p["n"], "word": p["word"], "clue": p["clue"], "dir": p["dir"],
             "rev": p["rev"], "at": list(p["at"]), "cells": [list(x) for x in p["cells"]]}
            for p in sorted(placed, key=lambda p: (p["n"], p["dir"]))
        ],
    }
