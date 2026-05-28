"""Tests for ingest.canonical.names — speaker name canonicalization."""
from __future__ import annotations

import csv
import pytest
from pathlib import Path

from ingest.canonical.names import (
    canonicalize_name,
    load_names_dict,
    normalize_for_dedup,
    strip_honorifics,
)


# ── strip_honorifics ──────────────────────────────────────────────────────────

class TestStripHonorifics:
    @pytest.mark.parametrize("raw,expected", [
        ("Shri Narendra Modi", "Narendra Modi"),
        ("Smt. Smriti Irani", "Smriti Irani"),
        ("Dr. Manmohan Singh", "Manmohan Singh"),
        ("Prof. M. V. Rajeev Gowda", "M. V. Rajeev Gowda"),
        ("Adv. Priyanka Chaturvedi", "Priyanka Chaturvedi"),
        ("Kumari Selja", "Selja"),
        ("Mr. Speaker", "Speaker"),
        ("Dr. B. R. Ambedkar", "B. R. Ambedkar"),
        ("Shri Rahul Gandhi", "Rahul Gandhi"),
        # Multiple honorifics
        ("Shri Dr. A. P. J. Abdul Kalam", "A. P. J. Abdul Kalam"),
    ])
    def test_strips_honorific(self, raw, expected):
        assert strip_honorifics(raw) == expected

    def test_no_honorific_unchanged(self):
        assert strip_honorifics("Narendra Modi") == "Narendra Modi"

    def test_empty_string_unchanged(self):
        assert strip_honorifics("") == ""

    def test_strips_are_idempotent(self):
        name = "Shri Narendra Modi"
        once = strip_honorifics(name)
        twice = strip_honorifics(once)
        assert once == twice


# ── normalize_for_dedup ───────────────────────────────────────────────────────

class TestNormalizeForDedup:
    def test_lowercase_spaces_to_underscores(self):
        assert normalize_for_dedup("Narendra Modi") == "narendra_modi"

    def test_strips_punctuation(self):
        assert normalize_for_dedup("B. R. Ambedkar") == "b_r_ambedkar"

    def test_none_returns_unknown(self):
        assert normalize_for_dedup(None) == "unknown"

    def test_empty_returns_unknown(self):
        assert normalize_for_dedup("") == "unknown"

    def test_collapses_multiple_spaces(self):
        result = normalize_for_dedup("A  B  C")
        assert "_" not in result.replace("a_b_c", "")  # no double underscores


# ── load_names_dict ───────────────────────────────────────────────────────────

class TestLoadNamesDict:
    def test_loads_valid_csv(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text(
            "variant,canonical_name\n"
            "Narendra Modi,Narendra Modi\n"
            "N. Modi,Narendra Modi\n"
            "Modi Narendra,Narendra Modi\n"
        )
        d = load_names_dict(csv_file)
        assert d["narendra modi"] == "Narendra Modi"
        assert d["n. modi"] == "Narendra Modi"
        assert d["modi narendra"] == "Narendra Modi"

    def test_missing_file_returns_empty(self, tmp_path):
        d = load_names_dict(tmp_path / "nonexistent.csv")
        assert d == {}

    def test_skips_rows_with_empty_variant(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text(
            "variant,canonical_name\n"
            ",Narendra Modi\n"
            "Valid Name,Valid Name\n"
        )
        d = load_names_dict(csv_file)
        assert "" not in d
        assert "valid name" in d

    def test_lookup_is_case_insensitive(self, tmp_path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("variant,canonical_name\nNarendra Modi,Narendra Modi\n")
        d = load_names_dict(csv_file)
        assert "narendra modi" in d


# ── canonicalize_name ─────────────────────────────────────────────────────────

class TestCanonicalizeNameIntegration:
    @pytest.fixture()
    def names_dict(self):
        return {
            "narendra modi": "Narendra Modi",
            "n. modi": "Narendra Modi",
            "modi narendra": "Narendra Modi",
            "rahul gandhi": "Rahul Gandhi",
        }

    def test_known_variant_resolves_with_unresolved_false(self, names_dict):
        name, unresolved = canonicalize_name("Shri Narendra Modi", names_dict)
        assert name == "Narendra Modi"
        assert unresolved is False

    def test_abbreviated_form_resolves(self, names_dict):
        name, unresolved = canonicalize_name("N. Modi", names_dict)
        assert name == "Narendra Modi"
        assert unresolved is False

    def test_reversed_order_resolves(self, names_dict):
        name, unresolved = canonicalize_name("Modi Narendra", names_dict)
        assert name == "Narendra Modi"
        assert unresolved is False

    def test_unknown_name_returns_stripped_with_unresolved_true(self, names_dict):
        name, unresolved = canonicalize_name("Shri Unknown Person", names_dict)
        assert name == "Unknown Person"
        assert unresolved is True

    def test_none_input_returns_none_false(self, names_dict):
        name, unresolved = canonicalize_name(None, names_dict)
        assert name is None
        assert unresolved is False

    def test_empty_string_returns_none_false(self, names_dict):
        name, unresolved = canonicalize_name("", names_dict)
        assert name is None
        assert unresolved is False

    def test_honorific_stripped_before_lookup(self, names_dict):
        """'Shri Narendra Modi' and 'Narendra Modi' must produce identical canonical names."""
        name1, _ = canonicalize_name("Shri Narendra Modi", names_dict)
        name2, _ = canonicalize_name("Narendra Modi", names_dict)
        assert name1 == name2

    def test_three_variants_produce_identical_speaker_name(self, names_dict):
        """
        'Shri Narendra Modi', 'Narendra Modi', 'N. Modi' → identical canonical name.
        This is the F01 test spec requirement.
        """
        variants = ["Shri Narendra Modi", "Narendra Modi", "N. Modi"]
        results = [canonicalize_name(v, names_dict)[0] for v in variants]
        assert len(set(results)) == 1, f"Expected identical names, got: {results}"

    def test_unresolved_raw_name_not_empty(self, names_dict):
        """Unresolved names must store the raw name (stripped), not empty string."""
        name, unresolved = canonicalize_name("Shri Unknown Member", names_dict)
        assert unresolved is True
        assert name is not None
        assert name != ""
        assert name == "Unknown Member"
