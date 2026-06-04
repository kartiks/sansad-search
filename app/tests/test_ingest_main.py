"""
Tests for the ingestion CLI entry point (ingest.main).

Phase 12 update: --stage fetch|process|all replaces the combined run() path.
--date-override removed; --date-from/--date-to added for Stage 2 scope.
_make_orchestrator no longer takes a date_override argument.

These tests exercise argument parsing, source selection, the
reindex-from-db path, and the orchestration glue in ``_async_main``.
External systems (PostgreSQL, Meilisearch) and the per-source orchestrators
(CAOrchestrator, LSOrchestrator, RSOrchestrator) are mocked.
"""
from __future__ import annotations

from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingest import main as main_mod


# ── argument parsing ────────────────────────────────────────────────────────
class TestParseArgs:
    def test_source_required(self) -> None:
        with pytest.raises(SystemExit):
            main_mod._parse_args([])

    def test_source_ca(self) -> None:
        args = main_mod._parse_args(["--source", "ca"])
        assert args.source == "ca"
        assert args.date_from is None
        assert args.date_to is None
        assert args.reindex_from_db is False

    def test_date_from_parsed(self) -> None:
        args = main_mod._parse_args(
            ["--source", "ls", "--date-from", "2014-05-01"]
        )
        assert args.date_from == "2014-05-01"

    def test_date_to_parsed(self) -> None:
        args = main_mod._parse_args(
            ["--source", "ls", "--date-to", "2024-12-31"]
        )
        assert args.date_to == "2024-12-31"

    def test_reindex_flag(self) -> None:
        args = main_mod._parse_args(["--source", "all", "--reindex-from-db"])
        assert args.reindex_from_db is True

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(SystemExit):
            main_mod._parse_args(["--source", "xx"])

    @pytest.mark.parametrize("source", ["ca", "ls", "rs", "all"])
    def test_all_valid_sources_accepted(self, source: str) -> None:
        args = main_mod._parse_args(["--source", source])
        assert args.source == source

    def test_date_override_no_longer_accepted(self) -> None:
        """--date-override was removed in Phase 12; must be rejected."""
        with pytest.raises(SystemExit):
            main_mod._parse_args(["--source", "ls", "--date-override", "2014-01-01"])


# ── orchestrator selection (_make_orchestrator) ──────────────────────────────
class TestMakeOrchestrator:
    """Verify the right orchestrator class is built with the real signature."""

    def _commons(self) -> tuple[Any, Any, Any, dict[str, str]]:
        return MagicMock(name="client"), MagicMock(name="checkpoint"), \
            MagicMock(name="indexer"), {}

    def test_ca_builds_ca_orchestrator(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "CAOrchestrator") as ca_cls:
            main_mod._make_orchestrator("ca", client, checkpoint, indexer, names)
        ca_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_ca_builds_ca_orchestrator_with_date_params(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "CAOrchestrator") as ca_cls:
            main_mod._make_orchestrator("ca", client, checkpoint, indexer, names,
                                        date_from="2024-01-01", date_to="2024-03-31")
        ca_cls.assert_called_once_with(client, checkpoint, indexer, names,
                                       date_from="2024-01-01", date_to="2024-03-31")

    def test_ls_builds_ls_orchestrator(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "LSOrchestrator") as ls_cls:
            main_mod._make_orchestrator("ls", client, checkpoint, indexer, names)
        ls_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_rs_builds_rs_orchestrator(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "RSOrchestrator") as rs_cls:
            main_mod._make_orchestrator("rs", client, checkpoint, indexer, names)
        rs_cls.assert_called_once_with(client, checkpoint, indexer, names, date_from=None, date_to=None)

    def test_unknown_source_raises(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with pytest.raises(ValueError):
            main_mod._make_orchestrator("zz", client, checkpoint, indexer, names)


# ── shared orchestration harness ─────────────────────────────────────────────
def _orchestrator_mock(
    s1_stats: Optional[dict] = None,
    s2_stats: Optional[dict] = None,
) -> MagicMock:
    """Return a mock orchestrator class with async run_stage1/run_stage2 methods."""
    if s1_stats is None:
        s1_stats = {"fetched": 1, "skipped": 0, "errors": 0}
    if s2_stats is None:
        s2_stats = {"indexed": 1, "skipped": 0, "errors": 0}
    instance = MagicMock()
    instance.run_stage1 = AsyncMock(return_value=s1_stats)
    instance.run_stage2 = AsyncMock(return_value=s2_stats)
    instance.run = AsyncMock(return_value={"indexed": 1, "skipped": 0, "errors": 0})
    cls = MagicMock(return_value=instance)
    return cls


def _patched_main(
    argv: list[str],
    ca_cls: Any,
    ls_cls: Any,
    rs_cls: Any,
    indexer_inst: Optional[MagicMock] = None,
) -> int:
    """Run main() with all external deps and orchestrators patched."""
    if indexer_inst is None:
        indexer_inst = MagicMock()
        indexer_inst.counts = {"CA": 1, "LS": 2, "RS": 3}
    checkpoint_inst = MagicMock()
    checkpoint_inst.__enter__ = MagicMock(return_value=checkpoint_inst)
    checkpoint_inst.__exit__ = MagicMock(return_value=False)

    with patch.object(main_mod, "_connect_postgres", return_value=MagicMock()), \
         patch.object(main_mod, "_connect_meilisearch", return_value=MagicMock()), \
         patch.object(main_mod, "load_names_dict", return_value={}), \
         patch.object(main_mod, "Indexer", return_value=indexer_inst), \
         patch.object(main_mod, "CheckpointStore", return_value=checkpoint_inst), \
         patch.object(main_mod, "CAOrchestrator", ca_cls), \
         patch.object(main_mod, "LSOrchestrator", ls_cls), \
         patch.object(main_mod, "RSOrchestrator", rs_cls):
        return main_mod.main(argv)


# ── end-to-end orchestration (mocked) ────────────────────────────────────────
class TestAsyncMainOrchestration:
    def test_source_ca_calls_only_ca_stages(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run_stage1.assert_awaited_once()
        ca_cls.return_value.run_stage2.assert_awaited_once()
        ls_cls.return_value.run_stage1.assert_not_called()
        rs_cls.return_value.run_stage1.assert_not_called()

    def test_source_ls_calls_only_ls_stages(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "ls"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ls_cls.return_value.run_stage1.assert_awaited_once()
        ls_cls.return_value.run_stage2.assert_awaited_once()
        ca_cls.return_value.run_stage1.assert_not_called()
        rs_cls.return_value.run_stage1.assert_not_called()

    def test_source_rs_calls_only_rs_stages(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "rs"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        rs_cls.return_value.run_stage1.assert_awaited_once()
        rs_cls.return_value.run_stage2.assert_awaited_once()
        ca_cls.return_value.run_stage1.assert_not_called()
        ls_cls.return_value.run_stage1.assert_not_called()

    def test_source_all_calls_all_three_in_order(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "all"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run_stage1.assert_awaited_once()
        ls_cls.return_value.run_stage1.assert_awaited_once()
        rs_cls.return_value.run_stage1.assert_awaited_once()

    def test_stage1_called_with_date_params_none_by_default(self) -> None:
        """run_stage1 always receives date_from and date_to (None when not specified)."""
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        ca_cls.return_value.run_stage1.assert_awaited_once_with(
            date_from=None, date_to=None
        )

    def test_stage2_called_with_date_from_none_by_default(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        ca_cls.return_value.run_stage2.assert_awaited_once_with(
            date_from=None, date_to=None
        )

    def test_orchestrator_constructed_with_http_client_first(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        ca_cls.assert_called_once()
        client_arg = ca_cls.call_args.args[0]
        assert isinstance(client_arg, httpx.AsyncClient)

    def test_update_index_status_called_on_completion(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        indexer_inst = MagicMock()
        indexer_inst.counts = {"CA": 1, "LS": 0, "RS": 0}
        rc = _patched_main(
            ["--source", "ca"], ca_cls, ls_cls, rs_cls, indexer_inst=indexer_inst
        )
        assert rc == 0
        indexer_inst.update_index_status.assert_called_once()

    def test_completion_summary_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        with caplog.at_level(logging.INFO, logger="ingest.main"):
            _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        messages = [r.getMessage() for r in caplog.records]
        assert any("Ingestion complete" in m for m in messages)
        assert any("Stage 2" in m or "records indexed" in m.lower() for m in messages)
        assert any("Errors" in m for m in messages)


# ── reindex-from-db path ─────────────────────────────────────────────────────
class TestReindexFromDb:
    def test_reindex_skips_scraping(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        indexer_inst = MagicMock()
        indexer_inst.reindex_from_db.return_value = 42
        with patch.object(main_mod, "_connect_postgres", return_value=MagicMock()), \
             patch.object(main_mod, "_connect_meilisearch", return_value=MagicMock()), \
             patch.object(main_mod, "load_names_dict", return_value={}), \
             patch.object(main_mod, "Indexer", return_value=indexer_inst), \
             patch.object(main_mod, "CheckpointStore") as cp_cls, \
             patch.object(main_mod, "CAOrchestrator", ca_cls), \
             patch.object(main_mod, "LSOrchestrator", ls_cls), \
             patch.object(main_mod, "RSOrchestrator", rs_cls):
            rc = main_mod.main(["--source", "all", "--reindex-from-db"])
        assert rc == 0
        indexer_inst.reindex_from_db.assert_called_once()
        # Reindex path must not touch scraping infrastructure.
        cp_cls.assert_not_called()
        ca_cls.return_value.run_stage1.assert_not_called()
        ls_cls.return_value.run_stage1.assert_not_called()
        rs_cls.return_value.run_stage1.assert_not_called()
