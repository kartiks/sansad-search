#!/usr/bin/env python3
"""
build_names_dict.py — Generate data/names_dict.csv (variant → canonical member name).

Sources (see data/README.md for licences):
  - Lok Sabha members, 1st–18th Lok Sabha:  sansad.in  /api_ls/member?loksabha=N
  - Rajya Sabha members, sitting + former:  sansad.in  /api_rs/member/sitting-members
  - Constituent Assembly members:           Wikidata, holders of Q61945113

One canonical name per person: the directory's own display name ("first last",
honorific dropped), e.g. "Hari Vishnu Kamath". Constituent Assembly members are
linked to a Lok Sabha / Rajya Sabha entry when their Wikidata label or alias is the
same name, so CA and later debates resolve to the same form.

Variants written for each person (lookup is case-insensitive, after
strip_honorifics and normalize_name_form in ingest/canonical/names.py):
  tier 0  full name                         "Hari Vishnu Kamath"
  tier 1  Wikidata aliases; the full name   "Acharya J. B. Kripalani"
          with a title the stripper keeps
  tier 2  initials forms                    "H. Vishnu Kamath", "H. V. Kamath", "H.V. Kamath"
          middle names dropped              "Morarji Desai" (only if no one else has the key)
  tier 3  surname only                      "Kamath"
A lookup key produced by several people is resolved by the lowest tier; a tie means
the key is ambiguous and is left out. Surname-only keys (tier 3) are written only
when no other member in any source has that surname, because the dictionary has no
date context to tell e.g. Mahavir Tyagi from K. C. Tyagi.

This script is not part of the ingestion run. Re-run it by hand and commit the CSV:

    python scripts/build_names_dict.py                       # fetch + write data/names_dict.csv
    python scripts/build_names_dict.py --save-members m.json # also keep the fetched member list
    python scripts/build_names_dict.py --members m.json      # rebuild offline from a saved list
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Iterable

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ingest.canonical.names import strip_honorifics  # noqa: E402

DEFAULT_OUTPUT = APP_DIR / "data" / "names_dict.csv"

LS_URL = "https://sansad.in/api_ls/member"
RS_URL = "https://sansad.in/api_rs/member/sitting-members"
WIKIDATA_URL = "https://query.wikidata.org/sparql"
CA_POSITION = "Q61945113"  # member of the Constituent Assembly of India
USER_AGENT = "SansadSearch-names-dict/1.0 (+https://github.com/kartiks/sansad-search)"
REQUEST_DELAY_S = 1.0
MAX_LOK_SABHA = 30  # stop condition guard; the loop ends at the first empty term

# A CA member with no exact-name match may still be linked through an initials form,
# but only to a member who sat in the early Parliament (1st/2nd Lok Sabha, or a
# Rajya Sabha term starting by this year): the people a CA member could plausibly be.
EARLY_LOK_SABHAS = {1, 2}
EARLY_RS_START_YEAR = 1962

FULL, ALIAS, INITIALS, SURNAME = 0, 1, 2, 3
# Middle names dropped ("Morarji Desai"): kept only when no one else claims the key.
MIDDLE_DROPPED = 2.5

# Service decorations and suffixes that appear inside name fields.
_DECORATIONS = {"avsm", "pvsm", "uysm", "ysm", "vsm", "vrc", "mvc", "retd", "retd.", "tps"}
# Directory "titles" that are not part of how a member is addressed.
_IGNORED_TITLES = {"title", "principal", "km.", "km", "miss", "advocate", "his highness",
                   "her highness", "rt. rev.", "h.h.", "h.h"}
_PARTICLES = {"de", "da", "di", "do", "dos", "of", "van", "von", "bin", "al", "el"}
# Titles some directory entries carry inside the first-name field ("Sardar Hukam").
# Words that are also common given names (Raja, Rani, Babu, Lala, Thakur) are not listed.
_LEADING_TITLES = {"sardar", "sardarni", "pandit", "acharya", "maulana", "molana", "begum",
                   "swami", "mahant", "sadhvi", "haji", "hafiz", "seth", "kunwar", "kunwarani",
                   "rajkumari", "maharaja", "maharani", "maharajkumar", "thiru", "jathedar",
                   "diwan", "kazi", "qazi"}

# Directory titles that are really the first word of the name: "Shri Diwan" +
# "Chand Sharma" is Diwan Chand Sharma, "D. C. Sharma" in the debates.
_NAME_TITLES = {"diwan", "syed", "mirza", "mohammad", "mohd."}


@dataclass(frozen=True)
class Member:
    source: str                     # "ls" | "rs" | "ca"
    source_id: str                  # mpsno or Wikidata QID
    given: str                      # given names ("" when the directory has one field)
    surname: str
    honorific: str = ""
    aliases: tuple[str, ...] = ()
    early: bool = False             # sat in the early Parliament (see EARLY_* above)


# ── Name cleaning and keys ─────────────────────────────────────────────────────

def _space_initials(name: str) -> str:
    """'A.C. George' → 'A. C. George' (same rule as normalize_name_form)."""
    return re.sub(r"\b([A-Za-z])\.(?=[A-Za-z])", r"\1. ", name)


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def lookup_key(name: str) -> str:
    """
    The key canonicalize_name() looks up for an attribution: honorifics stripped,
    initials spaced, whitespace collapsed, lowercased. Title-casing in
    normalize_name_form does not matter here because the lookup ignores case.
    """
    return _collapse(_space_initials(strip_honorifics(name))).lower()


def clean_name_part(raw: str | None) -> str:
    """Remove nicknames, place qualifiers, decorations and stray punctuation."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw)
    s = re.sub(r"`[^`]*`|\"[^\"]*\"", " ", s)              # `Suman`, "Vinnu"
    s = re.sub(r"(?<=[A-Za-z])`(?=[A-Za-z])", "'", s)    # O`brien → O'brien
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\([^)]*\)?", " ", s)                      # (Tai), (Retd.), (alias X)
    s = s.replace(",", " ")
    tokens = [t for t in s.split() if t.lower() not in _DECORATIONS and t.lower() != "alias"]
    s = _collapse(" ".join(tokens)).strip(" ,;:-'")
    if s.endswith(".") and not re.search(r"(?:^|[\s.])[A-Za-z]\.$", s):
        s = s.rstrip(".")                                   # "Prasad." but not "Mohan S."
    s = _space_initials(s)
    s = " ".join(w if w in _PARTICLES or not w.islower() else w.capitalize() for w in s.split())
    letters = [c for c in s if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and not re.fullmatch(r"(?:[A-Z]\.\s?)+", s):
        s = " ".join(w if re.fullmatch(r"[A-Z]\.", w) else w.capitalize() for w in s.split())
    return s


def split_leading_titles(name: str, keep: int = 1) -> tuple[str, str]:
    """'Sardar Hukam' → ('Sardar', 'Hukam'). The name keeps at least *keep* words."""
    toks = name.split()
    i = 0
    while i < len(toks) - keep and toks[i].lower().rstrip(".") in _LEADING_TITLES:
        i += 1
    return " ".join(toks[:i]), " ".join(toks[i:])


def split_directory_name(given: str | None, surname: str | None) -> tuple[str, str, str]:
    """
    Split a directory (first, last) pair into cleaned (given, surname, title), where
    title holds any leading title words found in the name ("Sardar", "Pandit").
    Handles last-name fields that hold "Surname, Shri Given" with no first name.
    """
    given = (given or "").strip()
    surname = (surname or "").strip()
    if not given and "," in surname:
        head, _, tail = surname.partition(",")
        if strip_honorifics(tail.strip()) != tail.strip():
            surname, given = head, strip_honorifics(tail.strip())
    g = clean_name_part(strip_honorifics(given)) if given else ""
    s = clean_name_part(surname)
    if g:
        title, g = split_leading_titles(g)
    else:
        title, s = split_leading_titles(s, keep=2)   # "Sardar Singh" is a name
    return g, s, title


def _unstripped_title(title: str) -> str:
    """The part of a directory title strip_honorifics keeps: 'Shri' → '', 'Col. Syed' → 'Syed'."""
    probe = " Zzplaceholder"
    rest = strip_honorifics(title + probe)
    return rest[: -len(probe)].strip() if rest.endswith(probe) else ""


def _is_ascii_name(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def usable_aliases(member: Member) -> list[str]:
    """
    Wikidata aliases that are other spellings of the member's name. Epithets
    ("Lok Nayak", "Bihar Kesari") and nicknames share no word with the name and are
    dropped: debates use them loosely, sometimes for other people.
    """
    name_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", _full_name(member))}
    out = []
    for alias in member.aliases:
        alias = " ".join(w.capitalize() if w.islower() else w
                         for w in clean_name_part(alias).split())
        words = re.findall(r"[A-Za-z]{3,}", alias)
        if (len(alias) < 4 or not _is_ascii_name(alias) or re.search(r"\d", alias)
                or len(alias.split()) > 6 or not name_words & {w.lower() for w in words}):
            continue
        out.append(alias)
    return out


def full_initials(name: str) -> str | None:
    """'Ganesh Vasudev Mavalankar' → 'G. V. Mavalankar'; None with fewer than two initials."""
    toks = name.split()
    if len(toks) < 3:
        return None
    return " ".join(_initial(t) for t in toks[:-1]) + " " + toks[-1]


def _initial(token: str) -> str:
    letter = token.lstrip("'")[:1]
    return letter.upper() + "."


def _is_initial(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]\.?", token))


# ── Variant generation ─────────────────────────────────────────────────────────

@dataclass
class Variant:
    display: str
    tier: int
    surname_key: str | None = None   # set on tier-3 variants


def _name_tokens(given: str, surname: str) -> tuple[list[str], list[str], bool]:
    """(given tokens, surname tokens, surname_only_allowed)."""
    g, s = given.split(), surname.split()
    if not g and len(s) > 1:
        # One-field directory entry ("Lahri Singh"): we cannot tell which part is
        # the surname, so initials use the last token and no surname-only form.
        return s[:-1], s[-1:], False
    return g, s, bool(g)


def initials_forms(given_tokens: list[str], surname_tokens: list[str]) -> list[str]:
    """
    Progressively initialise given names from the left, in spaced and compact form:
    ['Hari','Vishnu'] + ['Kamath'] → 'H. Vishnu Kamath', 'H. V. Kamath', 'H.V. Kamath'.
    """
    out: list[str] = []
    for i in range(1, len(given_tokens) + 1):
        if all(_is_initial(t) for t in given_tokens[:i]) and i < len(given_tokens):
            continue
        inits = [_initial(t) for t in given_tokens[:i]]
        rest = given_tokens[i:] + surname_tokens
        out.append(" ".join(inits + rest))
        if len(inits) > 1:
            out.append("".join(inits) + " " + " ".join(rest))
    return out


def variants_for(member: Member, full: str) -> list[Variant]:
    """All variants of one directory entry. *full* is the entry's own full name."""
    g, s, surname_ok = _name_tokens(member.given, member.surname)
    out = [Variant(full, FULL)]
    out += [Variant(v, INITIALS) for v in initials_forms(g, s)]
    surname = " ".join(s)
    if len(g) >= 2 and not _is_initial(g[0]) and surname_ok:
        # Middle names dropped: "Morarji Ranchhodji Desai" → "Morarji Desai"
        out.append(Variant(f"{g[0]} {surname}", MIDDLE_DROPPED))
    if surname_ok and len(surname.replace(".", "")) >= 3 and not _is_initial(surname):
        out.append(Variant(surname, SURNAME, lookup_key(surname)))

    for alias in usable_aliases(member):
        toks = alias.split()
        if len(toks) == 1:
            out.append(Variant(alias, SURNAME, lookup_key(alias)))
            continue
        out.append(Variant(alias, ALIAS))

    # Titles strip_honorifics keeps ("Acharya", "Sardar", "Pandit") become part of
    # the looked-up key, so write the titled forms too.
    title = _collapse(re.sub(r"\([^)]*\)?", " ", member.honorific))   # "Capt.(Retd.)" → "Capt."
    title = _unstripped_title(_space_initials(title)) if title else ""
    if title and title.lower() not in _IGNORED_TITLES and _is_ascii_name(title):
        out += [Variant(f"{title} {v.display}", max(v.tier, ALIAS), v.surname_key) for v in list(out)]

    _demote_single_words(out)
    return out


def _demote_single_words(variants: list[Variant]) -> None:
    """
    A one-word key ("Mayawati", "Rawat") or one that strip_honorifics shortens
    ("Major Singh" → "Singh") is only as specific as a surname, so it gets the
    surname-uniqueness check.
    """
    for v in variants:
        key = lookup_key(v.display)
        if v.tier < SURNAME and (len(key.split()) == 1 or strip_honorifics(v.display) != v.display):
            v.tier, v.surname_key = SURNAME, key


# ── Dictionary build ───────────────────────────────────────────────────────────

@dataclass
class BuildResult:
    rows: list[tuple[str, str]]
    stats: dict[str, int] = field(default_factory=dict)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)


def _full_name(member: Member) -> str:
    return _collapse(f"{member.given} {member.surname}")


def _fold_name_title(member: Member) -> Member:
    """Move a title that is really part of the name into the given names."""
    words = member.honorific.split()
    if not words or words[-1].lower() not in _NAME_TITLES:
        return member
    return replace(
        member,
        given=_collapse(f"{words[-1]} {member.given}"),
        honorific=" ".join(words[:-1]),
    )


def _same_token(a: str, b: str) -> bool:
    """Equal, or one is the other's initial ("K." / "Krishna")."""
    a, b = a.lower().rstrip("."), b.lower().rstrip(".")
    if a == b:
        return True
    if len(a) == 1 and len(b) > 1:
        return b.startswith(a)
    if len(b) == 1 and len(a) > 1:
        return a.startswith(b)
    return False


def _fuller_spellings(names: list[str]) -> dict[str, str]:
    """
    Map a name to the one fuller spelling of the same person elsewhere in the
    directories: "Lal K. Advani" (Rajya Sabha) → "Lal Krishna Advani" (Lok Sabha).

    The names must have the same surname and number of words, agree word for word
    (equal, or an initial of the other), and share at least one full given name,
    so "S. Singh" is never merged into "Sant Singh". A name with two or more fuller
    candidates is left alone.
    """
    by_shape: dict[tuple[str, int], set[str]] = defaultdict(set)
    for n in names:
        toks = n.split()
        if len(toks) >= 3:
            by_shape[(toks[-1].lower(), len(toks))].add(n)

    def letters(n: str) -> int:
        return sum(c.isalpha() for c in n)

    out: dict[str, str] = {}
    for group in by_shape.values():
        for n in group:
            toks = n.split()
            cands = [
                o for o in group
                if o != n and letters(o) > letters(n)
                and all(_same_token(a, b) for a, b in zip(toks, o.split()))
                and any(a.lower() == b.lower() and not _is_initial(a)
                        for a, b in zip(toks[:-1], o.split()[:-1]))
            ]
            if len(cands) == 1:
                out[n] = cands[0]
    return out


def build_rows(members: Iterable[Member]) -> BuildResult:
    """Resolve members into (variant, canonical_name) rows. Pure; no network."""
    folded_from: dict[int, Member] = {}
    folded: list[Member] = []
    for m in members:
        f = _fold_name_title(m)
        if f is not m:
            folded_from[id(f)] = m
        folded.append(f)
    members = folded
    sansad = [m for m in members if m.source in ("ls", "rs")]
    ca = [m for m in members if m.source == "ca"]

    # One display string per full-name key, first source wins (LS, then RS, then CA).
    canon_by_key: dict[str, str] = {}

    def canonical_for(name: str) -> str:
        return canon_by_key.setdefault(lookup_key(name), name)

    fuller = _fuller_spellings([_full_name(m) for m in sansad])
    assigned: list[tuple[Member, str]] = []
    for m in sansad:
        full = _full_name(m)
        if full:
            assigned.append((m, canonical_for(fuller.get(full, full))))

    # Link CA members to a sansad entry: (1) label or alias equals a full name;
    # (2) for early-Parliament members only, names agree once given names are
    # initialised, with at least two initials ("Ganesh Vasudev Mavalankar" and
    # "Ganesh Vasudeo Mavalankar" are both "G. V. Mavalankar").
    exact: dict[str, set[str]] = defaultdict(set)
    early_initials: dict[str, set[str]] = defaultdict(set)
    for m, c in assigned:
        exact[lookup_key(_full_name(m))].add(c)
        fi = full_initials(_full_name(m))
        if m.early and fi:
            early_initials[lookup_key(fi)].add(c)

    def _hits(index: dict[str, set[str]], keys: set[str]) -> set[str]:
        return set().union(*(index.get(k, set()) for k in keys))

    linked = 0
    for m in ca:
        names = [_full_name(m)] + usable_aliases(m)
        hits = _hits(exact, {lookup_key(n) for n in names})
        if not hits:
            hits = _hits(early_initials, {lookup_key(fi) for n in names if (fi := full_initials(n))})
        if len(hits) == 1:
            linked += 1
            assigned.append((m, next(iter(hits))))
        else:
            assigned.append((m, canonical_for(_full_name(m))))

    # Who owns each surname, across every source (whether or not we emit it).
    surname_owners: dict[str, set[str]] = defaultdict(set)
    for m, c in assigned:
        g, s, _ = _name_tokens(m.given, m.surname)
        surname_owners[lookup_key(" ".join(s))].add(c)
        surname_owners[lookup_key(c.split()[-1])].add(c)

    # key → canonical → (best tier, displays, surname keys)
    by_key: dict[str, dict[str, list]] = defaultdict(dict)
    for m, c in assigned:
        own_full = _full_name(m)
        vs = variants_for(m, own_full)
        if id(m) in folded_from:
            # Debates also omit the folded word: "Bashir Husain Zaidi" for Syed Bashir Husain Zaidi.
            original = folded_from[id(m)]
            for v in variants_for(original, _full_name(original)):
                v.tier = max(v.tier, ALIAS)
                vs.append(v)
        if own_full != c:
            # Linked CA member or differently spelled duplicate: its own name is an alias.
            for v in vs:
                if v.tier == FULL:
                    v.tier = ALIAS
            vs.insert(0, Variant(c, FULL))
            _demote_single_words(vs)
        for v in vs:
            key = lookup_key(v.display)
            if not key:
                continue
            entry = by_key[key].setdefault(c, [v.tier, set(), set()])
            entry[0] = min(entry[0], v.tier)
            entry[1].add(v.display)
            if v.surname_key:
                entry[2].add(v.surname_key)

    rows: list[tuple[str, str]] = []
    ambiguous: dict[str, list[str]] = {}
    for key, entries in by_key.items():
        if len(entries) > 1:
            # A middle-name-dropped form yields to anyone else claiming the key.
            entries = {c: e for c, e in entries.items() if e[0] != MIDDLE_DROPPED} or entries
            if len(entries) > 1 and all(e[0] == MIDDLE_DROPPED for e in entries.values()):
                ambiguous[key] = sorted(entries)
                continue
        best = min(e[0] for e in entries.values())
        winners = [c for c, e in entries.items() if e[0] == best]
        if len(winners) > 1:
            ambiguous[key] = sorted(winners)
            continue
        c = winners[0]
        tier, displays, surname_keys = entries[c]
        if tier == SURNAME:
            owners = set(entries)
            for sk in surname_keys:
                owners |= surname_owners.get(sk, set())
            if owners != {c}:
                ambiguous[key] = sorted(owners)
                continue
        seen: set[str] = set()
        for d in sorted(displays):
            norm = _collapse(d).lower()
            if norm not in seen:
                seen.add(norm)
                rows.append((d, c))

    rows.sort(key=lambda r: (r[1].lower(), r[0].lower()))
    stats = {
        "members_ls": sum(m.source == "ls" for m in members),
        "members_rs": sum(m.source == "rs" for m in members),
        "members_ca": len(ca),
        "ca_linked": linked,
        "canonical_names": len({c for _, c in rows}),
        "rows": len(rows),
        "ambiguous_keys": len(ambiguous),
    }
    return BuildResult(rows, stats, ambiguous)


def write_csv(rows: list[tuple[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["variant", "canonical_name"])
        w.writerows(rows)


# ── Source parsing (pure) ──────────────────────────────────────────────────────

def parse_ls_members(pages: dict[int, list[dict]]) -> list[Member]:
    """Lok Sabha API pages keyed by Lok Sabha number → one Member per mpsno."""
    by_id: dict[int, dict] = {}
    terms: dict[int, set[int]] = defaultdict(set)
    for ls_no, records in sorted(pages.items()):
        for r in records:
            by_id.setdefault(r["mpsno"], r)
            terms[r["mpsno"]].add(int(ls_no))
    out = []
    for mpsno, r in sorted(by_id.items()):
        given, surname, title = split_directory_name(r.get("firstName"), r.get("lastName"))
        if not (given or surname):
            continue
        out.append(Member("ls", str(mpsno), given, surname,
                          honorific=_collapse(f"{r.get('initial') or ''} {title}"),
                          early=bool(terms[mpsno] & EARLY_LOK_SABHAS)))
    return out


def parse_rs_members(records: list[dict]) -> list[Member]:
    """Rajya Sabha sitting-members records (mpFlag empty = all) → Members."""
    out, seen = [], set()
    for r in records:
        if r["mpsno"] in seen:
            continue
        seen.add(r["mpsno"])
        given, surname, title = split_directory_name(r.get("firstName"), r.get("lastName"))
        if not (given or surname):
            continue
        m = re.match(r"\s*(\d{4})", r.get("term") or "")
        early = bool(m and int(m.group(1)) <= EARLY_RS_START_YEAR)
        out.append(Member("rs", str(r["mpsno"]), given, surname,
                          honorific=_collapse(f"{r.get('initial') or ''} {title}"), early=early))
    return out


def parse_wikidata_members(bindings: list[dict]) -> list[Member]:
    """SPARQL JSON bindings (item, label, aliases) → CA Members."""
    out = []
    for b in bindings:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        label = clean_name_part(b["label"]["value"])
        if not label or not _is_ascii_name(label):
            continue
        aliases = tuple(a for a in (b.get("aliases", {}).get("value") or "").split("|") if a)
        title, label = split_leading_titles(label, keep=2)
        toks = label.split()
        out.append(Member("ca", qid, " ".join(toks[:-1]), toks[-1], honorific=title, aliases=aliases))
    return out


# ── Fetching ───────────────────────────────────────────────────────────────────

def _get_json(client, url: str, params: dict) -> dict:
    for attempt in range(3):
        try:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch_members(client, delay: float = REQUEST_DELAY_S) -> list[Member]:
    """Fetch all three sources. *client* is an httpx.Client (or compatible)."""
    ls_pages: dict[int, list[dict]] = {}
    for n in range(1, MAX_LOK_SABHA + 1):
        data = _get_json(client, LS_URL, {"loksabha": n, "page": 1, "size": 2000, "sitting": ""})
        records = data.get("membersDtoList") or []
        if not records:
            break
        ls_pages[n] = records
        print(f"  Lok Sabha {n}: {len(records)} members", file=sys.stderr)
        time.sleep(delay)

    rs_records: list[dict] = []
    page = 1
    while True:
        data = _get_json(client, RS_URL, {"state": "", "party": "", "page": page, "size": 1000,
                                          "search": "", "locale": "en", "mpFlag": ""})
        rs_records += data.get("records") or []
        if page >= (data.get("_metadata") or {}).get("totalPages", 0):
            break
        page += 1
        time.sleep(delay)
    print(f"  Rajya Sabha: {len(rs_records)} members", file=sys.stderr)

    query = (
        'SELECT ?item ?label (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases) WHERE { '
        f"?item wdt:P39 wd:{CA_POSITION} . "
        '?item rdfs:label ?label FILTER(lang(?label)="en") '
        'OPTIONAL { ?item skos:altLabel ?alias FILTER(lang(?alias)="en") } '
        "} GROUP BY ?item ?label"
    )
    data = _get_json(client, WIKIDATA_URL, {"query": query, "format": "json"})
    bindings = data["results"]["bindings"]
    print(f"  Constituent Assembly (Wikidata): {len(bindings)} members", file=sys.stderr)

    return parse_ls_members(ls_pages) + parse_rs_members(rs_records) + parse_wikidata_members(bindings)


def _save_members(members: list[Member], path: Path) -> None:
    path.write_text(json.dumps([asdict(m) for m in members], ensure_ascii=False, indent=0), encoding="utf-8")


def _load_members(path: Path) -> list[Member]:
    return [Member(**{**d, "aliases": tuple(d.get("aliases") or ())})
            for d in json.loads(path.read_text(encoding="utf-8"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--members", type=Path, help="build from a saved member list instead of fetching")
    ap.add_argument("--save-members", type=Path, help="write the fetched member list here")
    ap.add_argument("--report-ambiguous", type=Path, help="write ambiguous keys (JSON) here")
    args = ap.parse_args(argv)

    if args.members:
        members = _load_members(args.members)
    else:
        import httpx

        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120) as client:
            members = fetch_members(client)
    if args.save_members:
        _save_members(members, args.save_members)

    result = build_rows(members)
    write_csv(result.rows, args.output)
    if args.report_ambiguous:
        args.report_ambiguous.write_text(json.dumps(result.ambiguous, indent=1, sort_keys=True))
    for k, v in result.stats.items():
        print(f"{k}: {v}", file=sys.stderr)
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
