"""Tests for ingest.parsers.html_parser"""
import pytest
from pathlib import Path

from ingest.parsers.html_parser import parse_html, _parse_date, _detect_proceeding_type

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# ── _parse_date ───────────────────────────────────────────────────────────────

class TestParseDate:
    def test_long_form_date(self):
        assert _parse_date("15 March 2023") == "2023-03-15"

    def test_ordinal_date(self):
        assert _parse_date("1st January 2014") == "2014-01-01"

    def test_iso_date(self):
        assert _parse_date("date: 2022-07-10") == "2022-07-10"

    def test_no_date(self):
        assert _parse_date("No date here at all") is None

    def test_invalid_day(self):
        assert _parse_date("32 March 2023") is None

    def test_scope_boundary_included(self):
        # 2014-01-01 is in scope
        assert _parse_date("1 January 2014") == "2014-01-01"

    def test_scope_boundary_excluded(self):
        # 2013-12-31 is out of scope — parser just extracts, not filters
        assert _parse_date("31 December 2013") == "2013-12-31"


# ── _detect_proceeding_type ───────────────────────────────────────────────────

class TestDetectProceedingType:
    def test_starred_question(self):
        assert _detect_proceeding_type("Starred Questions 10 July 2022") == "starred_question"

    def test_unstarred_question(self):
        assert _detect_proceeding_type("Unstarred Questions") == "unstarred_question"

    def test_zero_hour(self):
        assert _detect_proceeding_type("Zero Hour Proceedings") == "zero_hour"

    def test_calling_attention(self):
        assert _detect_proceeding_type("Calling Attention Motion") == "calling_attention"

    def test_adjournment_motion(self):
        assert _detect_proceeding_type("Adjournment Motion Debate") == "adjournment_motion"

    def test_short_duration_discussion(self):
        assert _detect_proceeding_type("Short Duration Discussion") == "short_duration_discussion"

    def test_private_member_bill(self):
        assert _detect_proceeding_type("Private Member's Bill debate") == "private_member_bill"

    def test_short_notice_question(self):
        assert _detect_proceeding_type("Short Notice Question on flood relief") == "short_notice_question"

    def test_default_debate(self):
        assert _detect_proceeding_type("General Discussion on Union Budget") == "debate"


# ── parse_html ────────────────────────────────────────────────────────────────

class TestParseHtml:
    def test_returns_correct_source_ls(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS", "http://example.com/ls-debate")
        assert result["source"] == "LS"

    def test_returns_correct_source_rs(self):
        html = _load("starred_question_rs.html")
        result = parse_html(html, "RS")
        assert result["source"] == "RS"

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Invalid source"):
            parse_html("<html></html>", "CA")

    def test_extracts_date_from_title(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert result["date"] == "2023-03-15"

    def test_extracts_date_rs(self):
        html = _load("starred_question_rs.html")
        result = parse_html(html, "RS")
        assert result["date"] == "2022-07-10"

    def test_extracts_subject_from_h1(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert "Union Budget" in result["subject"]

    def test_proceeding_type_hint_overrides_detection(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS", proceeding_type_hint="zero_hour")
        assert result["proceeding_type"] == "zero_hour"

    def test_source_url_preserved(self):
        html = _load("debate_ls.html")
        url = "http://sansad.in/ls/debates/2023-03-15"
        result = parse_html(html, "LS", source_url=url)
        assert result["source_url"] == url

    def test_raw_text_contains_speech_content(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert "SHRI NARENDRA MODI" in result["raw_text"]
        assert "SHRI RAHUL GANDHI" in result["raw_text"]

    def test_script_tags_excluded_from_raw_text(self):
        html = """<html><body>
        <script>alert('xss')</script>
        <p>SHRI TEST MEMBER : Some speech text.</p>
        </body></html>"""
        result = parse_html(html, "LS")
        assert "alert" not in result["raw_text"]

    def test_session_name_extracted(self):
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert result["session_name"] is not None
        assert "Budget" in result["session_name"]

    def test_unstarred_question_proceeding_type(self):
        html = _load("unstarred_question_ls.html")
        result = parse_html(html, "LS")
        assert result["proceeding_type"] == "unstarred_question"

    def test_starred_question_proceeding_type(self):
        html = _load("starred_question_rs.html")
        result = parse_html(html, "RS")
        assert result["proceeding_type"] == "starred_question"

    def test_empty_html_returns_dict(self):
        result = parse_html("<html><body></body></html>", "LS")
        assert isinstance(result, dict)
        assert result["source"] == "LS"
        assert result["date"] is None
