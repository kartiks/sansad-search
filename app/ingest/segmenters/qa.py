"""
Q+A exchange segmenter.

Converts a raw record dict into Q+A exchange unit dicts.

Starred question output:
    main question text + minister's answer + all supplementary questions
    (with questioner attribution) + minister's responses to supplementaries.
    Full exchange stored as a single full_text_en string.

Unstarred question output:
    question text + written answer only (no supplementaries).

Each returned dict has the shape expected by ingest.indexer and DATA-MODELS.md 1.2.
"""

from __future__ import annotations

import re
from typing import Any

from ingest.segmenters.speech import (
    _HINDI_SCRIPT_RE,
    _TRANSLATION_RE,
    _compute_lang_original,
    _count_words,
    _detect_language_handling,
    _is_presiding_officer,
    _is_unattributed,
)

# ── Q+A structural markers ────────────────────────────────────────────────────

# Issue 4: NO[\.:\s]* matches NO. / NO: / NO<space> prefixes (e.g. "NO:458")
_QUESTION_NUM_RE = re.compile(
    r"(?:STARRED\s+QUESTION\s+NO[\.:\s]*|UNSTARRED\s+QUESTION\s+NO[\.:\s]*|Q\.?\s*NO[\.:\s]*)(\d+)",
    re.IGNORECASE,
)

# Supplementary question marker
_SUPPLEMENTARY_RE = re.compile(
    r"\bSUPPLEMENTARY\b|\bSUPP\b",
    re.IGNORECASE,
)

# Minister answer marker
_MINISTER_RE = re.compile(
    r"^([A-Z][A-Z\s\.\,\(\)\'\-]{2,100}MINISTER[^\n:]{0,60})\s*:\s*$",
    re.IGNORECASE,
)

# Subject / title pattern (bold title lines in HTML-converted text)
_SUBJECT_RE = re.compile(r"^([A-Z][A-Z\s\-\(\)]{5,200})$")

# Attribution for supplementary questioners (same format as speech segmenter)
_ATTRIBUTION_RE = re.compile(
    r"^([A-Z][A-Z\s\.\,\(\)\'\/\-]{1,150})\s*:\s*$",
)

# Written answer marker
_WRITTEN_ANSWER_RE = re.compile(
    r"\bWRITTEN\s+ANSWER\b|\bANSWER\b",
    re.IGNORECASE,
)

# Issue 5: fallback minister detection (first line contains 'Minister' but no trailing colon)
_MINISTER_CONTAINS_RE = re.compile(r"\bminister\b", re.IGNORECASE)

# Issue 6: questioner fallback — stop scanning at "Will the Minister" line
_WILL_THE_MINISTER_RE = re.compile(r"\bwill\s+the\s+minister\b", re.IGNORECASE)

# Issue 6: questioner fallback — skip sub-question part markers like (a), (b), 1., 2.
_QUESTION_PART_RE = re.compile(r"^\([a-zA-Z]\)|^\d+\.")


def _extract_question_number(text: str) -> int | None:
    m = _QUESTION_NUM_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _build_full_text(parts: list[str]) -> str | None:
    """Join non-empty text parts into a single exchange string."""
    combined = "\n\n".join(p.strip() for p in parts if p.strip())
    return combined or None


def segment_qa(
    raw_record: dict[str, Any],
    source: str,
    proceeding_type: str,
) -> list[dict[str, Any]]:
    """
    Convert a raw record dict into Q+A exchange unit dicts.

    Args:
        raw_record:      Output from html_parser.parse_html or pdf_parser.parse_pdf.
        source:          "LS" or "RS".
        proceeding_type: "starred_question" or "unstarred_question".

    Returns:
        List of Q+A exchange dicts. Typically one item per question number found;
        may be empty if no structured Q+A content is detected.
    """
    if source not in ("LS", "RS"):
        raise ValueError(f"Q+A exchanges only exist for LS/RS. Got source={source!r}")
    if proceeding_type not in ("starred_question", "unstarred_question"):
        raise ValueError(f"Invalid proceeding_type: {proceeding_type!r}")

    raw_text: str = raw_record.get("raw_text", "")
    is_starred = proceeding_type == "starred_question"

    # Split text into logical blocks separated by blank lines
    blocks = _split_blocks(raw_text)

    if not blocks:
        return []

    # Heuristic: if the entire document is one question, parse it as one.
    # If multiple question-number markers are found, split into per-question records.
    question_starts = _find_question_starts(blocks)

    if not question_starts:
        # Treat the whole document as a single Q+A
        return [_parse_single_qa(
            blocks, raw_record, source, proceeding_type, is_starred
        )]

    # Multiple questions in one document
    exchanges = []
    for i, start_idx in enumerate(question_starts):
        end_idx = question_starts[i + 1] if i + 1 < len(question_starts) else len(blocks)
        qa_blocks = blocks[start_idx:end_idx]
        record = _parse_single_qa(
            qa_blocks, raw_record, source, proceeding_type, is_starred
        )
        if record:
            exchanges.append(record)
    return exchanges


def _split_blocks(text: str) -> list[str]:
    """Split text on double newlines into non-empty blocks."""
    return [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]


def _find_question_starts(blocks: list[str]) -> list[int]:
    """Return indices of blocks that start a new question."""
    starts = []
    for i, block in enumerate(blocks):
        if _QUESTION_NUM_RE.search(block):
            starts.append(i)
    return starts


def _parse_single_qa(
    blocks: list[str],
    raw_record: dict[str, Any],
    source: str,
    proceeding_type: str,
    is_starred: bool,
) -> dict[str, Any] | None:
    """Parse a set of text blocks into one Q+A exchange record."""

    # Issue 8: seed from raw_record metadata as defaults; text loop may add to
    # questioner_names (supplementary questioners for starred questions)
    question_number: int | None = raw_record.get("question_number")
    subject: str | None = raw_record.get("subject")
    questioner_names: list[str] = list(raw_record.get("questioner_names") or [])
    questioner_party: str | None = None
    minister_name: str | None = None
    ministry: str | None = raw_record.get("ministry")

    text_parts: list[str] = []
    current_attribution: str | None = None
    in_answer = False

    for block in blocks:
        lines = block.splitlines()
        first_line = lines[0].strip() if lines else ""
        rest_content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        # Question number (always in first line)
        qnum = _extract_question_number(first_line)
        if qnum is not None and question_number is None:
            question_number = qnum
            if rest_content:
                text_parts.append(rest_content)
            continue

        # Minister detection on first line
        m = _MINISTER_RE.match(first_line)
        if m:
            minister_name = m.group(1).strip()
            in_answer = True
            if rest_content:
                text_parts.append(rest_content)
                if not is_starred and _WRITTEN_ANSWER_RE.search(rest_content):
                    break
            continue

        # Issue 5: fallback — first line contains 'Minister' but no trailing colon
        if not in_answer and _MINISTER_CONTAINS_RE.search(first_line) and not first_line.endswith(":"):
            in_answer = True
            minister_name = first_line.strip()
            if rest_content:
                text_parts.append(rest_content)
                if not is_starred and _WRITTEN_ANSWER_RE.search(rest_content):
                    break
            continue

        # Attribution line on first line (questioner or supplementary)
        attr_m = _ATTRIBUTION_RE.match(first_line)
        if attr_m:
            candidate = attr_m.group(1).strip()
            if not (_is_unattributed(candidate) or _is_presiding_officer(candidate)):
                current_attribution = candidate
                if not in_answer and candidate not in questioner_names:
                    questioner_names.append(candidate)
            if rest_content:
                text_parts.append(rest_content)
            continue

        # Accumulate text
        if current_attribution or in_answer or not questioner_names:
            text_parts.append(block)

        # For unstarred: stop after written answer block
        if not is_starred and _WRITTEN_ANSWER_RE.search(block) and in_answer:
            break

    # Build full_text_en
    combined_text = "\n\n".join(text_parts)
    full_text_en, is_translated, has_untranslated = _detect_language_handling(combined_text)
    lang_original = _compute_lang_original(combined_text)
    word_count = _count_words(full_text_en)

    # Issue 6: fallback questioner extraction for IA text format where questioner
    # names appear as mixed-case lines without a trailing colon (no attribution match).
    # Scan from the question-number block to the first "Will the Minister" line.
    if not questioner_names:
        found_qnum_block = False
        for blk in blocks:
            bl_lines = blk.splitlines()
            bl_first = bl_lines[0].strip() if bl_lines else ""
            if not found_qnum_block:
                if _QUESTION_NUM_RE.search(bl_first):
                    found_qnum_block = True
                continue
            # Stop scanning once we reach the minister's block
            if _MINISTER_RE.match(bl_first) or _MINISTER_CONTAINS_RE.search(bl_first):
                break
            for ln in bl_lines:
                ln = ln.strip()
                if not ln:
                    continue
                # Stop at "Will the Minister" or any minister marker within the block
                if _WILL_THE_MINISTER_RE.search(ln) or _MINISTER_CONTAINS_RE.search(ln):
                    break
                # Name candidate: mixed case (not all-caps), not a question-number
                # marker, not a sub-question part like (a)/(b) or 1./2.
                if (len(ln) >= 3 and
                        not ln.isupper() and
                        not _QUESTION_NUM_RE.search(ln) and
                        not _QUESTION_PART_RE.match(ln)):
                    questioner_names.append(ln)
                    break
            if questioner_names:
                break

    # Ensure at least one questioner
    if not questioner_names:
        questioner_names = ["Unknown"]

    if not text_parts and not question_number:
        return None

    return {
        "source": source,
        "proceeding_type": proceeding_type,
        "date": raw_record.get("date"),
        "session_name": raw_record.get("session_name"),
        "session_number": raw_record.get("session_number"),
        "sitting_number": raw_record.get("sitting_number"),
        "question_number": question_number,
        "subject": subject,
        "questioner_names": questioner_names,
        "questioner_party": questioner_party,
        "minister_name": minister_name,
        "ministry": ministry,
        "full_text_en": full_text_en,
        "lang_original": lang_original,
        "time_of_day": raw_record.get("time_of_day"),
        "word_count": word_count,
        "is_translated": is_translated,
        "has_untranslated_content": has_untranslated,
        "source_url": raw_record.get("source_url"),
        "page_reference": raw_record.get("page_reference"),
    }
