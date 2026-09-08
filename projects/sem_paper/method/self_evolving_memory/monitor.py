from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from noetrium.contracts import canonical_digest


_BANNED_OBSERVATION_KEYS = frozenset({
    "recommended_edit",
    "target_node",
    "expected_architecture",
    "human_ontology_label",
    "hidden_task_family",
})


@dataclass(frozen=True, slots=True)
class MemoryOpportunity:
    """Architecture-neutral HistoricalDemand AND EligiblePriorEvidence."""

    opportunity_id: str
    signal: str
    support_count: int
    exposure_count: int
    evidence_ids: tuple[str, ...]
    query_count: int
    hit_count: int
    digest: str

    @property
    def eligible(self) -> bool:
        return self.support_count > 0 and bool(self.evidence_ids)

    @property
    def eligible_prior_evidence(self) -> tuple[str, ...]:
        return self.evidence_ids if self.eligible else ()


@dataclass(frozen=True, slots=True)
class NeutralArchitectureObservation:
    """The only observation shape exposed to a proposal authority."""

    schema_field_profiles: Mapping[str, Any]
    memory_usage_statistics: Mapping[str, Any]
    query_outcomes: Mapping[str, Any]
    incident_exemplars: tuple[Mapping[str, Any], ...]
    unresolved_intent_clusters: Mapping[str, Any]
    pairwise_node_statistics: Mapping[str, Any]
    architecture_exposure: Mapping[str, Any]
    evolution_ledger_summary: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        value = {
            "schema_field_profiles": dict(self.schema_field_profiles),
            "memory_usage_statistics": dict(self.memory_usage_statistics),
            "query_outcomes": dict(self.query_outcomes),
            "incident_exemplars": [dict(item) for item in self.incident_exemplars],
            "unresolved_intent_clusters": dict(self.unresolved_intent_clusters),
            "pairwise_node_statistics": dict(self.pairwise_node_statistics),
            "architecture_exposure": dict(self.architecture_exposure),
            "evolution_ledger_summary": dict(self.evolution_ledger_summary),
        }
        if _BANNED_OBSERVATION_KEYS & {str(key) for key in value}:
            raise ValueError("neutral observation contains an architecture recommendation")
        return value

    def digest(self) -> str:
        return canonical_digest(self.as_dict())


class ArchitectureIndependentMonitor:
    """Collect structural symptoms without selecting an edit or node."""

    def __init__(self) -> None:
        self._support: dict[str, int] = {}
        self._exposures: dict[str, int] = {}
        self._signals: dict[str, str] = {}
        self._evidence: dict[str, list[str]] = {}
        self._queries = 0
        self._hits = 0

    def observe_failure(
        self, *, signal: str, evidence_ids: tuple[str, ...]
    ) -> MemoryOpportunity:
        normalized = signal.strip().lower() or "unresolved_outcome"
        key = canonical_digest({"signal": normalized})[:24]
        self._support[key] = self._support.get(key, 0) + 1
        self._exposures[key] = self._exposures.get(key, 0) + 1
        self._signals[key] = normalized
        bucket = self._evidence.setdefault(key, [])
        for evidence_id in evidence_ids:
            if evidence_id not in bucket:
                bucket.append(evidence_id)
        return self._opportunity(key)

    def record_query(self, *, hit: bool) -> None:
        self._queries += 1
        if hit:
            self._hits += 1

    def neutral_observation(
        self,
        *,
        schema_field_profiles: Mapping[str, Any] = (),
        incident_exemplars: tuple[Mapping[str, Any], ...] = (),
        pairwise_node_statistics: Mapping[str, Any] = (),
        architecture_exposure: Mapping[str, Any] = (),
        evolution_ledger_summary: Mapping[str, Any] = (),
    ) -> NeutralArchitectureObservation:
        return NeutralArchitectureObservation(
            schema_field_profiles,
            {
                "opportunity_count": len(self._support),
                "failure_support_total": sum(self._support.values()),
            },
            {"query_count": self._queries, "hit_count": self._hits},
            incident_exemplars,
            {
                key: value
                for key, value in self._signals.items()
            },
            pairwise_node_statistics,
            architecture_exposure,
            evolution_ledger_summary,
        )

    def _opportunity(self, key: str) -> MemoryOpportunity:
        evidence_ids = tuple(self._evidence.get(key, ()))
        signal = self._signals.get(key, "unknown")
        return MemoryOpportunity(
            f"opportunity:{key}", signal, self._support.get(key, 0),
            self._exposures.get(key, 0), evidence_ids, self._queries,
            self._hits, canonical_digest({
                "key": key, "signal": signal,
                "support_count": self._support.get(key, 0),
                "exposure_count": self._exposures.get(key, 0),
                "evidence_ids": evidence_ids,
            }),
        )

    def opportunities(self) -> tuple[MemoryOpportunity, ...]:
        return tuple(self._opportunity(key) for key in sorted(self._support))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "opportunity_count": len(self._support),
            "monitor_query_count": self._queries,
            "monitor_hit_count": self._hits,
            "eligible_prior_evidence_count": sum(
                len(item.eligible_prior_evidence) for item in self.opportunities()
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "support": dict(self._support),
            "exposures": dict(self._exposures),
            "signals": dict(self._signals),
            "evidence": {key: list(value) for key, value in self._evidence.items()},
            "queries": self._queries,
            "hits": self._hits,
        }

    def restore(self, payload: dict[str, Any]) -> None:
        self._support = {str(k): int(v) for k, v in payload.get("support", {}).items()}
        self._exposures = {str(k): int(v) for k, v in payload.get("exposures", {}).items()}
        self._signals = {str(k): str(v) for k, v in payload.get("signals", {}).items()}
        self._evidence = {
            str(k): [str(item) for item in v]
            for k, v in payload.get("evidence", {}).items()
        }
        self._queries = int(payload.get("queries", 0))
        self._hits = int(payload.get("hits", 0))


__all__ = [
    "ArchitectureIndependentMonitor",
    "MemoryOpportunity",
    "NeutralArchitectureObservation",
]
