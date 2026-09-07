from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


_ALLOWED_OPERATIONS = frozenset({
    "create",
    "create_edge",
    "update_node",
    "retire_node",
    "retire_edge",
})


@dataclass(frozen=True, slots=True)
class ProposalBlindGateDecision:
    accepted: bool
    reason: str
    checks: tuple[str, ...]


class ProposalBlindGate:
    """Deterministic runtime gate that is independent of task utility.

    Utility, success, transfer, and recovery are evaluated by the disjoint
    scientific audit.  Runtime adoption only checks proposal-blind structural
    and provenance invariants.
    """

    def evaluate(
        self,
        *,
        base_graph_digest: str,
        current_graph_digest: str,
        edits: Iterable[Any],
        evidence_ids: Iterable[str],
        known_evidence_ids: set[str],
    ) -> ProposalBlindGateDecision:
        edits = tuple(edits)
        evidence_ids = tuple(evidence_ids)
        checks = (
            "base_snapshot_binding",
            "bounded_operation_count",
            "allowed_operation_vocabulary",
            "evidence_provenance",
            "non_empty_edit",
        )
        if base_graph_digest != current_graph_digest:
            return ProposalBlindGateDecision(
                False, "candidate base snapshot is stale", checks
            )
        if not edits:
            return ProposalBlindGateDecision(
                False, "candidate contains no structural edit", checks
            )
        if len(edits) > 8:
            return ProposalBlindGateDecision(
                False, "candidate exceeds bounded operation count", checks
            )
        if any(getattr(edit, "operation", "") not in _ALLOWED_OPERATIONS for edit in edits):
            return ProposalBlindGateDecision(
                False, "candidate contains an unsupported edit operation", checks
            )
        if any(
            not isinstance(evidence_id, str) or evidence_id not in known_evidence_ids
            for evidence_id in evidence_ids
        ):
            return ProposalBlindGateDecision(
                False, "candidate references evidence outside the method journal", checks
            )
        return ProposalBlindGateDecision(True, "proposal-blind checks passed", checks)


__all__ = ["ProposalBlindGate", "ProposalBlindGateDecision"]
