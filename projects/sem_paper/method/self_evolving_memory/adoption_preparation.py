from __future__ import annotations

from research_platform.data.state.api import AtomicStateStorePort

from .adoption_guard import CandidateGuard
from .adoption_materialize import PreparedGenerationBuilder
from .adoption_mutations import AdoptionMutationCompiler
from .adoption_types import (
    AdoptionBaseState,
    AdoptionPreparationError,
    AdoptionPreparationStage,
    EvolutionLedgerEntry,
    MaterializedCandidate,
    PreparedAdoption,
)
from .evolution import CandidateArchitecture, EvaluationProof
from .generation import GenerationAllocator
from .materialization import Materializer


class AdoptionPreparer:
    """Orchestrates guard -> materialize -> mutation compile without owning sub-stage logic."""

    def __init__(self, state: AtomicStateStorePort, materializer: Materializer, allocator: GenerationAllocator, *, architecture_aggregate: str, ledger_aggregate: str) -> None:
        self.guard = CandidateGuard(state, architecture_aggregate=architecture_aggregate, ledger_aggregate=ledger_aggregate)
        self.builder = PreparedGenerationBuilder(materializer, allocator)
        self.compiler = AdoptionMutationCompiler(architecture_aggregate=architecture_aggregate, ledger_aggregate=ledger_aggregate)

    def prepare(self, candidate: CandidateArchitecture, proof: EvaluationProof) -> PreparedAdoption:
        base = self.guard.validate(candidate, proof)
        materialized = self.builder.build(candidate)
        try:
            return self.compiler.compile(candidate, proof, base, materialized)
        except Exception:
            self.builder.abandon(materialized.generation)
            raise


__all__ = [
    "AdoptionPreparer",
    "AdoptionBaseState",
    "AdoptionPreparationError",
    "AdoptionPreparationStage",
    "EvolutionLedgerEntry",
    "MaterializedCandidate",
    "PreparedAdoption",
]
