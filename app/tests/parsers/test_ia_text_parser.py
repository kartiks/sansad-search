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
        """Non-ISO eparlib_date must be silently ignored (date=None)."""
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
