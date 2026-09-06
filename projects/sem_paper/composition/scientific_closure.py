"""Scientific closure service for the SEM production entrypoints.

This service is the single project boundary that joins raw matrix evidence,
scientific estimands, uncertainty, and externally qualified live evidence. It
never turns missing evidence into a claim; absence is represented as a typed
blocked receipt and a false gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from research_platform.experimentation.study.api import ExperimentPlan, StudyMatrixExecutionReport
from research_platform.platform.kernel.errors import describe_exception

from .live_evidence import (
    LiveEvidenceReceipt,
    LiveEvidenceStatus,
    LiveEvidenceValidationError,
    load_live_evidence,
    validate_live_evidence,
)
from .scientific_metrics import (
    ScientificAuxiliaryEvidence,
    ScientificMetricComputationError,
    ScientificMetricReport,
    ScientificStatisticalReport,
    SemPaperScientificMetricProvider,
    load_scientific_auxiliary_evidence,
    validate_scientific_auxiliary_evidence,
)
from .study import is_claim_ready_protocol, is_confirmatory_protocol


@dataclass(frozen=True, slots=True)
class ScientificClaimGate:
    eligible: bool
    reasons: tuple[str, ...]
    plan_digest: str
    protocol_digest: str
    binding_digest: str
    metric_manifest_digest: str
    statistical_report_digest: str
    live_evidence_digest: str
    evolution_binding_digest: str
    evolution_binding_complete: bool
    evolution_scientific_ready: bool
    model_request_count: int
    arm_count: int
    auxiliary_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class ScientificClosureResult:
    metrics: ScientificMetricReport
    statistics: ScientificStatisticalReport
    live_evidence: LiveEvidenceReceipt
    auxiliary_evidence: ScientificAuxiliaryEvidence | None
    auxiliary_evidence_error: str | None
    gate: ScientificClaimGate


def source_tree_digest(root: Path) -> str:
    """Hash the checked-in scientific source surface deterministically."""

    if not root.is_dir():
        raise ValueError(f"scientific source root is missing: {root}")
    digest = hashlib.sha256()
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".json", ".md"}
        and "__pycache__" not in path.parts
        and not any(part.startswith(".rsync-") for part in path.parts)
    )
    if not paths:
        raise ValueError("scientific source root contains no digestible source")
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class SemPaperScientificClosureService:
    def __init__(self, provider: SemPaperScientificMetricProvider | None = None) -> None:
        self._provider = provider or SemPaperScientificMetricProvider()

    def evaluate(
        self,
        *,
        plan: ExperimentPlan,
        report: StudyMatrixExecutionReport,
        source_digest: str,
        live_evidence_path: Path | None,
        mode: str,
        model_request_count: int,
        evolution_binding_complete: bool,
        evolution_binding_digest: str,
        evolution_scientific_ready: bool = False,
        auxiliary_evidence_path: Path | None = None,
    ) -> ScientificClosureResult:
        plan.assert_consistent()
        auxiliary_evidence, auxiliary_error = self._auxiliary_receipt(
            plan=plan,
            source_digest=source_digest,
            path=auxiliary_evidence_path,
        )
        metrics = self._provider.compute(
            plan=plan,
            report=report,
            auxiliary_evidence=auxiliary_evidence,
        )
        statistics = self._provider.compute_statistics(plan=plan, report=report)
        live = self._live_receipt(
            plan=plan,
            source_digest=source_digest,
            path=live_evidence_path,
            metric_manifest_digest=metrics.metric_manifest_digest,
        )
        reasons: list[str] = []
        if mode != "baseline":
            reasons.append("mode_is_not_model_backed_baseline")
        if not is_confirmatory_protocol(plan.protocol):
            reasons.append("study_matrix_is_not_frozen_confirmatory_core6")
        if not evolution_binding_complete:
            reasons.append("evolution_stage_bindings_incomplete")
        if not evolution_scientific_ready:
            reasons.append("evolution_stage_bindings_not_scientifically_ready")
        if model_request_count <= 0:
            reasons.append("no_model_request_evidence")
        if auxiliary_error is not None:
            reasons.append(f"auxiliary_evidence:{auxiliary_error}")
        if not metrics.eligible:
            reasons.extend(f"metric:{item}" for item in (*metrics.missing, *metrics.blockers))
        if not statistics.eligible:
            reasons.extend(f"statistics:{item}" for item in (*statistics.missing, *statistics.blockers))
        if live.status is not LiveEvidenceStatus.PASS or not live.claim_eligible:
            reasons.extend(f"live_evidence:{item}" for item in live.blockers or (live.status.value,))
        blocked = sum(
            aggregate.mean
            for aggregate in report.aggregates
            if aggregate.metric_name == "task_blocked_total"
        )
        if blocked > 0:
            reasons.append("task_dependency_blocking_present")
        gate = ScientificClaimGate(
            eligible=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            plan_digest=plan.plan_digest,
            protocol_digest=plan.protocol_digest,
            binding_digest=plan.binding_digest,
            metric_manifest_digest=metrics.metric_manifest_digest,
            statistical_report_digest=statistics.digest,
            live_evidence_digest=live.digest,
            evolution_binding_digest=evolution_binding_digest,
            evolution_binding_complete=evolution_binding_complete,
            evolution_scientific_ready=evolution_scientific_ready,
            model_request_count=model_request_count,
            arm_count=len(plan.bindings),
            auxiliary_evidence_digest=(
                auxiliary_evidence.digest if auxiliary_evidence is not None else None
            ),
        )
        return ScientificClosureResult(
            metrics,
            statistics,
            live,
            auxiliary_evidence,
            auxiliary_error,
            gate,
        )

    @staticmethod
    def _auxiliary_receipt(
        *,
        plan: ExperimentPlan,
        source_digest: str,
        path: Path | None,
    ) -> tuple[ScientificAuxiliaryEvidence | None, str | None]:
        if path is None:
            return None, None
        try:
            evidence = load_scientific_auxiliary_evidence(path)
            return (
                validate_scientific_auxiliary_evidence(
                    evidence,
                    expected_source_tree_digest=source_digest,
                    expected_plan_digest=plan.plan_digest,
                    expected_protocol_digest=plan.protocol_digest,
                    expected_binding_digest=plan.binding_digest,
                ),
                None,
            )
        except ScientificMetricComputationError as exc:
            descriptor = describe_exception(exc)
            return None, f"{descriptor.error_type}:{descriptor.safe_message} [{descriptor.error_digest[:12]}]"

    @staticmethod
    def _live_receipt(
        *,
        plan: ExperimentPlan,
        source_digest: str,
        path: Path | None,
        metric_manifest_digest: str,
    ) -> LiveEvidenceReceipt:
        if path is None:
            return LiveEvidenceReceipt(
                schema_version="sem-live-evidence.v2",
                evidence_id=f"missing:{plan.plan_digest[:16]}",
                status=LiveEvidenceStatus.BLOCKED_BY_ENVIRONMENT,
                run_id=f"plan:{plan.plan_digest[:16]}",
                source_tree_digest=source_digest,
                qualified_closure_digest=None,
                t2b_gate_digest=None,
                protocol_digest=plan.protocol_digest,
                matrix_profile=(
                    "core-6"
                    if is_confirmatory_protocol(plan.protocol)
                    else "claim-ready"
                    if is_claim_ready_protocol(plan.protocol)
                    else "compiled"
                ),
                repetitions=plan.protocol.repetitions,
                claim_eligible=False,
                blockers=("live evidence receipt was not supplied",),
                plan_digest=plan.plan_digest,
                binding_digest=plan.binding_digest,
                metric_manifest_digest=metric_manifest_digest,
            )
        try:
            receipt = load_live_evidence(path)
            return validate_live_evidence(
                receipt,
                expected_source_tree_digest=source_digest,
                expected_protocol_digest=plan.protocol_digest,
                expected_plan_digest=plan.plan_digest,
                expected_binding_digest=plan.binding_digest,
                expected_metric_manifest_digest=metric_manifest_digest,
                require_claim_eligibility=False,
            )
        except LiveEvidenceValidationError as exc:
            descriptor = describe_exception(exc)
            return LiveEvidenceReceipt(
                schema_version="sem-live-evidence.v2",
                evidence_id=f"invalid:{plan.plan_digest[:16]}",
                status=LiveEvidenceStatus.FAILED,
                run_id=f"plan:{plan.plan_digest[:16]}",
                source_tree_digest=source_digest,
                qualified_closure_digest=None,
                t2b_gate_digest=None,
                protocol_digest=plan.protocol_digest,
                matrix_profile=(
                    "core-6"
                    if is_confirmatory_protocol(plan.protocol)
                    else "claim-ready"
                    if is_claim_ready_protocol(plan.protocol)
                    else "compiled"
                ),
                repetitions=plan.protocol.repetitions,
                claim_eligible=False,
                blockers=(f"{descriptor.error_type}:{descriptor.safe_message} [{descriptor.error_digest[:12]}]",),
                plan_digest=plan.plan_digest,
                binding_digest=plan.binding_digest,
                metric_manifest_digest=metric_manifest_digest,
            )


__all__ = [
    "ScientificClaimGate",
    "ScientificClosureResult",
    "SemPaperScientificClosureService",
    "source_tree_digest",
]
