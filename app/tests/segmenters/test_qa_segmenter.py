"""Tests for ingest.segmenters.qa"""
import pytest
from pathlib import Path

from ingest.segmenters.qa import segment_qa

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _raw_record(text: str, **kwargs) -> dict:
    base = {
        "source": "LS",
        "proceeding_type": "starred_question",
        "date": "2022-07-10",
        "session_name": "Monsoon Session 2022",
        "session_number": 258,
        "sitting_number": 3,
        "subject": "Test Question",
        "source_url": "http://example.com/q",
        "page_reference": None,
        "raw_text": text,
    }
    base.update(kwargs)
    return base


# ── Starred questions ─────────────────────────────────────────────────────────

class TestStarredQuestion:
    def test_starred_question_produces_record(self):
        text = (
            "STARRED QUESTION NO. 42\n\n"
            "Subject: Road Safety\n\n"
            "SHRI TEST QUESTIONER :\n"
            "What steps has the government taken for road safety?\n\n"
            "SHRI NITIN GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "The government has taken several steps.\n\n"
            "SHRI TEST QUESTIONER :\n"
            "Supplementary: What is the timeline?\n\n"
            "SHRI NITIN GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "The timeline is 2025.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert len(result) >= 1

    def test_question_number_extracted(self):
        text = (
            "STARRED QUESTION NO. 12\n\n"
            "SHRI A QUESTIONER :\nMain question text.\n\n"
            "SHRI B MINISTER OF FINANCE :\nMinister answer.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert result[0]["question_number"] == 12

    def test_proceeding_type_preserved(self):
        text = "STARRED QUESTION NO. 1\n\nSHRI A :\nQ\n\nSHRI B MINISTER :\nA\n"
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert result[0]["proceeding_type"] == "starred_question"

    def test_source_and_date_propagated(self):
        text = "STARRED QUESTION NO. 5\n\nSHRI A :\nQ\n\nSHRI B MINISTER :\nA\n"
        record = _raw_record(text)
        result = segment_qa(record, "RS", "starred_question")
        assert result[0]["source"] == "RS"
        assert result[0]["date"] == "2022-07-10"

    def test_full_text_not_none_for_english_exchange(self):
        text = (
            "STARRED QUESTION NO. 7\n\n"
            "SHRI PRIYANKA CHATURVEDI :\n"
            "What is the status of infrastructure development?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "Roads have been built across north-east India.\n\n"
            "SHRI PRIYANKA CHATURVEDI :\n"
            "Supplementary question: what is the completion date?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "All projects complete by 2025.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "RS", "starred_question")
        assert result[0]["full_text_en"] is not None

    def test_multiple_questions_in_document(self):
        text = (
            "STARRED QUESTION NO. 1\n\n"
            "SHRI A :\nFirst question.\n\n"
            "SHRI B MINISTER :\nFirst answer.\n\n"
            "STARRED QUESTION NO. 2\n\n"
            "SHRI C :\nSecond question.\n\n"
            "SHRI D MINISTER :\nSecond answer.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert len(result) == 2
        q_nums = {r["question_number"] for r in result}
        assert q_nums == {1, 2}

    def test_questioner_names_is_list(self):
        text = (
            "STARRED QUESTION NO. 3\n\n"
            "SHRI PRIYANKA CHATURVEDI :\nQuestion text.\n\n"
            "SHRI MINISTER OF FINANCE :\nAnswer.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "RS", "starred_question")
        assert isinstance(result[0]["questioner_names"], list)
        assert len(result[0]["questioner_names"]) >= 1

    def test_all_supplementaries_captured(self):
        """full_text_en must include content from all supplementary rounds, not just the first."""
        text = (
            "STARRED QUESTION NO. 15\n\n"
            "SHRI FIRST QUESTIONER :\n"
            "Main question: what is the road safety policy?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "The government has a comprehensive road safety policy.\n\n"
            "SHRI FIRST QUESTIONER :\n"
            "Supplementary one: what about rural roads?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "Rural roads are covered under PMGSY scheme.\n\n"
            "SHRI SECOND QUESTIONER :\n"
            "Supplementary two: what about highway fatalities?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "Fatality rate has dropped by 15 percent.\n\n"
            "SHRI THIRD QUESTIONER :\n"
            "Supplementary three: what is the budget allocation?\n\n"
            "SHRI GADKARI MINISTER OF ROAD TRANSPORT AND HIGHWAYS :\n"
            "Budget allocation is two lakh crore rupees.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert len(result) >= 1
        full_text = result[0]["full_text_en"] or ""
        # All three supplementary rounds must be represented
        assert "rural roads" in full_text.lower() or "PMGSY" in full_text
        assert "fatalities" in full_text.lower() or "fatality" in full_text.lower()
        assert "budget allocation" in full_text.lower() or "two lakh crore" in full_text.lower()

    def test_from_fixture_starred_rs(self):
        from ingest.parsers.html_parser import parse_html
        html = (FIXTURES / "starred_question_rs.html").read_text()
        raw = parse_html(html, "RS", proceeding_type_hint="starred_question")
        result = segment_qa(raw, "RS", "starred_question")
        assert len(result) >= 1
        assert result[0]["question_number"] == 12
        assert result[0]["source"] == "RS"


# ── Unstarred questions ───────────────────────────────────────────────────────

class TestUnstarredQuestion:
    def test_unstarred_produces_record(self):
        text = (
            "UNSTARRED QUESTION NO. 458\n\n"
            "SHRI ADHIR RANJAN CHOWDHURY :\n"
            "What is the status of MGNREGA implementation?\n\n"
            "SHRI GIRIRAJ SINGH MINISTER OF RURAL DEVELOPMENT :\n"
            "WRITTEN ANSWER\n"
            "The programme has provided employment to millions.\n"
        )
        record = _raw_record(text, proceeding_type="unstarred_question")
        result = segment_qa(record, "LS", "unstarred_question")
        assert len(result) >= 1

    def test_unstarred_proceeding_type(self):
        text = (
            "UNSTARRED QUESTION NO. 10\n\n"
            "SHRI A :\nQuestion.\n\n"
            "SHRI B MINISTER :\nWRITTEN ANSWER\nAnswer text.\n"
        )
        record = _raw_record(text, proceeding_type="unstarred_question")
        result = segment_qa(record, "LS", "unstarred_question")
        assert result[0]["proceeding_type"] == "unstarred_question"

    def test_unstarred_question_number(self):
        text = (
            "UNSTARRED QUESTION NO. 458\n\n"
            "SHRI A :\nQ.\n\n"
            "SHRI B MINISTER :\nWRITTEN ANSWER\nA.\n"
        )
        record = _raw_record(text, proceeding_type="unstarred_question")
        result = segment_qa(record, "LS", "unstarred_question")
        assert result[0]["question_number"] == 458

    def test_unstarred_questioner_names_has_exactly_one_element(self):
        """Unstarred questions have exactly one questioner (no co-signatories)."""
        text = (
            "UNSTARRED QUESTION NO. 99\n\n"
            "SHRI ADHIR RANJAN CHOWDHURY :\n"
            "What is the employment rate in rural areas?\n\n"
            "SHRI GIRIRAJ SINGH MINISTER OF RURAL DEVELOPMENT :\n"
            "WRITTEN ANSWER\n"
            "Employment is at an all-time high in rural India.\n"
        )
        record = _raw_record(text, proceeding_type="unstarred_question")
        result = segment_qa(record, "LS", "unstarred_question")
        assert len(result) >= 1
        questioner_names = result[0]["questioner_names"]
        assert isinstance(questioner_names, list), "questioner_names must be a list"
        assert len(questioner_names) == 1, \
            f"Unstarred question must have exactly 1 questioner, got {len(questioner_names)}"
        assert questioner_names[0] != "Unknown", \
            "questioner name must be the actual questioner, not 'Unknown'"

    def test_from_fixture_unstarred_ls(self):
        from ingest.parsers.html_parser import parse_html
        html = (FIXTURES / "unstarred_question_ls.html").read_text()
        raw = parse_html(html, "LS", proceeding_type_hint="unstarred_question")
        result = segment_qa(raw, "LS", "unstarred_question")
        assert len(result) >= 1
        assert result[0]["question_number"] == 458


# ── Validation ────────────────────────────────────────────────────────────────

class TestQaValidation:
    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Q\\+A exchanges only exist"):
            segment_qa(_raw_record(""), "CA", "starred_question")

    def test_invalid_proceeding_type_raises(self):
        with pytest.raises(ValueError, match="Invalid proceeding_type"):
            segment_qa(_raw_record(""), "LS", "debate")

    def test_empty_text_returns_list(self):
        result = segment_qa(_raw_record(""), "LS", "starred_question")
        assert isinstance(result, list)


# ── Language handling in Q+A ──────────────────────────────────────────────────

class TestQaLanguageHandling:
    def test_english_exchange_not_translated(self):
        text = (
            "STARRED QUESTION NO. 1\n\n"
            "SHRI A :\nWhat is the policy on education?\n\n"
            "SHRI B MINISTER OF EDUCATION :\nThe policy covers all students.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert result[0]["is_translated"] is False

    def test_hindi_only_exchange_no_translation(self):
        text = (
            "STARRED QUESTION NO. 2\n\n"
            "SHRI A :\nयह हिंदी में प्रश्न है।\n\n"
            "SHRI B MINISTER :\nयह हिंदी में उत्तर है।\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert result[0]["full_text_en"] is None
        assert result[0]["has_untranslated_content"] is True

    def test_case2_hindi_with_translation(self):
        """Q+A Case 2: Hindi exchange with [Translation] marker → is_translated=True, no Devanagari in full_text_en."""
        text = (
            "STARRED QUESTION NO. 3\n\n"
            "SHRI A :\nसरकार की नीति क्या है?\n\n"
            "[Translation]\n"
            "What is the government policy?\n\n"
            "SHRI B MINISTER OF FINANCE :\nवित्त मंत्री का उत्तर।\n\n"
            "[Translation]\n"
            "The Finance Minister's answer on the matter.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert len(result) >= 1
        r = result[0]
        assert r["is_translated"] is True
        assert r["full_text_en"] is not None
        assert not any("ऀ" <= ch <= "ॿ" for ch in r["full_text_en"]), \
            "full_text_en must not contain Devanagari characters"
        assert "government policy" in r["full_text_en"].lower() or \
               "Finance Minister" in r["full_text_en"]

    def test_case3_bilingual_exchange(self):
        """Q+A Case 3: bilingual exchange → is_translated=True, full_text_en contains both English and translated portions."""
        text = (
            "STARRED QUESTION NO. 4\n\n"
            "SHRI A :\n"
            "The question is about rural employment in English.\n"
            "यह हिंदी भाग है।\n"
            "[Translation]\n"
            "This is the translated Hindi portion of the question.\n\n"
            "SHRI B MINISTER OF RURAL DEVELOPMENT :\n"
            "The minister's answer in English covers the rural scheme.\n"
        )
        record = _raw_record(text)
        result = segment_qa(record, "LS", "starred_question")
        assert len(result) >= 1
        r = result[0]
        assert r["is_translated"] is True
        assert r["full_text_en"] is not None
        assert "rural employment in English" in r["full_text_en"], \
            "full_text_en must contain the original English portion"
        assert "translated Hindi portion" in r["full_text_en"], \
            "full_text_en must contain the translated Hindi portion"
