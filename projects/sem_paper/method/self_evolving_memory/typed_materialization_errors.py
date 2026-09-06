from __future__ import annotations


class TypedMaterializationError(ValueError):
    pass


class TypedGenerationDriftError(RuntimeError):
    pass


class TypedGenerationArtifactError(RuntimeError):
    pass


__all__ = [
    "TypedMaterializationError",
    "TypedGenerationDriftError",
    "TypedGenerationArtifactError",
]
