"""Tests for ingest.segmenters.speech"""
import pytest
from pathlib import Path

from ingest.segmenters.speech import (
    segment_speeches,
    _is_unattributed,
    _is_presiding_officer,
    _detect_language_handling,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _raw_record(text: str, **kwargs) -> dict:
    base = {
        "source": "LS",
        "proceeding_type": "debate",
        "date": "2023-03-15",
        "session_name": "Budget Session 2023",
        "session_number": 261,
        "sitting_number": 5,
        "subject": "General Discussion",
        "source_url": "http://example.com",
        "page_reference": None,
        "volume": None,
        "ocr_low_confidence": False,
        "raw_text": text,
    }
    base.update(kwargs)
    return base


# ── _is_unattributed ──────────────────────────────────────────────────────────

class TestIsUnattributed:
    @pytest.mark.parametrize("s", [
        "SEVERAL HON. MEMBERS",
        "AN HON. MEMBER",
        "SOME HON. MEMBERS",
        "HON. MEMBERS",
        "MEMBERS",
    ])
    def test_known_unattributed_strings(self, s):
        assert _is_unattributed(s) is True

    def test_named_speaker_not_unattributed(self):
        assert _is_unattributed("SHRI NARENDRA MODI") is False

    def test_zero_hour_not_unattributed(self):
        # "ZERO HOUR" must not be treated as unattributed (per test spec)
        assert _is_unattributed("ZERO HOUR") is False


# ── _is_presiding_officer ─────────────────────────────────────────────────────

class TestIsPresidingOfficer:
    @pytest.mark.parametrize("s", [
        "MR. SPEAKER",
        "THE SPEAKER",
        "MADAM SPEAKER",
        "THE DEPUTY SPEAKER",
        "MR. CHAIRMAN",
        "THE CHAIRMAN",
        "THE DEPUTY CHAIRMAN",
        "THE PRESIDENT",
        "MR. PRESIDENT",
    ])
    def test_presiding_officer_strings(self, s):
        assert _is_presiding_officer(s) is True

    def test_named_member_not_presiding(self):
        assert _is_presiding_officer("SHRI AMIT SHAH") is False


# ── _detect_language_handling ─────────────────────────────────────────────────

class TestLanguageHandling:
    def test_case1_english_verbatim(self):
        text = "The government has taken several steps to address the situation."
        full_text, is_translated, has_untranslated = _detect_language_handling(text)
        assert full_text == text
        assert is_translated is False
        assert has_untranslated is False

    def test_case2_hindi_with_translation(self):
        text = "यह एक हिंदी भाषण है।\n[Translation]\nThis is an English translation of the Hindi speech."
        full_text, is_translated, has_untranslated = _detect_language_handling(text)
        assert is_translated is True
        assert has_untranslated is False
        assert full_text is not None
        # Must contain translation text, not Devanagari
        assert "English translation of the Hindi speech" in full_text
        assert not any("ऀ" <= ch <= "ॿ" for ch in full_text), \
            "full_text_en must not contain Devanagari characters"

    def test_case3_bilingual_concatenated(self):
        text = "The first part is in English.\nयह हिंदी में है।\n[Translation]\nThis is the translated portion."
        full_text, is_translated, has_untranslated = _detect_language_handling(text)
        assert is_translated is True
        assert has_untranslated is False
        assert full_text is not None
        # Must contain both the original English portion and the translated Hindi portion
        assert "The first part is in English" in full_text
        assert "translated portion" in full_text

    def test_case4_hindi_no_translation(self):
        text = "यह पूरी तरह से हिंदी में है और कोई अनुवाद उपलब्ध नहीं है।"
        full_text, is_translated, has_untranslated = _detect_language_handling(text)
        assert full_text is None
        assert is_translated is False
        assert has_untranslated is True

    def test_full_text_en_null_not_empty_string_for_hindi_only(self):
        text = "केवल हिंदी पाठ। कोई अनुवाद नहीं।"
        full_text, _, _ = _detect_language_handling(text)
        assert full_text is None  # must be None, not ""

    def test_is_translated_true_when_translation_marker_present(self):
        text = "[Translation]\nSome English translation text here."
        _, is_translated, _ = _detect_language_handling(text)
        assert is_translated is True


# ── segment_speeches ──────────────────────────────────────────────────────────

class TestSegmentSpeeches:
    def test_basic_debate_produces_speeches(self):
        text = (
            "SHRI NARENDRA MODI :\n"
            "The government has taken major steps.\n\n"
            "SHRI RAHUL GANDHI :\n"
            "I disagree with the honourable prime minister.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert len(result) == 2

    def test_unattributed_excluded(self):
        text = (
            "SHRI NARENDRA MODI :\n"
            "Opening speech.\n\n"
            "SEVERAL HON. MEMBERS :\n"
            "Hear, hear!\n\n"
            "DR. MANMOHAN SINGH :\n"
            "Thank you, Mr. Speaker.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        speakers = [s["speaker_name"] for s in result]
        assert all("HON. MEMBERS" not in sp for sp in speakers)
        assert len(result) == 2

    def test_presiding_officer_excluded(self):
        text = (
            "SHRI NARENDRA MODI :\n"
            "My speech.\n\n"
            "MR. SPEAKER :\n"
            "Order, order.\n\n"
            "SHRI RAHUL GANDHI :\n"
            "Another speech.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        speakers = [s["speaker_name"] for s in result]
        assert all("SPEAKER" not in sp for sp in speakers)
        assert len(result) == 2

    def test_speaker_name_stored_raw(self):
        text = "SHRI NARENDRA MODI :\nSome speech.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["speaker_name"] == "SHRI NARENDRA MODI"

    def test_sequence_within_sitting_1_based(self):
        text = (
            "SHRI A :\nFirst.\n\n"
            "SHRI B :\nSecond.\n\n"
            "SHRI C :\nThird.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert [s["sequence_within_sitting"] for s in result] == [1, 2, 3]

    def test_same_member_twice_produces_two_records(self):
        text = (
            "SHRI NARENDRA MODI :\nFirst speech.\n\n"
            "SHRI RAHUL GANDHI :\nOpposition reply.\n\n"
            "SHRI NARENDRA MODI :\nRejoinder.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert len(result) == 3
        assert result[0]["speaker_name"] == "SHRI NARENDRA MODI"
        assert result[2]["speaker_name"] == "SHRI NARENDRA MODI"
        assert result[0]["sequence_within_sitting"] != result[2]["sequence_within_sitting"]

    def test_metadata_propagated_to_speeches(self):
        text = "SHRI NARENDRA MODI :\nSpeech text.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        s = result[0]
        assert s["source"] == "LS"
        assert s["date"] == "2023-03-15"
        assert s["session_name"] == "Budget Session 2023"
        assert s["proceeding_type"] == "debate"
        assert s["subject"] == "General Discussion"

    def test_ca_source_preserved(self):
        text = "DR. B. R. AMBEDKAR :\nI move the Constitution.\n"
        record = _raw_record(text, source="CA", volume=1, session_name=None)
        result = segment_speeches(record, "CA")
        assert result[0]["source"] == "CA"

    def test_language_case1_english_in_full_record(self):
        text = "SHRI TEST MEMBER :\nThis speech is entirely in English language.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["is_translated"] is False
        assert result[0]["has_untranslated_content"] is False
        assert result[0]["full_text_en"] is not None

    def test_language_case4_hindi_only(self):
        text = "SHRI TEST MEMBER :\nयह भाषण पूरी तरह हिंदी में है।\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["full_text_en"] is None
        assert result[0]["has_untranslated_content"] is True
        assert result[0]["is_translated"] is False

    def test_language_case2_translated(self):
        text = (
            "SHRI TEST MEMBER :\n"
            "हिंदी पाठ।\n"
            "[Translation]\n"
            "English translation of the Hindi speech text.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["is_translated"] is True
        assert result[0]["full_text_en"] is not None

    def test_speaker_name_unresolved_initially_true(self):
        # All speakers start unresolved; canonicalization happens in Phase 2
        text = "SHRI NARENDRA MODI :\nSpeech.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["speaker_name_unresolved"] is True

    def test_ocr_low_confidence_propagated(self):
        text = "SHRI OCR MEMBER :\nOCR extracted text.\n"
        record = _raw_record(text, ocr_low_confidence=True)
        result = segment_speeches(record, "LS")
        assert result[0]["ocr_low_confidence"] is True

    def test_speaker_role_member_for_regular_member(self):
        text = "SHRI NARENDRA MODI :\nSpeech by a regular member.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["speaker_role"] == "member"

    def test_speaker_role_field_present_in_output(self):
        text = "DR. MANMOHAN SINGH :\nAnother speech.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert "speaker_role" in result[0]
        assert result[0]["speaker_role"] is not None

    def test_empty_text_returns_empty_list(self):
        record = _raw_record("")
        result = segment_speeches(record, "LS")
        assert result == []

    def test_only_unattributed_returns_empty_list(self):
        text = "SEVERAL HON. MEMBERS :\nHear, hear!\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result == []

    def test_from_fixture_debate_ls(self):
        from ingest.parsers.html_parser import parse_html
        html = (FIXTURES / "debate_ls.html").read_text()
        raw = parse_html(html, "LS", source_url="http://example.com")
        speeches = segment_speeches(raw, "LS")
        speakers = [s["speaker_name"] for s in speeches]
        # Named speakers present
        assert any("MODI" in sp for sp in speakers)
        assert any("GANDHI" in sp for sp in speakers)
        assert any("MANMOHAN" in sp for sp in speakers)
        assert any("AMIT SHAH" in sp for sp in speakers)
        # Unattributed excluded
        assert all("HON. MEMBERS" not in sp for sp in speakers)
        # Presiding officer excluded
        assert all("SPEAKER" not in sp for sp in speakers)
