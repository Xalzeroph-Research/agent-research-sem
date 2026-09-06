from __future__ import annotations

"""Deluxe architecture-GC candidate generation.

GC is deliberately a proposal producer.  It never compiles, accepts, or
adopts an edit; the normal fixed evolution pipeline remains the only authority.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..architecture import MemoryArchitectureSpec, RetireNodeEdit
from ..deluxe.runtime.capabilities import CapabilityRegistry


@dataclass(frozen=True, slots=True)
class GCCandidate:
    node_id: str
    reason: str
    confidence: float


class ArchitectureGarbageCollector:
    def candidates(
        self,
        *,
        architecture: MemoryArchitectureSpec,
        registry: CapabilityRegistry,
        store: Mapping[str, Sequence[object]],
    ) -> tuple[GCCandidate, ...]:
        output: list[GCCandidate] = []
        for node_id in registry.retire_candidate_nodes():
            if node_id not in architecture.node_map():
                continue
            if architecture.downstream_ids(node_id):
                continue
            record_count = len(store.get(node_id, ()))
            output.append(
                GCCandidate(
                    node_id,
                    "capability_lifecycle_retire_candidate",
                    0.90 if record_count == 0 else 0.70,
                )
            )
        return tuple(sorted(output, key=lambda item: (-item.confidence, item.node_id)))

    def propose_retire(
        self,
        *,
        architecture: MemoryArchitectureSpec,
        registry: CapabilityRegistry,
        store: Mapping[str, Sequence[object]],
    ) -> RetireNodeEdit | None:
        candidates = self.candidates(architecture=architecture, registry=registry, store=store)
        return None if not candidates else RetireNodeEdit("RETIRE_NODE", candidates[0].node_id)


__all__ = ["ArchitectureGarbageCollector", "GCCandidate"]
