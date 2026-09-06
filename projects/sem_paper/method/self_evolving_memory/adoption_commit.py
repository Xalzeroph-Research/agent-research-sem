from __future__ import annotations

from research_platform.data.state.api import AggregateValue, AtomicStateStorePort

from dataclasses import dataclass

from .adoption_preparation import PreparedAdoption
from .generation import GenerationAllocator


class AdoptionCommitConsistencyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdoptionCommitReceipt:
    generation: str
    architecture_version: int
    architecture_digest: str
    ledger_version: int
    ledger_digest: str


class AdoptionCommitReconciler:
    """Rebuilds non-authoritative generation lifecycle state from authoritative aggregates."""

    def __init__(self, state: AtomicStateStorePort, allocator: GenerationAllocator, *, architecture_aggregate: str, ledger_aggregate: str) -> None:
        self.state = state
        self.allocator = allocator
        self.architecture_aggregate = architecture_aggregate
        self.ledger_aggregate = ledger_aggregate

    @staticmethod
    def _validate_pair(architecture: AggregateValue, ledger: AggregateValue) -> str:
        if architecture.generation != ledger.generation:
            raise AdoptionCommitConsistencyError(
                f"architecture/ledger generation mismatch: {architecture.generation} != {ledger.generation}"
            )
        return architecture.generation

    def reconcile(self) -> AdoptionCommitReceipt:
        architecture = self.state.read(self.architecture_aggregate)
        ledger = self.state.read(self.ledger_aggregate)
        generation = self._validate_pair(architecture, ledger)
        self.allocator.reconcile_committed(generation)
        return AdoptionCommitReceipt(
            generation,
            architecture.version,
            architecture.digest,
            ledger.version,
            ledger.digest,
        )


class AdoptionCommitter:
    """Only phase allowed to atomically publish architecture head + evolution ledger."""

    def __init__(self, state: AtomicStateStorePort, allocator: GenerationAllocator) -> None:
        self.state = state
        self.allocator = allocator

    @staticmethod
    def _receipt(values: tuple[AggregateValue, ...], generation: str) -> AdoptionCommitReceipt:
        if len(values) != 2:
            raise AdoptionCommitConsistencyError("adoption commit must publish exactly two authoritative aggregates")
        architecture, ledger = values
        if architecture.generation != generation or ledger.generation != generation:
            raise AdoptionCommitConsistencyError("atomic commit returned unexpected generation")
        return AdoptionCommitReceipt(
            generation,
            architecture.version,
            architecture.digest,
            ledger.version,
            ledger.digest,
        )

    def commit(self, prepared: PreparedAdoption) -> AdoptionCommitReceipt:
        try:
            values = self.state.commit_batch((
                prepared.architecture_mutation,
                prepared.ledger_mutation,
            ))
        except Exception:
            self.allocator.abandon(prepared.generation)
            raise

        # From this line onward the scientific/authoritative commit is already real.
        # Finalize the local lifecycle index idempotently; if the process dies here,
        # AdoptionCommitReconciler reconstructs it from the two authoritative aggregates.
        receipt = self._receipt(values, prepared.generation)
        self.allocator.reconcile_committed(prepared.generation)
        return receipt
