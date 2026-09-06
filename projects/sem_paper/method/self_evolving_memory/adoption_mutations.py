from __future__ import annotations

from research_platform.data.state.api import AtomicMutation

from .adoption_types import (
    AdoptionBaseState,
    AdoptionPreparationError,
    AdoptionPreparationStage,
    EvolutionLedgerEntry,
    MaterializedCandidate,
    PreparedAdoption,
)
from research_platform.platform.kernel import canonical_digest
from research_platform.platform.kernel.errors import describe_exception
from .evolution import CandidateArchitecture, EvaluationProof
from .architecture import MemoryArchitectureSpec
from .architecture.serialization import architecture_to_dict


class AdoptionMutationCompiler:
    """Compiles prepared method data into the two authoritative atomic mutations."""

    def __init__(self, *, architecture_aggregate: str, ledger_aggregate: str) -> None:
        self.architecture_aggregate = architecture_aggregate
        self.ledger_aggregate = ledger_aggregate

    @staticmethod
    def _ledger_document(entries: tuple[object, ...]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for item in entries:
            try:
                entry = item if isinstance(item, EvolutionLedgerEntry) else EvolutionLedgerEntry.from_document(item)
            except (TypeError, ValueError) as exc:
                raise ValueError("existing evolution ledger row is invalid") from exc
            rows.append(entry.to_document())
        return rows

    def compile(self, candidate: CandidateArchitecture, proof: EvaluationProof, base: AdoptionBaseState, materialized: MaterializedCandidate) -> PreparedAdoption:
        prepared = materialized.prepared_generation
        generation = materialized.generation
        try:
            entry = EvolutionLedgerEntry(
                candidate.candidate_id,
                candidate.base_generation,
                generation,
                proof.comparability.pair_id,
                candidate.target_spec_digest,
                prepared.source_snapshot_digest,
                prepared.source_sequence,
            )
            target_spec = (
                architecture_to_dict(candidate.target_spec)
                if isinstance(candidate.target_spec, MemoryArchitectureSpec)
                else candidate.target_spec
            )
            arch_payload = {
                "target_spec": target_spec,
                "materialized_records": prepared.records,
                "source_sequence": prepared.source_sequence,
                "source_snapshot_digest": prepared.source_snapshot_digest,
            }
            if prepared.typed_generation is not None:
                to_document = getattr(prepared.typed_generation, "to_document", None)
                if not callable(to_document):
                    raise TypeError("typed generation artifact must expose to_document")
                arch_payload["typed_generation"] = to_document()
            ledger_entries = tuple(base.ledger.payload) + (entry,)
            ledger_payload = self._ledger_document(ledger_entries)
            return PreparedAdoption(
                generation=generation,
                prepared_generation=prepared,
                architecture_mutation=AtomicMutation(
                    self.architecture_aggregate,
                    base.architecture.version,
                    base.architecture.generation,
                    generation,
                    canonical_digest(arch_payload),
                    arch_payload,
                ),
                ledger_mutation=AtomicMutation(
                    self.ledger_aggregate,
                    base.ledger.version,
                    base.ledger.generation,
                    generation,
                    canonical_digest(ledger_payload),
                    ledger_payload,
                ),
                ledger_entry=entry,
            )
        except Exception as exc:
            descriptor = describe_exception(exc)
            raise AdoptionPreparationError(
                AdoptionPreparationStage.MUTATION_COMPILE,
                "ADOPTION_MUTATION_COMPILE_FAILED",
                f"{descriptor.error_type}[{descriptor.error_digest[:16]}]",
            ) from exc
