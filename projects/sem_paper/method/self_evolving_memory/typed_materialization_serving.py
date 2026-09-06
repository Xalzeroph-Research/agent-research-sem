from __future__ import annotations

from typing import Protocol

from .architecture import MemoryArchitectureSpec
from .architecture.projection import NodePartitionedDeluxeSnapshot
from .architecture.validation import ArchitectureValidator
from .deluxe.api.ports import DeluxeServingSource
from .materialization import MaterializationContract
from .session_state_api import SEMSessionStatePort
from .typed_builders import (
    SemPaperTypedMaterializationConfiguration,
    TypedSemanticNodeTransformPort,
    build_sem_paper_typed_materialization_configuration,
)
from .typed_materialization_errors import TypedGenerationArtifactError, TypedGenerationDriftError, TypedMaterializationError
from .typed_materialization_generation import TypedMaterializedGeneration
from .typed_materialization_runtime import PinnedEvidenceMaterializationSource, TypedMemoryMaterializer, TypedNodeBuilderPort


class TypedGenerationArtifactPort(Protocol):
    def load(self, generation: str) -> TypedMaterializedGeneration: ...


class LiveTypedDeluxeSnapshotSource(DeluxeServingSource):
    """Build one Deluxe read projection from the session's pinned J_mem cut.

    This is a read-side derivation only. The session state remains the sole
    evidence and generation authority; the typed generation is never written
    back by serving.
    """

    def __init__(
        self,
        state: SEMSessionStatePort,
        *,
        architecture: MemoryArchitectureSpec,
        contracts: tuple[MaterializationContract, ...],
        builder: TypedNodeBuilderPort,
        candidate_id: str,
    ) -> None:
        if not candidate_id.strip():
            raise TypedMaterializationError("live Deluxe snapshot candidate_id is required")
        self._state = state
        self._architecture = architecture
        self._contracts = contracts
        self._builder = builder
        self._candidate_id = candidate_id

    def open_deluxe_snapshot(self):
        generation, evidence = self._state.open_serving_cut()
        typed = TypedMemoryMaterializer(
            PinnedEvidenceMaterializationSource(evidence),
            self._builder,
        ).build(
            generation,
            base_generation=generation,
            candidate_id=self._candidate_id,
            architecture=self._architecture,
            contracts=self._contracts,
        )
        return typed.deluxe_snapshot()


def build_live_typed_snapshot_factory(
    *,
    architecture: MemoryArchitectureSpec,
    contracts: tuple[MaterializationContract, ...],
    builder: TypedNodeBuilderPort,
    candidate_id: str = "deluxe.live.read.v1",
):
    """Compose a session-bound Deluxe factory over pinned canonical evidence."""

    ArchitectureValidator().verify(architecture)
    return lambda state: LiveTypedDeluxeSnapshotSource(
        state,
        architecture=architecture,
        contracts=contracts,
        builder=builder,
        candidate_id=candidate_id,
    )


def build_sem_paper_live_deluxe_snapshot_factory(
    transformer: TypedSemanticNodeTransformPort,
    *,
    preset: str = "seed_c_v018",
    candidate_id: str = "deluxe.live.sem_paper.v1",
):
    """Build the current Paper Deluxe read factory from an explicit transform seam."""

    configuration: SemPaperTypedMaterializationConfiguration = build_sem_paper_typed_materialization_configuration(
        transformer,
        preset=preset,
    )
    return build_live_typed_snapshot_factory(
        architecture=configuration.architecture,
        contracts=configuration.contracts,
        builder=configuration.builder,
        candidate_id=candidate_id,
    )


class AdoptedTypedGenerationSource(DeluxeServingSource):
    """Read provider for one generation after the authoritative state adopts it."""

    def __init__(self, state: SEMSessionStatePort, generation: TypedMaterializedGeneration) -> None:
        self._state = state
        self._generation = generation

    def open_deluxe_snapshot(self) -> NodePartitionedDeluxeSnapshot:
        current = self._state.current_generation()
        if current != self._generation.generation:
            raise TypedGenerationDriftError(
                f"typed Deluxe generation {self._generation.generation} is not adopted; current is {current}"
            )
        return self._generation.deluxe_snapshot()


def build_adopted_typed_snapshot_factory(generation: TypedMaterializedGeneration):
    """Compose a session factory around one already-adopted typed generation."""

    def factory(state: SEMSessionStatePort) -> AdoptedTypedGenerationSource:
        return AdoptedTypedGenerationSource(state, generation)

    return factory


class PersistedAdoptedTypedGenerationSource(DeluxeServingSource):
    """Reload typed memory from an injected authoritative artifact source."""

    def __init__(self, state: SEMSessionStatePort, artifacts: TypedGenerationArtifactPort) -> None:
        self._state = state
        self._artifacts = artifacts

    def open_deluxe_snapshot(self) -> NodePartitionedDeluxeSnapshot:
        current = self._state.current_generation()
        try:
            generation = self._artifacts.load(current)
        except Exception as exc:
            if isinstance(exc, TypedGenerationArtifactError):
                raise
            raise TypedGenerationArtifactError(f"failed to load adopted typed generation {current}") from exc
        if generation.generation != current:
            raise TypedGenerationDriftError(
                f"artifact generation {generation.generation} does not match adopted generation {current}"
            )
        return generation.deluxe_snapshot()


def build_persisted_adopted_typed_snapshot_factory(artifacts: TypedGenerationArtifactPort):
    def factory(state: SEMSessionStatePort) -> PersistedAdoptedTypedGenerationSource:
        return PersistedAdoptedTypedGenerationSource(state, artifacts)

    return factory


__all__ = [
    "TypedGenerationArtifactPort",
    "LiveTypedDeluxeSnapshotSource",
    "build_live_typed_snapshot_factory",
    "build_sem_paper_live_deluxe_snapshot_factory",
    "AdoptedTypedGenerationSource",
    "PersistedAdoptedTypedGenerationSource",
    "build_adopted_typed_snapshot_factory",
    "build_persisted_adopted_typed_snapshot_factory",
]
