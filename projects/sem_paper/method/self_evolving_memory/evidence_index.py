from __future__ import annotations

"""Architecture-independent indexing over the canonical ``J_mem`` journal.

The index is an acceleration/read model only.  It accepts the current project's
typed :class:`EvidenceRecord`, never the private audit record type, and can be
rebuilt from any pinned evidence snapshot.  Architecture-specific selection is
performed from the current ``MemoryArchitectureSpec`` rather than stored in
the index.
"""

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .architecture import EvidenceSourceChannel, MemoryArchitectureSpec, SourceKind
from .evidence_api import EvidenceRecord


@dataclass(slots=True)
class EvidenceIndex:
    """Rebuildable event-type/sequence index for grounded ``J_mem`` evidence."""

    by_event_type: dict[str, list[EvidenceRecord]] = field(default_factory=dict)
    ordered_memory: list[EvidenceRecord] = field(default_factory=list)

    @staticmethod
    def _event_type(row: EvidenceRecord) -> str:
        payload = row.payload
        if isinstance(payload, dict):
            value = payload.get("event_type", payload.get("type", ""))
            return str(value)
        return ""

    def add(self, row: EvidenceRecord) -> None:
        if not isinstance(row, EvidenceRecord):
            raise TypeError("EvidenceIndex accepts only canonical J_mem EvidenceRecord values")
        self.ordered_memory.append(row)
        event_type = self._event_type(row)
        self.by_event_type.setdefault(event_type, []).append(row)

    def rebuild(self, rows: Iterable[EvidenceRecord]) -> None:
        self.by_event_type.clear()
        self.ordered_memory.clear()
        for row in rows:
            self.add(row)

    def query_event_types(self, event_types: Sequence[str]) -> tuple[EvidenceRecord, ...]:
        if not event_types:
            return tuple(self.ordered_memory)
        wanted = frozenset(str(value) for value in event_types)
        return tuple(row for row in self.ordered_memory if self._event_type(row) in wanted)

    def select_for_architecture(self, architecture: MemoryArchitectureSpec) -> tuple[EvidenceRecord, ...]:
        required: set[str] = set()
        requires_all = False
        for node in architecture.nodes:
            for source in node.sources:
                if source.kind is not SourceKind.EVIDENCE:
                    continue
                if source.evidence_channel is not EvidenceSourceChannel.MEMORY:
                    continue
                if not source.event_types:
                    requires_all = True
                required.update(source.event_types)
        if requires_all or not required:
            return tuple(self.ordered_memory)
        return self.query_event_types(tuple(sorted(required)))

    def stats(self) -> dict[str, object]:
        return {
            "memory_events": len(self.ordered_memory),
            "event_types": {
                key: len(rows) for key, rows in sorted(self.by_event_type.items())
            },
        }


__all__ = ["EvidenceIndex"]
