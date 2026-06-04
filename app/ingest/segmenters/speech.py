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
    r"|MR\.?\s+CHAIRMAN|THE\s+CHAIRMAN|THE\s+DEPUTY\s+CHAIRMAN"
    r"|VICE[\s\-]CHAIRMAN|THE\s+PRESIDENT|MR\.?\s+PRESIDENT)\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Attribution line pattern: "SHRI NARENDRA MODI :" or "DR. MANMOHAN SINGH:"
_ATTRIBUTION_RE = re.compile(
    r"^([A-Z][A-Z\s\.\,\(\)\'\/\-]{1,150})\s*:\s*$",
)

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


def _split_into_speeches(raw_text: str) -> list[tuple[str, str]]:
    """
    Split a block of parliamentary text into (speaker, body) pairs.
    """
    results: list[tuple[str, str]] = []
    lines = raw_text.splitlines()

    current_speaker: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_speaker is not None and current_lines:
            body = "\n".join(current_lines).strip()
            if body:
                results.append((current_speaker, body))

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue

        m = _ATTRIBUTION_RE.match(stripped)
        if m:
            candidate = m.group(1).strip()
            flush()
            current_speaker = candidate
            current_lines = []
        else:
            current_lines.append(stripped)

    flush()
    return results


def segment_speeches(
    raw_record: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    """
    Convert a raw record dict into a list of Speech unit dicts.

    Args:
        raw_record:  Output from html_parser.parse_html or pdf_parser.parse_pdf.
        source:      "CA", "LS", or "RS".

    Returns:
        List of speech dicts ready for canonicalization + indexing.
        sequence_within_sitting is NOT set here; the orchestrator assigns it.
    """
    if source == "CA":
        ca_pairs: list[tuple[str, str, str | None]] | None = raw_record.get("ca_speech_pairs")
        if ca_pairs is not None:
            return _segment_ca_speeches(raw_record, ca_pairs)

    raw_text: str = raw_record.get("raw_text", "")
    speech_pairs = _split_into_speeches(raw_text)
    time_of_day = raw_record.get("time_of_day")

    speeches: list[dict[str, Any]] = []

    for speaker_raw, body in speech_pairs:
        if _is_unattributed(speaker_raw):
            continue
        if _is_presiding_officer(speaker_raw):
            continue

        role = _speaker_role(speaker_raw)
        full_text_en, is_translated, has_untranslated = _detect_language_handling(body)
        lang_original = _compute_lang_original(body)
        word_count = _count_words(full_text_en)

        speech: dict[str, Any] = {
            "source": source,
            "proceeding_type": raw_record.get("proceeding_type") or "debate",
            "date": raw_record.get("date"),
            "session_name": raw_record.get("session_name"),
            "session_number": raw_record.get("session_number"),
            "sitting_number": raw_record.get("sitting_number"),
            "subject": raw_record.get("subject"),
            "speaker_name": speaker_raw,          # canonicalized in Phase 2
            "speaker_party": None,                 # populated from source in Phase 2
            "speaker_constituency_or_state": None,
            "speaker_role": role,
            "full_text_en": full_text_en,
            "lang_original": lang_original,
            "time_of_day": time_of_day,
            "word_count": word_count,
            "is_translated": is_translated,
            "has_untranslated_content": has_untranslated,
            "speaker_name_unresolved": True,       # set to False after canonicalization
            "source_url": raw_record.get("source_url"),
            "page_reference": raw_record.get("page_reference"),
            "volume": raw_record.get("volume"),
        }
        speeches.append(speech)

    return speeches


def _segment_ca_speeches(
    raw_record: dict[str, Any],
    ca_pairs: list[tuple[str, str, str | None]],
) -> list[dict[str, Any]]:
    """
    Build speech dicts for CA records using pre-extracted (speaker, text, subject) triples.

    Each triple carries the per-speech subject assigned by the html_parser's
    section-header DOM walk. Skips presiding officer interventions; runs
    language detection on each body.
    """
    speeches: list[dict[str, Any]] = []
    time_of_day = raw_record.get("time_of_day")

    for speaker_raw, body, subject in ca_pairs:
        if _is_presiding_officer(speaker_raw):
            continue

        full_text_en, is_translated, has_untranslated = _detect_language_handling(body)
        lang_original = _compute_lang_original(body)
        word_count = _count_words(full_text_en)

        speech: dict[str, Any] = {
            "source": raw_record.get("source", "CA"),
            "proceeding_type": raw_record.get("proceeding_type") or "debate",
            "date": raw_record.get("date"),
            "session_name": None,
            "session_number": None,
            "sitting_number": raw_record.get("sitting_number"),
            "subject": subject,
            "speaker_name": speaker_raw,
            "speaker_party": None,
            "speaker_constituency_or_state": None,
            "speaker_role": _speaker_role(speaker_raw),
            "full_text_en": full_text_en,
            "lang_original": lang_original,
            "time_of_day": time_of_day,
            "word_count": word_count,
            "is_translated": is_translated,
            "has_untranslated_content": has_untranslated,
            "speaker_name_unresolved": True,
            "source_url": raw_record.get("source_url"),
            "page_reference": raw_record.get("page_reference"),
            "volume": raw_record.get("volume"),
        }
        speeches.append(speech)

    return speeches
