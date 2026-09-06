from __future__ import annotations

from .grounded_transform import GroundedSemanticTransformer


class MinecraftGroundedSemanticTransformer(GroundedSemanticTransformer):
    """Compatibility name for the MC adapter using the grounded SEM schema."""


__all__ = ["MinecraftGroundedSemanticTransformer"]
