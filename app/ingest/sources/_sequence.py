"""
sequence_within_sitting numbering shared by the corpus orchestrators.

Records are numbered in processing order within a sitting. The first time a run
meets a sitting it asks the indexer where the stored records for that sitting
end and continues from there, so a resumed run or a run split by date range
never gives two records the same position (and, since the position is part of
a speech's dedup key, never silently drops a new speech as a "duplicate").
"""
from __future__ import annotations

from typing import Any


class SittingSequencer:
    def __init__(self, indexer: Any, source: str) -> None:
        self._indexer = indexer
        self._source = source
        self._next: dict[tuple, int] = {}

    def next(self, record: dict) -> int:
        """Next position for *record*'s sitting (its date and sitting_number)."""
        key = (record.get("date"), record.get("sitting_number"))
        if key not in self._next:
            self._next[key] = self._indexer.next_sequence(self._source, *key)
        n = self._next[key]
        self._next[key] = n + 1
        return n
