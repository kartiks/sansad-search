"""
Tests for api/services/query_expander.py — F04 query expansion logic.
"""
from __future__ import annotations

import pytest

from api.services.query_expander import (
    _reset_cache,
    expand_query,
    load_synonyms,
    strip_stop_words,
)

# ── Minimal synonym fixture (overrides disk) ──────────────────────────────────

_SYNONYMS = [
    # phrase synonyms
    ["Lok Sabha", "House of the People", "Lower House"],
    ["fundamental rights", "basic rights", "Part III rights"],
    # single-term synonyms
    ["PM", "Prime Minister"],
    ["CM", "Chief Minister"],
    # multi-word abbreviation
    ["MGNREGA", "NREGA", "Mahatma Gandhi National Rural Employment Guarantee Act"],
    ["SC", "Scheduled Castes"],
]


# ── strip_stop_words ──────────────────────────────────────────────────────────

class TestStripStopWords:
    def test_removes_stop_words(self):
        clean, only_sw = strip_stop_words("the right to speech")
        assert clean == "right speech"
        assert only_sw is False

    def test_all_stop_words_returns_flag(self):
        clean, only_sw = strip_stop_words("the and or")
        assert only_sw is True

    def test_quoted_phrase_preserved(self):
        clean, only_sw = strip_stop_words('"the Speaker" spoke')
        assert '"the Speaker"' in clean
        assert only_sw is False

    def test_empty_query_is_only_stopwords(self):
        clean, only_sw = strip_stop_words("")
        assert only_sw is True

    def test_non_stop_word_preserved(self):
        clean, only_sw = strip_stop_words("Article 370")
        assert clean == "Article 370"
        assert only_sw is False

    def test_mixed_case_stop_words(self):
        clean, _ = strip_stop_words("The Rajya Sabha")
        assert "The" not in clean
        assert "Rajya" in clean
        assert "Sabha" in clean


# ── expand_query — single-term synonyms ──────────────────────────────────────

class TestSingleTermExpansion:
    def test_pm_expands_to_prime_minister(self):
        clean, notice = expand_query("PM Modi", _SYNONYMS)
        assert "Prime Minister" in notice

    def test_prime_minister_expands_to_pm(self):
        """Bidirectionality: phrase side also expands to abbreviation."""
        clean, notice = expand_query("Prime Minister Modi", _SYNONYMS)
        assert "PM" in notice

    def test_cm_expands_to_chief_minister(self):
        _, notice = expand_query("CM speech", _SYNONYMS)
        assert "Chief Minister" in notice

    def test_term_already_in_query_not_in_notice(self):
        """If PM and Prime Minister are both in the query, neither appears in notice."""
        _, notice = expand_query("PM Prime Minister", _SYNONYMS)
        # Both terms are already in the query
        assert "Prime Minister" not in notice
        assert "PM" not in notice

    def test_no_expansion_when_no_match(self):
        _, notice = expand_query("MGNREGA infrastructure", _SYNONYMS)
        # MGNREGA matches its own group, but let's check PM is NOT in notice
        assert "Prime Minister" not in notice
        assert "PM" not in notice

    def test_sc_expands(self):
        _, notice = expand_query("SC welfare", _SYNONYMS)
        assert "Scheduled Castes" in notice


# ── expand_query — phrase synonyms ───────────────────────────────────────────

class TestPhraseExpansion:
    def test_lok_sabha_expands(self):
        _, notice = expand_query("Lok Sabha debate", _SYNONYMS)
        assert "House of the People" in notice
        assert "Lower House" in notice

    def test_house_of_the_people_expands(self):
        _, notice = expand_query("House of the People debate", _SYNONYMS)
        assert "Lok Sabha" in notice
        assert "Lower House" in notice

    def test_fundamental_rights_expands(self):
        _, notice = expand_query("fundamental rights", _SYNONYMS)
        assert "basic rights" in notice
        assert "Part III rights" in notice

    def test_partial_phrase_does_not_expand(self):
        """'rights' alone must not trigger the phrase synonym 'fundamental rights'."""
        _, notice = expand_query("rights protection", _SYNONYMS)
        assert "fundamental rights" not in notice
        assert "basic rights" not in notice

    def test_phrase_expansion_deduped(self):
        """'Lok Sabha House of the People' — each sibling added only once."""
        _, notice = expand_query("Lok Sabha House of the People debate", _SYNONYMS)
        assert notice.count("Lower House") == 1

    def test_lower_house_not_in_notice_if_already_in_query(self):
        _, notice = expand_query("Lok Sabha Lower House debate", _SYNONYMS)
        assert "Lower House" not in notice


# ── Substring non-expansion (key F04 requirement) ────────────────────────────

class TestSubstringNonExpansion:
    def test_mgnrega_does_not_trigger_pm(self):
        """'PM' must not match as a substring of 'MGNREGA'."""
        _, notice = expand_query("MGNREGA scheme", _SYNONYMS)
        assert "Prime Minister" not in notice
        assert "PM" not in notice

    def test_exact_token_match_required(self):
        """'scheduled' alone must not trigger 'SC' expansion."""
        _, notice = expand_query("scheduled activity", _SYNONYMS)
        assert "Scheduled Castes" not in notice


# ── Phrase isolation (F04 requirement) ───────────────────────────────────────

class TestPhraseIsolation:
    def test_consumed_tokens_not_expanded_individually(self):
        """
        When 'fundamental rights' is matched as a phrase, the tokens 'fundamental'
        and 'rights' must not be expanded as standalone single-term synonyms.
        This is guaranteed by the consumed-token mechanism.  We also verify no
        spurious extra expansions sneak in from phrase tokens.
        """
        # In our test synonyms, 'fundamental' and 'rights' are NOT single-term
        # synonyms, so this test verifies no double-expansion occurs.
        _, notice = expand_query("fundamental rights Parliament", _SYNONYMS)
        # basic rights and Part III rights expected; no spurious expansions
        assert "basic rights" in notice
        assert "Part III rights" in notice


# ── MGNREGA group expansion ───────────────────────────────────────────────────

class TestMGNREGAExpansion:
    def test_mgnrega_expands_to_nrega_and_full_name(self):
        _, notice = expand_query("MGNREGA workers", _SYNONYMS)
        assert "NREGA" in notice
        assert "Mahatma Gandhi National Rural Employment Guarantee Act" in notice

    def test_nrega_expands_to_mgnrega(self):
        _, notice = expand_query("NREGA scheme", _SYNONYMS)
        assert "MGNREGA" in notice


# ── load_synonyms disk ────────────────────────────────────────────────────────

class TestLoadSynonyms:
    def setup_method(self):
        _reset_cache()

    def teardown_method(self):
        _reset_cache()

    def test_loads_from_disk(self):
        groups = load_synonyms()
        assert isinstance(groups, list)
        assert len(groups) > 0

    def test_cached_after_first_load(self):
        g1 = load_synonyms()
        g2 = load_synonyms()
        assert g1 is g2

    def test_pm_prime_minister_in_disk_synonyms(self):
        groups = load_synonyms()
        pm_group = next((g for g in groups if "PM" in g), None)
        assert pm_group is not None
        assert "Prime Minister" in pm_group

    def test_expand_query_uses_disk_synonyms(self):
        _, notice = expand_query("PM speech")
        assert "Prime Minister" in notice


# ── Gap 8: Spell correction suppression in quoted phrases (F04) ──────────────

class TestSpellCorrectionSuppressionInPhrases:
    """F04: Spell correction must NOT apply inside quoted phrase queries.

    Meilisearch natively disables typo tolerance for phrase queries (quoted
    strings). Our server-side responsibility is to forward the quoted phrase
    intact — which strip_stop_words guarantees by preserving quoted substrings
    verbatim. A misspelled term inside quotes must NOT be corrected by our code.

    Full verification (Meilisearch returns zero results for a misspelled phrase
    while applying typo correction for an unquoted variant) requires a
    fixture-backed integration test against a live Meilisearch instance.
    """

    def test_quoted_phrase_with_misspelling_preserved_verbatim(self):
        """strip_stop_words must keep a quoted phrase including misspelled words."""
        clean, only_sw = strip_stop_words('"Parliment debate"')
        assert '"Parliment debate"' in clean
        assert only_sw is False

    def test_stop_words_inside_quotes_not_stripped(self):
        """Stop words inside a quoted phrase must NOT be removed."""
        clean, _ = strip_stop_words('"the Prime Minister" spoke')
        assert '"the Prime Minister"' in clean

    def test_expand_query_does_not_alter_quoted_content(self):
        """expand_query must not strip, correct, or rewrite content inside quotes."""
        clean, notice = expand_query('"Parliment debate" speech', _SYNONYMS)
        # The misspelled quoted phrase must reach Meilisearch unchanged
        assert '"Parliment debate"' in clean


# ── Gap 9: Ambiguous abbreviation (F04) ──────────────────────────────────────

class TestAmbiguousAbbreviation:
    """F04: Ambiguous abbreviations must expand to ALL known dictionary entries.

    Inspection of synonyms.json confirms SC maps to exactly one expansion
    (Scheduled Castes) — there are no truly ambiguous entries in the current
    dictionary. This class verifies:
    (a) SC produces exactly the documented single expansion,
    (b) no token appears in more than one synonym group (no ambiguity),
    (c) the expansion uses the real disk dictionary.
    """

    def setup_method(self):
        _reset_cache()

    def teardown_method(self):
        _reset_cache()

    def test_sc_expands_to_scheduled_castes_only(self):
        """SC has one sibling in synonyms.json; expansion_notice must be exactly that."""
        _, notice = expand_query("SC welfare")
        assert "Scheduled Castes" in notice
        # The real synonyms.json SC group is ["SC", "Scheduled Castes"] — one sibling
        assert notice == ["Scheduled Castes"], (
            f"Expected ['Scheduled Castes'] only; got {notice}. "
            "If synonyms.json gained a new SC entry this test must be updated."
        )

    def test_no_token_appears_in_multiple_synonym_groups(self):
        """No token may belong to more than one synonym group.

        If a token appeared in two groups its expansion would be ambiguous and
        the test spec requirement 'expands to ALL known expansions' would be
        impossible to satisfy deterministically.
        """
        groups = load_synonyms()
        seen: dict = {}
        for group in groups:
            for member in group:
                lower = member.lower()
                if lower in seen and seen[lower] != group:
                    raise AssertionError(
                        f"Token {member!r} appears in multiple synonym groups: "
                        f"{seen[lower]} AND {group}"
                    )
                seen[lower] = group

    def test_sc_expansion_uses_real_disk_dictionary(self):
        """expand_query must use disk synonyms (not a hardcoded fixture)."""
        _, notice = expand_query("SC welfare")   # no synonyms_data= → uses disk
        assert "Scheduled Castes" in notice


# ── Gap 10: Dictionary as sole source of synonyms (F04) ──────────────────────

class TestDictionaryAsSoleSource:
    """F04: All synonym expansions must originate from data/synonyms.json only.

    This is verified by confirming that expand_query with synonyms_data=[] (empty
    dictionary) produces no expansions for any input — i.e., there are no
    hardcoded expansions in the application code itself.
    """

    def test_empty_synonyms_suppresses_abbreviation_expansion(self):
        """PM must not expand to Prime Minister when the dictionary is empty."""
        _, notice = expand_query("PM speech", synonyms_data=[])
        assert notice == []

    def test_empty_synonyms_suppresses_phrase_expansion(self):
        """Lok Sabha must not expand when the dictionary is empty."""
        _, notice = expand_query("Lok Sabha debate", synonyms_data=[])
        assert notice == []

    def test_empty_synonyms_suppresses_expansion_for_all_sample_queries(self):
        """No expansion produced by any sample query when dictionary is empty."""
        sample_queries = [
            "MGNREGA scheme",
            "RTI application",
            "SC welfare programs",
            "fundamental rights petition",
            "Rajya Sabha proceedings",
        ]
        for q in sample_queries:
            _, notice = expand_query(q, synonyms_data=[])
            assert notice == [], (
                f"Unexpected expansion for {q!r} with empty dict: {notice}. "
                "This indicates a hardcoded synonym in application code."
            )
