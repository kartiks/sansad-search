"""
Tests for the F10 debug endpoints (PRD v3.0):
- GET /api/debug/processed/{id}  — full speeches/qa_exchanges row
- GET /api/debug/raw/{id}        — full raw_documents row resolved via canonical_doc_id

All tests use dependency overrides; no real DB connections required.
"""
from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


# ── Row helpers ───────────────────────────────────────────────────────────────

def _speech_row(**overrides):
    base = {
        "id": "3f2a1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "lok_sabha_number": 17,
        "proceeding_type": "debate",
        "date": datetime.date(2023, 3, 15),
        "session_name": "Budget Session 2023",
        "session_number": 7,
        "sitting_number": 42,
        "subject": "General Discussion",
        "full_text_en": "Mr. Speaker, I rise to speak.",
        "lang_original": "en",
        "time_of_day": "14:35",
        "word_count": 1820,
        "is_translated": False,
        "has_untranslated_content": False,
        "page_reference": None,
        "source_url": "https://archive.org/details/eparlib.nic.in.123456",
        "sequence_within_sitting": 7,
        "volume": None,
        "speaker_name": "Jairam Ramesh",
        "speaker_role": "member",
        "speaker_party": "INC",
        "speaker_constituency_or_state": "Karnataka",
        "speaker_name_unresolved": False,
        "dedup_key": "LS|2023-03-15|7|7",
        "segments": [{"text": "Mr. Speaker", "segment_index": 0}],
        "canonical_doc_id": "123456",
        "created_at": datetime.datetime(2026, 5, 10, 9, 12, 0),
        "record_type": "speech",
        "question_number": None,
        "questioner_names": None,
        "questioner_party": None,
        "minister_name": None,
        "ministry": None,
    }
    base.update(overrides)
    return base


def _qa_row(**overrides):
    base = {
        "id": "qa2b1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "lok_sabha_number": 17,
        "proceeding_type": "starred_question",
        "date": datetime.date(2023, 8, 4),
        "session_name": "Monsoon Session 2023",
        "session_number": 8,
        "sitting_number": 12,
        "subject": "Implementation of NHM",
        "full_text_en": "Q: What is the status of NHM?",
        "lang_original": "en",
        "time_of_day": None,
        "word_count": 540,
        "is_translated": False,
        "has_untranslated_content": False,
        "page_reference": None,
        "source_url": "https://sansad.in/qa",
        "sequence_within_sitting": 3,
        "speaker_name": None,
        "speaker_role": None,
        "speaker_party": None,
        "speaker_constituency_or_state": None,
        "speaker_name_unresolved": False,
        "question_number": 42,
        "questioner_names": ["Shri A. Kumar"],
        "questioner_party": "BJP",
        "minister_name": "Dr. Mandaviya",
        "ministry": "Ministry of Health",
        "dedup_key": "LS|2023-08-04|42",
        "segments": None,
        "canonical_doc_id": "654321",
        "created_at": datetime.datetime(2026, 5, 11, 10, 0, 0),
        "record_type": "qa",
    }
    base.update(overrides)
    return base


def _raw_row(**overrides):
    base = {
        "canonical_doc_id": "123456",
        "corpus": "LS",
        "date": datetime.date(2023, 3, 15),
        "provider": "internet_archive",
        "format": "ia_text",
        "extracted_text": "Full text of the sitting document...",
        "metadata_json": {"eparlib_lok_sabha_number": "17"},
        "fetch_url": "https://archive.org/download/eparlib.nic.in.123456/file.txt",
        "citation_url": "https://archive.org/details/eparlib.nic.in.123456",
        "fetched_at": datetime.datetime(2026, 5, 10, 8, 0, 0),
    }
    base.update(overrides)
    return base


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_and_teardown():
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


def _make_client_with_fetchrow(fetchrow_result=None, fetchrow_side_effect=None,
                                fetch_result=None):
    mock_pool = make_mock_pool(
        fetchrow_result=fetchrow_result,
        fetchrow_side_effect=fetchrow_side_effect,
        fetch_result=fetch_result,
    )
    mock_meili = make_mock_meili_client()
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_client] = lambda: mock_meili
    return TestClient(app)


# ── GET /api/debug/processed/{id} ─────────────────────────────────────────────

class TestDebugProcessedRoute:
    def test_speech_row_returns_200_with_table_discriminator(self):
        """Returns {table: "speeches", row: {...}} for a speech record."""
        row = _speech_row()
        with _make_client_with_fetchrow(fetchrow_result=row) as client:
            resp = client.get("/api/debug/processed/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["table"] == "speeches"
        assert body["row"]["source"] == "LS"
        assert body["row"]["canonical_doc_id"] == "123456"

    def test_speech_row_date_serialized_as_iso_string(self):
        """DATE columns are serialized as ISO strings."""
        row = _speech_row()
        with _make_client_with_fetchrow(fetchrow_result=row) as client:
            resp = client.get("/api/debug/processed/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["row"]["date"] == "2023-03-15"

    def test_speech_row_segments_jsonb_returned_as_nested_json(self):
        """JSONB segments column is returned as a nested JSON structure."""
        row = _speech_row()
        with _make_client_with_fetchrow(fetchrow_result=row) as client:
            resp = client.get("/api/debug/processed/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["row"]["segments"], list)
        assert body["row"]["segments"][0]["text"] == "Mr. Speaker"

    def test_qa_row_returns_qa_exchanges_discriminator(self):
        """Returns {table: "qa_exchanges", row: {...}} for a Q+A record.

        The mock returns None for the first fetchrow (speeches) and the Q+A
        row for the second (qa_exchanges).
        """
        qa = _qa_row()
        side_effects = [None, qa]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/processed/qa2b1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["table"] == "qa_exchanges"
        assert body["row"]["question_number"] == 42

    def test_unknown_id_returns_404(self):
        """Returns 404 when the id is not found in either table."""
        side_effects = [None, None]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/processed/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"
        assert "Record not found" in body["message"]

    def test_invalid_uuid_returns_404(self):
        """Invalid UUID string triggers a DB cast error — returns 404."""
        exc = Exception("invalid input syntax for type uuid: \"not-a-uuid\"")
        with _make_client_with_fetchrow(fetchrow_side_effect=exc) as client:
            resp = client.get("/api/debug/processed/not-a-uuid")
        assert resp.status_code == 404

    def test_created_at_serialized_as_iso_string(self):
        """TIMESTAMPTZ created_at column is returned as an ISO string."""
        row = _speech_row()
        with _make_client_with_fetchrow(fetchrow_result=row) as client:
            resp = client.get("/api/debug/processed/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert "2026-05-10" in body["row"]["created_at"]


# ── GET /api/debug/raw/{id} ───────────────────────────────────────────────────

class TestDebugRawRoute:
    def test_returns_raw_document_row(self):
        """Returns {row: {...}} with the full raw_documents row."""
        speech = _speech_row()  # canonical_doc_id="123456", source="LS"
        raw = _raw_row()
        # fetchrow called twice: once for speeches lookup, once for raw_documents
        side_effects = [speech, raw]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert "row" in body
        assert body["row"]["canonical_doc_id"] == "123456"
        assert body["row"]["corpus"] == "LS"
        assert body["row"]["provider"] == "internet_archive"
        assert "Full text" in body["row"]["extracted_text"]

    def test_returns_raw_document_via_qa_row(self):
        """Resolves via qa_exchanges when speeches lookup returns None."""
        qa = _qa_row()  # canonical_doc_id="654321", source="LS"
        raw = _raw_row(canonical_doc_id="654321")
        # speeches → None, qa_exchanges → qa, raw_documents → raw
        side_effects = [None, qa, raw]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/qa2b1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["row"]["canonical_doc_id"] == "654321"

    def test_404_when_processed_record_not_found(self):
        """404 when neither speeches nor qa_exchanges has the id."""
        side_effects = [None, None]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"
        assert "Raw document not available" in body["message"]

    def test_404_when_canonical_doc_id_is_null(self):
        """404 when processed record exists but canonical_doc_id is NULL."""
        speech = _speech_row(canonical_doc_id=None)
        with _make_client_with_fetchrow(fetchrow_result=speech) as client:
            resp = client.get("/api/debug/raw/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"

    def test_404_when_raw_documents_row_not_found(self):
        """404 when processed record has canonical_doc_id but no raw_documents row."""
        speech = _speech_row()  # canonical_doc_id="123456"
        side_effects = [speech, None]  # raw_documents fetchrow → None
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 404

    def test_raw_fetched_at_serialized_as_iso_string(self):
        """TIMESTAMPTZ fetched_at column is returned as an ISO string."""
        speech = _speech_row()
        raw = _raw_row()
        side_effects = [speech, raw]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert "2026-05-10" in body["row"]["fetched_at"]

    def test_metadata_json_returned_as_nested_object(self):
        """metadata_json JSONB column is returned as a nested dict."""
        speech = _speech_row()
        raw = _raw_row()
        side_effects = [speech, raw]
        with _make_client_with_fetchrow(fetchrow_side_effect=side_effects) as client:
            resp = client.get("/api/debug/raw/3f2a1b00-0000-0000-0000-000000000001")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["row"]["metadata_json"], dict)
        assert body["row"]["metadata_json"]["eparlib_lok_sabha_number"] == "17"
