from __future__ import annotations

"""Typed scientific report contracts with no evidence I/O authority."""

from dataclasses import dataclass

from research_platform.platform.kernel import canonical_digest


class ScientificMetricComputationError(ValueError):
    """Scientific evidence cannot be interpreted under the frozen estimand contract."""


@dataclass(frozen=True, slots=True)
class ScientificMetricReport:
    plan_digest: str
    protocol_digest: str
    metric_manifest_digest: str
    values: tuple[tuple[str, float], ...]
    missing: tuple[str, ...]
    blockers: tuple[str, ...]
    auxiliary_evidence_digest: str | None = None

    @property
    def eligible(self) -> bool:
        return not self.missing and not self.blockers

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True, slots=True)
class StatisticalComparison:
    comparison_id: str
    treatment_provider: str
    reference_provider: str
    estimate: float
    sample_count: int
    standard_error: float
    ci_lower: float
    ci_upper: float
    raw_p_value: float
    adjusted_p_value: float
    correction_method: str


@dataclass(frozen=True, slots=True)
class ScientificStatisticalReport:
    """Paired effects, uncertainty, and multiplicity metadata for the plan."""

    plan_digest: str
    effects: tuple[tuple[str, float, int, float, float, float], ...]
    missing: tuple[str, ...]
    blockers: tuple[str, ...]
    comparisons: tuple[StatisticalComparison, ...] = ()
    missingness_policy: str = "complete_case_paired_observations"
    blocked_task_policy: str = "blocked_tasks_invalidate_scientific_claim"

    @property
    def eligible(self) -> bool:
        return not self.missing and not self.blockers

    @property
    def digest(self) -> str:
        return canonical_digest(self)


__all__ = [
    "ScientificMetricComputationError",
    "ScientificMetricReport",
    "ScientificStatisticalReport",
    "StatisticalComparison",
]
