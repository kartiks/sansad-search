"""Tests for app/data/synonyms.json — validates completeness and structure per F04."""
import json
import pytest
from pathlib import Path

SYNONYMS_PATH = Path(__file__).parent.parent / "data" / "synonyms.json"


@pytest.fixture(scope="module")
def synonyms():
    with SYNONYMS_PATH.open() as f:
        return json.load(f)


def test_synonyms_file_is_valid_json():
    assert SYNONYMS_PATH.exists()
    with SYNONYMS_PATH.open() as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_synonyms_has_all_categories(synonyms):
    required = ["legislative_bodies", "constitutional_terminology",
                "parliamentary_procedure", "abbreviations", "legislation"]
    for cat in required:
        assert cat in synonyms, f"Missing category: {cat}"


def test_all_groups_are_lists_of_at_least_two(synonyms):
    for cat, groups in synonyms.items():
        if not isinstance(groups, list):
            continue
        for i, group in enumerate(groups):
            assert isinstance(group, list), f"{cat}[{i}] must be a list"
            assert len(group) >= 2, f"{cat}[{i}] must have at least 2 terms"


# ── Legislative bodies (F04) ──────────────────────────────────────────────────

class TestLegislativeBodies:
    def _all_terms(self, synonyms) -> list[str]:
        return [t for g in synonyms["legislative_bodies"] for t in g]

    def test_lok_sabha_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Lok Sabha" in terms

    def test_house_of_people_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "House of the People" in terms

    def test_lower_house_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Lower House" in terms

    def test_rajya_sabha_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Rajya Sabha" in terms

    def test_council_of_states_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Council of States" in terms

    def test_upper_house_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Upper House" in terms

    def test_parliament_both_houses(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Parliament" in terms
        assert "both Houses" in terms

    def test_constituent_assembly_ca(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Constituent Assembly" in terms
        assert "CA" in terms

    def test_lok_sabha_in_same_group_as_house_of_people(self, synonyms):
        for group in synonyms["legislative_bodies"]:
            if "Lok Sabha" in group:
                assert "House of the People" in group
                return
        pytest.fail("Lok Sabha and House of the People must be in the same synonym group")

    def test_rajya_sabha_in_same_group_as_council_of_states(self, synonyms):
        for group in synonyms["legislative_bodies"]:
            if "Rajya Sabha" in group:
                assert "Council of States" in group
                return
        pytest.fail("Rajya Sabha and Council of States must be in the same synonym group")


# ── Constitutional terminology (F04) ─────────────────────────────────────────

class TestConstitutionalTerminology:
    def _all_terms(self, synonyms) -> list[str]:
        return [t for g in synonyms["constitutional_terminology"] for t in g]

    def test_fundamental_rights(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "fundamental rights" in terms
        assert "basic rights" in terms
        assert "Part III rights" in terms  # gap 13

    def test_fundamental_rights_three_way_same_group(self, synonyms):
        for group in synonyms["constitutional_terminology"]:
            if "fundamental rights" in group:
                assert "basic rights" in group
                assert "Part III rights" in group, \
                    "fundamental rights, basic rights, and Part III rights must be in the same group"
                return
        pytest.fail("fundamental rights not found in constitutional_terminology")

    def test_amendment_constitutional_amendment(self, synonyms):  # gap 14
        terms = self._all_terms(synonyms)
        assert "amendment" in terms
        assert "constitutional amendment" in terms

    def test_amendment_same_group(self, synonyms):
        for group in synonyms["constitutional_terminology"]:
            if "amendment" in group:
                assert "constitutional amendment" in group, \
                    "amendment and constitutional amendment must be in the same group"
                return
        pytest.fail("amendment not found in constitutional_terminology")

    def test_dpsp_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Directive Principles" in terms  # gap 16 — short form
        assert "DPSP" in terms
        assert "Directive Principles of State Policy" in terms

    def test_dpsp_three_way_same_group(self, synonyms):
        for group in synonyms["constitutional_terminology"]:
            if "DPSP" in group:
                assert "Directive Principles" in group, \
                    "Directive Principles (short form) must be in the DPSP group"
                assert "Directive Principles of State Policy" in group
                return
        pytest.fail("DPSP not found in constitutional_terminology")

    def test_preamble_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "Preamble" in terms
        assert "preamble to the Constitution" in terms  # gap 15

    def test_preamble_same_group(self, synonyms):
        for group in synonyms["constitutional_terminology"]:
            if "Preamble" in group:
                assert "preamble to the Constitution" in group, \
                    "Preamble and preamble to the Constitution must be in the same group"
                return
        pytest.fail("Preamble not found in constitutional_terminology")


# ── Parliamentary procedure (F04) ────────────────────────────────────────────

class TestParliamentaryProcedure:
    def _all_terms(self, synonyms) -> list[str]:
        return [t for g in synonyms["parliamentary_procedure"] for t in g]

    def test_starred_question_oral_question(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "starred question" in terms
        assert "oral question" in terms

    def test_unstarred_question_written_question(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "unstarred question" in terms
        assert "written question" in terms

    def test_zero_hour_variants(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "zero hour" in terms
        assert "zero-hour" in terms

    def test_private_member_bill_variants(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "private member bill" in terms
        assert "private member's bill" in terms

    def test_question_hour_question_period(self, synonyms):  # gap 17
        terms = self._all_terms(synonyms)
        assert "Question Hour" in terms
        assert "question period" in terms

    def test_question_hour_same_group(self, synonyms):
        for group in synonyms["parliamentary_procedure"]:
            if "Question Hour" in group:
                assert "question period" in group, \
                    "Question Hour and question period must be in the same group"
                return
        pytest.fail("Question Hour not found in parliamentary_procedure")

    def test_calling_attention_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "calling attention" in terms
        assert "calling attention motion" in terms  # gap 18

    def test_calling_attention_same_group(self, synonyms):
        for group in synonyms["parliamentary_procedure"]:
            if "calling attention" in group:
                assert "calling attention motion" in group, \
                    "calling attention and calling attention motion must be in the same group"
                return
        pytest.fail("calling attention not found in parliamentary_procedure")

    def test_adjournment_motion_present(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "adjournment motion" in terms
        assert "adjournment" in terms  # gap 19

    def test_adjournment_same_group(self, synonyms):
        for group in synonyms["parliamentary_procedure"]:
            if "adjournment motion" in group:
                assert "adjournment" in group, \
                    "adjournment motion and adjournment must be in the same group"
                return
        pytest.fail("adjournment motion not found in parliamentary_procedure")

    def test_division_vote(self, synonyms):
        terms = self._all_terms(synonyms)
        assert "division" in terms
        assert "vote" in terms


# ── Abbreviations (F04) ───────────────────────────────────────────────────────

class TestAbbreviations:
    def _all_terms(self, synonyms) -> list[str]:
        return [t for g in synonyms["abbreviations"] for t in g]

    @pytest.mark.parametrize("abbr,expansion", [
        ("PM", "Prime Minister"),
        ("CM", "Chief Minister"),
        ("SC", "Scheduled Castes"),
        ("ST", "Scheduled Tribes"),
        ("SC/ST", "Scheduled Castes and Scheduled Tribes"),
        ("OBC", "Other Backward Classes"),
        ("EWS", "Economically Weaker Sections"),
        ("GST", "Goods and Services Tax"),
        ("CAG", "Comptroller and Auditor General"),
        ("CBI", "Central Bureau of Investigation"),
        ("ED", "Enforcement Directorate"),
        ("FIR", "First Information Report"),
        ("PIL", "Public Interest Litigation"),
        ("Art.", "Article"),
        ("Sec.", "Section"),
        ("Cl.", "Clause"),
    ])
    def test_abbreviation_expansion(self, synonyms, abbr, expansion):
        for group in synonyms["abbreviations"]:
            if abbr in group:
                assert expansion in group, f"{abbr} must expand to {expansion!r}"
                return
        pytest.fail(f"{abbr!r} not found in abbreviations category")

    def test_obc_other_backward_communities(self, synonyms):  # gap 20
        for group in synonyms["abbreviations"]:
            if "OBC" in group:
                assert "Other Backward Communities" in group, \
                    "OBC group must include Other Backward Communities"
                return
        pytest.fail("OBC not found in abbreviations")

    def test_sc_and_st_are_separate_from_sc_st(self, synonyms):
        sc_group = None
        scst_group = None
        for group in synonyms["abbreviations"]:
            if "SC" in group and "ST" not in group:
                sc_group = group
            if "SC/ST" in group:
                scst_group = group
        assert sc_group is not None, "SC (without ST) must be in its own group"
        assert scst_group is not None, "SC/ST phrase must be in its own group"


# ── Well-known legislation (F04) ─────────────────────────────────────────────

class TestLegislation:
    def _all_terms(self, synonyms) -> list[str]:
        return [t for g in synonyms["legislation"] for t in g]

    @pytest.mark.parametrize("abbr,expansion", [
        ("RTI", "Right to Information"),
        ("RTE", "Right to Education"),
        ("MGNREGA", "Mahatma Gandhi National Rural Employment Guarantee Act"),
        ("NREGA", "Mahatma Gandhi National Rural Employment Guarantee Act"),
        ("POCSO", "Protection of Children from Sexual Offences"),
        ("IPC", "Indian Penal Code"),
        ("CrPC", "Code of Criminal Procedure"),
        ("BNS", "Bharatiya Nyaya Sanhita"),
        ("BNSS", "Bharatiya Nagarik Suraksha Sanhita"),
    ])
    def test_legislation_expansion(self, synonyms, abbr, expansion):
        for group in synonyms["legislation"]:
            if abbr in group:
                assert expansion in group, f"{abbr} must map to {expansion!r}"
                return
        pytest.fail(f"{abbr!r} not found in legislation category")

    def test_mgnrega_nrega_same_group(self, synonyms):
        for group in synonyms["legislation"]:
            if "MGNREGA" in group:
                assert "NREGA" in group, "MGNREGA and NREGA must be in the same group"
                return
        pytest.fail("MGNREGA not found in legislation")

    def test_rti_right_to_information_act(self, synonyms):  # gap 21
        for group in synonyms["legislation"]:
            if "RTI" in group:
                assert "Right to Information Act" in group, \
                    "RTI group must include Right to Information Act"
                return
        pytest.fail("RTI not found in legislation")

    def test_rte_right_to_education_act(self, synonyms):  # gap 22
        for group in synonyms["legislation"]:
            if "RTE" in group:
                assert "Right to Education Act" in group, \
                    "RTE group must include Right to Education Act"
                return
        pytest.fail("RTE not found in legislation")


# ── Bidirectionality (structural check) ──────────────────────────────────────

class TestBidirectionality:
    def test_all_groups_are_bidirectional_by_structure(self, synonyms):
        """
        The JSON uses synonym groups (arrays), not one-directional pairs.
        Every term in a group can expand to all others — bidirectionality is
        guaranteed by the group structure and enforced in setup_meilisearch.py.
        This test verifies each group has ≥2 terms so bidirectionality holds.
        """
        for cat, groups in synonyms.items():
            if not isinstance(groups, list):
                continue
            for i, group in enumerate(groups):
                if not isinstance(group, list):
                    continue
                assert len(group) >= 2, (
                    f"{cat}[{i}] has only 1 term — bidirectionality requires ≥2"
                )
