"""Tests for ingest.canonical.sessions — session name canonicalization."""
from __future__ import annotations

import pytest

from ingest.canonical.sessions import canonicalize_session


class TestCanonicalizeSession:
    # ── CA always returns None ─────────────────────────────────────────────────

    def test_ca_source_returns_none(self):
        assert canonicalize_session("Budget Session 2023", "CA") is None

    def test_ca_source_returns_none_even_when_session_is_none(self):
        assert canonicalize_session(None, "CA") is None

    # ── None / empty input ─────────────────────────────────────────────────────

    def test_none_session_name_returns_none(self):
        assert canonicalize_session(None, "LS") is None

    def test_empty_session_name_returns_none(self):
        assert canonicalize_session("", "LS") is None

    # ── Basic canonicalization ─────────────────────────────────────────────────

    @pytest.mark.parametrize("raw,expected", [
        ("Budget Session, 2023", "Budget Session 2023"),
        ("Budget Session 2023", "Budget Session 2023"),
        ("BUDGET SESSION 2023", "Budget Session 2023"),
        ("budget session 2023", "Budget Session 2023"),
        ("Monsoon Session 2022", "Monsoon Session 2022"),
        ("MONSOON SESSION 2022", "Monsoon Session 2022"),
        ("Winter Session, 2021", "Winter Session 2021"),
        ("WINTER SESSION 2021", "Winter Session 2021"),
    ])
    def test_basic_session_type_canonicalization(self, raw, expected):
        result = canonicalize_session(raw, "LS")
        assert result == expected, f"{raw!r} → {result!r} (expected {expected!r})"

    # ── Multi-part sessions ────────────────────────────────────────────────────

    @pytest.mark.parametrize("raw,expected", [
        ("Monsoon Session 2022 (Part 2)", "Monsoon Session 2022 (Part 2)"),
        ("Budget Session 2023 (Second Part)", "Budget Session 2023 (Part 2)"),
        ("Winter Session 2021 (Second Part)", "Winter Session 2021 (Part 2)"),
        ("Budget Session, 2023 (Part 2)", "Budget Session 2023 (Part 2)"),
        ("Monsoon Session 2022 (First Part)", "Monsoon Session 2022 (Part 1)"),
    ])
    def test_part_suffix_canonicalization(self, raw, expected):
        result = canonicalize_session(raw, "RS")
        assert result == expected, f"{raw!r} → {result!r}"

    # ── Variant equivalence (test spec requirement) ────────────────────────────

    def test_variants_of_same_session_produce_identical_name(self):
        """
        'Budget Session, 2023', 'Budget Session 2023', 'BUDGET SESSION 2023'
        must all produce the same canonical string.
        """
        variants = [
            "Budget Session, 2023",
            "Budget Session 2023",
            "BUDGET SESSION 2023",
        ]
        results = {canonicalize_session(v, "LS") for v in variants}
        assert len(results) == 1, f"Expected identical results, got: {results}"

    def test_ls_and_rs_same_session_canonical(self):
        """Same session name produces the same canonical form for LS and RS."""
        ls = canonicalize_session("Monsoon Session 2022", "LS")
        rs = canonicalize_session("Monsoon Session 2022", "RS")
        assert ls == rs
