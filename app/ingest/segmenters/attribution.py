"""
Speaker attribution handling for flat parliamentary text (IA djvu.txt, eLibrary Tika text).

Two jobs:

1. ``assemble_wrapped_attributions`` — re-joins attributions that the source layout
   wrapped across several lines before the colon, e.g.

       THE MINISTER OF STATE IN THE MINISTRY OF FINANCE (SHRI NAMO
       NARAIN MEENA): On behalf of ...

   Without this, only the last line is seen and the speaker becomes a fragment
   such as "NARAIN MEENA" or a portfolio word such as "FINANCE".

2. ``parse_attribution`` — splits an attribution head ("SHRI X (PLACE)",
   "THE MINISTER OF Y (SHRI Z)", "HON. CHAIRPERSON") into name, role,
   constituency and portfolio, and rejects headings that merely look like
   attributions ("STATUTORY RESOLUTION RE: ...", "MOTION RE: ...").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Tokens an attribution may start with: honorifics, titles and office prefixes.
_START_RE = re.compile(
    r"^(?:SHRI|SHRIMATI|SMT|SUSHRI|KUMARI|KUM|DR|PROF|MR|MRS|MS|MADAM|ADV|ER"
    r"|CH|CHAUDHARY|CHAUDHRI|SARDAR|SARDARNI|RAJKUMARI|KUNWAR|KUNVAR|RAJA|RANI"
    r"|MAHARAJA|MAHARANI|BEGUM|NAWAB|PANDIT|ACHARYA|MAULANA|SWAMI|SADHVI|YOGI|SANT"
    r"|MAHANT|BABA|HAJI|JUSTICE|COL|CAPT|MAJ|GEN|LT|BRIG|AIR|THAKUR"
    r"|HON|HONOURABLE|THE|MINISTER|DEPUTY|PRIME|SPEAKER|CHAIRMAN|CHAIRPERSON"
    r"|SECRETARY|VICE|PRESIDENT)\b\.?",
)

# Words that mark a heading or procedural line, never a person.
_NON_NAME_WORDS = frozenset(
    "RE MOTION MOTIONS BILL BILLS RESOLUTION STATEMENT STATEMENTS REPORT REPORTS "
    "COMMITTEE QUESTION QUESTIONS ANSWER ANSWERS PAPERS TABLE MATTERS MATTER RULE "
    "DISCUSSION DEMANDS GRANTS BUDGET ORDINANCE AMENDMENT SUBMISSION ANNOUNCEMENT "
    "OBSERVATION RULING ELECTION MESSAGE MESSAGES PETITION PETITIONS ASSENT CHAPTER "
    "APPENDIX ANNEXURE SCHEDULE CLAUSE SECTION ARTICLE NOTE NOTES SUBJECT RESULT "
    "DIVISION AYES NOES TOTAL HRS HOURS ITEM ITEMS PART CONTENTS INDEX".split()
)

_PRESIDING_RE = re.compile(
    r"^(?:(?:MR|MADAM|HON|HONOURABLE|THE)\s+)*"
    r"(?:DEPUTY\s+|VICE\s+)?(?:SPEAKER|SPEAK\s+ER|CHAIRMAN|CHAIRPERSON|CHAIR\s+PERSON|PRESIDENT)"
    r"(?:\s*\(.*\))?$"
    r"|^SECRETARY\s+GENERAL(?:\s*\(.*\))?$"
)

# Same check on letters only, tolerant of common OCR slips:
# "MR, SPEAKER", "MR DEPUT Y-SPEAKER", "MR. SPBAKER", "MR. CHATRMAN", "HON'BLE SPEAKER"
_PRESIDING_COMPACT_RE = re.compile(
    r"^(?:MR|MADAM|HON|HONBLE|HONOURABLE|THE)*(?:D[EB]PUTY|VICE)?"
    r"(?:SP[EBF]{1,2}A?K[EB]R|SPEAKAR|CHA[IT1L]?RM[AE]N|CHAIRPERSON|CHAIRMAM|PRESIDENT)$"
    r"|^SECRETARYGENERAL$"
)


def is_presiding_compact(head: str) -> bool:
    """Presiding-officer check on letters only, ignoring a trailing '(SHRI X)'."""
    head = re.sub(r"\(.*\)\s*$", "", head.upper())
    compact = re.sub(r"[^A-Z]", "", head)
    if _PRESIDING_COMPACT_RE.match(compact):
        return True
    # Heavier OCR damage ("MR. CHAICMAN", "MR. DEPATY-SPEAKER", "MRA. SPEAKER"):
    # fuzzy-match the office after a mandatory MR/MADAM/HON prefix, so ordinary
    # names never qualify.
    for prefix in _FUZZY_PREFIXES:
        if not compact.startswith(prefix):
            continue
        rest = compact[len(prefix):]
        m = re.match(r"^(?:D[EB]PUTY|VICE)?([A-Z]{6,12})$", rest)
        if m and m.group(1)[:2] in ("CH", "SP", "SF", "SB") and any(
            SequenceMatcher(None, m.group(1), target).ratio() >= 0.75
            for target in ("SPEAKER", "CHAIRMAN", "CHAIRPERSON")
        ):
            return True
        # Damaged "DEPUTY" too: match the whole office, with a stricter ratio.
        if rest[:1] == "D" and 11 <= len(rest) <= 16 and any(
            SequenceMatcher(None, rest, target).ratio() >= 0.8
            for target in ("DEPUTYSPEAKER", "DEPUTYCHAIRMAN")
        ):
            return True
    return False


# Prefixes for the fuzzy presiding check; "MRA" is OCR for "MR." ("MRA. SPEAKER").
_FUZZY_PREFIXES = ("MADAM", "HONBLE", "HON", "MRA", "MR")


_MINISTER_RE = re.compile(
    r"^(?:THE\s+)?(?:PRIME\s+MINISTER|DEPUTY\s+MINISTER|MINISTER|MINISTRY)\b"
)

_TRAILING_PAREN_RE = re.compile(r"^(?P<head>.*?)\s*\((?P<inner>[^()]*)\)\s*$")

# Parentheticals that are part of the name, not a constituency: "(DR.)", "(PROF.)", "(SMT.)"
_HONORIFIC_PAREN_RE = re.compile(r"^(?:DR|PROF|SMT|SHRIMATI|MRS|MS|ADV|CAPT|COL|RETD|RETIRED)\.?$")

# A line that is a plausible attribution head (before the colon).
_ATTR_LINE_RE = re.compile(r"^([A-Z][A-Z\s\.\,\(\)\'\/\-]{1,200}?)\s*:\s*(.*)$")


@dataclass(frozen=True)
class Attribution:
    name: str                       # speaker name as written (honorifics kept)
    role: str                       # "member" | "minister" | "presiding_officer"
    constituency: str | None = None
    portfolio: str | None = None    # ministerial office for minister attributions


def _letters_upper(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters if c.isascii())


def _normalize(s: str) -> str:
    s = s.replace("’", "'").replace("“", "").replace("”", "")
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ,;")


def _is_name_like(name: str) -> bool:
    """True when *name* reads like a person's name (with or without honorific)."""
    tokens = re.findall(r"[A-Z][A-Z'\-]*", name.upper())
    if not tokens or len(tokens) > 10:
        return False
    if any(t in _NON_NAME_WORDS for t in tokens):
        return False
    if re.search(r"\d", name):
        return False
    if _START_RE.match(name.upper()):
        return True
    # No honorific: accept short multi-word names only ("PRALHAD JOSHI").
    return 2 <= len(tokens) <= 6


def parse_attribution(raw: str) -> Attribution | None:
    """Parse an attribution head (text before the colon). None if it is not a speaker."""
    s = _normalize(raw)
    s = re.sub(r"^[^A-Z(]+", "", s)          # stray OCR punctuation before the name
    s = re.sub(r"\)+$", ")", s)              # "NAME))" → "NAME)"
    if not s:
        return None
    upper = s.upper()
    flat = re.sub(r"[.\-]", " ", upper)
    flat = re.sub(r"\s+", " ", flat).strip()

    if _PRESIDING_RE.match(flat) or is_presiding_compact(upper):
        return Attribution(name=s, role="presiding_officer")

    if _MINISTER_RE.match(upper):
        m = _TRAILING_PAREN_RE.match(s)
        if m and m.group("inner").strip():
            inner = m.group("inner").strip()
            if _is_name_like(inner):
                return Attribution(name=inner, role="minister", portfolio=m.group("head").strip())
        if "(" not in s and len(s.split()) <= 4:
            # "THE PRIME MINISTER" with no name given
            return Attribution(name=s, role="minister", portfolio=s)
        return None

    # A fragment of a wrapped attribution whose head was not recovered: "PRALHAD JOSHI)"
    if s.count(")") > s.count("("):
        s = s.rstrip(")").strip()

    constituency = None
    m = _TRAILING_PAREN_RE.match(s)
    if m:
        inner = m.group("inner").strip()
        if inner and not _HONORIFIC_PAREN_RE.match(inner.upper()):
            constituency = inner
            s = m.group("head").strip()
    if not _is_name_like(s):
        return None
    return Attribution(name=s, role="member", constituency=constituency)


# ── Title-case attributions (older debates, roughly pre-1970) ─────────────────
#
#   *184. Shri K. K. Das: Will the Minister ...
#   The Honourable Sardar Baldev Singh: (a) Yes.
#   The Minister of Home Affairs (Shri Datar): Yes.
#   Home Affairs, (Shri Datar): Yes.          ← wrapped minister attribution

_TITLE_HONORIFIC = (
    r"(?:Shri|Sbri|Shrl|Sri|Shrimati|Shrimathi|Smt\.?|Sushri|Kumari|Sardar|Sardarni|Dr\.?|Pandit|Pt\.|"
    r"Mr\.?|Mrs\.?|Prof\.?|Seth|Begum|Maulana|Raja|Rani|Rajmata|Thakur|Babu|Acharya|Syed|"
    r"Haji|Giani|Kaka|Chaudhuri|Choudhary|Ch\.|Swami|Mahant|Sant|Lt\.|Col\.|Capt\.|Maj\.|Gen\.|Brig\.)"
)
_TITLE_ATTR_RE = re.compile(
    r"^(?:\*?\s*\d{1,5}\s*[.,]\s*)?\*?\s*"
    r"(?P<head>"
    r"(?:The\s+Hon(?:ou|o)rable\s+|Hon(?:'ble|\.)\s+)?" + _TITLE_HONORIFIC + r"\s+[^:]{1,70}?"
    r"|The\s+(?:Deputy\s+|Prime\s+)?Minister\b[^:]{0,120}?"
    r"|Mr\.?\s+(?:Deputy[\s\-]*)?Speaker|Mr\.?\s+Chairman|Madam\s+(?:Deputy[\s\-]*)?Speaker"
    r"|(?:An|Some|Several)\s+Hon(?:\.|ourable)\s+Members?"
    r")\s*:\s*(?P<body>.*)$"
)
# "<portfolio fragment> (Shri Name): body" — a minister attribution whose head wrapped
_TITLE_PAREN_NAME_RE = re.compile(
    r"^(?P<pre>[A-Z][^():]{0,80}?)\s*\((?P<name>" + _TITLE_HONORIFIC + r"\s+[^()]{2,60})\)\s*:\s*(?P<body>.*)$"
)
_LOWER_WORD_RE = re.compile(r"\b(?!(?:de|ud|bin|van|von|da|di|el|al|ji|alias)\b)[a-z][a-z]+\b")


def match_title_case_attribution(line: str) -> tuple[str, str] | None:
    """
    Recognise a title-case attribution line. Returns (HEAD IN UPPER CASE, body) or None.

    Every word of the name must be capitalised (initials allowed), so a wrapped body
    line such as "Shri Nehru said: ..." is not mistaken for an attribution.
    """
    m = _TITLE_ATTR_RE.match(line)
    if m:
        head = m.group("head").strip()
        name_part = re.sub(r"\(.*?\)", "", head)
        if not head.lower().startswith(("the minister", "the deputy minister", "the prime minister")):
            if _LOWER_WORD_RE.search(name_part) or len(name_part.split()) > 9:
                return None
        return head.upper(), m.group("body").strip()
    m = _TITLE_PAREN_NAME_RE.match(line)
    if m and not _LOWER_WORD_RE.search(m.group("name")):
        pre = m.group("pre").strip(" ,")
        return f"MINISTER {pre} ({m.group('name').strip()})".upper(), m.group("body").strip()
    return None


def _is_head_candidate(s: str) -> bool:
    """First line of a wrapped attribution: upper-case, starts like an attribution, no colon yet."""
    if ":" in s or len(s) > 150 or not _letters_upper(s):
        return False
    if s.endswith((".", "?", "!")) and not re.search(r"\b[A-Z]\.$", s):
        return False
    return bool(_START_RE.match(s)) and not re.match(r"^THE\s+(?:HOUSE|LOK|RAJYA)\b", s)


def _is_continuation(s: str) -> bool:
    return 0 < len(s) <= 150 and ":" not in s and _letters_upper(s) and not s.endswith(("?", "!"))


def _join(parts: list[str]) -> str:
    out = parts[0]
    for p in parts[1:]:
        if out.endswith("-") and not out.endswith(" -"):
            out = out[:-1] + p          # hyphenated line break: CHAU- / DHURI
        else:
            out = out + " " + p
    return out


def assemble_wrapped_attributions(lines: list[str], max_lines: int = 4, max_gap: int = 8) -> list[str]:
    """
    Return a copy of *lines* where attributions wrapped over several lines are joined
    onto the first line (consumed lines become blank, so line positions keep their
    meaning for isolation checks).
    """
    out = list(lines)
    n = len(out)
    i = 0
    while i < n:
        head = out[i].strip()
        if not _is_head_candidate(head):
            i += 1
            continue
        parts = [head]
        used = [i]
        j = i + 1
        while j < n and j - i <= max_gap and len(parts) < max_lines:
            t = out[j].strip()
            if not t:
                j += 1
                continue
            m = _ATTR_LINE_RE.match(t)
            if m and _letters_upper(m.group(1)):
                candidate = _join(parts + [m.group(1).strip()])
                if parse_attribution(candidate) is not None:
                    joined = candidate + ": " + m.group(2) if m.group(2) else candidate + ":"
                    out[i] = joined.rstrip()
                    for k in used[1:] + [j]:
                        out[k] = ""
                    i = j
                break
            if not _is_continuation(t):
                break
            parts.append(t)
            used.append(j)
            j += 1
        i += 1
    return out
