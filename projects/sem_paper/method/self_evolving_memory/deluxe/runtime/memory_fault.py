from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Sequence

from ..api import CapabilityCard, MemoryFault, WorkingSet, WorkingSetEntry
from .capabilities import CapabilityRegistry


@dataclass(slots=True)
class MemoryFaultHandler:
    """One bounded recovery slot after a real hard working-set miss."""

    registry: CapabilityRegistry
    faults: list[MemoryFault] = field(default_factory=list)

    def recover_if_needed(
        self,
        *,
        intent: str,
        working_set: WorkingSet,
        ranked_capabilities: Sequence[tuple[float, CapabilityCard]],
        hard_limit: int,
    ) -> WorkingSet:
        if not intent.strip() or hard_limit <= 0:
            raise ValueError("Deluxe Memory Fault inputs are invalid")
        current = set(working_set.capability_ids)
        candidate = next(
            ((score, card) for score, card in ranked_capabilities if card.capability_id not in current),
            None,
        )
        if candidate is None or candidate[0] <= 0.0:
            return working_set
        score, card = candidate
        entries = list(working_set.entries)
        recovered = len(entries) < hard_limit or bool(entries)
        if recovered:
            entry = WorkingSetEntry(card.capability_id, card.provider_node_id, score, True)
            if len(entries) >= hard_limit:
                entries[-1] = entry
            else:
                entries.append(entry)
        fault_id = "mf_" + hashlib.sha256(
            f"{intent}|{card.capability_id}|{len(self.faults)}".encode("utf-8")
        ).hexdigest()[:12]
        self.faults.append(
            MemoryFault(
                fault_id,
                intent,
                card.capability_id,
                card.provider_node_id,
                "provider_excluded_by_hard_working_set",
                recovered,
            )
        )
        return WorkingSet(tuple(entries[:hard_limit]), hard_limit)

    def recovery_rate(self) -> float:
        return sum(1 for fault in self.faults if fault.recovered) / max(1, len(self.faults))


__all__ = ["MemoryFaultHandler"]
