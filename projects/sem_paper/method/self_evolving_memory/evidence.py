from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class EvidenceChannelError(ValueError):
    """Raised when memory and audit evidence boundaries are violated."""


class EvidenceJournal:
    """Append-only boundary between J_mem and J_audit."""

    def __init__(self) -> None:
        self._memory: dict[str, Any] = {}
        self._audit: dict[str, Any] = {}

    @staticmethod
    def _event_id(event: Any) -> str:
        event_id = getattr(event, "evidence_id", None)
        if not isinstance(event_id, str) or not event_id:
            raise EvidenceChannelError("evidence event must expose a non-empty evidence_id")
        return event_id

    def append(self, event: Any, *, channel: str = "memory") -> str:
        event_id = self._event_id(event)
        if channel not in {"memory", "audit"}:
            raise EvidenceChannelError(f"unknown evidence channel: {channel}")
        target = self._memory if channel == "memory" else self._audit
        other = self._audit if channel == "memory" else self._memory
        if event_id in other:
            raise EvidenceChannelError(f"evidence event cannot cross channels: {event_id}")
        target.setdefault(event_id, event)
        return event_id

    @property
    def memory_events(self) -> tuple[Any, ...]:
        return tuple(self._memory.values())

    @property
    def audit_events(self) -> tuple[Any, ...]:
        return tuple(self._audit.values())

    def restore(self, *, memory_events: Iterable[Any] = (), audit_events: Iterable[Any] = ()) -> None:
        self._memory.clear()
        self._audit.clear()
        for event in memory_events:
            self.append(event, channel="memory")
        for event in audit_events:
            self.append(event, channel="audit")


__all__ = ["EvidenceChannelError", "EvidenceJournal"]
