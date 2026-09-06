from __future__ import annotations

"""Typed, read-only structural probes over a pinned architecture and telemetry cut."""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, ClassVar, Mapping, Sequence, TypeAlias

from ..architecture import MemoryArchitectureSpec
from ..json_snapshot import freeze_json_mapping
from .slicing import AutomaticSliceDiscovery
from .telemetry import IncidentKind, QueryRecordObservation, TelemetryBook


@dataclass(frozen=True, slots=True)
class ProfileProbeRequest:
    node_id: str
    kind: ClassVar[str] = "PROFILE"

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("profile probe node_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class IncidentExamplesProbeRequest:
    node_id: str | None = None
    incident_kind: IncidentKind | None = None
    kind: ClassVar[str] = "GET_INCIDENT_EXAMPLES"

    def __post_init__(self) -> None:
        if self.node_id is not None and (not isinstance(self.node_id, str) or not self.node_id.strip()):
            raise ValueError("incident examples node_id cannot be empty or non-string")
        if self.incident_kind is not None and not isinstance(self.incident_kind, IncidentKind):
            raise ValueError("incident examples incident_kind must be typed when present")


@dataclass(frozen=True, slots=True)
class PairStatsProbeRequest:
    node_a: str
    node_b: str
    kind: ClassVar[str] = "GET_PAIR_STATS"

    def __post_init__(self) -> None:
        if any(not isinstance(node_id, str) or not node_id.strip() for node_id in (self.node_a, self.node_b)):
            raise ValueError("pair-stats probe node ids must be non-empty strings")
        if self.node_a == self.node_b:
            raise ValueError("pair-stats probe requires distinct nodes")


@dataclass(frozen=True, slots=True)
class IntentClusterProbeRequest:
    cluster_id: str
    kind: ClassVar[str] = "GET_INTENT_CLUSTER"

    def __post_init__(self) -> None:
        if not isinstance(self.cluster_id, str) or not self.cluster_id.strip():
            raise ValueError("intent-cluster probe cluster_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class StructuralNodeProbeRequest:
    node_ids: tuple[str, ...]
    kind: ClassVar[str] = "REQUEST_STRUCTURAL_PROBE"

    def __post_init__(self) -> None:
        if not isinstance(self.node_ids, tuple) or not self.node_ids or len(self.node_ids) > 4:
            raise ValueError("structural node probe requires a tuple of one to four nodes")
        if any(not isinstance(node_id, str) or not node_id.strip() for node_id in self.node_ids):
            raise ValueError("structural node probe node ids must be non-empty strings")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("structural node probe node ids must be unique")


ProbeRequest: TypeAlias = (
    ProfileProbeRequest
    | IncidentExamplesProbeRequest
    | PairStatsProbeRequest
    | IntentClusterProbeRequest
    | StructuralNodeProbeRequest
)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    probe_id: str
    kind: str
    facts: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.probe_id, str) or not self.probe_id.strip():
            raise ValueError("probe result id must be a non-empty string")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("probe result kind must be a non-empty string")
        if not isinstance(self.facts, Mapping):
            raise TypeError("probe result facts must be a mapping")
        object.__setattr__(
            self,
            "facts",
            freeze_json_mapping(self.facts, label="probe result facts"),
        )


class StructuralProbeEngine:
    """Fixed, bounded, neutral facts over a pinned architecture/read cut."""

    def __init__(
        self,
        architecture: MemoryArchitectureSpec,
        store: Mapping[str, Sequence[QueryRecordObservation]],
        telemetry: TelemetryBook,
    ) -> None:
        self.architecture = architecture
        self.store = store
        self.telemetry = telemetry
        self.slicer = AutomaticSliceDiscovery()

    @staticmethod
    def _request_document(request: ProbeRequest) -> dict[str, object]:
        if isinstance(request, ProfileProbeRequest):
            return {"node_id": request.node_id}
        if isinstance(request, IncidentExamplesProbeRequest):
            return {
                "node_id": request.node_id,
                "incident_kind": request.incident_kind.value if request.incident_kind else None,
            }
        if isinstance(request, PairStatsProbeRequest):
            return {"node_a": request.node_a, "node_b": request.node_b}
        if isinstance(request, IntentClusterProbeRequest):
            return {"cluster_id": request.cluster_id}
        if isinstance(request, StructuralNodeProbeRequest):
            return {"node_ids": list(request.node_ids)}
        raise TypeError("unsupported structural probe request")

    def execute(self, request: ProbeRequest) -> ProbeResult:
        if not isinstance(
            request,
            (
                ProfileProbeRequest,
                IncidentExamplesProbeRequest,
                PairStatsProbeRequest,
                IntentClusterProbeRequest,
                StructuralNodeProbeRequest,
            ),
        ):
            raise TypeError("structural probe requires a typed request")
        facts = self._facts(request)
        raw = json.dumps(
            [request.kind, self._request_document(request), facts],
            sort_keys=True,
            default=repr,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return ProbeResult(
            probe_id="probe_" + hashlib.sha256(raw).hexdigest()[:12],
            kind=request.kind,
            facts=facts,
        )

    def _facts(self, request: ProbeRequest) -> Mapping[str, Any]:
        if isinstance(request, ProfileProbeRequest):
            node = self.architecture.node_map().get(request.node_id)
            if node is None:
                return {"error": "unknown_node"}
            stats = self.telemetry.node_stats.get(request.node_id)
            return {
                "node_id": request.node_id,
                "record_count": len(self.store.get(request.node_id, ())),
                "schema_fields": [field.name for field in node.schema],
                "access": sorted(access.value for access in node.access),
                "runtime_stats": stats.as_dict() if stats else {},
            }
        if isinstance(request, IncidentExamplesProbeRequest):
            items = [
                incident
                for incident in self.telemetry.incidents
                if (request.node_id is None or request.node_id in incident.node_ids)
                and (request.incident_kind is None or incident.kind is request.incident_kind)
            ]
            return {
                "examples": [
                    {
                        "incident_id": incident.incident_id,
                        "kind": incident.kind.value,
                        "intent": incident.intent,
                        "node_ids": list(incident.node_ids),
                    }
                    for incident in items[-8:]
                ]
            }
        if isinstance(request, PairStatsProbeRequest):
            both = selected_a = selected_b = 0
            for query in self.telemetry.queries:
                has_a = request.node_a in query.selected_nodes
                has_b = request.node_b in query.selected_nodes
                selected_a += int(has_a)
                selected_b += int(has_b)
                both += int(has_a and has_b)
            return {
                "node_a": request.node_a,
                "node_b": request.node_b,
                "co_selected": both,
                "selected_a": selected_a,
                "selected_b": selected_b,
                "jaccard": both / max(1, selected_a + selected_b - both),
            }
        if isinstance(request, IntentClusterProbeRequest):
            for neutral_slice in self.slicer.discover(self.telemetry.incidents):
                if neutral_slice.slice_id == request.cluster_id:
                    return asdict(neutral_slice)
            return {"error": "unknown_cluster"}
        if not isinstance(request, StructuralNodeProbeRequest):
            raise TypeError("unsupported structural probe request")

        facts: dict[str, Any] = {}
        for node_id in request.node_ids:
            rows = tuple(self.store.get(node_id, ()))
            sampled = rows[:200]
            field_values: dict[str, set[str]] = {}
            source_refs: set[str] = set()
            for row in sampled:
                source_refs.update(row.source_refs)
                for key, value in row.payload.items():
                    if isinstance(value, (str, int, float, bool)):
                        field_values.setdefault(str(key), set()).add(repr(value))
            facts[node_id] = {
                "record_count": len(rows),
                "sampled_record_count": len(sampled),
                "field_distinct_counts": {key: len(values) for key, values in field_values.items()},
                "source_ref_count": len(source_refs),
            }
        return {"nodes": facts}


__all__ = [
    "IncidentExamplesProbeRequest",
    "IntentClusterProbeRequest",
    "PairStatsProbeRequest",
    "ProbeRequest",
    "ProbeResult",
    "ProfileProbeRequest",
    "StructuralNodeProbeRequest",
    "StructuralProbeEngine",
]
