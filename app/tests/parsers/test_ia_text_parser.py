"""Tests for ingest.parsers.ia_text_parser — IA _djvu.txt + metadata JSON parser."""
from __future__ import annotations

import pytest

from ingest.parsers.ia_text_parser import parse_ia_text


def _meta(**overrides) -> dict:
    """Build a minimal valid IA metadata dict."""
    base = {
        "identifier": "eparlib.nic.in.12345",
        "eparlib_document_url": "https://eparlib.sansad.in/handle/123456789/12345",
        "eparlib_date": "2023-03-15",
        "eparlib_session_number": "261",
        "eparlib_title": "Lok Sabha Debates",
    }
    base.update(overrides)
    return base


_SAMPLE_TEXT = (
    "SHRI NARENDRA MODI: I rise to speak on the infrastructure bill.\n"
    "This is an important matter for the nation.\n"
    "SHRI RAHUL GANDHI: I would like to raise a point.\n"
    "The government must explain its position.\n"
)


class TestParseIaText:
    def test_returns_dict_for_valid_input(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert isinstance(result, dict)

    def test_source_preserved(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result["source"] == "LS"

    def test_source_rs(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "RS")
        assert result["source"] == "RS"

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="only LS and RS"):
            parse_ia_text(_SAMPLE_TEXT, _meta(), "CA")

    def test_raw_text_populated(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert "NARENDRA MODI" in result["raw_text"]

    def test_source_url_from_eparlib_document_url(self):
        """source_url must be eparlib_document_url, never archive.org (Non-Neg #9)."""
        meta = _meta(eparlib_document_url="https://eparlib.sansad.in/handle/123456789/12345")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["source_url"] == "https://eparlib.sansad.in/handle/123456789/12345"
        assert "archive.org" not in (result["source_url"] or "")

    def test_date_from_eparlib_date(self):
        meta = _meta(eparlib_date="2023-03-15")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] == "2023-03-15"

    def test_session_number_from_eparlib_session_number(self):
        meta = _meta(eparlib_session_number="261")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 261

    def test_session_number_as_int(self):
        """session_number must be an int, not a string."""
        meta = _meta(eparlib_session_number="5")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert isinstance(result["session_number"], int)
        assert result["session_number"] == 5

    def test_subject_from_eparlib_title(self):
        meta = _meta(eparlib_title="Starred Questions — 15 March 2023")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["subject"] == "Starred Questions — 15 March 2023"

    def test_subject_falls_back_to_title(self):
        meta = {
            "identifier": "eparlib.nic.in.12345",
            "eparlib_document_url": "https://eparlib.sansad.in/handle/123456789/12345",
            "eparlib_date": "2023-03-15",
            "title": "Lok Sabha Debates 15 March 2023",
        }
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert "Lok Sabha Debates" in (result["subject"] or "")

    def test_page_reference_is_none(self):
        """IA text has no page numbers; page_reference must be None."""
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["page_reference"] is None

    def test_volume_is_none(self):
        """volume is not applicable for LS/RS."""
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["volume"] is None

    def test_session_name_is_none(self):
        """session_name is resolved by sessions.py canonicalizer, not here."""
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["session_name"] is None

    def test_empty_text_returns_none(self):
        result = parse_ia_text("", _meta(), "LS")
        assert result is None

    def test_whitespace_only_text_returns_none(self):
        result = parse_ia_text("   \n\n\t\n  ", _meta(), "LS")
        assert result is None

    def test_bytes_input_decoded(self):
        text_bytes = _SAMPLE_TEXT.encode("utf-8")
        result = parse_ia_text(text_bytes, _meta(), "LS")
        assert result is not None
        assert "NARENDRA MODI" in result["raw_text"]

    def test_metadata_list_values_extracted(self):
        """IA metadata values may be lists; _get() should extract the first element."""
        meta = _meta(
            eparlib_document_url=["https://eparlib.sansad.in/handle/123456789/12345"],
            eparlib_date=["2023-03-15"],
            eparlib_session_number=["261"],
        )
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["source_url"] == "https://eparlib.sansad.in/handle/123456789/12345"
        assert result["date"] == "2023-03-15"
        assert result["session_number"] == 261

    def test_invalid_date_format_ignored(self):
        """Unrecognised date format (not ISO, not D-Mon-YYYY) must return date=None."""
        meta = _meta(eparlib_date="March 15, 2023")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] is None

    def test_missing_eparlib_document_url_gives_none_source_url(self):
        meta = {
            "identifier": "eparlib.nic.in.12345",
            "eparlib_date": "2023-03-15",
        }
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["source_url"] is None

    def test_proceeding_type_inferred_starred_question(self):
        meta = _meta(eparlib_title="Starred Questions")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "starred_question"

    def test_proceeding_type_inferred_unstarred_question(self):
        meta = _meta(eparlib_title="Unstarred Questions List")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "unstarred_question"

    def test_proceeding_type_inferred_zero_hour(self):
        meta = _meta(eparlib_title="Zero Hour Submissions")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "zero_hour"

    def test_proceeding_type_inferred_debate(self):
        meta = _meta(eparlib_title="General Debate on Budget")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "debate"

    def test_no_ocr_performed(self):
        """Confirm ia_text_parser performs no local OCR (no pytesseract reference)."""
        import inspect
        import ingest.parsers.ia_text_parser as m
        src = inspect.getsource(m)
        assert "pytesseract" not in src
        assert "tesseract" not in src.lower()

    def test_form_feed_page_breaks_cleaned(self):
        """Form feed characters in _djvu.txt are cleaned into paragraph breaks."""
        text_with_ff = "First section\x0cSecond section\x0cThird section"
        result = parse_ia_text(text_with_ff, _meta(), "LS")
        assert result is not None
        assert "First section" in result["raw_text"]
        assert "Second section" in result["raw_text"]
        assert "\x0c" not in result["raw_text"]

    def test_time_of_day_is_none(self):
        """IA pre-OCR text has no sitting start time; time_of_day must be None."""
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["time_of_day"] is None


# ── Issue 1: eparlib_date 'D-Month-YYYY' parsing ─────────────────────────────

class TestEparlibDateParsing:
    def test_date_abbreviated_month(self):
        """'15-Mar-2023' must convert to ISO '2023-03-15'."""
        meta = _meta(eparlib_date="15-Mar-2023")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] == "2023-03-15"

    def test_date_full_month_name(self):
        """'15-March-2023' must convert to ISO '2023-03-15'."""
        meta = _meta(eparlib_date="15-March-2023")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] == "2023-03-15"

    def test_date_iso_passthrough(self):
        """ISO '2023-03-15' must be returned unchanged."""
        meta = _meta(eparlib_date="2023-03-15")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] == "2023-03-15"

    def test_date_single_digit_day(self):
        """'1-Jan-2020' (single-digit day) must convert to ISO '2020-01-01'."""
        meta = _meta(eparlib_date="1-Jan-2020")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] == "2020-01-01"

    def test_unrecognised_date_format_returns_none(self):
        """'March 15, 2023' is not a recognised format; date must be None."""
        meta = _meta(eparlib_date="March 15, 2023")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["date"] is None


# ── Issue 2: Roman numeral session_number ────────────────────────────────────

class TestRomanNumeralSessionNumber:
    def test_roman_viii(self):
        """'VIII' must convert to session_number=8."""
        meta = _meta(eparlib_session_number="VIII")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 8

    def test_roman_i(self):
        meta = _meta(eparlib_session_number="I")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 1

    def test_roman_xvii(self):
        meta = _meta(eparlib_session_number="XVII")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 17

    def test_roman_lowercase(self):
        """Roman numeral lookup is case-insensitive."""
        meta = _meta(eparlib_session_number="viii")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 8

    def test_numeric_string_still_works(self):
        meta = _meta(eparlib_session_number="261")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] == 261

    def test_unrecognised_session_number_returns_none(self):
        """An unrecognised Roman numeral (e.g. 'XXX') returns None."""
        meta = _meta(eparlib_session_number="XXX")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["session_number"] is None


# ── Issue 3: eparlib_question_type → proceeding_type ─────────────────────────

class TestEparlibQuestionType:
    def test_unstarred_type_field(self):
        """eparlib_question_type='Unstarred' → 'unstarred_question'."""
        meta = _meta(eparlib_question_type="Unstarred", eparlib_title="Lok Sabha Debates")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "unstarred_question"

    def test_starred_type_field(self):
        """eparlib_question_type='Starred' → 'starred_question'."""
        meta = _meta(eparlib_question_type="Starred", eparlib_title="Lok Sabha Debates")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "starred_question"

    def test_eparlib_type_takes_precedence_over_title(self):
        """When eparlib_question_type is set it overrides the title-based inference."""
        meta = _meta(eparlib_question_type="Starred", eparlib_title="Unstarred Questions")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "starred_question"

    def test_title_fallback_when_no_type_field(self):
        """Without eparlib_question_type, title inference is used as fallback."""
        meta = _meta(eparlib_title="Starred Questions")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "starred_question"

    def test_type_field_case_insensitive(self):
        """'unstarred' and 'UNSTARRED' both map correctly."""
        meta = _meta(eparlib_question_type="UNSTARRED")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["proceeding_type"] == "unstarred_question"


# ── Issue 7: question_number, questioner_names, ministry ─────────────────────

class TestEparlibQAMetadataFields:
    def test_question_number_from_metadata(self):
        """eparlib_question_number='42' → question_number=42 (int)."""
        meta = _meta(eparlib_question_number="42")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["question_number"] == 42
        assert isinstance(result["question_number"], int)

    def test_question_number_absent_is_none(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["question_number"] is None

    def test_questioner_names_from_comma_string(self):
        """eparlib_members as comma-separated string → list of names."""
        meta = _meta(eparlib_members="Shri A Kumar, Shri B Singh")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["questioner_names"] == ["Shri A Kumar", "Shri B Singh"]

    def test_questioner_names_from_list(self):
        """eparlib_members as list → all elements returned."""
        meta = _meta(eparlib_members=["Shri A Kumar", "Shri B Singh", "Shri C Rao"])
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["questioner_names"] == ["Shri A Kumar", "Shri B Singh", "Shri C Rao"]

    def test_questioner_names_single_member(self):
        """Single member string (no comma) → list with one element."""
        meta = _meta(eparlib_members="Shri Ram Kumar")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["questioner_names"] == ["Shri Ram Kumar"]

    def test_questioner_names_empty_when_absent(self):
        """Without eparlib_members, questioner_names is an empty list."""
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["questioner_names"] == []

    def test_ministry_from_metadata(self):
        """eparlib_relation_ministry is propagated as 'ministry'."""
        meta = _meta(eparlib_relation_ministry="Ministry of Finance")
        result = parse_ia_text(_SAMPLE_TEXT, meta, "LS")
        assert result is not None
        assert result["ministry"] == "Ministry of Finance"

    def test_ministry_absent_is_none(self):
        result = parse_ia_text(_SAMPLE_TEXT, _meta(), "LS")
        assert result is not None
        assert result["ministry"] is None
