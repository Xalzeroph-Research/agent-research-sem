from __future__ import annotations

from research_platform.platform.kernel import canonical_digest
from research_platform.participant.method.api import (
    MethodImplementation,
    MethodObservationOutboxFactoryPort,
    MethodRuntimeBinding,
    MethodRuntimeIdentity,
    MethodServices,
    MethodSession,
)

from .implementation import SelfEvolvingMemoryImplementation
from .session import SEMSession
from .session_assembly import SEMSessionAssembly
from .session_snapshot_contracts import SCHEMA_VERSION
from .session_state_api import SEMSessionStateFactory


class SelfEvolvingMemoryRuntime:
    """Session execution engine for SEM implementations.

    Runtime composition is intentionally separate from scientific implementation
    selection.  The runtime receives an implementation at session-open time and owns
    the session assembly/lifecycle mechanics only.
    """

    RUNTIME_ID = "sem.session_runtime"
    RUNTIME_VERSION = "1"
    RUNTIME_ABI_VERSION = "1"

    def __init__(
        self,
        state_factory: SEMSessionStateFactory,
        observation_outbox_factory: MethodObservationOutboxFactoryPort,
    ) -> None:
        self._state_factory = state_factory
        self._observation_outbox_factory = observation_outbox_factory
        artifact = canonical_digest(
            {
                "runtime_id": self.RUNTIME_ID,
                "runtime_version": self.RUNTIME_VERSION,
                "runtime_abi_version": self.RUNTIME_ABI_VERSION,
                "supported_snapshot_schema": SCHEMA_VERSION,
                "assembly_contract": "sem-session-assembly.v2",
                "session_state_backend": state_factory.backend_id,
            }
        )
        self._runtime_identity = MethodRuntimeIdentity(
            self.RUNTIME_ID,
            self.RUNTIME_VERSION,
            self.RUNTIME_ABI_VERSION,
            artifact,
        )

    @property
    def runtime_identity(self) -> MethodRuntimeIdentity:
        return self._runtime_identity

    def open_session(
        self,
        implementation: MethodImplementation,
        *,
        binding: MethodRuntimeBinding,
        session_id: str,
        services: MethodServices,
    ) -> MethodSession:
        if not isinstance(implementation, SelfEvolvingMemoryImplementation):
            raise TypeError("SelfEvolvingMemoryRuntime requires SelfEvolvingMemoryImplementation")
        if not isinstance(services, MethodServices):
            raise TypeError("SelfEvolvingMemoryRuntime requires MethodServices with an observation sink")
        base = implementation.identity
        if binding.implementation != base:
            raise ValueError("method runtime binding implementation identity does not match SEM implementation")
        if binding.runtime != self.runtime_identity:
            raise ValueError("method runtime binding runtime identity does not match SEM runtime")
        runtime = SEMSessionAssembly(
            implementation.serving_factory,
            implementation.evolution_factory,
            self._state_factory,
            self._observation_outbox_factory,
            implementation.deluxe_snapshot_factory,
        ).build(session_id, services.observation_sink, binding)
        return SEMSession(session_id, runtime)


__all__ = ["SelfEvolvingMemoryRuntime"]
