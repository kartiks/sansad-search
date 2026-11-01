"""
Speaker name canonicalization.

Rules (applied in order):
  1. Strip leading honorific prefixes (Shri, Smt., Dr., Prof., etc.)
  2. Look up the stripped name in names_dict.csv
     - Found  → return (canonical_name, speaker_name_unresolved=False)
     - Not found → return (stripped_name, speaker_name_unresolved=True)
  3. None / empty input → return (None, False)

normalize_for_dedup() produces the dedup-key component:
  lowercase, spaces → underscores, non-alphanumeric characters stripped.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

# ── Honorific prefix regex ─────────────────────────────────────────────────────
# Matches one or more leading honorific prefixes separated by whitespace/dots.
# Each pass of the regex removes one prefix; callers strip in a loop.
_HONORIFIC_RE = re.compile(
    r"^\s*(?:"
    r"The\s+Hon(?:ou|o)rable|Hon(?:ou|o)rable|Hon'ble|Hon\.|"
    r"Shrimati|Shri|Sushri|Smt\.|Smt|Dr\.|Dr|Prof\.|Prof|Adv\.|Adv|Kumari|"
    r"Sri|Mr\.|Mr|Mrs\.|Mrs|Ms\.|Ms|"
    r"Col\.|Col|Capt\.|Capt|Maj\.|Maj|Gen\.|Gen|Lt\.|Lt|"
    r"Brig\.|Brig|Air\s+Cmde\.|Air\s+Marshal|"
    r"Brigadier|Colonel|General|Major|Captain|Lieutenant"
    r")[\s.,]+",
    re.IGNORECASE,
)


def strip_honorifics(name: str) -> str:
    """
    Remove all leading honorific prefixes from *name*.

    Applies the regex repeatedly until no more prefixes are stripped.
    """
    result = name.strip()
    while True:
        stripped = _HONORIFIC_RE.sub("", result).strip()
        if stripped == result:
            break
        result = stripped
    return result


def normalize_name_form(name: str) -> str:
    """
    Tidy the written form of a name without changing who it refers to.

    - OCR commas between initials: "A, B, A. GHANI" → "A. B. A. GHANI"
    - initials spacing: "A.C.GEORGE" / "M.M. PALLAM RAJU" → "A. C. GEORGE" / "M. M. PALLAM RAJU"
    - names written entirely in capitals become title case ("ADHIR RANJAN
      CHOWDHURY" → "Adhir Ranjan Chowdhury"), matching how other sources store names.
    """
    s = re.sub(r"\s+", " ", name.strip())
    s = re.sub(r"\b([A-Z]),\s*(?=[A-Z][.,\s])", r"\1. ", s)   # A, B, → A. B.
    s = re.sub(r"\b([A-Z])\.(?=[A-Z])", r"\1. ", s)            # A.C. → A. C.
    s = re.sub(r"\s+", " ", s).strip(" ,;:")
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if letters and all(c.isupper() for c in letters):
        def cap(word: str) -> str:
            return re.sub(
                r"[A-Za-z]+",
                lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(),
                word,
            )
        s = " ".join(cap(w) for w in s.split(" "))
        s = re.sub(r"\b(Mc|Mac|O'|D')([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def tidy_name(name: Optional[str]) -> Optional[str]:
    """Honorifics stripped and written form normalized; None for empty input."""
    if not name or not name.strip():
        return None
    return normalize_name_form(strip_honorifics(name)) or None


# A lowercase letter directly followed by a capitalised word or an initial marks
# two names run together with no separator, as in eparlib_members
# "Nitish KumarRamji Lal Suman" or "Mahabal MishraM. Anjan Kumar Yadav".
_JOINED_NAME_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z](?:[a-z]|\.))")
# Name prefixes that legitimately take an internal capital (McDonald, MacLeod).
_INTERNAL_CAPITAL_PREFIXES = ("Mc", "Mac")


def split_joined_names(name: Optional[str]) -> list[str]:
    """
    Split a string holding several names run together into separate names.

    The Internet Archive eparlib_members field often lists co-questioners with
    no delimiter: "P. Jaya Prada NahataYashvir Singh" → ["P. Jaya Prada Nahata",
    "Yashvir Singh"]. Names written in capitals are left alone, since the
    boundary can't be seen in them.
    """
    if not name or not name.strip():
        return []
    parts: list[str] = []
    start = 0
    for m in _JOINED_NAME_BOUNDARY_RE.finditer(name):
        word_start = max(name.rfind(" ", 0, m.start()), name.rfind(".", 0, m.start())) + 1
        if name[word_start:m.start()] in _INTERNAL_CAPITAL_PREFIXES:
            continue
        parts.append(name[start:m.start()])
        start = m.start()
    parts.append(name[start:])
    return [p.strip(" ,;") for p in parts if p.strip(" ,;")]


def _lookup_key(name: str) -> str:
    return _normalize_for_lookup(normalize_name_form(strip_honorifics(name)))


# Visible boundaries inside capitals-joined lists: initials starting straight after
# a word ("GOPALSAMYT.R. BAALU"), or a word after a closing bracket
# ("KHAN (DURRU)ASHOK"). A nickname in quotes is handled by _CAPS_NICKNAME_RE.
_CAPS_VISIBLE_BOUNDARY_RE = re.compile(r"(?<=[A-Z]{2})(?=[A-Z]\.)|(?<=\))(?=[A-Z])")
# "RAJIV RANJAN SINGH 'LALAN'KAPIL SIBAL": the name ends after the closing quote.
_CAPS_NICKNAME_RE = re.compile(r"( '[A-Z][A-Z .]*')(?=[A-Z])")


def split_capitals_joined(name: Optional[str], names_dict: dict[str, str]) -> list[str]:
    """
    Split names run together in capitals, using the names dictionary.

    Rajya Sabha member lists write co-questioners in capitals with no delimiter
    ("KALRAJ MISHRASANTOSH BAGRODIA"), so the case change split_joined_names
    relies on isn't there. A boundary may fall between any two letters (or after
    an initial's full stop); a split is accepted only when every piece is a known
    name, preferring the fewest pieces. Otherwise the name is returned unchanged.
    """
    if not name or not name.strip():
        return []
    s = name.strip()
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if not letters or not all(c.isupper() for c in letters):
        return [s]
    if _lookup_key(s) in names_dict:
        return [s]
    marked = _CAPS_VISIBLE_BOUNDARY_RE.sub("|", _CAPS_NICKNAME_RE.sub(r"\1|", s))
    pieces = [p.strip(" ,;") for p in marked.split("|") if p.strip(" ,;")]
    return [part for piece in pieces for part in _split_by_dictionary(piece, names_dict)]


def _segment(
    s: str, points: list[int], piece_ok, max_unknown: int
) -> Optional[list[str]]:
    """Fewest-piece split of *s* at *points*; piece_ok(piece) → 0 known, 1 unknown, None no."""
    best: dict[int, tuple[tuple[int, int], int]] = {0: ((0, 0), -1)}
    last = len(points) - 1
    for j in range(1, len(points)):
        for i in range(j - 1, -1, -1):
            if i not in best or (i == 0 and j == last):
                continue
            piece = s[points[i]:points[j]].strip(" ,;")
            kind = piece_ok(piece) if len(piece) >= 3 else None
            if kind is None:
                continue
            (u, k), _ = best[i]
            cand = ((u + kind, k + 1), i)
            if cand[0][0] > max_unknown:
                continue
            if j not in best or cand[0] < best[j][0]:
                best[j] = cand
    if last not in best:
        return None
    pieces: list[str] = []
    j = last
    while j > 0:
        i = best[j][1]
        pieces.append(s[points[i]:points[j]].strip(" ,;"))
        j = i
    return list(reversed(pieces))


def _split_by_dictionary(s: str, names_dict: dict[str, str]) -> list[str]:
    """
    Split *s* where names were run together, at points inside words.

    First try pieces that are all known names. Failing that, allow one unknown
    piece (a member the dictionary lacks) when every other piece is a known name
    of two or more words, and the unknown piece has two or more words too; the
    two-word rule stops a short known name ("RAMA") splitting a single unknown
    one ("RAMACHANDRA KHUNTIA"). Returns [s] when neither works.
    """
    if not names_dict or _lookup_key(s) in names_dict:
        return [s]
    n = len(s)
    cuts = [i for i in range(1, n) if s[i].isalpha() and s[i - 1] not in " -'(."]
    points = [0] + cuts + [n]

    def all_known(piece: str) -> Optional[int]:
        return 0 if _lookup_key(piece) in names_dict else None

    def one_unknown(piece: str) -> Optional[int]:
        if len(piece.split()) < 2:
            return None
        return 0 if _lookup_key(piece) in names_dict else 1

    return (
        _segment(s, points, all_known, max_unknown=0)
        or _segment(s, points, one_unknown, max_unknown=1)
        or [s]
    )


def _letters_key(name: str) -> str:
    """Lowercase letters only, so "Kalp Nath Rai" and "Kalpnath Rai" compare equal."""
    return re.sub(r"[^a-z]", "", name.lower())


def unique_names(names: list[str]) -> list[str]:
    """Drop repeats of a name, compared on letters only; first spelling wins."""
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = _letters_key(n) or n
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def drop_answering_minister(
    questioners: list[str], minister: Optional[str]
) -> list[str]:
    """
    Remove the answering minister from a Q&A questioner list.

    eParlib member lists name the minister who answered alongside the members
    who asked ("Laxminarayan Pandey" + "Arjun Singh", answered by Arjun Singh).
    Names are compared on letters only, which absorbs OCR spacing and hyphens.
    A lone questioner is kept: in a minister's statement correcting an earlier
    reply the minister is both.
    """
    if not minister or len(questioners) < 2:
        return questioners
    key = _letters_key(minister)
    if not key:
        return questioners
    kept = [q for q in questioners if _letters_key(q) != key]
    return kept or questioners


def _normalize_for_lookup(name: str) -> str:
    """Lowercase and collapse internal whitespace for dictionary lookup."""
    return re.sub(r"\s+", " ", name.strip().lower())


def load_names_dict(path: Path) -> dict[str, str]:
    """
    Load names_dict.csv into a variant → canonical_name lookup dict.

    CSV must have columns: variant, canonical_name
    Rows with empty variant or canonical_name are silently skipped.
    Missing file returns an empty dict (no error).
    """
    lookup: dict[str, str] = {}
    if not path.exists():
        return lookup
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            variant = (row.get("variant") or "").strip()
            canonical = (row.get("canonical_name") or "").strip()
            if variant and canonical:
                lookup[_normalize_for_lookup(variant)] = canonical
    return lookup


def canonicalize_name(
    raw_name: Optional[str],
    names_dict: dict[str, str],
) -> tuple[Optional[str], bool]:
    """
    Canonicalize a speaker name.

    Returns:
        (canonical_name, speaker_name_unresolved)

    Cases:
      - raw_name is None or empty  → (None, False)
      - stripped name in dict      → (canonical_name, False)
      - stripped name not in dict  → (stripped_name, True)
    """
    if not raw_name or not raw_name.strip():
        return None, False

    stripped = normalize_name_form(strip_honorifics(raw_name))
    if not stripped:
        # Entire name was honorifics — treat as unresolved, use raw
        return raw_name.strip(), True

    key = _normalize_for_lookup(stripped)
    if key in names_dict:
        return names_dict[key], False

    return stripped, True


def normalize_for_dedup(name: Optional[str]) -> str:
    """
    Produce the speaker_name component of a dedup key.

    Rules: lowercase → strip non-alphanumeric (keep spaces) → spaces to underscores.
    Returns "unknown" for None or empty names.
    """
    if not name:
        return "unknown"
    result = name.lower()
    result = re.sub(r"[^\w\s]", "", result)   # strip punctuation/special chars
    result = re.sub(r"\s+", "_", result.strip())
    return result or "unknown"
