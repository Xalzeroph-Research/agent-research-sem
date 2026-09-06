from __future__ import annotations

from dataclasses import dataclass

from research_platform.platform.kernel import ExecutionContext

from .evolution import AdoptionPort, CandidateArchitecture, EvaluationProof
from .session_evolution_api import SessionAdoptionAuthority


@dataclass(frozen=True, slots=True)
class PreparedCandidateAdoption:
    """Bind evaluated artifacts into the session's minimal commit capability."""

    authority: AdoptionPort
    candidate: CandidateArchitecture
    proof: EvaluationProof

    def commit(self) -> str:
        return self.authority.adopt(self.candidate, self.proof)


class SessionScopedAdoptionStage:
    """Publish one evaluated candidate through the bound session authority."""

    def __init__(self, authority: AdoptionPort, session: SessionAdoptionAuthority) -> None:
        self._authority = authority
        self._session = session

    def adopt(
        self,
        candidate: CandidateArchitecture,
        proof: EvaluationProof,
        context: ExecutionContext | None,
    ) -> str:
        if context is None:
            raise ValueError("session-scoped adoption requires ExecutionContext")
        publication = self._session.commit_prepared_adoption(
            PreparedCandidateAdoption(self._authority, candidate, proof),
            context,
        )
        return publication.generation


__all__ = ["PreparedCandidateAdoption", "SessionScopedAdoptionStage"]
