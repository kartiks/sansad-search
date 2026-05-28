"""
Tests for api/services/search.py — filter builder, sort mapper, snippet,
date display, and total display.
"""
from __future__ import annotations

import pytest

from api.services.search import (
    build_filter_expression,
    build_sort_params,
    format_date_display,
    format_total_display,
    get_proceeding_type_label,
    _build_snippet,
    format_result,
)


# ── format_date_display ───────────────────────────────────────────────────────

class TestFormatDateDisplay:
    def test_basic_date(self):
        assert format_date_display("2023-03-15") == "15 March 2023"

    def test_single_digit_day(self):
        assert format_date_display("1950-01-01") == "1 January 1950"

    def test_none_returns_none(self):
        assert format_date_display(None) is None

    def test_invalid_returns_none(self):
        assert format_date_display("not-a-date") is None

    def test_december_1946(self):
        assert format_date_display("1946-12-09") == "9 December 1946"


# ── format_total_display ──────────────────────────────────────────────────────

class TestFormatTotalDisplay:
    def test_below_threshold(self):
        assert format_total_display(1234) == "1,234"

    def test_exactly_threshold(self):
        assert format_total_display(10000) == "10,000+"

    def test_above_threshold(self):
        assert format_total_display(50000) == "10,000+"

    def test_zero(self):
        assert format_total_display(0) == "0"

    def test_nine_nine_nine_nine(self):
        assert format_total_display(9999) == "9,999"


# ── get_proceeding_type_label ─────────────────────────────────────────────────

class TestProceedingTypeLabel:
    @pytest.mark.parametrize("pt,expected", [
        ("debate", "Debate"),
        ("zero_hour", "Zero Hour"),
        ("starred_question", "Starred Question"),
        ("unstarred_question", "Unstarred Question"),
        ("calling_attention", "Calling Attention"),
        ("adjournment_motion", "Adjournment Motion"),
        ("private_member_bill", "Private Member Bill"),
        ("short_duration_discussion", "Short Duration Discussion"),
        ("short_notice_question", "Short Notice Question"),
    ])
    def test_known_types(self, pt, expected):
        assert get_proceeding_type_label(pt) == expected

    def test_none_returns_none(self):
        assert get_proceeding_type_label(None) is None

    def test_unknown_type_titlecases(self):
        label = get_proceeding_type_label("some_new_type")
        assert label is not None
        assert "Some" in label


# ── build_filter_expression ───────────────────────────────────────────────────

class TestBuildFilterExpression:
    def test_none_filters_returns_none(self):
        assert build_filter_expression(None) is None

    def test_empty_filters_returns_none(self):
        assert build_filter_expression({}) is None

    def test_sources_filter(self):
        expr = build_filter_expression({"sources": ["LS"]})
        assert 'source IN ["LS"]' in expr

    def test_multiple_sources(self):
        expr = build_filter_expression({"sources": ["LS", "RS"]})
        assert "LS" in expr
        assert "RS" in expr

    def test_proceeding_types_filter(self):
        expr = build_filter_expression({"proceeding_types": ["debate"]})
        assert 'proceeding_type IN ["debate"]' in expr

    def test_date_from_filter(self):
        expr = build_filter_expression({"date_from": "2020-01-01"})
        assert 'date >= "2020-01-01"' in expr

    def test_date_to_filter(self):
        expr = build_filter_expression({"date_to": "2022-12-31"})
        assert 'date <= "2022-12-31"' in expr

    def test_speaker_filter(self):
        expr = build_filter_expression({"speaker": "Singh"})
        assert 'speaker_name CONTAINS "Singh"' in expr

    def test_session_filter(self):
        expr = build_filter_expression({"session": "Budget Session"})
        assert 'session_name CONTAINS "Budget Session"' in expr

    def test_multiple_filters_joined_with_and(self):
        expr = build_filter_expression({
            "sources": ["LS"],
            "proceeding_types": ["starred_question"],
        })
        assert " AND " in expr
        assert "source" in expr
        assert "proceeding_type" in expr

    def test_all_active_filters_joined(self):
        expr = build_filter_expression({
            "sources": ["LS"],
            "proceeding_types": ["debate"],
            "date_from": "2020-01-01",
            "date_to": "2022-12-31",
            "speaker": "Jairam Ramesh",
            "session": "Budget Session",
        })
        assert expr.count(" AND ") == 5  # 6 parts → 5 ANDs

    def test_whitespace_only_speaker_excluded(self):
        expr = build_filter_expression({"speaker": "   "})
        assert expr is None

    def test_whitespace_only_session_excluded(self):
        expr = build_filter_expression({"session": "\t\n"})
        assert expr is None

    def test_session_filter_excludes_ca_implicitly(self):
        """
        Session filter works at Meilisearch level: CA docs have no session_name
        so CONTAINS will never match them.  We verify the expression is built.
        """
        expr = build_filter_expression({"session": "Budget"})
        assert 'session_name CONTAINS "Budget"' in expr


# ── build_sort_params ─────────────────────────────────────────────────────────

class TestBuildSortParams:
    def test_relevance_returns_empty(self):
        assert build_sort_params("relevance") == []

    def test_chronological(self):
        params = build_sort_params("chronological")
        assert params[0] == "date:asc"
        assert params[1] == "sequence_within_sitting:asc"

    def test_reverse_chronological(self):
        params = build_sort_params("reverse_chronological")
        assert params[0] == "date:desc"
        assert params[1] == "sequence_within_sitting:desc"

    def test_secondary_sort_key_present(self):
        """Both sort modes must include sequence_within_sitting as secondary key."""
        for sort_val in ("chronological", "reverse_chronological"):
            params = build_sort_params(sort_val)
            assert len(params) == 2
            assert any("sequence_within_sitting" in p for p in params)

    def test_unknown_sort_returns_empty(self):
        assert build_sort_params("unknown") == []


# ── _build_snippet ────────────────────────────────────────────────────────────

class TestBuildSnippet:
    def test_returns_none_for_empty_text(self):
        snippet, from_sup = _build_snippet("", ["term"])
        assert snippet is None
        assert from_sup is False

    def test_returns_none_for_none_text(self):
        snippet, from_sup = _build_snippet(None, ["term"])
        assert snippet is None
        assert from_sup is False

    def test_marks_matched_term(self):
        text = "The Prime Minister spoke about infrastructure development."
        snippet, _ = _build_snippet(text, ["prime", "minister"])
        assert "<mark>Prime</mark>" in snippet
        assert "<mark>Minister</mark>" in snippet

    def test_html_escaped(self):
        text = "Article 370 & Jammu <Kashmir> discussion"
        snippet, _ = _build_snippet(text, ["article"])
        # HTML entities must appear
        assert "&amp;" in snippet or "&lt;" in snippet

    def test_non_matching_terms_not_marked(self):
        text = "The budget session discussed taxation policies."
        snippet, _ = _build_snippet(text, ["infrastructure"])
        assert "<mark>" not in snippet

    def test_supplementary_detection(self):
        text = (
            "Main question: What is the policy on water conservation?\n"
            "Answer: The government has taken steps.\n"
            "SUPPLEMENTARY QUESTION: Can the minister clarify the budget allocation?"
        )
        # The best snippet for "budget allocation" is in the supplementary section
        snippet, from_sup = _build_snippet(text, ["budget", "allocation"])
        assert from_sup is True

    def test_non_supplementary_detection(self):
        text = "The Prime Minister addressed the House on budget priorities."
        snippet, from_sup = _build_snippet(text, ["prime", "minister"])
        assert from_sup is False

    def test_best_window_selected(self):
        # Place query terms far apart; best window should contain both
        text = "aaa bbb " + "word " * 40 + "target1 target2 " + "word " * 40
        snippet, _ = _build_snippet(text, ["target1", "target2"])
        assert "<mark>target1</mark>" in snippet or "<mark>target2</mark>" in snippet


# ── format_result ─────────────────────────────────────────────────────────────

class TestFormatResult:
    def _make_hit(self, **overrides):
        base = {
            "id": "abc-123",
            "record_type": "speech",
            "source": "LS",
            "proceeding_type": "debate",
            "date": "2023-03-15",
            "session_name": "Budget Session 2023",
            "subject": "General Discussion",
            "full_text_en": "The Prime Minister spoke about infrastructure.",
            "is_translated": False,
            "source_url": "https://sansad.in/...",
            "speaker_name": "Jairam Ramesh",
            "speaker_party": "INC",
        }
        base.update(overrides)
        return base

    def test_basic_speech_result(self):
        hit = self._make_hit()
        result = format_result(hit, ["prime", "minister"])
        assert result["id"] == "abc-123"
        assert result["record_type"] == "speech"
        assert result["proceeding_type_label"] == "Debate"
        assert result["date_display"] == "15 March 2023"
        assert result["snippet"] is not None
        assert "<mark>Prime</mark>" in result["snippet"]

    def test_null_full_text_omits_snippet_key(self):
        """When full_text_en is null the 'snippet' key must be absent (DATA-MODELS.md 3.1)."""
        hit = self._make_hit(full_text_en=None)
        result = format_result(hit, ["prime"])
        assert "snippet" not in result
        assert "snippet_from_supplementary" not in result

    def test_present_full_text_includes_snippet_key(self):
        """When full_text_en is present both snippet keys must appear in the result."""
        hit = self._make_hit(full_text_en="The Prime Minister spoke about infrastructure.")
        result = format_result(hit, ["prime"])
        assert "snippet" in result
        assert "snippet_from_supplementary" in result

    def test_qa_fields_present(self):
        hit = {
            "id": "qa-1",
            "record_type": "qa",
            "source": "LS",
            "proceeding_type": "starred_question",
            "date": "2023-03-15",
            "question_number": 42,
            "questioner_names": ["Jairam Ramesh"],
            "questioner_party": "INC",
            "minister_name": "Amit Shah",
            "ministry": "Home Affairs",
            "full_text_en": "Question about budget.",
            "is_translated": False,
        }
        result = format_result(hit, ["budget"])
        assert result["question_number"] == 42
        assert result["minister_name"] == "Amit Shah"
        assert result["ministry"] == "Home Affairs"
        assert result["proceeding_type_label"] == "Starred Question"

    def test_date_display_formatted(self):
        hit = self._make_hit(date="1950-01-26")
        result = format_result(hit, [])
        assert result["date_display"] == "26 January 1950"
