from __future__ import annotations

from collections.abc import Mapping

from research_platform.data.state.api import AtomicStateStorePort

from .typed_materialization import (
    TypedGenerationArtifactError,
    TypedGenerationArtifactPort,
    TypedMaterializedGeneration,
)


class AtomicTypedGenerationArtifactSource(TypedGenerationArtifactPort):
    """Read-only typed artifact source backed by the existing adoption aggregate."""

    def __init__(self, state: AtomicStateStorePort, *, architecture_aggregate: str) -> None:
        if not architecture_aggregate.strip():
            raise ValueError("typed artifact architecture aggregate is required")
        self._state = state
        self._architecture_aggregate = architecture_aggregate

    def load(self, generation: str) -> TypedMaterializedGeneration:
        if not generation.strip():
            raise TypedGenerationArtifactError("typed artifact generation is required")
        aggregate = self._state.read(self._architecture_aggregate)
        if aggregate.generation != generation:
            raise TypedGenerationArtifactError(
                f"architecture aggregate generation {aggregate.generation} does not match requested {generation}"
            )
        payload = aggregate.payload
        if not isinstance(payload, Mapping):
            raise TypedGenerationArtifactError("architecture aggregate payload is not a mapping")
        document = payload.get("typed_generation")
        if not isinstance(document, Mapping):
            raise TypedGenerationArtifactError("adopted architecture has no typed generation artifact")
        try:
            restored = TypedMaterializedGeneration.from_document(dict(document))
        except Exception as exc:
            raise TypedGenerationArtifactError("persisted typed generation artifact is invalid") from exc
        if restored.generation != generation:
            raise TypedGenerationArtifactError(
                f"persisted typed generation {restored.generation} does not match requested {generation}"
            )
        return restored


__all__ = ["AtomicTypedGenerationArtifactSource"]
