from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .evolution import (
    AcceptancePort,
    AdoptionPort,
    CompilerPort,
    DiagnosisPort,
    EligibilityPort,
    EvaluatorPort,
    EvolutionPipeline,
    SynthesisPort,
)
from .session_evolution_api import (
    EvolutionSessionBinding,
    EvolutionReconciliationPort,
    EvolutionSessionSource,
    SessionAdoptionAuthority,
    SessionEvolutionController,
)
from .session_adoption import SessionScopedAdoptionStage
from .session_evolution_runtime import PipelineSessionEvolution


class EligibilityFactory(Protocol):
    def __call__(self, source: EvolutionSessionSource) -> EligibilityPort: ...


class DiagnosisFactory(Protocol):
    def __call__(self, source: EvolutionSessionSource) -> DiagnosisPort: ...


class SynthesisFactory(Protocol):
    def __call__(self) -> SynthesisPort: ...


class CompilerFactory(Protocol):
    def __call__(self) -> CompilerPort: ...


class EvaluatorFactory(Protocol):
    def __call__(self) -> EvaluatorPort: ...


class AcceptanceFactory(Protocol):
    def __call__(self) -> AcceptancePort: ...


class AdoptionFactory(Protocol):
    def __call__(self, authority: SessionAdoptionAuthority) -> AdoptionPort: ...


class ReconciliationFactory(Protocol):
    def __call__(self) -> EvolutionReconciliationPort: ...


@dataclass(frozen=True, slots=True)
class EvolutionStageFactories:
    """Minimal-authority provider factories for the SEM evolution pipeline.

    Only scheduling/diagnosis receive the live session read source. Every downstream
    stage must operate on the explicit pipeline artifact handed to it.
    """

    eligibility: EligibilityFactory
    diagnosis: DiagnosisFactory
    synthesis: SynthesisFactory
    compiler: CompilerFactory
    evaluator: EvaluatorFactory
    acceptance: AcceptanceFactory
    adoption: AdoptionFactory
    reconciliation: ReconciliationFactory | None = None


class PipelineSessionEvolutionFactory:
    """Session-scoped composition only; it owns no stage semantics or authority."""

    def __init__(self, stages: EvolutionStageFactories) -> None:
        self._stages = stages

    def __call__(self, binding: EvolutionSessionBinding) -> SessionEvolutionController:
        stages = self._stages
        source = binding.source
        eligibility = stages.eligibility(source)
        diagnosis = stages.diagnosis(source)
        synthesis = stages.synthesis()
        compiler = stages.compiler()
        evaluator = stages.evaluator()
        acceptance = stages.acceptance()
        adoption = SessionScopedAdoptionStage(
            stages.adoption(binding.adoption),
            binding.adoption,
        )
        pipeline = EvolutionPipeline(
            diagnosis=diagnosis,
            synthesis=synthesis,
            compiler=compiler,
            evaluator=evaluator,
            acceptance=acceptance,
            adoption=adoption,
            eligibility=eligibility,
        )
        reconciliation = None if stages.reconciliation is None else stages.reconciliation()
        return PipelineSessionEvolution(pipeline, reconciliation)


__all__ = [
    "AcceptanceFactory",
    "AdoptionFactory",
    "CompilerFactory",
    "DiagnosisFactory",
    "EligibilityFactory",
    "EvaluatorFactory",
    "EvolutionStageFactories",
    "PipelineSessionEvolutionFactory",
    "ReconciliationFactory",
    "SynthesisFactory",
]
