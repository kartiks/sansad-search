"""
Tests for the ingestion CLI entry point (ingest.main).

These tests exercise argument parsing, source selection, the
reindex-from-db path, and the orchestration glue in ``_async_main``.
External systems (PostgreSQL, Meilisearch) and the per-source orchestrators
(CAOrchestrator, LSOrchestrator, RSOrchestrator) are mocked — the
orchestrators are tested in isolation in their own test modules, so here we
only verify that ``main`` selects and drives the correct orchestrator with
the correct constructor arguments and a no-argument ``run()`` call.
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
        assert args.date_override is None
        assert args.reindex_from_db is False

    def test_date_override_parsed(self) -> None:
        args = main_mod._parse_args(
            ["--source", "ls", "--date-override", "2014-05-01"]
        )
        assert args.date_override == "2014-05-01"

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


# ── orchestrator selection (_make_orchestrator) ──────────────────────────────
class TestMakeOrchestrator:
    """Verify the right orchestrator class is built with the real signature.

    Real constructor order is (client, checkpoint, indexer, names_dict, ...) —
    these tests fail if the argument order regresses.
    """

    def _commons(self) -> tuple[Any, Any, Any, dict[str, str]]:
        return MagicMock(name="client"), MagicMock(name="checkpoint"), \
            MagicMock(name="indexer"), {}

    def test_ca_builds_ca_orchestrator_without_date(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "CAOrchestrator") as ca_cls:
            main_mod._make_orchestrator(
                "ca", client, checkpoint, indexer, names, "2014-01-01"
            )
        # CA ignores the override and takes no date_from.
        ca_cls.assert_called_once_with(client, checkpoint, indexer, names)

    def test_ls_builds_ls_orchestrator_with_date_from(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "LSOrchestrator") as ls_cls:
            main_mod._make_orchestrator(
                "ls", client, checkpoint, indexer, names, "2014-05-01"
            )
        ls_cls.assert_called_once_with(
            client, checkpoint, indexer, names, date_from="2014-05-01"
        )

    def test_rs_builds_rs_orchestrator_with_date_from(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "RSOrchestrator") as rs_cls:
            main_mod._make_orchestrator(
                "rs", client, checkpoint, indexer, names, "2014-05-01"
            )
        rs_cls.assert_called_once_with(
            client, checkpoint, indexer, names, date_from="2014-05-01"
        )

    def test_ls_date_from_none_when_no_override(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with patch.object(main_mod, "LSOrchestrator") as ls_cls:
            main_mod._make_orchestrator(
                "ls", client, checkpoint, indexer, names, None
            )
        ls_cls.assert_called_once_with(
            client, checkpoint, indexer, names, date_from=None
        )

    def test_unknown_source_raises(self) -> None:
        client, checkpoint, indexer, names = self._commons()
        with pytest.raises(ValueError):
            main_mod._make_orchestrator(
                "zz", client, checkpoint, indexer, names, None
            )


# ── shared orchestration harness ─────────────────────────────────────────────
def _orchestrator_mock(stats: Optional[dict[str, int]] = None) -> MagicMock:
    """Return a mock orchestrator class whose instance has an async run()."""
    if stats is None:
        stats = {"indexed": 1, "skipped": 0, "errors": 0}
    instance = MagicMock()
    instance.run = AsyncMock(return_value=stats)
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
    def test_source_ca_calls_only_ca_run(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run.assert_awaited_once()
        ls_cls.return_value.run.assert_not_called()
        rs_cls.return_value.run.assert_not_called()

    def test_source_ls_calls_only_ls_run(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "ls"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ls_cls.return_value.run.assert_awaited_once()
        ca_cls.return_value.run.assert_not_called()
        rs_cls.return_value.run.assert_not_called()

    def test_source_rs_calls_only_rs_run(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "rs"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        rs_cls.return_value.run.assert_awaited_once()
        ca_cls.return_value.run.assert_not_called()
        ls_cls.return_value.run.assert_not_called()

    def test_source_all_calls_all_three_runs_in_order(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        rc = _patched_main(["--source", "all"], ca_cls, ls_cls, rs_cls)
        assert rc == 0
        ca_cls.return_value.run.assert_awaited_once()
        ls_cls.return_value.run.assert_awaited_once()
        rs_cls.return_value.run.assert_awaited_once()

    def test_run_called_with_no_arguments(self) -> None:
        # The real orchestrator.run() takes no args (the client is injected at
        # construction). A regression to run(client) would fail this.
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        ca_cls.return_value.run.assert_awaited_once_with()

    def test_orchestrator_constructed_with_http_client_first(self) -> None:
        # First positional constructor arg must be the shared httpx.AsyncClient.
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ca"], ca_cls, ls_cls, rs_cls)
        ca_cls.assert_called_once()
        client_arg = ca_cls.call_args.args[0]
        assert isinstance(client_arg, httpx.AsyncClient)

    def test_date_override_forwarded_to_ls_as_date_from(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(
            ["--source", "ls", "--date-override", "2014-05-01"],
            ca_cls, ls_cls, rs_cls,
        )
        ls_cls.assert_called_once()
        # date_from is the ISO string, passed straight through to the providers.
        assert ls_cls.call_args.kwargs["date_from"] == "2014-05-01"

    def test_date_override_forwarded_to_rs_as_date_from(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(
            ["--source", "rs", "--date-override", "2016-02-29"],
            ca_cls, ls_cls, rs_cls,
        )
        rs_cls.assert_called_once()
        assert rs_cls.call_args.kwargs["date_from"] == "2016-02-29"

    def test_no_date_override_passes_none_date_from(self) -> None:
        ca_cls, ls_cls, rs_cls = (
            _orchestrator_mock(), _orchestrator_mock(), _orchestrator_mock()
        )
        _patched_main(["--source", "ls"], ca_cls, ls_cls, rs_cls)
        assert ls_cls.call_args.kwargs["date_from"] is None

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
        assert any("Total indexed" in m for m in messages)
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
        ca_cls.return_value.run.assert_not_called()
        ls_cls.return_value.run.assert_not_called()
        rs_cls.return_value.run.assert_not_called()
