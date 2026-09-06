from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Protocol

from research_platform.experimentation.evaluation.api import BranchReceipt, build_comparability_proof

from .contracts import CandidateArchitecture, EvaluationProof
from .deluxe_candidate import DeluxeCandidateAudit, DeluxeCandidatePolicy


class BranchRole(StrEnum):
    CONTROL = "control"
    CANDIDATE = "candidate"


class CandidateEvaluationError(RuntimeError):
    """A branch runner failed; the pipeline remains the stage authority."""

    def __init__(self, role: BranchRole, cause: BaseException) -> None:
        super().__init__(f"SEM candidate evaluation branch failed: {role.value}")
        self.role = role
        self.cause = cause
        self.cause_type = type(cause).__name__

    @property
    def failure_correlation_refs(self) -> tuple[str, ...]:
        return (f"evaluation-branch:{self.role.value}",)


class BranchRunnerPort(Protocol):
    """Project composition seam for one isolated control/candidate branch."""

    def run(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
    ) -> BranchReceipt: ...


@dataclass(frozen=True, slots=True)
class PairedBranchEvaluation:
    control: BranchReceipt
    candidate: BranchReceipt
    proof: EvaluationProof


class PairedBranchEvaluator:
    """Evaluate one candidate through an injected paired branch runner.

    This class translates experiment receipts into the SEM evaluator contract.
    It never decides acceptance and never calls adoption.  A failed
    comparability proof is returned as evidence so the pipeline can reject it
    without pretending that the candidate was scientifically comparable.
    """

    def __init__(self, runner: BranchRunnerPort) -> None:
        self.runner = runner

    def evaluate(self, candidate: CandidateArchitecture) -> EvaluationProof:
        control = self._run(BranchRole.CONTROL, None)
        candidate_receipt = self._run(BranchRole.CANDIDATE, candidate)
        proof = build_comparability_proof(control, candidate_receipt)
        metrics = self._metrics(control, candidate_receipt, proof.valid)
        return EvaluationProof(proof, metrics)

    def evaluate_with_receipts(self, candidate: CandidateArchitecture) -> PairedBranchEvaluation:
        control = self._run(BranchRole.CONTROL, None)
        candidate_receipt = self._run(BranchRole.CANDIDATE, candidate)
        proof = build_comparability_proof(control, candidate_receipt)
        return PairedBranchEvaluation(
            control,
            candidate_receipt,
            EvaluationProof(proof, self._metrics(control, candidate_receipt, proof.valid)),
        )

    def evaluate_deluxe(
        self,
        candidate: CandidateArchitecture,
        *,
        policy: DeluxeCandidatePolicy | None = None,
    ) -> tuple[EvaluationProof, DeluxeCandidateAudit]:
        """Run paired evaluation and attach the fixed Deluxe stability audit.

        The returned audit is diagnostic evidence.  It cannot accept, reject,
        compile, or adopt a candidate; those authorities stay in the injected
        pipeline ports.
        """

        paired = self.evaluate_with_receipts(candidate)
        audit = (policy or DeluxeCandidatePolicy()).audit(
            candidate=candidate,
            proof=paired.proof,
        )
        metrics = dict(paired.proof.metrics)
        metrics.update(
            {
                "deluxe.stability.accepted": float(audit.accepted_by_stability),
                "deluxe.stability.regressing_window_fraction": audit.regressing_window_fraction,
                "deluxe.created_provider_adoption_share": audit.created_provider_adoption_share,
                "deluxe.created_provider_count": float(audit.created_provider_count),
                "deluxe.created_provider_with_records": float(audit.created_provider_with_records),
            }
        )
        return EvaluationProof(paired.proof.comparability, metrics), audit

    def _run(self, role: BranchRole, candidate: CandidateArchitecture | None) -> BranchReceipt:
        try:
            receipt = self.runner.run(role=role, candidate=candidate)
        except CandidateEvaluationError:
            raise
        except Exception as exc:
            raise CandidateEvaluationError(role, exc) from exc
        if not isinstance(receipt, BranchReceipt):
            raise CandidateEvaluationError(role, TypeError("branch runner returned an invalid receipt"))
        try:
            self._validate_receipt(receipt)
        except (TypeError, ValueError) as exc:
            raise CandidateEvaluationError(role, exc) from exc
        if role is BranchRole.CONTROL and candidate is not None:
            raise CandidateEvaluationError(role, ValueError("control branch received a candidate"))
        if role is BranchRole.CANDIDATE and candidate is None:
            raise CandidateEvaluationError(role, ValueError("candidate branch received no candidate"))
        return receipt

    @staticmethod
    def _metrics(
        control: BranchReceipt,
        candidate: BranchReceipt,
        comparable: bool,
    ) -> dict[str, float]:
        control_metrics = PairedBranchEvaluator._metric_map(control)
        candidate_metrics = PairedBranchEvaluator._metric_map(candidate)
        output: dict[str, float] = {"comparability.valid": float(comparable)}
        for name, value in sorted(control_metrics.items()):
            output[f"control.{name}"] = value
        for name, value in sorted(candidate_metrics.items()):
            output[f"candidate.{name}"] = value
        for name in sorted(set(control_metrics) & set(candidate_metrics)):
            output[f"delta.{name}"] = candidate_metrics[name] - control_metrics[name]
        return output

    @staticmethod
    def _validate_receipt(receipt: BranchReceipt) -> None:
        identities = (
            receipt.branch_id,
            receipt.source_checkpoint_id,
            receipt.workload_id,
            receipt.environment_generation,
            receipt.task_manifest_digest,
        )
        if any(not isinstance(value, str) or not value.strip() for value in identities):
            raise ValueError("branch receipt identities must be non-empty strings")
        for label, values in (
            ("branch_writes", receipt.branch_writes),
            ("lifetime_writes", receipt.lifetime_writes),
            ("private_to_method_flows", receipt.private_to_method_flows),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"branch receipt {label} must be a tuple of non-empty strings")
        PairedBranchEvaluator._metric_map(receipt)

    @staticmethod
    def _metric_map(receipt: BranchReceipt) -> dict[str, float]:
        if not isinstance(receipt.metrics, tuple):
            raise ValueError("branch receipt metrics must be a tuple")
        output: dict[str, float] = {}
        for row in receipt.metrics:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("branch receipt metric rows must be two-item tuples")
            name, value = row
            if not isinstance(name, str) or not name.strip():
                raise ValueError("branch receipt metric name must be a non-empty string")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"branch receipt metric must be numeric: {name}")
            try:
                numeric = float(value)
            except OverflowError as exc:
                raise ValueError(f"branch receipt metric is not finite: {name}") from exc
            if not math.isfinite(numeric):
                raise ValueError(f"branch receipt metric is not finite: {name}")
            if name in output:
                raise ValueError(f"branch receipt contains duplicate metric: {name}")
            output[name] = numeric
        return output


__all__ = [
    "BranchRole",
    "BranchRunnerPort",
    "CandidateEvaluationError",
    "PairedBranchEvaluation",
    "PairedBranchEvaluator",
]
