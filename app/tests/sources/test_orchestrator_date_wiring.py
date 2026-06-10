"""
Tests that LSOrchestrator, RSOrchestrator, and CAOrchestrator thread the
``date_from`` and ``date_to`` overrides into their default provider chains,
and that omitting them preserves each provider's built-in defaults.

These are white-box checks on the constructed providers (no I/O). They guard
the wiring that makes ``--date-from``/``--date-to`` take effect end-to-end:
main → orchestrator → provider → discovery helper.

LS chain (updated 2026-06):
  [InternetArchiveProvider(LS), ElibraryDSpace7Provider]
  EparlibDspaceProvider removed — eparlib.sansad.in server is unresponsive.
  ElibraryDSpace7Provider enforces date_from >= "2019-01-01" to avoid
  overlapping with the IA provider.

RS chain (updated 2026-06):
  [InternetArchiveProvider(RS)]
  SansadRsHtmlProvider removed — sansad.in RS page is JS-rendered.
  RsdebateDspaceProvider removed — rsdebate.nic.in is unresponsive.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from ingest.sources.ca import CAOrchestrator
from ingest.sources.ls import LSOrchestrator
from ingest.sources.providers.coi_html import CoidHtmlProvider
from ingest.sources.providers.elibrary_dspace7 import ElibraryDSpace7Provider
from ingest.sources.providers.internet_archive import InternetArchiveProvider
from ingest.sources.rs import RSOrchestrator


def _by_type(providers, cls):
    return next(p for p in providers if isinstance(p, cls))


class TestLSWiring:
    def test_date_from_forwarded_to_ia_provider(self) -> None:
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="2021-01-01"
        )
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_from == "2021-01-01"

    def test_date_to_forwarded_to_ia_provider(self) -> None:
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            date_from="2021-01-01", date_to="2021-12-31",
        )
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_to == "2021-12-31"

    def test_elibrary_date_from_clamped_to_2019(self) -> None:
        """Even if the orchestrator date_from is before 2019, elibrary uses 2019-01-01."""
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="1947-08-15"
        )
        elibrary = _by_type(orch._providers, ElibraryDSpace7Provider)
        assert elibrary._date_from == "2019-01-01"

    def test_elibrary_date_from_respected_when_after_2019(self) -> None:
        """When orchestrator date_from > 2019, elibrary uses it."""
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="2022-06-01"
        )
        elibrary = _by_type(orch._providers, ElibraryDSpace7Provider)
        assert elibrary._date_from == "2022-06-01"

    def test_elibrary_date_to_forwarded(self) -> None:
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            date_from="2020-01-01", date_to="2024-12-31",
        )
        elibrary = _by_type(orch._providers, ElibraryDSpace7Provider)
        assert elibrary._date_to == "2024-12-31"

    def test_no_date_to_leaves_providers_with_none(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        elibrary = _by_type(orch._providers, ElibraryDSpace7Provider)
        assert ia._date_to is None
        assert elibrary._date_to is None

    def test_no_date_from_uses_provider_defaults(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        elibrary = _by_type(orch._providers, ElibraryDSpace7Provider)
        assert ia._date_from == "1947-08-15"
        assert elibrary._date_from == "2019-01-01"

    def test_ls_default_chain_order(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        assert [type(p).__name__ for p in orch._providers] == [
            "InternetArchiveProvider",
            "ElibraryDSpace7Provider",
        ]

    def test_ia_corpus_is_ls(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._corpus == "LS"

    def test_injected_providers_used_as_is(self) -> None:
        sentinel = [MagicMock()]
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            providers=sentinel, date_from="2016-05-01",
        )
        assert orch._providers is sentinel


class TestRSWiring:
    def test_date_from_forwarded_to_ia_provider(self) -> None:
        orch = RSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="2016-05-01"
        )
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_from == "2016-05-01"

    def test_date_to_forwarded_to_ia_provider(self) -> None:
        orch = RSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            date_from="2016-01-01", date_to="2018-08-31",
        )
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_to == "2018-08-31"

    def test_no_date_to_leaves_ia_with_none(self) -> None:
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_to is None

    def test_no_date_from_uses_provider_defaults(self) -> None:
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._date_from == "1947-08-15"

    def test_rs_default_chain_order(self) -> None:
        """RS chain is IA-only: SansadRsHtml and RsdebateDspace removed."""
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        assert [type(p).__name__ for p in orch._providers] == [
            "InternetArchiveProvider",
        ]

    def test_ia_corpus_is_rs(self) -> None:
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._corpus == "RS"

    def test_injected_providers_used_as_is(self) -> None:
        sentinel = [MagicMock()]
        orch = RSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            providers=sentinel, date_from="2016-05-01",
        )
        assert orch._providers is sentinel


class TestCAWiring:
    def test_date_from_and_date_to_forwarded_to_coi_html_provider(self) -> None:
        from datetime import date as dt
        orch = CAOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            date_from="1947-01-01", date_to="1949-12-31",
        )
        assert isinstance(orch._provider, CoidHtmlProvider)
        assert orch._provider._date_from == dt(1947, 1, 1)
        assert orch._provider._date_to == dt(1949, 12, 31)

    def test_no_date_params_leaves_coi_html_provider_without_bounds(self) -> None:
        orch = CAOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        assert isinstance(orch._provider, CoidHtmlProvider)
        assert orch._provider._date_from is None
        assert orch._provider._date_to is None

    def test_injected_provider_used_as_is(self) -> None:
        mock_provider = MagicMock()
        orch = CAOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            provider=mock_provider,
            date_from="1947-01-01", date_to="1949-12-31",
        )
        assert orch._provider is mock_provider
