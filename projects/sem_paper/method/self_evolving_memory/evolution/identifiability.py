from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from ..architecture import MemoryArchitectureSpec, architecture_digest
from research_platform.platform.kernel import JsonValue


class IdentifiabilityRecord(Protocol):
    """Minimal current-project record view required by the diagnostic engine."""

    payload: Mapping[str, JsonValue]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitectureFingerprint:
    canonical_hash: str
    semantic_signature: str
    topology_signature: str
    behavior_signature: str
    provenance_signature: str
    node_count: int
    edge_count: int


@dataclass(frozen=True, slots=True)
class EquivalenceReport:
    exact: bool
    semantic_card_overlap: float
    topology_overlap: float
    behavior_overlap: float
    provenance_overlap: float
    equivalence_level: str
    likely_functionally_equivalent: bool


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _signature(values: set[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _semantic_cards(architecture: MemoryArchitectureSpec) -> set[str]:
    return {
        "|".join(
            (
                node.scope.value,
                node.mode.value,
                " ".join(node.purpose.lower().split()),
                ",".join(sorted(access.value for access in node.access)),
            )
        )
        for node in architecture.nodes
    }


def _topology_facts(architecture: MemoryArchitectureSpec) -> set[str]:
    node_map = architecture.node_map()
    facts: set[str] = set()
    for node in architecture.nodes:
        own = (
            f"{node.scope.value}:{node.mode.value}:{len(node.schema)}:"
            f"{len(node.sources)}:{node.transform.semantic_operator_count}"
        )
        facts.add(f"NODE:{own}")
        for source in node.sources:
            if source.kind.value == "EVIDENCE":
                facts.add(
                    f"EDGE:EVIDENCE->{own}:{source.evidence_channel.value}:"
                    f"{','.join(sorted(source.event_types))}"
                )
                continue
            parent = node_map.get(source.node_id or "")
            if parent is None:
                facts.add(f"EDGE:UNKNOWN->{own}")
                continue
            parent_shape = (
                f"{parent.scope.value}:{parent.mode.value}:{len(parent.schema)}:"
                f"{len(parent.sources)}:{parent.transform.semantic_operator_count}"
            )
            facts.add(f"EDGE:{parent_shape}->{own}")
    return facts


def _behavior_facts(
    architecture: MemoryArchitectureSpec,
    store: Mapping[str, Sequence[IdentifiabilityRecord]] | None,
) -> set[str]:
    if store is None:
        return set()
    facts: set[str] = set()
    for node in architecture.nodes:
        rows = tuple(store.get(node.node_id, ()))
        key_shapes = {"|".join(sorted(row.payload)) for row in rows}
        count_bucket = "0" if not rows else "1-4" if len(rows) <= 4 else "5-16" if len(rows) <= 16 else "17+"
        parent_bucket = {
            len(row.source_refs) if len(row.source_refs) <= 3 else 4
            for row in rows
        }
        facts.add(
            f"{node.node_id}|count={count_bucket}|shapes={';'.join(sorted(key_shapes))}"
            f"|parents={','.join(str(value) for value in sorted(parent_bucket))}"
        )
    return facts


def _provenance_facts(
    store: Mapping[str, Sequence[IdentifiabilityRecord]] | None,
) -> set[str]:
    if store is None:
        return set()
    facts: set[str] = set()
    for rows in store.values():
        for row in rows:
            facts.add(
                f"parents={len(row.source_refs)}|keys={','.join(sorted(row.payload))}"
            )
    return facts


class ArchitectureIdentifiabilityEngine:
    """E0-E3 structural/behavioral equivalence diagnosis over current contracts.

    This is read-only diagnostic evidence. It does not choose an architecture,
    accept a candidate, write memory, or act as an experiment verifier.
    Provenance is compared structurally here; J_mem/J_audit admissibility is
    owned by the separate project grounding audit.
    """

    def fingerprint(
        self,
        architecture: MemoryArchitectureSpec,
        *,
        store: Mapping[str, Sequence[IdentifiabilityRecord]] | None = None,
    ) -> ArchitectureFingerprint:
        semantic = _semantic_cards(architecture)
        topology = _topology_facts(architecture)
        behavior = _behavior_facts(architecture, store)
        provenance = _provenance_facts(store)
        return ArchitectureFingerprint(
            canonical_hash=architecture_digest(architecture),
            semantic_signature=_signature(semantic),
            topology_signature=_signature(topology),
            behavior_signature=_signature(behavior),
            provenance_signature=_signature(provenance),
            node_count=len(architecture.nodes),
            edge_count=sum(len(node.sources) for node in architecture.nodes),
        )

    def compare(
        self,
        left: MemoryArchitectureSpec,
        right: MemoryArchitectureSpec,
        *,
        store_left: Mapping[str, Sequence[IdentifiabilityRecord]] | None = None,
        store_right: Mapping[str, Sequence[IdentifiabilityRecord]] | None = None,
    ) -> EquivalenceReport:
        left_fingerprint = self.fingerprint(left, store=store_left)
        right_fingerprint = self.fingerprint(right, store=store_right)
        semantic = _jaccard(_semantic_cards(left), _semantic_cards(right))
        topology = _jaccard(_topology_facts(left), _topology_facts(right))
        left_behavior = _behavior_facts(left, store_left)
        right_behavior = _behavior_facts(right, store_right)
        behavior = _jaccard(left_behavior, right_behavior) if left_behavior or right_behavior else 0.0
        left_provenance = _provenance_facts(store_left)
        right_provenance = _provenance_facts(store_right)
        provenance = (
            _jaccard(left_provenance, right_provenance)
            if left_provenance or right_provenance
            else 0.0
        )
        exact = left_fingerprint.canonical_hash == right_fingerprint.canonical_hash
        if exact:
            level = "E0_EXACT"
        elif semantic >= 0.90 and topology >= 0.85 and behavior >= 0.85 and provenance >= 0.80:
            level = "E3_PROVENANCE_FUNCTIONAL"
        elif semantic >= 0.90 and topology >= 0.80 and behavior >= 0.80:
            level = "E2_BEHAVIORAL"
        elif semantic >= 0.80:
            level = "E1_SEMANTIC"
        else:
            level = "DISTINCT"
        return EquivalenceReport(
            exact=exact,
            semantic_card_overlap=semantic,
            topology_overlap=topology,
            behavior_overlap=behavior,
            provenance_overlap=provenance,
            equivalence_level=level,
            likely_functionally_equivalent=level
            in {"E0_EXACT", "E2_BEHAVIORAL", "E3_PROVENANCE_FUNCTIONAL"},
        )


__all__ = [
    "ArchitectureFingerprint",
    "ArchitectureIdentifiabilityEngine",
    "EquivalenceReport",
    "IdentifiabilityRecord",
]
