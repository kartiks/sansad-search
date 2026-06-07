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

    def test_sequence_not_assigned_by_segmenter(self):
        """sequence_within_sitting is assigned at orchestrator level, not by segmenter."""
        text = (
            "SHRI A :\nFirst.\n\n"
            "SHRI B :\nSecond.\n\n"
            "SHRI C :\nThird.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert len(result) == 3
        # Segmenter must not assign sequence — orchestrator is responsible
        for s in result:
            assert "sequence_within_sitting" not in s, (
                "sequence_within_sitting must be assigned by the orchestrator, not the segmenter"
            )

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

    def test_proceeding_type_none_falls_back_to_debate(self):
        # ia_text_parser sets proceeding_type=None when no type is derivable;
        # dict.get(key, default) does not fire for None values, so the fallback
        # must use `or "debate"` to avoid propagating None to the NOT NULL column.
        text = "SHRI NARENDRA MODI :\nSpeech text.\n"
        record = _raw_record(text, proceeding_type=None)
        result = segment_speeches(record, "LS")
        assert result[0]["proceeding_type"] == "debate"

    def test_proceeding_type_none_falls_back_to_debate_ca_path(self):
        # Same None guard applies in _segment_ca_speeches (used by CA orchestrator).
        record = _raw_record(
            "",
            source="CA",
            proceeding_type=None,
            ca_speech_pairs=[("DR. B. R. AMBEDKAR", "I move the Constitution.", "Constituent Assembly")],
        )
        result = segment_speeches(record, "CA")
        assert result[0]["proceeding_type"] == "debate"

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


# ── Phase 10: lang_original, word_count, time_of_day ─────────────────────────

class TestLangOriginal:
    def test_case1_english_produces_en(self):
        text = "SHRI TEST :\nThe government has addressed the situation properly.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["lang_original"] == "en"

    def test_case4_hindi_only_produces_hi(self):
        text = "SHRI TEST :\nयह भाषण पूरी तरह हिंदी में है।\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["lang_original"] == "hi"

    def test_case2_translated_hindi_produces_hi(self):
        """Hindi speech with [Translation] marker — no English before the Hindi."""
        text = (
            "SHRI TEST :\n"
            "यह हिंदी में है।\n"
            "[Translation]\n"
            "This is the English translation of the Hindi text.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["lang_original"] == "hi"

    def test_case3_bilingual_produces_mixed(self):
        """Significant English before first Hindi → genuinely bilingual (mixed)."""
        english_before = "The first part of this speech is delivered in English and is quite long. " * 3
        text = (
            "SHRI TEST :\n"
            f"{english_before}\n"
            "अब हम हिंदी में आते हैं।\n"
            "[Translation]\n"
            "Now we move to Hindi.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["lang_original"] == "mixed"

    def test_lang_original_present_in_all_records(self):
        text = "SHRI A :\nFirst speech.\n\nSHRI B :\nSecond speech.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        for s in result:
            assert "lang_original" in s
            assert s["lang_original"] in ("en", "hi", "mixed")


class TestWordCount:
    def test_word_count_computed_for_english_speech(self):
        text = "SHRI TEST :\nThis speech has six words here.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["word_count"] == 6

    def test_word_count_null_when_full_text_en_null(self):
        """Case 4: Hindi only — full_text_en is None → word_count must be None."""
        text = "SHRI TEST :\nयह हिंदी में है और कोई अनुवाद नहीं।\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["full_text_en"] is None
        assert result[0]["word_count"] is None

    def test_word_count_present_for_translated_speech(self):
        text = (
            "SHRI TEST :\n"
            "हिंदी।\n"
            "[Translation]\n"
            "Translation with three words here plus more.\n"
        )
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["word_count"] is not None
        assert isinstance(result[0]["word_count"], int)
        assert result[0]["word_count"] > 0


class TestTimeOfDay:
    def test_time_of_day_passed_through_from_raw_record(self):
        text = "SHRI TEST :\nA speech.\n"
        record = _raw_record(text)
        record["time_of_day"] = "11:30"
        result = segment_speeches(record, "LS")
        assert result[0]["time_of_day"] == "11:30"

    def test_time_of_day_none_when_not_in_raw_record(self):
        text = "SHRI TEST :\nA speech.\n"
        record = _raw_record(text)
        result = segment_speeches(record, "LS")
        assert result[0]["time_of_day"] is None

    def test_time_of_day_present_in_all_records(self):
        text = "SHRI A :\nFirst.\n\nSHRI B :\nSecond.\n"
        record = _raw_record(text)
        record["time_of_day"] = "14:00"
        result = segment_speeches(record, "LS")
        for s in result:
            assert "time_of_day" in s
            assert s["time_of_day"] == "14:00"


class TestCASubjectPerSpeech:
    """CA speech pairs now carry per-speech subjects from the section-header walk."""

    def test_ca_speeches_use_subject_from_pair_triples(self):
        """CA segmenter reads subject from the third element of ca_speech_pairs."""
        raw = {
            "source": "CA",
            "proceeding_type": "debate",
            "date": "1946-12-09",
            "session_name": None,
            "session_number": None,
            "sitting_number": None,
            "source_url": None,
            "page_reference": None,
            "volume": 1,
            "time_of_day": None,
            "raw_text": "",
            "ca_speech_pairs": [
                ("Shri Jawaharlal Nehru", "I move the Objectives Resolution.", "Objectives Resolution"),
                ("Dr. B.R. Ambedkar", "I support the resolution.", "Objectives Resolution"),
                ("Shri T.T. Krishnamachari", "I also support.", "The Question of Procedure"),
            ],
        }
        result = segment_speeches(raw, "CA")
        assert len(result) == 3
        assert result[0]["subject"] == "Objectives Resolution"
        assert result[1]["subject"] == "Objectives Resolution"
        assert result[2]["subject"] == "The Question of Procedure"

    def test_ca_speech_subject_can_be_none(self):
        """When no section header or TOC fallback exists, subject is None."""
        raw = {
            "source": "CA",
            "proceeding_type": "debate",
            "date": "1946-12-09",
            "session_name": None,
            "session_number": None,
            "sitting_number": None,
            "source_url": None,
            "page_reference": None,
            "volume": 1,
            "time_of_day": None,
            "raw_text": "",
            "ca_speech_pairs": [
                ("Shri Test Speaker", "Some speech text.", None),
            ],
        }
        result = segment_speeches(raw, "CA")
        assert len(result) == 1
        assert result[0]["subject"] is None


# ── Phase 13: Adjacent Speech Merging (F01, PRD v3.0) ─────────────────────────

class TestAdjacentSpeechMerging:
    def test_two_consecutive_same_speaker_merge_into_one_record(self):
        text = (
            "SHRI NARENDRA MODI :\nFirst part of the speech.\n\n"
            "SHRI NARENDRA MODI :\nSecond part of the speech.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 1
        rec = result[0]
        assert [s["segment_index"] for s in rec["segments"]] == [0, 1]
        assert rec["segments"][0]["text"] == "First part of the speech."
        assert rec["segments"][1]["text"] == "Second part of the speech."
        assert rec["full_text_en"] == (
            "First part of the speech.\n\nSecond part of the speech."
        )

    def test_three_consecutive_same_speaker_produce_three_element_segments(self):
        text = (
            "SHRI A SPEAKER :\nOne.\n\n"
            "SHRI A SPEAKER :\nTwo.\n\n"
            "SHRI A SPEAKER :\nThree.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 1
        assert [s["segment_index"] for s in result[0]["segments"]] == [0, 1, 2]
        assert result[0]["full_text_en"] == "One.\n\nTwo.\n\nThree."

    def test_word_count_is_combined_total_for_merged_record(self):
        text = (
            "SHRI A SPEAKER :\nTwo words.\n\n"
            "SHRI A SPEAKER :\nThree more words.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        # "Two words." (2) + "Three more words." (3) = 5
        assert result[0]["word_count"] == 5

    def test_intervening_different_speaker_breaks_merge(self):
        text = (
            "SHRI NARENDRA MODI :\nFirst.\n\n"
            "SHRI RAHUL GANDHI :\nReply.\n\n"
            "SHRI NARENDRA MODI :\nRejoinder.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 3
        for rec in result:
            assert len(rec["segments"]) == 1

    def test_section_heading_between_same_speaker_breaks_merge(self):
        text = (
            "SHRI NARENDRA MODI :\nRemarks on the first topic.\n\n"
            "NEW ARTICLE 67-A\n\n"
            "SHRI NARENDRA MODI :\nRemarks on the second topic.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 2
        assert all(len(r["segments"]) == 1 for r in result)

    def test_procedural_block_header_between_same_speaker_breaks_merge(self):
        text = (
            "SHRI NARENDRA MODI :\nDebate remarks.\n\n"
            "STARRED QUESTION NO. 42\n\n"
            "SHRI NARENDRA MODI :\nFurther remarks.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 2

    def test_unmerged_speech_has_single_element_segments(self):
        text = "SHRI SOLO SPEAKER :\nA standalone speech.\n"
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 1
        assert len(result[0]["segments"]) == 1
        assert result[0]["segments"][0]["segment_index"] == 0
        assert result[0]["segments"][0]["text"] == "A standalone speech."

    def test_segments_ordered_by_document_position(self):
        text = (
            "SHRI A SPEAKER :\nEarliest.\n\n"
            "SHRI A SPEAKER :\nMiddle.\n\n"
            "SHRI A SPEAKER :\nLatest.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        segs = result[0]["segments"]
        assert segs[0]["text"] == "Earliest."
        assert segs[-1]["text"] == "Latest."
        assert [s["segment_index"] for s in segs] == sorted(s["segment_index"] for s in segs)

    def test_merged_record_takes_first_segment_sequence_position(self):
        """The merged record occupies the first segment's document-order slot.

        The orchestrator assigns sequence_within_sitting by walking the
        segmenter output in order; the merged record (two MODI speeches) must
        land at position 1, before the following GANDHI speech at position 2.
        """
        text = (
            "SHRI NARENDRA MODI :\nFirst.\n\n"
            "SHRI NARENDRA MODI :\nSecond.\n\n"
            "SHRI RAHUL GANDHI :\nReply.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        # Mimic the orchestrator's 1-based sequence assignment.
        for i, rec in enumerate(result, start=1):
            rec["sequence_within_sitting"] = i
        merged = next(r for r in result if len(r["segments"]) == 2)
        gandhi = next(r for r in result if r["speaker_name"] == "SHRI RAHUL GANDHI")
        assert merged["sequence_within_sitting"] == 1
        assert gandhi["sequence_within_sitting"] == 2

    def test_merged_segments_mixed_english_and_untranslated_hindi(self):
        """Edge case: first segment English, second Hindi with no translation.

        full_text_en must include the English segment (not be nulled) and
        has_untranslated_content must be true.
        """
        text = (
            "SHRI A SPEAKER :\nThe policy has been implemented nationwide.\n\n"
            "SHRI A SPEAKER :\nयह हिस्सा बिना अनुवाद के है।\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        assert len(result) == 1
        rec = result[0]
        assert rec["full_text_en"] is not None
        assert "policy has been implemented" in rec["full_text_en"]
        assert rec["has_untranslated_content"] is True
        # The untranslated segment is preserved as a null-text element.
        assert len(rec["segments"]) == 2
        assert rec["segments"][1]["text"] is None

    def test_presiding_officer_interjection_breaks_merge(self):
        text = (
            "SHRI NARENDRA MODI :\nFirst point.\n\n"
            "MR. SPEAKER :\nOrder, order.\n\n"
            "SHRI NARENDRA MODI :\nSecond point.\n"
        )
        result = segment_speeches(_raw_record(text), "LS")
        # Presiding officer excluded as a record, but acts as a break signal.
        assert len(result) == 2
        assert all(s["speaker_name"] == "SHRI NARENDRA MODI" for s in result)


class TestCAAdjacentMerging:
    def _ca_raw(self, ca_pairs):
        return {
            "source": "CA",
            "proceeding_type": "debate",
            "date": "1946-12-09",
            "sitting_number": None,
            "source_url": None,
            "page_reference": None,
            "volume": 1,
            "time_of_day": None,
            "raw_text": "",
            "ca_speech_pairs": ca_pairs,
        }

    def test_same_speaker_same_subject_merges(self):
        raw = self._ca_raw([
            ("Shri Jawaharlal Nehru", "First remark.", "Objectives Resolution"),
            ("Shri Jawaharlal Nehru", "Second remark.", "Objectives Resolution"),
        ])
        result = segment_speeches(raw, "CA")
        assert len(result) == 1
        assert len(result[0]["segments"]) == 2
        assert result[0]["full_text_en"] == "First remark.\n\nSecond remark."

    def test_subject_change_breaks_merge(self):
        """A new bold section header (subject change) is a section-heading break."""
        raw = self._ca_raw([
            ("Shri Jawaharlal Nehru", "On the resolution.", "Objectives Resolution"),
            ("Shri Jawaharlal Nehru", "On procedure.", "Question of Procedure"),
        ])
        result = segment_speeches(raw, "CA")
        assert len(result) == 2
        assert all(len(r["segments"]) == 1 for r in result)
        assert result[0]["subject"] == "Objectives Resolution"
        assert result[1]["subject"] == "Question of Procedure"

    def test_ca_lok_sabha_number_always_null(self):
        raw = self._ca_raw([
            ("Shri Test Speaker", "A speech.", "Topic"),
        ])
        result = segment_speeches(raw, "CA")
        assert result[0]["lok_sabha_number"] is None


class TestLokSabhaNumberPassthrough:
    def test_lok_sabha_number_passed_through_for_ls(self):
        text = "SHRI TEST :\nA speech in the seventeenth Lok Sabha.\n"
        record = _raw_record(text, lok_sabha_number=17)
        result = segment_speeches(record, "LS")
        assert result[0]["lok_sabha_number"] == 17

    def test_lok_sabha_number_null_when_absent(self):
        text = "SHRI TEST :\nA speech.\n"
        result = segment_speeches(_raw_record(text), "LS")
        assert result[0]["lok_sabha_number"] is None
