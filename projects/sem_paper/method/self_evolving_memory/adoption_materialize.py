from __future__ import annotations

from .adoption_types import AdoptionPreparationError, AdoptionPreparationStage, MaterializedCandidate
from .evolution import CandidateArchitecture
from .generation import GenerationAllocator
from .materialization import Materializer
from research_platform.platform.kernel.errors import describe_exception


class PreparedGenerationBuilder:
    """Owns allocate -> clean materialize -> abandon-on-failure lifecycle."""

    def __init__(self, materializer: Materializer, allocator: GenerationAllocator) -> None:
        self.materializer = materializer
        self.allocator = allocator

    def build(self, candidate: CandidateArchitecture) -> MaterializedCandidate:
        try:
            generation = self.allocator.allocate(candidate.candidate_id)
        except Exception as exc:
            descriptor = describe_exception(exc)
            raise AdoptionPreparationError(
                AdoptionPreparationStage.GENERATION,
                "ADOPTION_GENERATION_ALLOCATE_FAILED",
                f"{descriptor.error_type}[{descriptor.error_digest[:16]}]",
            ) from exc
        try:
            prepared = self.materializer.clean_build(
                generation,
                base_generation=candidate.base_generation,
                candidate_id=candidate.candidate_id,
                target_spec_digest=candidate.target_spec_digest,
                contracts=tuple(candidate.materialization_contracts),
                target_spec=candidate.target_spec,
            )
        except Exception as exc:
            descriptor = describe_exception(exc)
            self.allocator.abandon(generation)
            raise AdoptionPreparationError(
                AdoptionPreparationStage.MATERIALIZATION,
                "ADOPTION_MATERIALIZATION_FAILED",
                f"{descriptor.error_type}[{descriptor.error_digest[:16]}]",
            ) from exc
        return MaterializedCandidate(generation, prepared)

    def abandon(self, generation: str) -> None:
        self.allocator.abandon(generation)
