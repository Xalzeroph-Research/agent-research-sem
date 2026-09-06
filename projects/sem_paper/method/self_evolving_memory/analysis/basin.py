from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from ..architecture import MemoryArchitectureSpec, architecture_digest


@dataclass(frozen=True, slots=True)
class BasinMember:
    run_id: str
    architecture_hash: str
    generation: int
    node_count: int
    semantic_signature: tuple[str, ...]


def semantic_signature(architecture: MemoryArchitectureSpec) -> tuple[str, ...]:
    return tuple(
        sorted(
            "|".join(
                (
                    node.scope.value,
                    node.mode.value,
                    node.purpose.strip().lower(),
                    ",".join(sorted(access.value for access in node.access)),
                )
            )
            for node in architecture.nodes
        )
    )


def analyze_architecture_basin(
    runs: Sequence[tuple[str, MemoryArchitectureSpec]],
) -> dict[str, Any]:
    members = tuple(
        BasinMember(
            run_id,
            architecture_digest(architecture),
            architecture.generation,
            len(architecture.nodes),
            semantic_signature(architecture),
        )
        for run_id, architecture in runs
    )
    exact = Counter(member.architecture_hash for member in members)
    semantic = Counter(member.semantic_signature for member in members)
    denominator = max(1, len(members))
    return {
        "n_runs": len(members),
        "members": [asdict(member) for member in members],
        "exact_architecture_basin_count": len(exact),
        "semantic_organization_basin_count": len(semantic),
        "largest_exact_basin_share": max(exact.values(), default=0) / denominator,
        "largest_semantic_basin_share": max(semantic.values(), default=0) / denominator,
        # Architecture snapshots alone cannot establish functional
        # equivalence.  That claim requires the offline FOS computed from
        # held-out neutral demand probes; keeping this false prevents a
        # generation-only or structural comparison from leaking into runtime
        # conclusions.
        "functional_equifinality_possible": False,
        "functional_equifinality_evidence": "requires_offline_fos",
    }


__all__ = ["BasinMember", "analyze_architecture_basin", "semantic_signature"]
