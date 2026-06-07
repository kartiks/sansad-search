"""
Tests for the F09 record detail endpoints (PRD v3.0):
- GET /api/record/{id}            — single record + sitting context
                                     (has_prev / has_next, sitting_total,
                                     lok_sabha_number).
- GET /api/record/{id}/adjacent   — inline adjacent range-fetch.

All tests use dependency overrides; no real DB connections required.
"""
from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.lib.db import get_pool
from api.lib.meilisearch_client import get_client
from tests.api.conftest import make_mock_meili_client, make_mock_pool


# ── Row helpers ───────────────────────────────────────────────────────────────

def _speech_row(**overrides):
    """Dict-like asyncpg Record for a speech record."""
    base = {
        "id": "3f2a1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "lok_sabha_number": 17,
        "proceeding_type": "debate",
        "date": datetime.date(2023, 3, 15),
        "session_name": "Budget Session 2023",
        "session_number": 7,
        "sitting_number": 42,
        "subject": "General Discussion on the Union Budget",
        "full_text_en": "Mr. Speaker, I rise to speak on...",
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
        "question_number": None,
        "questioner_names": None,
        "questioner_party": None,
        "minister_name": None,
        "ministry": None,
        "record_type": "speech",
    }
    base.update(overrides)
    return base


def _qa_row(**overrides):
    """Dict-like asyncpg Record for a Q+A record."""
    base = {
        "id": "qa2b1b00-0000-0000-0000-000000000001",
        "source": "LS",
        "lok_sabha_number": 17,
        "proceeding_type": "starred_question",
        "date": datetime.date(2023, 8, 4),
        "session_name": "Monsoon Session 2023",
        "session_number": 8,
        "sitting_number": 12,
        "subject": "Implementation of National Health Mission",
        "full_text_en": "Q: What is the status of NHM?...",
        "lang_original": "en",
        "time_of_day": None,
        "word_count": 540,
        "is_translated": False,
        "has_untranslated_content": False,
        "page_reference": None,
        "source_url": "https://archive.org/details/eparlib.nic.in.654321",
        "sequence_within_sitting": 3,
        "volume": None,
        "speaker_name": None,
        "speaker_role": None,
        "speaker_party": None,
        "speaker_constituency_or_state": None,
        "speaker_name_unresolved": None,
        "question_number": 42,
        "questioner_names": ["Shri A. Kumar"],
        "questioner_party": "BJP",
        "minister_name": "Dr. Mansukh Mandaviya",
        "ministry": "Ministry of Health and Family Welfare",
        "record_type": "qa",
    }
    base.update(overrides)
    return base


def _seq_rows(seqs):
    """Build sitting sequence rows (only sequence_within_sitting, per query)."""
    return [{"sequence_within_sitting": s} for s in seqs]


def _focal(source="LS", date=datetime.date(2023, 3, 15), sitting_number=42, seq=7):
    return {
        "source": source,
        "date": date,
        "sitting_number": sitting_number,
        "sequence_within_sitting": seq,
    }


def _get_client(pool_mock=None, meili_mock=None):
    if pool_mock:
        app.dependency_overrides[get_pool] = lambda: pool_mock
    if meili_mock:
        app.dependency_overrides[get_client] = lambda: meili_mock
    return TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_teardown():
    with patch("api.main.init_pool", new_callable=AsyncMock), \
         patch("api.main.close_pool", new_callable=AsyncMock):
        yield
    app.dependency_overrides.clear()


# ── 200 — Speech record ───────────────────────────────────────────────────────

class TestGetSpeechRecord:
    def test_returns_200(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200

    def test_record_type_is_speech(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["record_type"] == "speech"

    def test_date_display_formatted(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["date_display"] == "15 March 2023"

    def test_date_iso_string(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["date"] == "2023-03-15"

    def test_proceeding_type_label_formatted(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["proceeding_type_label"] == "Debate"

    def test_lok_sabha_number_present(self):
        row = _speech_row(lok_sabha_number=17)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["lok_sabha_number"] == 17

    def test_lok_sabha_number_null_passthrough(self):
        row = _speech_row(source="RS", lok_sabha_number=None)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["lok_sabha_number"] is None

    def test_all_required_fields_present(self):
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        for field in ("id", "record_type", "source", "lok_sabha_number",
                      "proceeding_type", "proceeding_type_label", "date",
                      "date_display", "full_text_en", "lang_original",
                      "sequence_within_sitting", "sitting_total",
                      "has_prev", "has_next"):
            assert field in body, f"Missing field: {field}"

    def test_adjacent_object_removed(self):
        """PRD v3.0 replaced the adjacent.{prev_id,next_id} object."""
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert "adjacent" not in body


# ── 200 — has_prev / has_next boundary flags ──────────────────────────────────

class TestSittingBoundaryFlags:
    def test_sitting_total_matches_sitting_size(self):
        row = _speech_row(sequence_within_sitting=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3, 4, 5, 6, 7]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["sitting_total"] == 7

    def test_has_prev_and_has_next_true_in_middle(self):
        row = _speech_row(sequence_within_sitting=3)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3, 4, 5]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["has_prev"] is True
        assert body["has_next"] is True

    def test_has_prev_false_at_lower_boundary(self):
        row = _speech_row(sequence_within_sitting=1)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3, 4, 5]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["has_prev"] is False
        assert body["has_next"] is True

    def test_has_next_false_at_upper_boundary(self):
        row = _speech_row(sequence_within_sitting=5)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3, 4, 5]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["has_prev"] is True
        assert body["has_next"] is False

    def test_both_false_for_single_record_sitting(self):
        row = _speech_row(sequence_within_sitting=1)
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["has_prev"] is False
        assert body["has_next"] is False
        assert body["sitting_total"] == 1


# ── 200 — Q+A record ─────────────────────────────────────────────────────────

class TestGetQARecord:
    def test_returns_200(self):
        row = _qa_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200

    def test_record_type_is_qa(self):
        row = _qa_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["record_type"] == "qa"

    def test_qa_fields_present(self):
        row = _qa_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["question_number"] == 42
        assert body["questioner_names"] == ["Shri A. Kumar"]
        assert body["minister_name"] == "Dr. Mansukh Mandaviya"

    def test_proceeding_type_label_starred(self):
        row = _qa_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([1, 2, 3]))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(f"/api/record/{row['id']}").json()
        assert body["proceeding_type_label"] == "Starred Question"


# ── 404 — Not found ───────────────────────────────────────────────────────────

class TestRecordNotFound:
    def test_returns_404_when_no_row(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/record/3f2a1b00-0000-0000-0000-000000000099")
        assert resp.status_code == 404

    def test_404_response_shape(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get("/api/record/3f2a1b00-0000-0000-0000-000000000099").json()
        assert body["error"] == "not_found"
        assert body["message"] == "Record not found."

    def test_invalid_uuid_returns_404(self):
        pool = make_mock_pool(fetchrow_side_effect=Exception("invalid input for UUID"))
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get("/api/record/not-a-uuid")
        assert resp.status_code == 404


# ── Separation of concerns ────────────────────────────────────────────────────

class TestRecordServesFromPostgres:
    def test_meilisearch_not_called(self):
        """Record detail must read from PostgreSQL only."""
        row = _speech_row()
        pool = make_mock_pool(fetchrow_result=row, fetch_result=_seq_rows([6, 7, 8]))
        meili = make_mock_meili_client(
            search_side_effect=Exception("Meili should not be called")
        )
        with _get_client(pool, meili) as client:
            resp = client.get(f"/api/record/{row['id']}")
        assert resp.status_code == 200


# ── GET /api/record/{id}/adjacent ─────────────────────────────────────────────

_ADJ_ID = "3f2a1b00-0000-0000-0000-000000000001"


class TestAdjacentEndpoint:
    def test_next_returns_records_ascending(self):
        focal = _focal(seq=7)
        batch = [
            _speech_row(id="adj-8", sequence_within_sitting=8),
            _speech_row(id="adj-9", sequence_within_sitting=9),
            _speech_row(id="adj-10", sequence_within_sitting=10),
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7},
            ).json()
        seqs = [r["sequence_within_sitting"] for r in body["records"]]
        assert seqs == [8, 9, 10]
        assert body["direction"] == "next"

    def test_prev_returns_records_reversed_to_ascending(self):
        focal = _focal(seq=10)
        # Stored DESC (closest-to-focal first) as the real query returns for prev.
        batch = [
            _speech_row(id="adj-9", sequence_within_sitting=9),
            _speech_row(id="adj-8", sequence_within_sitting=8),
            _speech_row(id="adj-7", sequence_within_sitting=7),
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "prev", "from_seq": 10},
            ).json()
        seqs = [r["sequence_within_sitting"] for r in body["records"]]
        assert seqs == [7, 8, 9]

    def test_has_more_true_when_more_remain(self):
        """6 rows returned for limit 5 → has_more True, batch trimmed to 5."""
        focal = _focal(seq=7)
        batch = [
            _speech_row(id=f"adj-{s}", sequence_within_sitting=s)
            for s in range(8, 14)  # 8..13 → 6 rows
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7},
            ).json()
        assert body["has_more"] is True
        assert len(body["records"]) == 5

    def test_has_more_false_when_batch_is_last(self):
        focal = _focal(seq=7)
        batch = [
            _speech_row(id="adj-8", sequence_within_sitting=8),
            _speech_row(id="adj-9", sequence_within_sitting=9),
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7},
            ).json()
        assert body["has_more"] is False
        assert len(body["records"]) == 2

    def test_records_carry_full_fields(self):
        focal = _focal(seq=7)
        batch = [_qa_row(id="adj-q", sequence_within_sitting=8)]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            rec = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7},
            ).json()["records"][0]
        for field in ("id", "record_type", "date_display", "subject",
                      "full_text_en", "proceeding_type_label", "minister_name",
                      "questioner_names", "sequence_within_sitting"):
            assert field in rec
        # Sitting-context fields must NOT be on adjacent records (§3.4).
        assert "sitting_total" not in rec
        assert "has_prev" not in rec
        assert "has_next" not in rec

    def test_invalid_direction_returns_400(self):
        focal = _focal(seq=7)
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=[])
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "sideways", "from_seq": 7},
            )
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    def test_non_integer_from_seq_returns_400(self):
        focal = _focal(seq=7)
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=[])
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": "abc"},
            )
        assert resp.status_code == 400
        assert resp.json()["error"] == "validation_error"

    def test_focal_not_found_returns_404(self):
        pool = make_mock_pool(fetchrow_result=None)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            resp = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7},
            )
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    def test_empty_batch_returns_empty_records(self):
        focal = _focal(seq=99)
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=[])
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 99},
            ).json()
        assert body["records"] == []
        assert body["has_more"] is False

    def test_limit_above_max_clamped_to_5(self):
        """limit=50 in the URL is clamped to max 5 by record.py:222."""
        focal = _focal(seq=7)
        # 6 rows: if limit were not clamped the service would keep all 6.
        batch = [
            _speech_row(id=f"adj-{s}", sequence_within_sitting=s)
            for s in range(8, 14)
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7, "limit": 50},
            ).json()
        assert len(body["records"]) <= 5
        assert body["has_more"] is True

    def test_limit_zero_floored_to_1(self):
        """limit=0 is floored to 1 by record.py:222."""
        focal = _focal(seq=7)
        # 2 rows: with clamped limit=1 the service fetches limit+1=2, trims to 1.
        batch = [
            _speech_row(id="adj-8", sequence_within_sitting=8),
            _speech_row(id="adj-9", sequence_within_sitting=9),
        ]
        pool = make_mock_pool(fetchrow_result=focal, fetch_result=batch)
        meili = make_mock_meili_client()
        with _get_client(pool, meili) as client:
            body = client.get(
                f"/api/record/{_ADJ_ID}/adjacent",
                params={"direction": "next", "from_seq": 7, "limit": 0},
            ).json()
        assert len(body["records"]) == 1
        assert body["has_more"] is True
