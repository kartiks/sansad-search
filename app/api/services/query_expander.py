"""
Query expansion service for SansadSearch.

Reads synonyms from data/synonyms.json (NNG-4 — the sole source).

Server-side responsibilities:
  1. Strip stop words from query (preserves quoted phrases verbatim).
  2. Detect phrase synonyms: if the full phrase (consecutive tokens) is present
     in the query, add sibling terms to expansion_notice and mark those token
     positions as consumed.
  3. Detect single-term synonyms: for each non-consumed token that exactly
     matches a synonym group member, add sibling terms to expansion_notice.
  4. Return (clean_query, expansion_notice).

Meilisearch handles actual synonym expansion at search time via the synonym
pairs configured in the index (loaded by setup_meilisearch.py).  This module
generates only the expansion_notice array for the "Also searching for:" strip.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

# ── Stop words ────────────────────────────────────────────────────────────────

_STOP_WORDS: frozenset = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "that", "this", "these", "those", "it", "its", "which", "who", "what",
    "when", "where", "how", "why", "all", "each", "every", "both", "more",
    "most", "other", "some", "such", "no", "not", "only", "same", "than",
    "too", "very", "just", "any", "if", "as", "so",
})

# ── Synonyms loading ──────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_SYNONYMS_PATH = _DATA_DIR / "synonyms.json"

# Module-level cache; replaced with an empty list on load failure.
_SYNONYMS_CACHE: Optional[List[List[str]]] = None


def load_synonyms() -> List[List[str]]:
    """
    Load synonym groups from data/synonyms.json.
    Returns a list of groups; each group is a list of equivalent strings.
    Result is cached after the first load.
    """
    global _SYNONYMS_CACHE
    if _SYNONYMS_CACHE is not None:
        return _SYNONYMS_CACHE

    try:
        with open(_SYNONYMS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        _SYNONYMS_CACHE = []
        return _SYNONYMS_CACHE

    groups: List[List[str]] = []
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            for group in value:
                if isinstance(group, list) and len(group) >= 2:
                    groups.append([str(t) for t in group])

    _SYNONYMS_CACHE = groups
    return _SYNONYMS_CACHE


def _reset_cache() -> None:
    """Reset the module-level synonym cache (test-only helper)."""
    global _SYNONYMS_CACHE
    _SYNONYMS_CACHE = None


# ── Tokenization ──────────────────────────────────────────────────────────────

# Tokens include alphanumerics plus /  .  - to handle SC/ST, Art., zero-hour.
_TOKEN_RE = re.compile(r"[a-zA-Z0-9/\.\-]+")
_QUOTED_RE = re.compile(r'"[^"]*"')


def _tokenize(text: str) -> List[str]:
    """Return a list of lowercase tokens from *text*."""
    return _TOKEN_RE.findall(text.lower())


# ── Stop-word stripping ───────────────────────────────────────────────────────

def strip_stop_words(query: str) -> Tuple[str, bool]:
    """
    Strip stop words from *query*, preserving quoted phrases verbatim.

    Returns:
        (clean_query, is_only_stopwords)
        - clean_query: query string with unquoted stop words removed.
        - is_only_stopwords: True when the result has no non-stop-word content.
    """
    # Normalize smart/curly quotes → ASCII straight quotes so phrase detection
    # works regardless of keyboard or OS (macOS/iOS auto-convert " to “”).
    query = query.replace('“', '"').replace('”', '"')

    # Extract quoted phrases → placeholder so they survive intact.
    placeholders: dict = {}
    working = query
    for i, match in enumerate(_QUOTED_RE.finditer(query)):
        ph = f"\x00QPHRASE{i}\x00"
        placeholders[ph] = match.group(0)
        working = working.replace(match.group(0), ph, 1)

    kept: List[str] = []
    for token in working.split():
        if token in placeholders:
            kept.append(placeholders[token])
        elif token.lower() not in _STOP_WORDS:
            kept.append(token)

    clean = " ".join(kept).strip()
    is_only_stopwords = not bool(_TOKEN_RE.search(clean))
    return clean, is_only_stopwords


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_phrase_in_tokens(
    phrase_tokens: List[str], query_tokens: List[str]
) -> int:
    """
    Return the start index of *phrase_tokens* in *query_tokens*, or -1.
    Matching is case-sensitive on already-lowercased inputs.
    """
    n = len(phrase_tokens)
    if n == 0:
        return -1
    for i in range(len(query_tokens) - n + 1):
        if query_tokens[i : i + n] == phrase_tokens:
            return i
    return -1


# ── Public expansion function ─────────────────────────────────────────────────

def expand_query(
    query: str,
    synonyms_data: Optional[List[List[str]]] = None,
) -> Tuple[str, List[str]]:
    """
    Expand *query* using the synonym dictionary.

    Args:
        query:         The raw (possibly already truncated) query string.
        synonyms_data: Synonym groups to use; defaults to loading from disk.

    Returns:
        (clean_query, expansion_notice)
        - clean_query:       Query with stop words stripped (sent to Meilisearch).
        - expansion_notice:  Sibling terms triggered by synonym matches, excluding
                             any term already present in the original query.
                             Deduped; insertion-ordered.
    """
    clean_query, _ = strip_stop_words(query)

    if synonyms_data is None:
        synonyms_data = load_synonyms()

    query_tokens = _tokenize(query)          # all tokens (incl. stop words)
    original_token_set = set(query_tokens)   # for fast "already in query" checks

    expansion: List[str] = []
    seen_lower: set = set()
    consumed_indices: set = set()            # token positions used by phrase matches

    def _already_in_query(member: str) -> bool:
        """True when every token of *member* is already in query_tokens."""
        mtok = _tokenize(member.lower())
        if not mtok:
            return True
        if len(mtok) == 1:
            return mtok[0] in original_token_set
        return _find_phrase_in_tokens(mtok, query_tokens) >= 0

    def _add_expansion(member: str) -> None:
        lower = member.lower()
        if lower in seen_lower:
            return
        if _already_in_query(member):
            return
        expansion.append(member)
        seen_lower.add(lower)

    # ── Phase 1: phrase synonyms (members with ≥2 tokens) ────────────────────
    for group in synonyms_data:
        for member in group:
            member_tokens = _tokenize(member.lower())
            if len(member_tokens) < 2:
                continue
            start = _find_phrase_in_tokens(member_tokens, query_tokens)
            if start < 0:
                continue
            # Consume the matched token positions.
            for idx in range(start, start + len(member_tokens)):
                consumed_indices.add(idx)
            # Add sibling terms to expansion_notice.
            for other in group:
                if other != member:
                    _add_expansion(other)

    # ── Phase 2: single-term synonyms (non-consumed token positions) ──────────
    for i, token in enumerate(query_tokens):
        if i in consumed_indices:
            continue
        for group in synonyms_data:
            matched_member: Optional[str] = None
            for member in group:
                member_tokens = _tokenize(member.lower())
                if len(member_tokens) == 1 and member_tokens[0] == token:
                    matched_member = member
                    break
            if matched_member is not None:
                for other in group:
                    if other != matched_member:
                        _add_expansion(other)

    return clean_query, expansion
