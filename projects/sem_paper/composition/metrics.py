"""Frozen SEM metric registry and provenance contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricDirection(StrEnum):
    HIGHER = "higher_is_better"
    LOWER = "lower_is_better"
    DESCRIPTIVE = "descriptive"


@dataclass(frozen=True, slots=True)
class SemPaperMetricDefinition:
    name: str
    estimand: str
    unit: str
    direction: MetricDirection
    source_plane: str
    required_for_claim: bool

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.name, self.estimand, self.unit, self.source_plane)):
            raise ValueError("SEM metric identity and provenance are required")


SEM_PAPER_METRIC_REGISTRY: tuple[SemPaperMetricDefinition, ...] = (
    SemPaperMetricDefinition("success_rate", "mean task success", "probability", MetricDirection.HIGHER, "workload", False),
    SemPaperMetricDefinition("utility_mean", "mean task utility", "utility", MetricDirection.HIGHER, "workload", False),
    SemPaperMetricDefinition("steps_total", "total environment steps", "steps", MetricDirection.LOWER, "workload", False),
    SemPaperMetricDefinition("duration_s_total", "total wall duration", "seconds", MetricDirection.LOWER, "workload", False),
    SemPaperMetricDefinition("memory_queries_total", "total memory queries", "queries", MetricDirection.LOWER, "method", False),
    SemPaperMetricDefinition("task_failed_total", "failed task count", "tasks", MetricDirection.LOWER, "workload", False),
    SemPaperMetricDefinition("task_blocked_total", "dependency-blocked task count", "tasks", MetricDirection.LOWER, "workload", False),
    SemPaperMetricDefinition("LTE_SR", "mean matched lifetime Self-vs-Fixed effect across pre-registered environment units", "utility", MetricDirection.HIGHER, "scientific.lifetime", True),
    SemPaperMetricDefinition("LPI", "probability that matched lifetime SelfEvolve utility exceeds FixedSeed", "probability", MetricDirection.HIGHER, "scientific.lifetime", True),
    SemPaperMetricDefinition("CLU", "cumulative lifetime utility", "utility", MetricDirection.HIGHER, "scientific.lifetime", True),
    SemPaperMetricDefinition("TDP", "trajectory divergence profile", "distance", MetricDirection.DESCRIPTIVE, "scientific.trajectory", True),
    SemPaperMetricDefinition("ELCE", "held-out edit-local causal effect", "utility", MetricDirection.HIGHER, "scientific.held_out", True),
    SemPaperMetricDefinition("HPEF", "held-out positive edit fraction", "probability", MetricDirection.HIGHER, "scientific.held_out", True),
    SemPaperMetricDefinition("GAG", "gate-to-audit generalization gap", "utility_gap", MetricDirection.DESCRIPTIVE, "scientific.held_out", True),
)

SEM_PAPER_METRIC_NAMES = tuple(item.name for item in SEM_PAPER_METRIC_REGISTRY if item.source_plane in {"workload", "method"})
SEM_PAPER_SCIENTIFIC_METRIC_NAMES = tuple(item.name for item in SEM_PAPER_METRIC_REGISTRY if item.required_for_claim)


def validate_sem_paper_metric_registry() -> None:
    names = tuple(item.name for item in SEM_PAPER_METRIC_REGISTRY)
    if len(names) != len(set(names)):
        raise ValueError("SEM metric registry contains duplicate names")
    required = {"LTE_SR", "LPI", "CLU", "TDP", "ELCE", "HPEF", "GAG"}
    if set(SEM_PAPER_SCIENTIFIC_METRIC_NAMES) != required:
        raise ValueError("SEM scientific metric registry is incomplete")


validate_sem_paper_metric_registry()


__all__ = [
    "MetricDirection",
    "SEM_PAPER_METRIC_NAMES",
    "SEM_PAPER_METRIC_REGISTRY",
    "SEM_PAPER_SCIENTIFIC_METRIC_NAMES",
    "SemPaperMetricDefinition",
    "validate_sem_paper_metric_registry",
]
