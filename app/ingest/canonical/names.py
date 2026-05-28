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
    r"Shri|Smt\.|Smt|Dr\.|Dr|Prof\.|Prof|Adv\.|Adv|Kumari|"
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

    stripped = strip_honorifics(raw_name)
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
