from __future__ import annotations

from research_platform.data.state.api import AtomicStateStorePort

from .adoption_commit import AdoptionCommitReconciler, AdoptionCommitter
from .adoption_preparation import AdoptionPreparer, EvolutionLedgerEntry
from .evolution import CandidateArchitecture, EvaluationProof
from .generation import GenerationAllocator
from .materialization import Materializer


class AtomicAdoptionService:
    """Facade over prepare -> atomic commit, with exact post-crash reconciliation."""

    ARCH = "method.sem.architecture_head"
    LEDGER = "method.sem.evolution_ledger"

    def __init__(self, state: AtomicStateStorePort, materializer: Materializer, allocator: GenerationAllocator) -> None:
        self.preparer = AdoptionPreparer(
            state,
            materializer,
            allocator,
            architecture_aggregate=self.ARCH,
            ledger_aggregate=self.LEDGER,
        )
        self.committer = AdoptionCommitter(state, allocator)
        self.reconciler = AdoptionCommitReconciler(
            state,
            allocator,
            architecture_aggregate=self.ARCH,
            ledger_aggregate=self.LEDGER,
        )

    def adopt(self, candidate: CandidateArchitecture, proof: EvaluationProof) -> str:
        prepared = self.preparer.prepare(candidate, proof)
        return self.committer.commit(prepared).generation

    def reconcile_committed_generation(self) -> str:
        return self.reconciler.reconcile().generation


__all__ = ["AtomicAdoptionService", "EvolutionLedgerEntry", "GenerationAllocator"]
