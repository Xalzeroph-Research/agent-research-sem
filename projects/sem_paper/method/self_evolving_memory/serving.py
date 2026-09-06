from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from typing import Iterator, Protocol
from research_platform.platform.kernel import JsonObject, JsonValue

from .json_snapshot import freeze_json_mapping


@dataclass(frozen=True, slots=True)
class MemoryNodeDocument:
    node_id: str
    sequence: int
    digest: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("memory node document node_id must be a non-empty string")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("memory node document sequence must be a positive integer")
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(char not in "0123456789abcdef" for char in self.digest)
        ):
            raise ValueError("memory node document digest must be a lower-case SHA-256 digest")
        if not isinstance(self.text, str):
            raise ValueError("memory node document text must be a string")


class MemoryReadSnapshot(Protocol):
    """Pinned raw memory read surface; retrieval algorithms own their derived indexes."""

    @property
    def generation(self) -> str: ...
    @property
    def node_count(self) -> int: ...
    def latest_node_id(self) -> str | None: ...
    def contains(self, node_id: str) -> bool: ...
    def node_ids(self) -> tuple[str, ...]: ...
    def node_sequence(self, node_id: str) -> int | None: ...
    def prefix_digest(self, count: int) -> str: ...
    def iter_node_documents(self, start_position: int = 0) -> Iterator[MemoryNodeDocument]: ...
    def resolve(self, node_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...]: ...


class MemorySnapshotProvider(Protocol):
    def open_snapshot(self) -> MemoryReadSnapshot: ...


class QueryPlanner(Protocol):
    def plan(self, intent: str, snapshot: MemoryReadSnapshot, *, limit: int) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class ServingResult:
    generation: str
    context_text: str
    selected_nodes: tuple[str, ...]
    diagnostic_records: tuple["MemoryServingRecord", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.generation, str) or not self.generation.strip():
            raise ValueError("serving result generation must be a non-empty string")
        if not isinstance(self.context_text, str):
            raise ValueError("serving result context_text must be a string")
        if not isinstance(self.selected_nodes, tuple) or any(
            not isinstance(node_id, str) or not node_id.strip() for node_id in self.selected_nodes
        ):
            raise ValueError("serving result selected_nodes must be non-empty strings")
        if len(self.selected_nodes) != len(set(self.selected_nodes)):
            raise ValueError("serving result selected_nodes must be unique")
        if not isinstance(self.diagnostic_records, tuple) or any(
            not isinstance(record, MemoryServingRecord) for record in self.diagnostic_records
        ):
            raise ValueError("serving result diagnostic_records must be typed")
        selected = set(self.selected_nodes)
        if any(record.node_id not in selected for record in self.diagnostic_records):
            raise ValueError("serving diagnostics must refer to selected nodes")


@dataclass(frozen=True, slots=True)
class ServingRuntimeState:
    """Provider-owned serving state embedded in the method checkpoint."""

    state_kind: str
    schema_version: str
    payload: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.state_kind, str) or not self.state_kind.strip():
            raise ValueError("serving runtime state state_kind must be a non-empty string")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("serving runtime state schema_version must be a non-empty string")
        if not isinstance(self.payload, Mapping):
            raise ValueError("serving runtime state payload must be a mapping")
        object.__setattr__(
            self,
            "payload",
            freeze_json_mapping(self.payload, label="serving runtime state payload"),
        )


@dataclass(frozen=True, slots=True)
class MemoryServingRecord:
    """Provider-neutral facts needed by the session diagnostic adapter.

    This value is deliberately owned by serving rather than evolution. A
    serving provider reports what it returned; the evolution diagnostic plane
    decides how (or whether) to interpret those facts.
    """

    node_id: str
    record_id: str
    score: float
    payload: Mapping[str, JsonValue] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("serving diagnostic node_id must be a non-empty string")
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("serving diagnostic record_id must be a non-empty string")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("serving diagnostic record score must be numeric")
        try:
            score = float(self.score)
        except OverflowError as exc:
            raise ValueError("serving diagnostic record score must be finite") from exc
        if not math.isfinite(score):
            raise ValueError("serving diagnostic record score must be finite")
        object.__setattr__(self, "score", score)
        if not isinstance(self.payload, Mapping):
            raise ValueError("serving diagnostic record payload must be a mapping")
        object.__setattr__(
            self,
            "payload",
            freeze_json_mapping(self.payload, label="serving diagnostic record payload"),
        )
        if not isinstance(self.source_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.source_refs
        ):
            raise ValueError("serving diagnostic source refs must be a tuple of non-empty strings")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("serving diagnostic source refs must be unique")


class MemoryServingService:
    """Plan against a pinned snapshot, materialize only the records actually selected."""

    def __init__(self, snapshots: MemorySnapshotProvider, planner: QueryPlanner) -> None:
        self.snapshots = snapshots
        self.planner = planner

    STATE_KIND = "sem.memory_serving.stateless"
    STATE_SCHEMA_VERSION = "1"

    def snapshot_state(self) -> ServingRuntimeState:
        return ServingRuntimeState(self.STATE_KIND, self.STATE_SCHEMA_VERSION, {})

    def validate_state(self, snapshot: ServingRuntimeState) -> None:
        if snapshot.state_kind != self.STATE_KIND or snapshot.schema_version != self.STATE_SCHEMA_VERSION:
            raise ValueError("memory serving checkpoint identity mismatch")
        if snapshot.payload:
            raise ValueError("stateless memory serving checkpoint payload must be empty")

    def restore_state(self, snapshot: ServingRuntimeState) -> None:
        self.validate_state(snapshot)

    def recall(self, intent: str, *, limit: int) -> ServingResult:
        if limit <= 0:
            raise ValueError("memory recall limit must be positive")
        snapshot = self.snapshots.open_snapshot()
        nodes = self.planner.plan(intent, snapshot, limit=limit)
        if len(nodes) > limit:
            raise ValueError("query planner exceeded recall limit")
        if len(nodes) != len(set(nodes)):
            raise ValueError("query planner selected duplicate nodes")
        if any(not snapshot.contains(node_id) for node_id in nodes):
            raise ValueError("query planner selected node outside pinned generation")
        records = snapshot.resolve(nodes)
        record_map = dict(records)
        if any(node_id not in record_map for node_id in nodes):
            raise ValueError("pinned memory snapshot failed to resolve selected node")
        text = "\n".join(record_map[node_id] for node_id in nodes)
        return ServingResult(
            snapshot.generation,
            text,
            nodes,
            tuple(
                MemoryServingRecord(
                    node_id=node_id,
                    record_id=node_id,
                    # The raw serving ABI exposes selection but no calibrated
                    # rank score. A resolved selected row is therefore a
                    # positive binary observation, not a fabricated rank.
                    score=1.0,
                    payload={"text": record_map[node_id]},
                    source_refs=(node_id,),
                )
                for node_id in nodes
            ),
        )


__all__ = [
    "MemoryNodeDocument",
    "MemoryReadSnapshot",
    "MemoryServingRecord",
    "MemoryServingService",
    "MemorySnapshotProvider",
    "QueryPlanner",
    "ServingResult",
    "ServingRuntimeState",
]
