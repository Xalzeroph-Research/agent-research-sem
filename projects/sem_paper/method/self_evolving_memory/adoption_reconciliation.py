from __future__ import annotations

from typing import Protocol

from research_platform.platform.kernel import ExecutionContext

from .session_evolution_api import (
    EvolutionReconciliation,
    EvolutionReconciliationStatus,
)


class CommittedGenerationAuthority(Protocol):
    def reconcile_committed_generation(self) -> str: ...


class ConservativeAdoptionReconciliationPort:
    """Reads authoritative adoption state without claiming unprovable task attribution.

    If the authoritative head is still the task's base generation, no adoption from
    this task can have committed.  A different head is intentionally left unresolved
    until the evolution ledger carries a task correlation key.
    """

    def __init__(self, authority: CommittedGenerationAuthority) -> None:
        self.authority = authority

    def reconcile(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        del context
        generation = self.authority.reconcile_committed_generation()
        evidence = (f"sem-adoption-head:{generation}", f"sem-task-key:{task_key}")
        if generation == base_generation:
            return EvolutionReconciliation(
                EvolutionReconciliationStatus.NO_AUTHORITATIVE_ADOPTION,
                authoritative_generation=generation,
                evidence_refs=evidence,
                reason="authoritative architecture head did not advance",
            )
        return EvolutionReconciliation(
            EvolutionReconciliationStatus.UNRESOLVED,
            authoritative_generation=generation,
            evidence_refs=evidence,
            reason="architecture head advanced but adoption ledger has no task correlation key",
        )


__all__ = ["CommittedGenerationAuthority", "ConservativeAdoptionReconciliationPort"]
