from __future__ import annotations

import hashlib
import json

from research_platform.participant.method.api import MethodIdentity

from .authority import validate_tier_authority
from .session_evolution_api import SessionEvolutionFactory
from .session_serving_api import DeluxeSnapshotFactory, SessionServingFactory
from .serving_providers import build_deluxe_session_serving, build_hybrid_session_serving
from .session_snapshot_contracts import IMPLEMENTATION_VERSION, SCHEMA_VERSION


class SelfEvolvingMemoryImplementation:
    """Scientific SEM implementation/configuration with no runtime lifecycle authority."""

    DEFAULT_SERVING_PROVIDER_ID = "sem.serving.hybrid_lexical_recency.v1"

    def __init__(
        self,
        *,
        evolution_factory: SessionEvolutionFactory,
        evolution_provider_id: str,
        serving_factory: SessionServingFactory = build_hybrid_session_serving,
        serving_provider_id: str | None = None,
        deluxe_snapshot_factory: DeluxeSnapshotFactory | None = None,
        configuration_digest: str | None = None,
    ) -> None:
        validate_tier_authority()
        custom_serving = serving_factory is not build_hybrid_session_serving
        if custom_serving and not serving_provider_id:
            raise ValueError("custom SEM serving factory requires stable serving_provider_id")
        if not evolution_provider_id.strip():
            raise ValueError("SEM implementation requires stable evolution_provider_id")
        if serving_factory is build_deluxe_session_serving and deluxe_snapshot_factory is None:
            raise ValueError("Deluxe serving requires an explicit typed snapshot factory")
        if configuration_digest is not None and (
            len(configuration_digest) != 64
            or any(char not in "0123456789abcdef" for char in configuration_digest.lower())
        ):
            raise ValueError("SEM configuration_digest must be a SHA-256 digest when provided")

        self._serving_factory = serving_factory
        self._evolution_factory = evolution_factory
        self._deluxe_snapshot_factory = deluxe_snapshot_factory
        self._configuration_digest = configuration_digest
        self.serving_provider_id = serving_provider_id or self.DEFAULT_SERVING_PROVIDER_ID
        self.evolution_provider_id = evolution_provider_id
        raw = json.dumps(
            {
                "serving_provider_id": self.serving_provider_id,
                "evolution_provider_id": self.evolution_provider_id,
                "configuration_digest": self._configuration_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._artifact_digest = hashlib.sha256(raw).hexdigest()
        self._identity = MethodIdentity(
            "self_evolving_memory",
            IMPLEMENTATION_VERSION,
            "1",
            SCHEMA_VERSION,
            self._artifact_digest,
        )

    @property
    def identity(self) -> MethodIdentity:
        return self._identity

    @property
    def serving_factory(self) -> SessionServingFactory:
        return self._serving_factory

    @property
    def evolution_factory(self) -> SessionEvolutionFactory:
        return self._evolution_factory

    @property
    def deluxe_snapshot_factory(self) -> DeluxeSnapshotFactory | None:
        return self._deluxe_snapshot_factory

    @property
    def configuration_digest(self) -> str | None:
        return self._configuration_digest


__all__ = ["SelfEvolvingMemoryImplementation"]
