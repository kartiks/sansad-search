"""
Speaker attribution, time markers and heading subjects in flat LS/RS text.

The text snippets mirror layouts seen in real raw_documents: eLibrary (Tika) text
with a blank line after every line, IA djvu.txt with attributions wrapped over two
or three lines, and pre-1970 debates with title-case attributions.
"""
import pytest

from ingest.canonical.names import canonicalize_name, normalize_name_form, tidy_name
from ingest.segmenters.attribution import (
    assemble_wrapped_attributions,
    is_presiding_compact,
    match_title_case_attribution,
    parse_attribution,
)
from ingest.segmenters.speech import segment_speeches


def _rec(text, subject=None, time_of_day=None):
    return {
        "source": "LS",
        "proceeding_type": "debate",
        "date": "2019-07-02",
        "raw_text": text,
        "subject": subject,
        "time_of_day": time_of_day,
    }


def _names(records):
    return [r["speaker_name"] for r in records]


# ── parse_attribution ─────────────────────────────────────────────────────────

class TestParseAttribution:
    def test_minister_name_taken_from_parenthesis(self):
        a = parse_attribution("THE MINISTER OF STATE IN THE MINISTRY OF FINANCE (SHRI NAMO NARAIN MEENA)")
        assert a.name == "SHRI NAMO NARAIN MEENA"
        assert a.role == "minister"
        assert a.portfolio == "THE MINISTER OF STATE IN THE MINISTRY OF FINANCE"

    def test_member_constituency_captured(self):
        a = parse_attribution("SHRI B. MANICKAM TAGORE (VIRUDHUNAGAR)")
        assert a.name == "SHRI B. MANICKAM TAGORE"
        assert a.constituency == "VIRUDHUNAGAR"
        assert a.role == "member"

    def test_honorific_parenthesis_is_not_a_constituency(self):
        a = parse_attribution("SHRI X. Y. KUMAR (DR.)")
        assert a.constituency is None

    @pytest.mark.parametrize("head", [
        "STATUTORY RESOLUTION RE",
        "MOTION RE",
        "STATEMENT RE",
        "FRUIT(S)",
        "PAPERS LAID ON THE TABLE",
    ])
    def test_headings_are_not_speakers(self, head):
        assert parse_attribution(head) is None

    @pytest.mark.parametrize("head", [
        "HON. CHAIRPERSON",
        "MR. DEPUTY-SPEAKER",
        "DEPUTY SPEAKER",
        "SPEAKER",
        "SECRETARY-GENERAL",
        "HON. CHAIRPERSON (SHRI RAJENDRA AGRAWAL)",
    ])
    def test_presiding_officers(self, head):
        assert parse_attribution(head).role == "presiding_officer"

    def test_unrecovered_wrap_fragment_still_named(self):
        a = parse_attribution("PRALHAD JOSHI)")
        assert a.name == "PRALHAD JOSHI"


class TestPresidingCompact:
    @pytest.mark.parametrize("head", [
        "MR, SPEAKER", "MR.SPEAKER", "MR DEPUT Y-SPEAKER", "MR. SPBAKER",
        "MR. SPFAKER", "MR. CHATRMAN", "MR. CHAICMAN", "HON'BLE SPEAKER", "HON. CHAIRMEN",
        "MR. DEPATY-SPEAKER", "Mr. Depnty-Speaker", "MR. DFPUTY-SPEAKER", "MR. DEPIWTY-SPEAKER",
        "MR. DEPUITY-SPEAKER", "MRA. SPEAKER", "MR. DEPUTY-CHAIRMAN", "MR. DEPUTY-CHATRMAN",
    ])
    def test_ocr_variants_detected(self, head):
        assert is_presiding_compact(head)

    @pytest.mark.parametrize("head", [
        "MR. SHARMAN", "MR. MENON", "SHRI SPEAKMAN", "MR. DESHPANDE", "MR. DEVASAHAYAM",
        "MR. DESHMUKH", "MRA. RAO", "MR. DEPUTY MINISTER",
    ])
    def test_names_not_mistaken_for_presiding(self, head):
        assert not is_presiding_compact(head)


# ── wrapped attributions ──────────────────────────────────────────────────────

class TestWrappedAttributions:
    def test_elibrary_wrap_with_blank_lines(self):
        text = (
            "THE MINISTER OF STATE IN THE MINISTRY OF AGRICULTURE AND \n"
            "\n"
            "FARMERS WELFARE (SHRI PARSHOTTAM RUPALA) : Hon. Speaker, Sir, I rise to lay the papers.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert _names(recs) == ["SHRI PARSHOTTAM RUPALA"]
        assert recs[0]["speaker_role"] == "minister"

    def test_ia_wrap_inside_parenthesis(self):
        text = (
            "SHRI M. VENUGOPALA REDDY : Madam, my question is about schools.\n"
            "THE MINISTER OF STATE IN THE MINISTRY OF FINANCE (SHRI NAMO \n"
            "NARAIN MEENA): On behalf of Shri P. Chidambaram, I beg to lay on the Table.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert _names(recs) == ["SHRI M. VENUGOPALA REDDY", "SHRI NAMO NARAIN MEENA"]
        # the wrapped head line is not left in the previous speaker's body
        assert "MINISTER OF STATE" not in recs[0]["full_text_en"]

    def test_three_line_wrap(self):
        text = (
            "THE MINISTER OF STATE OF THE MINISTRY OF DEVELOPMENT OF \n"
            "NORTH EASTERN REGION AND MINISTER OF STATE IN THE MINISTRY \n"
            "OF PARLIAMENTARY AFFAIRS (SHRI PABAN SINGH GHATOWAR): I beg to move.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert _names(recs) == ["SHRI PABAN SINGH GHATOWAR"]

    def test_hyphenated_name_wrap(self):
        lines = assemble_wrapped_attributions([
            "SHRI A. B. A. GHANI KHAN CHAU-",
            "DHURI: I also know her concerns.",
        ])
        assert lines[0].startswith("SHRI A. B. A. GHANI KHAN CHAUDHURI:")
        assert lines[1] == ""

    def test_portfolio_words_never_become_speakers(self):
        text = (
            "THE MINISTER OF CONSUMER AFFAIRS, FOOD AND PUBLIC \n"
            "\n"
            "DISTRIBUTION (SHRI RAM VILAS PASWAN): I would like to tell you.\n"
        )
        names = _names(segment_speeches(_rec(text), "LS"))
        assert "DISTRIBUTION" not in names
        assert names == ["SHRI RAM VILAS PASWAN"]

    def test_minister_role_carried_to_later_name_only_attribution(self):
        text = (
            "THE MINISTER OF RAILWAYS (SHRI PIYUSH GOYAL): The project is sanctioned.\n"
            "\n"
            "SHRI ADHIR RANJAN CHOWDHURY: When will it be completed?\n"
            "\n"
            "SHRI PIYUSH GOYAL: By next year.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        roles = {r["speaker_name"]: r["speaker_role"] for r in recs}
        assert roles["SHRI PIYUSH GOYAL"] == "minister"
        assert roles["SHRI ADHIR RANJAN CHOWDHURY"] == "member"

    def test_presiding_variants_excluded_from_records(self):
        text = (
            "HON. CHAIRPERSON: Please conclude.\n\n"
            "MR. DEPUTY-SPEAKER: Order, order.\n\n"
            "SHRI SOUGATA RAY: Sir, I will conclude.\n"
        )
        assert _names(segment_speeches(_rec(text), "LS")) == ["SHRI SOUGATA RAY"]

    def test_constituency_stored_title_case(self):
        text = "SHRI NARANBHAI KACHHADIYA (AMRELI): At present the government has not acted.\n"
        recs = segment_speeches(_rec(text), "LS")
        assert recs[0]["speaker_constituency_or_state"] == "Amreli"


# ── title-case attributions (older debates) ───────────────────────────────────

class TestTitleCaseAttributions:
    def test_question_number_prefix(self):
        head, body = match_title_case_attribution("*184. Shri K. K. Das: Will the Minister be pleased")
        assert head == "SHRI K. K. DAS"
        assert body.startswith("Will the Minister")

    def test_honourable_prefix(self):
        head, _ = match_title_case_attribution("The Honourable Sardar Baldev Singh: (a) Yes.")
        assert head == "THE HONOURABLE SARDAR BALDEV SINGH"

    def test_wrapped_minister_paren(self):
        head, body = match_title_case_attribution("Home Affairs, (Shri Datar): Yes.")
        assert parse_attribution(head).name == "SHRI DATAR"
        assert parse_attribution(head).role == "minister"
        assert body == "Yes."

    @pytest.mark.parametrize("line", [
        "Shri Nehru said: we must act",          # body text that wrapped to a line start
        "The following member made the declaration under Rule 30:",
        "Price : Rs. 1.00",
    ])
    def test_body_lines_not_attributions(self, line):
        assert match_title_case_attribution(line) is None

    def test_old_debate_segments(self):
        text = (
            "*82. Sardar Hukam Singh: Will the Minister of Commerce be pleased to state the position?\n"
            "\n"
            "The Minister of Commerce and Industry (Shri T. T. Krishnamachari): The position is improving.\n"
            "\n"
            "Mr. Speaker: Next question.\n"
            "\n"
            "Shri K. K. Das: May I know the figures?\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert _names(recs) == ["SARDAR HUKAM SINGH", "SHRI T. T. KRISHNAMACHARI", "SHRI K. K. DAS"]
        assert recs[1]["speaker_role"] == "minister"


# ── time markers and heading subjects ─────────────────────────────────────────

class TestTimeAndSubject:
    def test_time_marker_sets_time_of_day(self):
        text = (
            "11.02 hrs \n"
            "SHRI A. B. KUMAR: First speech.\n"
            "\n"
            "12.00 hrs.\n"
            "SHRI C. D. RAO: Second speech.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert [r["time_of_day"] for r in recs] == ["11:02", "12:00"]

    def test_heading_becomes_subject_when_document_subject_generic(self):
        text = (
            "\n"
            "PAPERS LAID ON THE TABLE\n"
            "\n"
            "SHRI A. B. KUMAR: I beg to lay on the Table.\n"
        )
        recs = segment_speeches(_rec(text, subject="Lok Sabha Debates"), "LS")
        assert recs[0]["subject"] == "Papers Laid on the Table"

    def test_multi_line_heading_joined(self):
        text = (
            "\n"
            "STATEMENT RE: TAXATION AND OTHER\n"
            "\n"
            "LAWS (RELAXATION OF CERTAIN PROVISIONS) ORDINANCE\n"
            "\n"
            "SHRI A. B. KUMAR: I beg to lay a statement.\n"
        )
        recs = segment_speeches(_rec(text), "LS")
        assert recs[0]["subject"].startswith("Statement Re: Taxation and Other Laws")

    def test_specific_document_subject_kept(self):
        text = "\nPAPERS LAID ON THE TABLE\n\nSHRI A. B. KUMAR: Sir, about the Cauvery dispute.\n"
        recs = segment_speeches(_rec(text, subject="Cauvery Water Dispute"), "LS")
        assert recs[0]["subject"] == "Cauvery Water Dispute"

    @pytest.mark.parametrize("heading", [
        "OFFICIAL REPORT", "LOK SABHA DEBATES", "TWELFTH SESSION, 1956",
        "PHALGUNA 12, 1904 (SAKA)", "WRITTEN ANSWERS TO QUESTIONS",
    ])
    def test_boilerplate_headings_never_subjects(self, heading):
        text = f"\n{heading}\n\nSHRI A. B. KUMAR: Speech text here.\n"
        recs = segment_speeches(_rec(text), "LS")
        assert recs[0]["subject"] is None


# ── name canonical form ───────────────────────────────────────────────────────

class TestNameForm:
    @pytest.mark.parametrize("raw,expected", [
        ("SHRI ADHIR RANJAN CHOWDHURY", "Adhir Ranjan Chowdhury"),
        ("SHRI A, B, A. GHANI KHAN CHAUDHURI", "A. B. A. Ghani Khan Chaudhuri"),
        ("SHRI A.C.GEORGE", "A. C. George"),
        ("SHRIMATI NIRMALA SITHARAMAN", "Nirmala Sitharaman"),
        ("SUSHRI MAMATA BANERJEE", "Mamata Banerjee"),
        ("THE HONOURABLE SARDAR BALDEV SINGH", "Sardar Baldev Singh"),
        ("SHRI JOHN D'SOUZA", "John D'Souza"),
    ])
    def test_canonical_form(self, raw, expected):
        assert canonicalize_name(raw, {})[0] == expected

    def test_mixed_case_names_untouched(self):
        assert normalize_name_form("B. R. Ambedkar") == "B. R. Ambedkar"

    def test_tidy_name_empty(self):
        assert tidy_name("") is None
        assert tidy_name(None) is None
