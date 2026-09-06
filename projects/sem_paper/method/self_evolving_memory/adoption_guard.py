from __future__ import annotations

from research_platform.data.state.api import AtomicStateStorePort, StateVersionConflict

from .adoption_types import AdoptionBaseState, AdoptionPreparationError, AdoptionPreparationStage
from .evolution import CandidateArchitecture, EvaluationProof


class CandidateGuard:
    """Read-only proof/base-generation guard. Never allocates or materializes."""

    def __init__(self, state: AtomicStateStorePort, *, architecture_aggregate: str, ledger_aggregate: str) -> None:
        self.state = state
        self.architecture_aggregate = architecture_aggregate
        self.ledger_aggregate = ledger_aggregate

    def validate(self, candidate: CandidateArchitecture, proof: EvaluationProof) -> AdoptionBaseState:
        if not proof.comparability.valid:
            raise AdoptionPreparationError(
                AdoptionPreparationStage.PROOF,
                "ADOPTION_PROOF_INVALID",
                "cannot adopt invalid paired evaluation",
            )
        current = self.state.read(self.architecture_aggregate)
        ledger = self.state.read(self.ledger_aggregate)
        if current.generation != candidate.base_generation:
            err = StateVersionConflict("candidate base generation is stale")
            raise AdoptionPreparationError(
                AdoptionPreparationStage.BASE_STATE,
                "ADOPTION_BASE_STALE",
                str(err),
            ) from err
        return AdoptionBaseState(current, ledger)
