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
            parse_html("<html></html>", "XX")

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

    def test_ca_source_accepted_no_error(self):
        """parse_html must accept source='CA' without raising ValueError."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        assert result["source"] == "CA"

    def test_ca_session_name_is_none(self):
        """CA records must have session_name=None per PRD spec."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        assert result["session_name"] is None

    def test_ca_session_number_is_none(self):
        """CA records must have session_number=None per PRD spec."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        assert result["session_number"] is None

    def test_time_of_day_key_present_in_result(self):
        """parse_html must always return time_of_day key."""
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert "time_of_day" in result

    def test_time_of_day_extracted_from_time_element(self):
        """When <time>11:00</time> is present, time_of_day must be '11:00'."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        assert result["time_of_day"] == "11:00"

    def test_time_of_day_none_when_no_time_element(self):
        """When no <time> element or HH:MM pattern exists, time_of_day is None."""
        html = "<html><body><p>SHRI TEST : Some speech.</p></body></html>"
        result = parse_html(html, "LS")
        assert result["time_of_day"] is None


# ── Phase 10: CA parsing rules ────────────────────────────────────────────────

class TestCASpeechPairsWithSubjects:
    def test_ca_speech_pairs_is_list_of_triples(self):
        """ca_speech_pairs must be a list of (speaker, text, subject) triples."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        assert pairs is not None
        assert len(pairs) == 3
        for triple in pairs:
            assert len(triple) == 3, f"Expected 3-tuple, got {len(triple)}-tuple"

    def test_ca_section_header_assigned_as_subject(self):
        """Speeches after a section header must have that header as subject."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        # Fixture: speeches 1+2 → "Objectives Resolution"; speech 3 → "The Question of Procedure"
        assert pairs[0][2] == "Objectives Resolution"
        assert pairs[1][2] == "Objectives Resolution"
        assert pairs[2][2] == "The Question of Procedure"

    def test_ca_speeches_under_same_header_share_subject(self):
        """Two speeches under the same section header must have identical subject values."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        assert pairs[0][2] == pairs[1][2]

    def test_ca_speech_subject_changes_at_new_header(self):
        """A speech after a new header must not retain the previous header's subject."""
        html = _load("coi_day.html")
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        assert pairs[1][2] != pairs[2][2]

    def test_ca_toc_fallback_when_no_header_before_first_speech(self):
        """When no section header precedes the first speech, use TOC first item."""
        html = """<!DOCTYPE html>
<html><body><div class="wrapper">
  <ul>
    <li><a href="#topic1">Constituent Assembly Resolved</a></li>
  </ul>
  <div class="lg:grid lg:grid-cols-12 relative">
    <div class="lg:col-span-3 grid grid-cols-4 sm:grid-cols-6 lg:gap-x-2.5 xl:grid-cols-4 empty">
      <div class="col-span-2"><span class="bg-[#F8FFA3]">1.1.1</span></div>
      <span class="col-span-2 md:text-lg font-medium">Shri Test Speaker</span>
    </div>
    <div class="lg:col-span-9">Speech before any section header.</div>
    <div class="social-links-block"></div>
  </div>
</div></body></html>"""
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        assert len(pairs) == 1
        # subject must be TOC first item, not None
        assert pairs[0][2] == "Constituent Assembly Resolved"

    def test_ca_speaker_nested_in_extra_div_extracted(self):
        """Speaker span nested inside an extra wrapper div inside info_div must still be found."""
        html = """<!DOCTYPE html>
<html><body><div class="wrapper">
  <div class="lg:grid lg:grid-cols-12 relative">
    <div class="lg:col-span-3 grid grid-cols-4 sm:grid-cols-6 lg:gap-x-2.5 xl:grid-cols-4 empty">
      <div class="col-span-2"><span class="bg-[#F8FFA3]">1.1.1</span></div>
      <div class="col-span-2">
        <span class="md:text-lg font-medium">Shri Nested Speaker</span>
      </div>
    </div>
    <div class="lg:col-span-9">Speech text from nested speaker.</div>
    <div class="social-links-block"></div>
  </div>
</div></body></html>"""
        result = parse_html(html, "CA")
        pairs = result["ca_speech_pairs"]
        assert len(pairs) == 1
        assert pairs[0][0] == "Shri Nested Speaker"

    def test_ca_ls_does_not_produce_ca_speech_pairs(self):
        """ca_speech_pairs is only set for source=CA."""
        html = _load("debate_ls.html")
        result = parse_html(html, "LS")
        assert result["ca_speech_pairs"] is None


class TestCATocExtraction:
    def test_extract_toc_first_item(self):
        """_extract_coi_toc_first_item returns text of first <a href="#..."> in first <ul>."""
        from ingest.parsers.html_parser import _extract_coi_toc_first_item
        from bs4 import BeautifulSoup
        html = """<html><body>
        <ul><li><a href="#section1">First Topic</a></li><li><a href="#s2">Second</a></li></ul>
        </body></html>"""
        soup = BeautifulSoup(html, "lxml")
        result = _extract_coi_toc_first_item(soup)
        assert result == "First Topic"

    def test_extract_toc_returns_none_when_no_toc(self):
        from ingest.parsers.html_parser import _extract_coi_toc_first_item
        from bs4 import BeautifulSoup
        html = "<html><body><p>No TOC here.</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_coi_toc_first_item(soup)
        assert result is None
