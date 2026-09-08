from __future__ import annotations

from dataclasses import dataclass

from noetrium.contracts import canonical_digest
from noetrium.contracts.systems.participant__method import (
    MethodEndpointPort,
    MethodIdentity,
    MethodImplementation,
    MethodRuntimeIdentity,
    MethodRuntimeBinding,
    MethodServices,
    MethodSession,
)
from noetrium_platform.capabilities.participant.method.runtime import (
    DefaultMethodEndpointFactory,
)

from .core import SEMMethodSession, SEM_METHOD_ID


class _MethodObservationSink:
    """Explicit downstream sink for the Noe method-services boundary."""

    def record(self, observation: object) -> str:
        return str(getattr(observation, "observation_id", ""))


@dataclass(frozen=True, slots=True)
class SEMMethodImplementation:
    """SEM's scientific implementation/configuration identity."""

    treatment_id: str
    seed: str
    initial_memory: tuple[str, ...] = ()

    @property
    def identity(self) -> MethodIdentity:
        return MethodIdentity(
            SEM_METHOD_ID,
            "3.0.0",
            "1",
            "1",
            canonical_digest(
                {
                    "treatment_id": self.treatment_id,
                    "seed": self.seed,
                    "initial_memory": self.initial_memory,
                }
            ),
        )

    @property
    def configuration_digest(self) -> str:
        return canonical_digest(
            {
                "treatment_id": self.treatment_id,
                "seed": self.seed,
                "initial_memory": self.initial_memory,
            }
        )


class SEMMethodSessionRuntime:
    """Noe MethodSessionRuntime adapter for the SEM implementation."""

    @property
    def runtime_identity(self) -> MethodRuntimeIdentity:
        return MethodRuntimeIdentity(
            "sem.method-session-runtime",
            "1.0.0",
            "1",
            canonical_digest(
                {
                    "runtime": "sem.method-session-runtime",
                    "implementation": SEM_METHOD_ID,
                }
            ),
        )

    def open_session(
        self,
        implementation: MethodImplementation,
        *,
        binding: MethodRuntimeBinding,
        session_id: str,
        services: MethodServices,
    ) -> MethodSession:
        if not isinstance(implementation, SEMMethodImplementation):
            raise TypeError("SEM runtime requires SEMMethodImplementation")
        if binding.implementation != implementation.identity:
            raise ValueError("SEM method/runtime binding identity mismatch")
        if not isinstance(services, MethodServices):
            raise TypeError("SEM method session requires Noe MethodServices")
        return SEMMethodSession(
            session_id=session_id,
            treatment_id=implementation.treatment_id,
            seed=implementation.seed,
            initial_memory=implementation.initial_memory,
        )


def open_sem_method_session(
    *,
    session_id: str,
    treatment_id: str,
    seed: str,
    initial_memory: tuple[str, ...] = (),
) -> tuple[SEMMethodSession, MethodEndpointPort]:
    """Open SEM through Noe's public method endpoint/runtime boundary."""

    implementation = SEMMethodImplementation(treatment_id, seed, initial_memory)
    runtime = SEMMethodSessionRuntime()
    endpoint = DefaultMethodEndpointFactory().bind(implementation, runtime)
    session = endpoint.open_session(
        session_id=session_id,
        services=MethodServices(_MethodObservationSink()),
    )
    return session, endpoint


__all__ = [
    "SEMMethodImplementation",
    "SEMMethodSessionRuntime",
    "open_sem_method_session",
]