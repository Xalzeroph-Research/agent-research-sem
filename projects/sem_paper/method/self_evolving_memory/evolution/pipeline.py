from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from research_platform.platform.kernel import ExecutionContext

from .contracts import (
    AcceptancePort,
    CompilerPort,
    ContextualAdoptionPort,
    DiagnosisPort,
    EditKind,
    EligibilityPort,
    EvaluatorPort,
    EvolutionOutcome,
    EvolutionStage,
    EvolutionStageFailure,
    SynthesisPort,
)

_T = TypeVar("_T")


class EvolutionPipeline:
    """Pure authority sequencing; every stage is explicit and independently attributable."""

    def __init__(
        self,
        *,
        eligibility: EligibilityPort,
        diagnosis: DiagnosisPort,
        synthesis: SynthesisPort,
        compiler: CompilerPort,
        evaluator: EvaluatorPort,
        acceptance: AcceptancePort,
        adoption: ContextualAdoptionPort,
    ) -> None:
        self.eligibility = eligibility
        self.diagnosis = diagnosis
        self.synthesis = synthesis
        self.compiler = compiler
        self.evaluator = evaluator
        self.acceptance = acceptance
        self.adoption = adoption

    @staticmethod
    def _stage(stage: EvolutionStage, call: Callable[[], _T]) -> _T:
        try:
            return call()
        except EvolutionStageFailure:
            raise
        except Exception as exc:
            raise EvolutionStageFailure(stage, exc) from exc

    def run(self, context: ExecutionContext | None = None) -> EvolutionOutcome:
        gate = self._stage(EvolutionStage.ELIGIBILITY, self.eligibility.check)
        if not gate.eligible:
            return EvolutionOutcome("deferred", None, None, None, gate.reason_code)

        aor = self._stage(EvolutionStage.DIAGNOSIS, self.diagnosis.diagnose)
        intent = self._stage(EvolutionStage.SYNTHESIS, lambda: self.synthesis.propose(aor))
        if intent.edit == EditKind.NO_EDIT:
            return EvolutionOutcome("no_edit", aor.generation, aor.generation, intent.edit)

        candidate = self._stage(
            EvolutionStage.COMPILATION,
            lambda: self.compiler.compile(intent, aor.generation),
        )
        proof = self._stage(EvolutionStage.EVALUATION, lambda: self.evaluator.evaluate(candidate))
        if not proof.comparability.valid:
            return EvolutionOutcome(
                "invalid_evaluation",
                aor.generation,
                aor.generation,
                intent.edit,
                ";".join(proof.comparability.violations),
            )
        accepted = self._stage(
            EvolutionStage.ACCEPTANCE,
            lambda: self.acceptance.accept(intent, proof),
        )
        if not accepted:
            return EvolutionOutcome("rejected", aor.generation, aor.generation, intent.edit)

        new_generation = self._stage(
            EvolutionStage.ADOPTION,
            lambda: self.adoption.adopt(candidate, proof, context),
        )
        return EvolutionOutcome("adopted", aor.generation, new_generation, intent.edit)
