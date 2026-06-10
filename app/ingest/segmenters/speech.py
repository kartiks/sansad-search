"""
Speech segmenter.

Converts a raw record dict (from html_parser or pdf_parser) into a list of
Speech unit dicts, one per attributed speech. Handles all proceeding types and
all four language handling cases (English, translated Hindi, bilingual,
Hindi-only).

Excluded from output:
- Unattributed speech: "SEVERAL HON. MEMBERS", "AN HON. MEMBER", "SOME HON. MEMBERS", etc.
- Presiding officer interventions (speaker_role == 'presiding_officer').
- Procedural interruptions (points of order, rulings, division votes).

NOTE: sequence_within_sitting is NOT assigned by the segmenter. It is assigned
at the corpus-orchestrator level across all speech and Q+A records within a
sitting in document order (ARCHITECTURE.md §5 — Unified sitting-level sequence).

Each returned dict has the shape expected by ingest.indexer and DATA-MODELS.md 1.1.
"""

from __future__ import annotations

import re
from typing import Any

# ── Attribution patterns ──────────────────────────────────────────────────────

# Unattributed speaker strings — never become standalone records
_UNATTRIBUTED_RE = re.compile(
    r"^(SEVERAL\s+HON\.?\s+MEMBERS?|AN\s+HON\.?\s+MEMBER|SOME\s+HON\.?\s+MEMBERS?"
    r"|HON\.?\s+MEMBERS?|MEMBERS?|HONOURABLE\s+MEMBERS?)\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Presiding officers — excluded as standalone records
_PRESIDING_OFFICER_RE = re.compile(
    r"^(MR\.?\s+SPEAKER|THE\s+SPEAKER|MADAM\s+SPEAKER|THE\s+DEPUTY\s+SPEAKER"
    r"|HON\.?\s+(?:DEPUTY\s+)?SPEAKER"   # elibrary Tika format uses "HON. SPEAKER"
    r"|MR\.?\s+CHAIRMAN|THE\s+CHAIRMAN|THE\s+DEPUTY\s+CHAIRMAN"
    r"|VICE[\s\-]CHAIRMAN|THE\s+PRESIDENT|MR\.?\s+PRESIDENT)\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Attribution line pattern: "SHRI NARENDRA MODI :" or "DR. MANMOHAN SINGH:"
# Matches a speaker name that fills the ENTIRE line (nothing after the colon).
_ATTRIBUTION_RE = re.compile(
    r"^([A-Z][A-Z\s\.\,\(\)\'\/\-]{1,150})\s*:\s*$",
)

# Inline attribution pattern: "SHRI NAME (CONSTITUENCY): text..."
# Used in Tika-extracted elibrary.sansad.in text where the speaker name and the
# first sentence of the speech appear on the same line.
# Checked only when _ATTRIBUTION_RE does not match; captures (speaker, body).
_INLINE_ATTRIBUTION_RE = re.compile(
    r"^([A-Z][A-Z\s\.\,\(\)\'\/\-]{1,150})\s*:\s+(.+)",
)

# Trailing constituency/role parenthetical: "(VIRUDHUNAGAR)", "(GODDA)", etc.
# Stripped from speaker names extracted from inline attributions.
# Does NOT strip mid-name parentheticals like "(PROF.)" — only the trailing one.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Honorific prefixes (used for speaker_role detection heuristic)
_HONORIFICS = frozenset([
    "shri", "smt", "smt.", "dr", "dr.", "prof", "prof.", "adv", "adv.",
    "kumari", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
])

# Translation markers
_TRANSLATION_RE = re.compile(
    r"\[(?:Translation|TRANSLATION|Tr\.?|English\s+translation)\]",
    re.IGNORECASE,
)
_HINDI_SCRIPT_RE = re.compile(r"[ऀ-ॿ]")

# Minimum English characters before first Hindi/marker to classify as bilingual (mixed)
_BILINGUAL_THRESHOLD = 50

# ── Adjacent Speech Merging break signals (F01, PRD v3.0) ─────────────────────
#
# A break signal between two consecutive same-speaker speeches prevents merging.
# Three kinds:
#   1. A different speaker (handled structurally — a new attribution / an
#      excluded speaker resets the merge group).
#   2. A section heading (H1/H2/H3 in HTML). In the flat text the parsers emit,
#      HTML markup is gone, so headings are recovered as ALL-CAPS standalone
#      lines (see _is_section_heading). CA uses the parser-assigned subject
#      instead (a subject change is the heading boundary) — far more reliable.
#   3. A procedural entry: a question-number heading, a block header
#      ("QUESTIONS" / "STARRED QUESTION NO. X"), or a formal marker
#      ("The House adjourned ...").
#
# BUILD-TIME VERIFICATION FINDING (ARCHITECTURE.md §8, item 6 — merge break
# detection per format): In HTML-derived flat text and IA pre-OCR / PDF text,
# structural H-tags are not preserved, so section-heading breaks are recovered
# heuristically from ALL-CAPS standalone lines and the procedural patterns
# below. Title-case headings in flat text are NOT reliably recoverable and may
# be under-detected (risking over-merge); ALL-CAPS headers and procedural
# markers ARE recoverable. CA (coi HTML) carries an explicit per-speech subject,
# so CA heading boundaries are detected exactly via subject change, not text
# heuristics. Finding recorded: 2026-06-06.
_PROCEDURAL_BREAK_RE = re.compile(
    r"^(?:"
    r"(?:STARRED\s+|UNSTARRED\s+)?QUESTIONS?\s*$"                 # QUESTIONS / STARRED QUESTIONS
    r"|(?:STARRED\s+|UNSTARRED\s+)?QUESTION\s+NO[\.:\s]*\d+"       # STARRED QUESTION NO. X
    r"|Q\.?\s*NO[\.:\s]*\d+"
    r"|ORAL\s+ANSWERS?\b"
    r"|WRITTEN\s+ANSWERS?\b"
    r"|THE\s+HOUSE\s+(?:THEN\s+)?(?:ADJOURNED|RE-?ASSEMBLED|MET)\b"  # formal markers
    r")",
    re.IGNORECASE,
)


def _is_section_heading(line: str) -> bool:
    """
    Heuristic ALL-CAPS section-heading detector for flat (non-HTML) text.

    Conservative by design: only an isolated, short, ALL-CAPS line that is not
    an attribution, not unattributed/presiding boilerplate, and not a full
    sentence is treated as a heading. Title-case headings are intentionally not
    matched here (not reliably separable from body text) — see the build-time
    finding above.
    """
    s = line.strip()
    if not s or len(s) > 80:
        return False
    if s.endswith(":"):                      # attribution-like
        return False
    if s.endswith((".", "?", "!")):          # sentence/body, not a heading
        return False
    if _ATTRIBUTION_RE.match(s) or _is_unattributed(s) or _is_presiding_officer(s):
        return False
    words = s.split()
    if len(words) > 12:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


def _is_break_line(line: str) -> bool:
    """True when an isolated line is a procedural marker or a section heading."""
    return bool(_PROCEDURAL_BREAK_RE.match(line.strip())) or _is_section_heading(line)


def _is_unattributed(speaker: str) -> bool:
    return bool(_UNATTRIBUTED_RE.match(speaker.strip()))


def _is_presiding_officer(speaker: str) -> bool:
    return bool(_PRESIDING_OFFICER_RE.match(speaker.strip()))


def _speaker_role(speaker: str) -> str:
    if _PRESIDING_OFFICER_RE.match(speaker.strip()):
        return "presiding_officer"
    return "member"


def _count_english_before_hindi_or_marker(text: str) -> int:
    """Count English characters before the first Hindi script or [Translation] marker."""
    chars = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _HINDI_SCRIPT_RE.search(stripped) or _TRANSLATION_RE.search(stripped):
            break
        chars += len(stripped)
    return chars


def _compute_lang_original(text: str) -> str:
    """
    Derive lang_original per F01 Language Handling rules.

    Returns 'en', 'hi', or 'mixed':
    - Case 1 (no Hindi script, no translation marker): 'en'
    - Case 4 (Hindi script, no translation marker): 'hi'
    - Case 2 (Hindi + translation, predominantly Hindi): 'hi'
    - Case 3 (Hindi + translation, significant English before first Hindi): 'mixed'
    """
    has_hindi = bool(_HINDI_SCRIPT_RE.search(text))
    has_marker = bool(_TRANSLATION_RE.search(text))

    if not has_hindi:
        return "en"  # Cases 1 and any English-only text with marker

    if not has_marker:
        return "hi"  # Case 4: Hindi only, no translation

    # Case 2 or 3: has both Hindi and translation marker
    # Measure English content before the first Hindi/marker line to distinguish
    en_before = _count_english_before_hindi_or_marker(text)
    if en_before >= _BILINGUAL_THRESHOLD:
        return "mixed"  # Case 3: genuinely bilingual
    return "hi"  # Case 2: predominantly Hindi with translation


def _detect_language_handling(text: str) -> tuple[str | None, bool, bool]:
    """
    Analyse speech text and return (full_text_en, is_translated, has_untranslated_content).

    Rules (applied in order per F01 Language Handling):
    1. No Hindi script + no translation marker → pure English
    2. Translation marker present → translated Hindi portions present
    3. Both Hindi script and English text → bilingual
    4. Only Hindi script, no translation marker → no translation available
    """
    has_hindi_script = bool(_HINDI_SCRIPT_RE.search(text))
    has_translation_marker = bool(_TRANSLATION_RE.search(text))

    if not has_hindi_script and not has_translation_marker:
        # Case 1: English verbatim
        return text.strip() or None, False, False

    if has_translation_marker:
        # Case 2 or 3: Extract text after translation markers (and English portions)
        en_text = _extract_english_portions(text)
        return en_text or None, True, False

    if has_hindi_script:
        # Case 4: Hindi only, no translation
        return None, False, True

    return text.strip() or None, False, False


def _extract_english_portions(text: str) -> str:
    """
    For bilingual and translated texts: collect English content.
    Translation markers are stripped; Hindi-only lines are excluded.
    """
    lines = text.splitlines()
    english_lines: list[str] = []
    in_translation_block = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if _TRANSLATION_RE.match(stripped):
            in_translation_block = True
            continue

        # Line is purely Devanagari — skip unless we're in a translation block
        if _HINDI_SCRIPT_RE.search(stripped):
            if not in_translation_block:
                continue
            if all(_HINDI_SCRIPT_RE.match(ch) or not ch.strip() for ch in stripped):
                continue

        english_lines.append(stripped)
        in_translation_block = False  # reset after non-Hindi line

    return " ".join(english_lines).strip()


def _count_words(text: str | None) -> int | None:
    """Count words in text; return None when text is None."""
    if text is None:
        return None
    return len(text.split())


def _tokenize(raw_text: str) -> list[tuple[str, ...]]:
    """
    Tokenize parliamentary text into an ordered stream of:
        ("speech", speaker, body)   — one attributed speech
        ("break", text)             — a section heading or procedural marker

    A line is treated as a break only when it is *isolated* (preceded and
    followed by a blank line or a document boundary) and matches a break
    pattern; this prevents an emphatic ALL-CAPS line inside a speech body from
    splitting that body. Break tokens belong to no speaker and reset the merge
    group downstream.
    """
    lines = raw_text.splitlines()
    n = len(lines)

    def is_blank(i: int) -> bool:
        return i < 0 or i >= n or not lines[i].strip()

    tokens: list[tuple[str, ...]] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    def flush():
        nonlocal current_speaker, current_lines
        if current_speaker is not None:
            body = "\n".join(current_lines).strip()
            if body:
                tokens.append(("speech", current_speaker, body))
        current_speaker = None
        current_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue

        # Standalone attribution (NAME:\n — IA djvu.txt and HTML-parsed formats).
        m = _ATTRIBUTION_RE.match(stripped)
        if m:
            flush()
            current_speaker = m.group(1).strip()
            current_lines = []
            continue

        # Inline attribution (NAME: text — Tika-extracted elibrary.sansad.in text).
        # Only checked when the standalone pattern did not match, so existing
        # IA/HTML format behaviour is unchanged.
        m_inline = _INLINE_ATTRIBUTION_RE.match(stripped)
        if m_inline:
            speaker_raw = m_inline.group(1).strip()
            # Guard: procedural headings like "STARRED QUESTION NO. 5" should
            # not be treated as speaker attributions.
            if not _PROCEDURAL_BREAK_RE.match(speaker_raw):
                flush()
                # Strip trailing constituency "(PLACE)" — e.g. "(VIRUDHUNAGAR)".
                speaker = _TRAILING_PAREN_RE.sub("", speaker_raw).strip()
                # Strip stray trailing ")" — artifact of wrapped multi-line
                # minister names split across PDF pages.
                speaker = re.sub(r"\)+\s*$", "", speaker).strip()
                current_speaker = speaker
                current_lines = [m_inline.group(2).strip()]
                continue

        if is_blank(i - 1) and is_blank(i + 1) and _is_break_line(stripped):
            flush()
            tokens.append(("break", stripped))
            continue

        current_lines.append(stripped)

    flush()
    return tokens


def _merge_speech_groups(
    pairs: list[tuple[str, str]],
    break_after: set[int],
) -> list[tuple[str, list[str]]]:
    """
    Collapse consecutive same-speaker speeches into merge groups.

    Args:
        pairs:        ordered (speaker, body) pairs (excluded speakers removed).
        break_after:  set of indices i such that a break signal occurred
                      immediately after pairs[i] — the next speech starts a new
                      group even if the speaker is unchanged.

    Returns ordered list of (speaker, [body, ...]) groups, one per output record.
    """
    groups: list[tuple[str, list[str]]] = []
    prev_speaker: str | None = None
    broken = False

    for idx, (speaker, body) in enumerate(pairs):
        if groups and speaker == prev_speaker and not broken:
            groups[-1][1].append(body)
        else:
            groups.append((speaker, [body]))
        prev_speaker = speaker
        broken = idx in break_after

    return groups


def _build_speech_record(
    speaker_raw: str,
    bodies: list[str],
    *,
    source: str,
    proceeding_type: str,
    date: Any,
    session_name: str | None,
    session_number: int | None,
    sitting_number: int | None,
    subject: str | None,
    time_of_day: str | None,
    source_url: str | None,
    page_reference: int | None,
    volume: int | None,
    lok_sabha_number: int | None,
) -> dict[str, Any]:
    """
    Build one Speech unit dict from a merge group of one or more body texts.

    Per-segment language handling preserves the F01 edge case: when one merged
    segment has English and another does not, full_text_en includes the
    available English segments and has_untranslated_content is set true (it is
    not nulled just because one segment lacked a translation). The `segments`
    JSONB array carries one element per original speech; full_text_en is the
    non-null segment texts joined with "\n\n"; word_count is the combined total.
    """
    seg_texts: list[str | None] = []
    is_translated_any = False
    has_untranslated_any = False
    for body in bodies:
        ft, is_translated, has_untranslated = _detect_language_handling(body)
        seg_texts.append(ft)
        is_translated_any = is_translated_any or is_translated
        has_untranslated_any = has_untranslated_any or has_untranslated

    non_null = [t for t in seg_texts if t]
    full_text_en = "\n\n".join(non_null) if non_null else None
    word_count = _count_words(full_text_en)
    lang_original = _compute_lang_original("\n\n".join(bodies))
    segments = [
        {"text": seg_texts[i], "segment_index": i} for i in range(len(seg_texts))
    ]

    return {
        "source": source,
        "proceeding_type": proceeding_type or "debate",
        "date": date,
        "session_name": session_name,
        "session_number": session_number,
        "sitting_number": sitting_number,
        "subject": subject,
        "speaker_name": speaker_raw,          # canonicalized in Stage 2
        "speaker_party": None,                 # populated from source in Stage 2
        "speaker_constituency_or_state": None,
        "speaker_role": _speaker_role(speaker_raw),
        "full_text_en": full_text_en,
        "segments": segments,
        "lang_original": lang_original,
        "time_of_day": time_of_day,
        "word_count": word_count,
        "is_translated": is_translated_any,
        "has_untranslated_content": has_untranslated_any,
        "speaker_name_unresolved": True,       # set False after canonicalization
        "source_url": source_url,
        "page_reference": page_reference,
        "volume": volume,
        "lok_sabha_number": lok_sabha_number,
    }


def segment_speeches(
    raw_record: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    """
    Convert a raw record dict into a list of Speech unit dicts.

    Applies Adjacent Speech Merging (F01, PRD v3.0): consecutive speeches by the
    same speaker within this document (same sitting + same proceeding_type) with
    no break signal between them are merged into one record carrying a multi-
    element `segments` array. A different/excluded speaker, a section heading, or
    a procedural entry between two same-speaker speeches breaks the merge.

    Args:
        raw_record:  Output from html_parser.parse_html or pdf_parser.parse_pdf.
        source:      "CA", "LS", or "RS".

    Returns:
        List of speech dicts ready for canonicalization + indexing.
        sequence_within_sitting is NOT set here; the orchestrator assigns it (the
        merged record naturally occupies the first segment's document position).
    """
    if source == "CA":
        ca_pairs: list[tuple[str, str, str | None]] | None = raw_record.get("ca_speech_pairs")
        if ca_pairs is not None:
            return _segment_ca_speeches(raw_record, ca_pairs)

    raw_text: str = raw_record.get("raw_text", "")
    tokens = _tokenize(raw_text)

    # Build attributed (speaker, body) pairs and record break positions. A break
    # token OR an excluded speaker (unattributed / presiding officer) between two
    # speeches is a break signal for the preceding speech's merge group.
    pairs: list[tuple[str, str]] = []
    break_after: set[int] = set()
    for tok in tokens:
        if tok[0] == "break":
            if pairs:
                break_after.add(len(pairs) - 1)
            continue
        _, speaker_raw, body = tok
        if _is_unattributed(speaker_raw) or _is_presiding_officer(speaker_raw):
            if pairs:
                break_after.add(len(pairs) - 1)
            continue
        pairs.append((speaker_raw, body))

    groups = _merge_speech_groups(pairs, break_after)

    return [
        _build_speech_record(
            speaker_raw,
            bodies,
            source=source,
            proceeding_type=raw_record.get("proceeding_type") or "debate",
            date=raw_record.get("date"),
            session_name=raw_record.get("session_name"),
            session_number=raw_record.get("session_number"),
            sitting_number=raw_record.get("sitting_number"),
            subject=raw_record.get("subject"),
            time_of_day=raw_record.get("time_of_day"),
            source_url=raw_record.get("source_url"),
            page_reference=raw_record.get("page_reference"),
            volume=raw_record.get("volume"),
            lok_sabha_number=raw_record.get("lok_sabha_number"),
        )
        for speaker_raw, bodies in groups
    ]


def _segment_ca_speeches(
    raw_record: dict[str, Any],
    ca_pairs: list[tuple[str, str, str | None]],
) -> list[dict[str, Any]]:
    """
    Build speech dicts for CA records using pre-extracted (speaker, text, subject)
    triples. Each triple carries the per-speech subject assigned by the
    html_parser's section-header DOM walk.

    Adjacent Speech Merging for CA uses the explicit subject as the section-
    heading signal: consecutive same-speaker speeches under the *same* subject
    merge; a subject change (a new bold section header) or an excluded speaker
    breaks the group. CA has no lok_sabha_number (always null).
    """
    time_of_day = raw_record.get("time_of_day")

    groups: list[tuple[str, str | None, list[str]]] = []  # (speaker, subject, bodies)
    prev_speaker: str | None = None
    prev_subject: str | None = None
    for speaker_raw, body, subject in ca_pairs:
        if _is_presiding_officer(speaker_raw):
            prev_speaker = None  # excluded speaker breaks the merge group
            continue
        if groups and speaker_raw == prev_speaker and subject == prev_subject:
            groups[-1][2].append(body)
        else:
            groups.append((speaker_raw, subject, [body]))
        prev_speaker = speaker_raw
        prev_subject = subject

    return [
        _build_speech_record(
            speaker_raw,
            bodies,
            source=raw_record.get("source", "CA"),
            proceeding_type=raw_record.get("proceeding_type") or "debate",
            date=raw_record.get("date"),
            session_name=None,
            session_number=None,
            sitting_number=raw_record.get("sitting_number"),
            subject=subject,
            time_of_day=time_of_day,
            source_url=raw_record.get("source_url"),
            page_reference=raw_record.get("page_reference"),
            volume=raw_record.get("volume"),
            lok_sabha_number=None,
        )
        for speaker_raw, subject, bodies in groups
    ]
