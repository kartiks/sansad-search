"""Tests for app/db/schema.sql — validates the schema executes cleanly and creates correct tables/indexes."""
import os
import subprocess
import pytest
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


@pytest.fixture(scope="module")
def pg_available():
    """Skip tests if PostgreSQL is not available in this environment."""
    db_url = os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("TEST_DATABASE_URL not set — skipping PostgreSQL schema tests")
    return db_url


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), "schema.sql must exist"


def test_schema_has_speeches_table():
    content = SCHEMA_PATH.read_text()
    assert "CREATE TABLE IF NOT EXISTS speeches" in content


def test_schema_has_qa_exchanges_table():
    content = SCHEMA_PATH.read_text()
    assert "CREATE TABLE IF NOT EXISTS qa_exchanges" in content


def test_schema_has_index_status_table():
    content = SCHEMA_PATH.read_text()
    assert "CREATE TABLE IF NOT EXISTS index_status" in content


def test_schema_has_dedup_key_unique_speeches():
    content = SCHEMA_PATH.read_text()
    # Verify UNIQUE dedup_key exists specifically in the speeches table block
    speeches_block = content.split("CREATE TABLE IF NOT EXISTS qa_exchanges")[0]
    assert "dedup_key" in speeches_block
    assert "UNIQUE" in speeches_block


def test_schema_has_dedup_key_unique_qa_exchanges():
    content = SCHEMA_PATH.read_text()
    # Verify UNIQUE dedup_key exists specifically in the qa_exchanges table block
    qa_block = content.split("CREATE TABLE IF NOT EXISTS qa_exchanges")[1].split(
        "CREATE TABLE IF NOT EXISTS index_status"
    )[0]
    assert "dedup_key" in qa_block, "qa_exchanges must have a dedup_key column"
    assert "UNIQUE" in qa_block, "qa_exchanges.dedup_key must have UNIQUE constraint"


def test_schema_has_all_required_speeches_columns():
    content = SCHEMA_PATH.read_text()
    required = [
        "id", "source", "proceeding_type", "date", "session_name",
        "speaker_name", "full_text_en", "is_translated",
        "has_untranslated_content", "speaker_name_unresolved",
        "dedup_key", "ocr_low_confidence", "sequence_within_sitting",
    ]
    for col in required:
        assert col in content, f"Missing column: {col}"


def test_schema_has_all_required_qa_columns():
    content = SCHEMA_PATH.read_text()
    required = [
        "id", "source", "proceeding_type", "date", "questioner_names",
        "minister_name", "ministry", "full_text_en", "is_translated",
        "has_untranslated_content", "question_number", "dedup_key",
    ]
    for col in required:
        assert col in content, f"Missing QA column: {col}"


def test_schema_has_index_on_speeches_date():
    content = SCHEMA_PATH.read_text()
    assert "idx_speeches_date" in content


def test_schema_has_gin_index_for_questioner_names():
    content = SCHEMA_PATH.read_text()
    assert "GIN" in content
    assert "questioner_names" in content


def test_schema_executes_against_postgres(pg_available):
    """Integration test: apply schema to a real PostgreSQL instance."""
    result = subprocess.run(
        ["psql", pg_available, "-f", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"schema.sql failed:\n{result.stderr}"
