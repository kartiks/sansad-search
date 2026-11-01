"""
Indexer.index_document / next_sequence / read_raw_documents_for_scope against a
live PostgreSQL. Skipped unless TEST_DATABASE_URL is set (point it at a throwaway
database: every test truncates the ingestion tables).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import psycopg2
import pytest

from ingest.checkpoints.store import CheckpointStore
from ingest.indexer import Indexer, build_dedup_key

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
_TABLES = ("speeches", "qa_exchanges", "raw_documents", "processed_documents",
           "ingestion_dedup_keys", "index_status")


@pytest.fixture(scope="module")
def pg_dsn():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set — skipping live PostgreSQL indexer tests")
    conn = psycopg2.connect(dsn)
    with conn.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text())
    conn.commit()
    conn.close()
    return dsn


@pytest.fixture()
def db(pg_dsn):
    conn = psycopg2.connect(pg_dsn)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def indexer(db, pg_dsn):
    meili = MagicMock()
    meili.index.return_value.add_documents.return_value = MagicMock(task_uid=1)
    return Indexer(db, meili, pg_dsn=pg_dsn)


@pytest.fixture()
def checkpoint(pg_dsn):
    with CheckpointStore(pg_dsn) as cp:
        yield cp


def _speech(seq: int, **kw) -> dict:
    r = {
        "record_type": "speech", "source": "LS", "proceeding_type": "debate",
        "date": "1996-07-15", "sitting_number": 3, "speaker_name": f"Member {seq}",
        "sequence_within_sitting": seq, "full_text_en": f"Speech {seq} — 50% of 100%s",
        "lang_original": "en", "is_translated": False, "has_untranslated_content": False,
        "speaker_name_unresolved": True, "segments": [{"text": "x"}],
        "canonical_doc_id": "1001", "source_url": "https://archive.org/details/x",
    }
    r.update(kw)
    return r


def _qa(qnum: int, **kw) -> dict:
    r = {
        "record_type": "qa", "source": "LS", "proceeding_type": "unstarred_question",
        "date": "1996-07-15", "sitting_number": 3, "question_number": qnum,
        "questioner_names": ["A. Member", "B. Member"], "minister_name": "C. Minister",
        "sequence_within_sitting": 100 + qnum, "full_text_en": "Will the Minister…",
        "lang_original": "en", "is_translated": False, "has_untranslated_content": False,
        "canonical_doc_id": "2002",
    }
    r.update(kw)
    return r


def _count(db, sql: str, params: tuple | None = None) -> int:
    with db.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_index_document_writes_records_keys_and_marker_together(db, indexer, checkpoint):
    records = [_speech(1), _speech(2), _speech(3, speaker_name="O'Brien")]
    n = indexer.index_document(records, checkpoint, corpus="LS", canonical_doc_id="1001",
                               provider="internet_archive", fetch_url="u")
    assert n == 3
    assert _count(db, "SELECT count(*) FROM speeches") == 3
    assert _count(db, "SELECT count(*) FROM ingestion_dedup_keys WHERE corpus='LS'") == 3
    assert checkpoint.processed_ids("LS") == {"1001"}
    # "%" in speech text survives (values are mogrified, not re-parsed as placeholders)
    assert _count(db, "SELECT count(*) FROM speeches WHERE full_text_en LIKE %s",
                  ("%— 50\\% of 100\\%s",)) == 3
    # every stored record was queued for Meilisearch with its PostgreSQL id
    with db.cursor() as cur:
        cur.execute("SELECT id::text FROM speeches")
        ids = {r[0] for r in cur.fetchall()}
    assert {d["id"] for d in indexer._meili_batch} == ids


def test_index_document_qa_with_arrays(db, indexer, checkpoint):
    records = [_qa(1), _qa(2, questioner_names=[])]
    assert indexer.index_document(records, checkpoint, corpus="LS", canonical_doc_id="2002") == 2
    with db.cursor() as cur:
        cur.execute("SELECT question_number, questioner_names FROM qa_exchanges ORDER BY 1")
        assert cur.fetchall() == [(1, ["A. Member", "B. Member"]), (2, [])]


def test_rerun_inserts_nothing_and_duplicates_in_one_document_collapse(db, indexer, checkpoint):
    records = [_speech(1), _speech(1)]  # same dedup key twice
    assert indexer.index_document(records, checkpoint, corpus="LS", canonical_doc_id="1001") == 1
    assert indexer.index_document([_speech(1)], checkpoint, corpus="LS", canonical_doc_id="1001") == 0
    assert _count(db, "SELECT count(*) FROM speeches") == 1


def test_document_with_no_records_is_still_marked(db, indexer, checkpoint):
    assert indexer.index_document([], checkpoint, corpus="LS", canonical_doc_id="3003") == 0
    assert checkpoint.processed_ids("LS") == {"3003"}


def test_record_without_date_is_skipped_not_fatal(db, indexer, checkpoint):
    records = [_speech(1), _speech(2, date=None)]
    assert indexer.index_document(records, checkpoint, corpus="LS", canonical_doc_id="1001") == 1


def test_bad_value_falls_back_to_record_by_record(db, indexer, checkpoint):
    # session_number is INTEGER: a text value fails the batch, then only that record.
    records = [_speech(1), _speech(2, session_number="not a number")]
    assert indexer.index_document(records, checkpoint, corpus="LS", canonical_doc_id="1001") == 1
    assert checkpoint.processed_ids("LS") == {"1001"}


def test_next_sequence_continues_after_stored_records(db, indexer, checkpoint):
    assert indexer.next_sequence("LS", "1996-07-15", 3) == 1
    indexer.index_document([_speech(1), _speech(2)], checkpoint, corpus="LS", canonical_doc_id="1001")
    indexer.index_document([_qa(7)], checkpoint, corpus="LS", canonical_doc_id="2002")
    assert indexer.next_sequence("LS", "1996-07-15", 3) == 108  # qa seq 107 is the highest
    assert indexer.next_sequence("LS", "1996-07-15", 4) == 1
    assert indexer.next_sequence("LS", "1996-07-15", None) == 1
    assert indexer.next_sequence("LS", None, 3) == 1


def test_read_raw_documents_orders_skips_and_chunks(db, indexer, monkeypatch):
    import ingest.indexer as mod
    monkeypatch.setattr(mod, "RAW_DOC_CHUNK", 2)
    for doc_id, d in (("12", "1996-07-15"), ("9", "1996-07-15"), ("100", "1996-07-14"), ("7", None), ("5", "1996-07-16")):
        indexer.write_raw_document(doc_id, "LS", d, "internet_archive", "ia_text", "t", {"k": doc_id}, None, None)
    rows = list(indexer.read_raw_documents_for_scope("LS", skip_ids={"5"}))
    assert [r["canonical_doc_id"] for r in rows] == ["100", "9", "12", "7"]
    assert rows[0]["metadata_json"] == {"k": "100"}


def test_dedup_key_matches_single_record_path(db, indexer, checkpoint):
    rec = _speech(4)
    indexer.index_document([rec], checkpoint, corpus="LS", canonical_doc_id="1001")
    with db.cursor() as cur:
        cur.execute("SELECT dedup_key FROM speeches")
        assert cur.fetchone()[0] == build_dedup_key(rec)
