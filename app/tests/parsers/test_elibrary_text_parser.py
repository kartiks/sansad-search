"""
Tests for parse_elibrary_text.

Covers:
- Normal parse with full metadata produces expected raw record shape
- Empty / too-short text returns None
- Roman numeral session number conversion
- Missing metadata fields fall back to None gracefully
- source field threaded correctly
"""
from __future__ import annotations

import pytest

from ingest.parsers.elibrary_text_parser import parse_elibrary_text

# A minimal but realistic text snippet (≥100 chars)
_SAMPLE_TEXT = (
    "LOK SABHA DEBATES (English Version)\n"
    "Fourth Session (Eighteenth Lok Sabha)\n"
    "Saturday, February 01, 2025\n\n"
    "SHRI SPEAKER: The House will now take up the next item on the agenda.\n"
    "FINANCE MINISTER: Hon. Speaker, I present the Budget for 2025-26.\n"
)

_METADATA = {
    "date": "2025-02-01",
    "lok_sabha_number": 18,
    "session_number": 4,
}


class TestParseElibraryText:
    def test_returns_dict_for_valid_input(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result is not None
        assert isinstance(result, dict)

    def test_source_field(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["source"] == "LS"

    def test_source_field_custom(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA, source="RS")
        assert result["source"] == "RS"

    def test_proceeding_type_is_debate(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["proceeding_type"] == "debate"

    def test_date_from_metadata(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["date"] == "2025-02-01"

    def test_lok_sabha_number_from_metadata(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["lok_sabha_number"] == 18

    def test_session_number_from_metadata(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["session_number"] == 4

    def test_session_name_is_none(self):
        # session_name is not derivable from API metadata alone
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["session_name"] is None

    def test_raw_text_present(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["raw_text"] == _SAMPLE_TEXT

    def test_lang_original_is_en(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["lang_original"] == "en"

    def test_source_url_is_none(self):
        # Overridden by orchestrator; parser sets None
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["source_url"] is None

    def test_empty_text_returns_none(self):
        result = parse_elibrary_text("", _METADATA)
        assert result is None

    def test_too_short_text_returns_none(self):
        result = parse_elibrary_text("Short.", _METADATA)
        assert result is None

    def test_whitespace_only_text_returns_none(self):
        result = parse_elibrary_text("   \n\t  ", _METADATA)
        assert result is None

    def test_missing_date_returns_none_date(self):
        meta = {**_METADATA, "date": None}
        result = parse_elibrary_text(_SAMPLE_TEXT, meta)
        assert result is not None
        assert result["date"] is None

    def test_missing_lok_sabha_number_returns_none(self):
        meta = {"date": "2025-02-01", "session_number": 4}
        result = parse_elibrary_text(_SAMPLE_TEXT, meta)
        assert result is not None
        assert result["lok_sabha_number"] is None

    def test_string_session_number_parsed(self):
        meta = {**_METADATA, "session_number": None}
        # Provide session_number as Roman numeral string in metadata
        meta2 = {"date": "2025-02-01", "lok_sabha_number": 18, "session_number": "IV"}
        result = parse_elibrary_text(_SAMPLE_TEXT, meta2)
        assert result is not None
        # parse_elibrary_text receives session_number from provider (already int)
        # but also accepts Roman numerals via the _parse_session_number helper
        assert result["session_number"] == 4  # IV → 4

    def test_questioner_names_empty(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["questioner_names"] == []

    def test_ministry_is_none(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["ministry"] is None

    def test_subject_is_none(self):
        result = parse_elibrary_text(_SAMPLE_TEXT, _METADATA)
        assert result["subject"] is None
