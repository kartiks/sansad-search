"""
Tests that LSOrchestrator and RSOrchestrator thread the ``date_from`` override
into their default provider chains, and that omitting it preserves each
provider's built-in 2014-01-01 PRD-scope default.

These are white-box checks on the constructed providers (no I/O). They guard
the wiring that makes ``--date-override`` take effect end-to-end: main →
orchestrator → provider → discovery helper. date_from is an ISO YYYY-MM-DD
string; SansadRsHtmlProvider converts it to a datetime.date internally.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from ingest.sources.ls import LSOrchestrator
from ingest.sources.providers.eparlib_dspace import EparlibDspaceProvider
from ingest.sources.providers.internet_archive import InternetArchiveProvider
from ingest.sources.providers.rsdebate_dspace import RsdebateDspaceProvider
from ingest.sources.providers.sansad_rs_html import SansadRsHtmlProvider
from ingest.sources.rs import RSOrchestrator


def _by_type(providers, cls):
    return next(p for p in providers if isinstance(p, cls))


class TestLSWiring:
    def test_date_from_forwarded_to_both_ls_providers(self) -> None:
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="2016-05-01"
        )
        ia = _by_type(orch._providers, InternetArchiveProvider)
        eparlib = _by_type(orch._providers, EparlibDspaceProvider)
        assert ia._date_from == "2016-05-01"
        assert eparlib._date_from == "2016-05-01"

    def test_no_date_from_keeps_provider_defaults(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        ia = _by_type(orch._providers, InternetArchiveProvider)
        eparlib = _by_type(orch._providers, EparlibDspaceProvider)
        # Providers keep their own built-in 2014-01-01 default.
        assert ia._date_from == "2014-01-01"
        assert eparlib._date_from == "2014-01-01"

    def test_ls_default_chain_order(self) -> None:
        orch = LSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        assert [type(p).__name__ for p in orch._providers] == [
            "InternetArchiveProvider",
            "EparlibDspaceProvider",
        ]

    def test_injected_providers_used_as_is(self) -> None:
        sentinel = [MagicMock()]
        orch = LSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            providers=sentinel, date_from="2016-05-01",
        )
        assert orch._providers is sentinel


class TestRSWiring:
    def test_date_from_forwarded_to_all_rs_providers(self) -> None:
        orch = RSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {}, date_from="2016-05-01"
        )
        html = _by_type(orch._providers, SansadRsHtmlProvider)
        ia = _by_type(orch._providers, InternetArchiveProvider)
        rsdebate = _by_type(orch._providers, RsdebateDspaceProvider)
        # SansadRsHtmlProvider parses the ISO string to a date internally.
        assert html._date_from == date(2016, 5, 1)
        assert ia._date_from == "2016-05-01"
        assert rsdebate._date_from == "2016-05-01"

    def test_no_date_from_keeps_provider_defaults(self) -> None:
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        html = _by_type(orch._providers, SansadRsHtmlProvider)
        ia = _by_type(orch._providers, InternetArchiveProvider)
        rsdebate = _by_type(orch._providers, RsdebateDspaceProvider)
        assert html._date_from == date(2014, 1, 1)
        assert ia._date_from == "2014-01-01"
        assert rsdebate._date_from == "2014-01-01"

    def test_rs_default_chain_order(self) -> None:
        # PRD v1.3 / Phase 9: exact order [SansadRsHtml, IA(RS), RsdebateDspace].
        orch = RSOrchestrator(MagicMock(), MagicMock(), MagicMock(), {})
        assert [type(p).__name__ for p in orch._providers] == [
            "SansadRsHtmlProvider",
            "InternetArchiveProvider",
            "RsdebateDspaceProvider",
        ]
        ia = _by_type(orch._providers, InternetArchiveProvider)
        assert ia._corpus == "RS"

    def test_injected_providers_used_as_is(self) -> None:
        sentinel = [MagicMock(), MagicMock()]
        orch = RSOrchestrator(
            MagicMock(), MagicMock(), MagicMock(), {},
            providers=sentinel, date_from="2016-05-01",
        )
        assert orch._providers is sentinel
