"""Tests for ingest.setup_meilisearch — pure-function and constant validation.

No Meilisearch connection required; all tests run against in-memory data.
"""
import json
from pathlib import Path

import pytest

from ingest.setup_meilisearch import (
    _load_synonyms,
    SEARCHABLE_ATTRIBUTES,
    FILTERABLE_ATTRIBUTES,
    SORTABLE_ATTRIBUTES,
    RANKING_RULES,
    TYPO_TOLERANCE,
    PAGINATION,
    INDEX_NAME,
)

SYNONYMS_PATH = Path(__file__).parent.parent / "data" / "synonyms.json"


# ── _load_synonyms ────────────────────────────────────────────────────────────

class TestLoadSynonyms:
    def test_returns_list(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        assert isinstance(pairs, list)

    def test_each_pair_has_word_and_synonyms_keys(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        for pair in pairs:
            assert "word" in pair, f"Missing 'word' key: {pair}"
            assert "synonyms" in pair, f"Missing 'synonyms' key: {pair}"

    def test_synonyms_is_list_of_strings(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        for pair in pairs:
            assert isinstance(pair["synonyms"], list)
            assert all(isinstance(s, str) for s in pair["synonyms"])

    def test_bidirectional_pm_prime_minister(self):
        """PM → [Prime Minister] and Prime Minister → [PM] must both be present."""
        pairs = _load_synonyms(SYNONYMS_PATH)
        word_map = {p["word"]: p["synonyms"] for p in pairs}
        assert "PM" in word_map, "PM must have a synonym entry"
        assert "Prime Minister" in word_map["PM"]
        assert "Prime Minister" in word_map, "Prime Minister must have a synonym entry"
        assert "PM" in word_map["Prime Minister"]

    def test_bidirectional_lok_sabha_house_of_people(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        word_map = {p["word"]: p["synonyms"] for p in pairs}
        assert "Lok Sabha" in word_map
        assert "House of the People" in word_map["Lok Sabha"]
        assert "House of the People" in word_map
        assert "Lok Sabha" in word_map["House of the People"]

    def test_no_term_expands_to_itself(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        for pair in pairs:
            assert pair["word"] not in pair["synonyms"], \
                f"{pair['word']!r} must not expand to itself"

    def test_each_term_excluded_from_own_synonyms_list(self):
        pairs = _load_synonyms(SYNONYMS_PATH)
        for pair in pairs:
            assert pair["word"] not in pair["synonyms"]

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_synonyms(tmp_path / "nonexistent.json")

    def test_all_synonym_groups_produce_bidirectional_entries(self):
        """Every term in every group must appear as both a 'word' and in others' 'synonyms'."""
        with SYNONYMS_PATH.open() as f:
            data = json.load(f)

        pairs = _load_synonyms(SYNONYMS_PATH)
        word_map = {p["word"]: set(p["synonyms"]) for p in pairs}

        for category_groups in data.values():
            if not isinstance(category_groups, list):
                continue
            for group in category_groups:
                if not isinstance(group, list) or len(group) < 2:
                    continue
                for term in group:
                    assert term in word_map, f"{term!r} missing from synonym word entries"
                    for other in group:
                        if other != term:
                            assert other in word_map[term], \
                                f"{term!r} should expand to {other!r} but does not"


# ── Index configuration constants (DATA-MODELS.md §2.3) ──────────────────────

class TestIndexConfiguration:
    def test_index_name(self):
        assert INDEX_NAME == "parliamentary_records"

    def test_searchable_attributes_order(self):
        """Order determines Meilisearch field-level ranking weight."""
        expected = [
            "speaker_name",
            "minister_name",
            "ministry",
            "questioner_names",
            "subject",
            "full_text_en",
        ]
        assert SEARCHABLE_ATTRIBUTES == expected

    def test_filterable_attributes_contains_required(self):
        required = ["source", "proceeding_type", "date", "speaker_name",
                    "session_name", "minister_name", "record_type"]
        for attr in required:
            assert attr in FILTERABLE_ATTRIBUTES, f"Missing filterable attr: {attr}"

    def test_sortable_attributes(self):
        assert "date" in SORTABLE_ATTRIBUTES
        assert "sequence_within_sitting" in SORTABLE_ATTRIBUTES

    def test_ranking_rules_order(self):
        expected = ["words", "typos", "proximity", "attribute", "sort", "exactness"]
        assert RANKING_RULES == expected

    def test_pagination_max_total_hits(self):
        assert PAGINATION["maxTotalHits"] == 10000

    def test_typo_tolerance_enabled(self):
        assert TYPO_TOLERANCE["enabled"] is True

    def test_typo_tolerance_one_typo_threshold_is_4(self):
        """
        Test spec: "A query term of exactly 4 characters must be eligible for
        spell correction." Setting oneTypo=4 means words of length ≥4 get
        one-typo tolerance; words of 1–3 chars (fewer than 4) are exempt.
        """
        assert TYPO_TOLERANCE["minWordSizeForTypos"]["oneTypo"] == 4, (
            "oneTypo must be 4 so that 4-char terms are eligible for spell correction; "
            "values > 4 would also exempt 4-char terms, violating the test spec."
        )

    def test_typo_tolerance_two_typos_threshold(self):
        assert TYPO_TOLERANCE["minWordSizeForTypos"]["twoTypos"] == 9

    def test_typo_tolerance_disabled_on_structural_attributes(self):
        disabled = TYPO_TOLERANCE["disableOnAttributes"]
        for attr in ["date", "source", "proceeding_type", "source_url"]:
            assert attr in disabled, f"{attr} must have typo tolerance disabled"
