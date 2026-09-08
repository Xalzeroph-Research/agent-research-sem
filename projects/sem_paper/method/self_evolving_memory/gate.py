from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .semantics import validate_transform


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
    """Deterministic validation independent of task utility or audit labels."""

    def evaluate(
        self,
        *,
        base_graph_digest: str,
        current_graph_digest: str,
        edits: Iterable[Any],
        evidence_ids: Iterable[str],
        known_evidence_ids: set[str],
        graph_snapshot: Any | None = None,
    ) -> ProposalBlindGateDecision:
        edits = tuple(edits)
        evidence_ids = tuple(evidence_ids)
        checks = (
            "base_snapshot_binding",
            "syntax_validation",
            "bounded_operation_count",
            "allowed_operation_vocabulary",
            "field_and_type_validation",
            "transform_validation",
            "graph_and_acyclicity_validation",
            "source_compatibility_validation",
            "edit_semantics_validation",
            "complexity_validation",
            "canonical_no_op_detection",
            "evidence_provenance",
        )
        if base_graph_digest != current_graph_digest:
            return ProposalBlindGateDecision(False, "candidate base snapshot is stale", checks)
        if not edits:
            return ProposalBlindGateDecision(False, "candidate contains no structural edit", checks)
        if len(edits) > 8:
            return ProposalBlindGateDecision(False, "candidate exceeds bounded operation count", checks)
        if any(
            not isinstance(getattr(edit, "operation", None), str)
            or not isinstance(getattr(edit, "target_id", None), str)
            or not getattr(edit, "target_id", "").strip()
            for edit in edits
        ):
            return ProposalBlindGateDecision(False, "candidate failed syntax validation", checks)
        if any(getattr(edit, "operation", "") not in _ALLOWED_OPERATIONS for edit in edits):
            return ProposalBlindGateDecision(False, "candidate contains an unsupported edit operation", checks)
        if any(
            not isinstance(evidence_id, str) or evidence_id not in known_evidence_ids
            for evidence_id in evidence_ids
        ):
            return ProposalBlindGateDecision(
                False, "candidate references evidence outside the method journal", checks
            )

        snapshot_nodes = {
            node.node_id: node
            for node in getattr(graph_snapshot, "nodes", ())
        }
        created_ids = {
            edit.target_id for edit in edits if edit.operation == "create"
        }
        for edit in edits:
            payload = getattr(edit, "payload", {})
            if not isinstance(payload, Mapping):
                return ProposalBlindGateDecision(False, "edit payload must be a mapping", checks)
            if edit.operation == "create":
                required = {
                    "kind", "label", "content", "purpose", "scope", "mode",
                    "schema", "access", "sources", "transform",
                    "maintenance_contract",
                }
                if not required.issubset(payload):
                    return ProposalBlindGateDecision(False, "created node lacks typed fields", checks)
                if edit.target_id in snapshot_nodes:
                    return ProposalBlindGateDecision(False, "candidate is a canonical no-op", checks)
                if not all(isinstance(payload.get(key), str) for key in (
                    "kind", "label", "content", "purpose", "scope", "mode",
                )):
                    return ProposalBlindGateDecision(False, "created node has invalid field types", checks)
                if not isinstance(payload["schema"], Mapping):
                    return ProposalBlindGateDecision(False, "node schema must be a mapping", checks)
                if not isinstance(payload["access"], (tuple, list)):
                    return ProposalBlindGateDecision(False, "node access must be a sequence", checks)
                if not isinstance(payload["sources"], (tuple, list)):
                    return ProposalBlindGateDecision(False, "node sources must be a sequence", checks)
                valid, reason = validate_transform(payload["transform"])
                if not valid:
                    return ProposalBlindGateDecision(False, reason, checks)
            elif edit.operation == "create_edge":
                source_id = str(payload.get("source_id", ""))
                target_id = str(payload.get("target_id", ""))
                relation = str(payload.get("relation", ""))
                if not source_id or not target_id or not relation:
                    return ProposalBlindGateDecision(False, "edge lacks typed endpoints", checks)
                if source_id == target_id:
                    return ProposalBlindGateDecision(False, "self-edge violates acyclicity", checks)
                if source_id not in snapshot_nodes and source_id not in created_ids:
                    return ProposalBlindGateDecision(False, "edge source is not available", checks)
                if target_id not in snapshot_nodes and target_id not in created_ids:
                    return ProposalBlindGateDecision(False, "edge target is not available", checks)
            elif edit.operation == "update_node":
                if edit.target_id not in snapshot_nodes:
                    return ProposalBlindGateDecision(False, "updated node does not exist", checks)
                if not payload:
                    return ProposalBlindGateDecision(False, "empty node update is a no-op", checks)
            elif edit.operation == "retire_node":
                node = snapshot_nodes.get(edit.target_id)
                if node is None or not node.active:
                    return ProposalBlindGateDecision(False, "retiring node is a canonical no-op", checks)
            elif edit.operation == "retire_edge":
                if not payload.get("source_id") or not payload.get("target_id"):
                    return ProposalBlindGateDecision(False, "retired edge lacks provenance", checks)

        if any(
            isinstance(getattr(edit, "payload", None), Mapping)
            and any(str(key).lower() in {"python", "callable", "module", "code"} for key in edit.payload)
            for edit in edits
        ):
            return ProposalBlindGateDecision(False, "candidate contains executable transform fields", checks)
        return ProposalBlindGateDecision(True, "proposal-blind checks passed", checks)


__all__ = ["ProposalBlindGate", "ProposalBlindGateDecision"]
