from __future__ import annotations

"""Fixed Deluxe candidate stability/adoption audit over paired receipts."""

from dataclasses import dataclass
from statistics import mean
from typing import Mapping, Sequence

from .contracts import CandidateArchitecture, EvaluationProof


@dataclass(frozen=True, slots=True)
class DeluxeCandidateConfig:
    long_window_size: int = 3
    min_windows_for_stability: int = 2
    max_regressing_window_fraction: float = 0.5
    window_nonregression_tolerance: float = 0.15

    def __post_init__(self) -> None:
        if self.long_window_size <= 0 or self.min_windows_for_stability <= 0:
            raise ValueError("Deluxe candidate windows must be positive")
        if not 0.0 <= self.max_regressing_window_fraction <= 1.0:
            raise ValueError("Deluxe regression fraction must be in [0,1]")
        if self.window_nonregression_tolerance < 0.0:
            raise ValueError("Deluxe window tolerance cannot be negative")


@dataclass(frozen=True, slots=True)
class DeluxeCandidateAudit:
    accepted_by_stability: bool
    reasons: tuple[str, ...]
    window_deltas: tuple[float, ...]
    regressing_window_fraction: float
    created_provider_adoption_share: float
    created_provider_count: int
    created_provider_with_records: int


def _metric_series(metrics: Mapping[str, float], prefix: str) -> tuple[float, ...]:
    values: list[tuple[int, float]] = []
    for key, value in metrics.items():
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix) :]
        if not suffix.isdigit():
            continue
        values.append((int(suffix), float(value)))
    return tuple(value for _, value in sorted(values))


class DeluxeCandidatePolicy:
    """Add fixed long-window diagnostics without becoming acceptance authority."""

    def __init__(self, config: DeluxeCandidateConfig | None = None) -> None:
        self.config = config or DeluxeCandidateConfig()

    def audit(
        self,
        *,
        candidate: CandidateArchitecture,
        proof: EvaluationProof,
        control_series: Sequence[float] | None = None,
        candidate_series: Sequence[float] | None = None,
    ) -> DeluxeCandidateAudit:
        control = tuple(float(value) for value in (control_series or _metric_series(proof.metrics, "control.task.utility.")))
        proposed = tuple(float(value) for value in (candidate_series or _metric_series(proof.metrics, "candidate.task.utility.")))
        n = min(len(control), len(proposed))
        window = self.config.long_window_size
        deltas = tuple(
            mean(proposed[index : index + window]) - mean(control[index : index + window])
            for index in range(0, n, window)
            if index + window <= n
        )
        reasons: list[str] = []
        if len(deltas) < self.config.min_windows_for_stability:
            reasons.append("insufficient_long_window_evidence")
        regressions = sum(
            delta < -self.config.window_nonregression_tolerance for delta in deltas
        )
        fraction = regressions / max(1, len(deltas))
        if deltas and fraction > self.config.max_regressing_window_fraction:
            reasons.append("long_duration_window_instability")
        old_ids = set()
        if isinstance(candidate.target_spec, object) and hasattr(candidate.target_spec, "node_map"):
            old_ids = set()  # base architecture is intentionally not hidden in the candidate envelope
        created_count = sum(edit.kind.value == "CREATE" for edit in candidate.primitive_edits)
        created_with_records = sum(
            edit.kind.value == "CREATE"
            and any(
                key.startswith(f"candidate.node.{edit.target}.records.")
                for key in proof.metrics
            )
            for edit in candidate.primitive_edits
        )
        selected = sum(
            value
            for key, value in proof.metrics.items()
            if key.startswith("candidate.node.") and key.endswith(".selected")
        )
        adopted = sum(
            value
            for edit in candidate.primitive_edits
            if edit.kind.value == "CREATE"
            for key, value in proof.metrics.items()
            if key == f"candidate.node.{edit.target}.selected"
        )
        return DeluxeCandidateAudit(
            not reasons,
            tuple(reasons),
            deltas,
            fraction if deltas else 0.0,
            adopted / max(1.0, selected),
            created_count,
            created_with_records,
        )


__all__ = ["DeluxeCandidateAudit", "DeluxeCandidateConfig", "DeluxeCandidatePolicy"]
