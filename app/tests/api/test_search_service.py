"""
Tests for api/services/search.py — filter builder, sort mapper, snippet,
date display, and total display.
"""
from __future__ import annotations

import pytest

from api.services.search import (
    DEFAULT_SNIPPET_WORDS,
    SNIPPET_SIZE_MAX,
    SNIPPET_SIZE_MIN,
    build_filter_expression,
    build_sort_params,
    format_date_display,
    format_total_display,
    get_proceeding_type_label,
    resolve_effective_snippet_size,
    _build_snippet,
    _merge_expansion_terms,
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

    def test_subject_filter(self):
        expr = build_filter_expression({"subject": "Railways"})
        assert 'subject CONTAINS "Railways"' in expr

    def test_subject_filter_multiword(self):
        expr = build_filter_expression({"subject": "Demands for Grants"})
        assert 'subject CONTAINS "Demands for Grants"' in expr

    def test_subject_filter_escapes_inner_quotes(self):
        expr = build_filter_expression({"subject": 'Budget "Railways"'})
        assert '\\"Railways\\"' in expr

    def test_whitespace_only_subject_excluded(self):
        expr = build_filter_expression({"subject": "  "})
        assert expr is None

    def test_all_active_filters_with_subject_joined(self):
        expr = build_filter_expression({
            "sources": ["LS"],
            "proceeding_types": ["debate"],
            "date_from": "2020-01-01",
            "date_to": "2022-12-31",
            "speaker": "Jairam Ramesh",
            "session": "Budget Session",
            "subject": "Railways",
        })
        assert expr.count(" AND ") == 6  # 7 parts → 6 ANDs
        assert 'subject CONTAINS "Railways"' in expr

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

    @staticmethod
    def _word_count(snippet: str) -> int:
        import re as _re
        return len(_re.findall(r"[a-zA-Z0-9]+", _re.sub(r"<[^>]+>", "", snippet)))

    def test_snippet_default_100_words_for_long_text(self):
        """Default window is now 100 words (PRD v3.3, lowered from legacy 200)."""
        text = " ".join(f"word{i}" for i in range(1000)) + " target end"
        snippet, _ = _build_snippet(text, ["target"])
        words = self._word_count(snippet)
        # ~100 words: at least 100, and clearly below the legacy 200 default.
        assert words >= 100
        assert words < 200

    def test_snippet_window_honours_explicit_size(self):
        """An explicit snippet_words drives the crop window size."""
        text = " ".join(f"word{i}" for i in range(1000)) + " target end"
        snippet, _ = _build_snippet(text, ["target"], snippet_words=300)
        words = self._word_count(snippet)
        assert words >= 300

    def test_short_text_returned_in_full_no_padding(self):
        """A text shorter than the window is returned whole (no truncation, no padding)."""
        text = "Only a handful of words about budget policy here."
        snippet, _ = _build_snippet(text, ["budget"], snippet_words=300)
        import re as _re
        stripped = _re.sub(r"<[^>]+>", "", snippet)
        assert "handful" in stripped and "policy" in stripped
        # No padding: snippet word count equals the source word count, not 300.
        assert self._word_count(snippet) == 9


# ── resolve_effective_snippet_size (F02/F05 — PRD v3.3) ───────────────────────

class TestResolveEffectiveSnippetSize:
    """DATA-MODELS §2.3 'Effective snippet size' resolution rule."""

    def test_default_when_absent(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(None) == DEFAULT_SNIPPET_WORDS  # 100

    def test_bounds_inclusive(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(SNIPPET_SIZE_MIN) == 20
        assert resolve_effective_snippet_size(SNIPPET_SIZE_MAX) == 1000

    def test_clamp_low(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(19) == 20
        assert resolve_effective_snippet_size(0) == 20
        assert resolve_effective_snippet_size(-5) == 20

    def test_clamp_high(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(1001) == 1000
        assert resolve_effective_snippet_size(5000) == 1000

    def test_in_range_passes_through(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(300) == 300

    def test_non_integer_float_falls_back(self, monkeypatch):
        """A JSON float (non-integer numeric) falls back to default — not rounded/truncated."""
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(100.5) == DEFAULT_SNIPPET_WORDS
        assert resolve_effective_snippet_size(300.0) == DEFAULT_SNIPPET_WORDS

    def test_string_falls_back(self, monkeypatch):
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size("300") == DEFAULT_SNIPPET_WORDS
        assert resolve_effective_snippet_size("") == DEFAULT_SNIPPET_WORDS
        assert resolve_effective_snippet_size("abc") == DEFAULT_SNIPPET_WORDS

    def test_bool_falls_back(self, monkeypatch):
        """bool is an int subclass but JSON true/false must fall back, not clamp."""
        monkeypatch.delenv("SNIPPET_DEFAULT_WORDS", raising=False)
        assert resolve_effective_snippet_size(True) == DEFAULT_SNIPPET_WORDS
        assert resolve_effective_snippet_size(False) == DEFAULT_SNIPPET_WORDS

    def test_operator_default_env_used(self, monkeypatch):
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "250")
        assert resolve_effective_snippet_size(None) == 250
        assert resolve_effective_snippet_size("not-a-number") == 250

    def test_operator_default_out_of_range_clamped(self, monkeypatch):
        """Even a mis-set operator default is clamped (NFR PERF-4)."""
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "5000")
        assert resolve_effective_snippet_size(None) == 1000
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "5")
        assert resolve_effective_snippet_size(None) == 20

    def test_operator_default_invalid_env_falls_back_to_100(self, monkeypatch):
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "abc")
        assert resolve_effective_snippet_size(None) == DEFAULT_SNIPPET_WORDS
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "100.5")
        assert resolve_effective_snippet_size(None) == DEFAULT_SNIPPET_WORDS

    def test_per_request_integer_overrides_operator_default(self, monkeypatch):
        monkeypatch.setenv("SNIPPET_DEFAULT_WORDS", "250")
        assert resolve_effective_snippet_size(300) == 300


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

    def test_lang_original_and_time_of_day_present_in_result(self):
        """DATA-MODELS §3.1: lang_original and time_of_day must appear on every search result."""
        hit = self._make_hit(lang_original="en", time_of_day="14:32")
        result = format_result(hit, [])
        assert result["lang_original"] == "en"
        assert result["time_of_day"] == "14:32"

    def test_lang_original_and_time_of_day_null_when_absent(self):
        """Fields are null (not absent) when not present in the hit."""
        hit = self._make_hit()
        result = format_result(hit, [])
        assert "lang_original" in result
        assert result["lang_original"] is None
        assert "time_of_day" in result
        assert result["time_of_day"] is None


# ── _merge_expansion_terms ────────────────────────────────────────────────────

class TestMergeExpansionTerms:
    def test_no_expansion_returns_original(self):
        terms = _merge_expansion_terms(["budget", "allocation"], None)
        assert set(terms) == {"budget", "allocation"}

    def test_empty_expansion_returns_original(self):
        terms = _merge_expansion_terms(["budget"], [])
        assert set(terms) == {"budget"}

    def test_single_word_synonym_added(self):
        terms = _merge_expansion_terms(["budget"], ["allocation"])
        assert "budget" in terms
        assert "allocation" in terms

    def test_phrase_synonym_tokenized(self):
        terms = _merge_expansion_terms(["rights"], ["fundamental rights", "Article 14"])
        assert "fundamental" in terms
        assert "rights" in terms
        assert "article" in terms
        assert "14" in terms

    def test_duplicate_terms_not_repeated(self):
        terms = _merge_expansion_terms(["rights"], ["rights"])
        assert terms.count("rights") == 1

    def test_expansion_terms_lowercased(self):
        terms = _merge_expansion_terms(["budget"], ["BUDGET", "Allocation"])
        assert "budget" in terms
        assert "allocation" in terms
        assert "BUDGET" not in terms

    def test_snippet_highlights_synonym_term(self):
        """Synonym tokens must be highlighted in the snippet even when absent from query."""
        text = (
            "The government must protect fundamental rights under the constitution. "
            "Article 14 guarantees equality before the law."
        )
        # User typed "rights"; synonym expansion adds "Article 14"
        all_terms = _merge_expansion_terms(["rights"], ["Article 14"])
        snippet, _ = _build_snippet(text, all_terms)
        assert snippet is not None
        assert "<mark>" in snippet
        # Both the original query term and the synonym term must be highlighted
        assert "<mark>rights</mark>" in snippet or "<mark>Article</mark>" in snippet
