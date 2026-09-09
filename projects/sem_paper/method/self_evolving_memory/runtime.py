from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
import base64
from pathlib import Path
from typing import Any

from noetrium.contracts import canonical_digest
from noetrium.contracts.systems.participant__method import (
    MethodEndpointPort,
    MethodIdentity,
    MethodImplementation,
    MethodRuntimeIdentity,
    MethodRuntimeBinding,
    MethodServices,
    MethodSession,
    MethodSnapshot,
    MethodProgramIdentity,
)
from noetrium.contracts.systems.execution__workflow import (
    MethodNodeResult,
    MethodProgramBuilder,
    MethodRuntimeContext,
)
from noetrium.contracts.systems.model__request import ExecutionContext
from noetrium.platform import bind_method_endpoint
from noetrium.platform import (
    bind_method_checkpoint_store,
    bind_universal_method_machine,
    run_method_program,
)

from .core import SEMMethodSession, SEM_METHOD_ID


NOETRIUM_UMM_COMMIT = "e07a15671b92e0715e5652ddd78b5b550542bb26"


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
    endpoint = bind_method_endpoint(implementation, runtime)
    session = endpoint.open_session(
        session_id=session_id,
        services=MethodServices(_MethodObservationSink()),
    )
    return session, endpoint


def _json_record(value: object) -> dict[str, Any]:
    if is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, Mapping):
        raise TypeError("SEM UMM assignment result must be a dataclass or mapping")
    return dict(value)


def _snapshot_record(snapshot: MethodSnapshot) -> dict[str, object]:
    return {
        "method_id": snapshot.method_id,
        "implementation_version": snapshot.implementation_version,
        "schema_version": snapshot.schema_version,
        "method_runtime_binding_digest": snapshot.method_runtime_binding_digest,
        "session_id": snapshot.session_id,
        "payload_sha256": snapshot.payload_sha256,
        "opaque_payload_b64": base64.b64encode(snapshot.opaque_payload).decode("ascii"),
    }


def _snapshot_from_record(value: Mapping[str, object]) -> MethodSnapshot:
    return MethodSnapshot(
        method_id=str(value["method_id"]),
        implementation_version=str(value["implementation_version"]),
        schema_version=str(value["schema_version"]),
        method_runtime_binding_digest=str(value["method_runtime_binding_digest"]),
        session_id=str(value["session_id"]),
        payload_sha256=str(value["payload_sha256"]),
        opaque_payload=base64.b64decode(str(value["opaque_payload_b64"])),
    )


def run_sem_assignment_program(
    *,
    session: SEMMethodSession,
    implementation: SEMMethodImplementation,
    execution: ExecutionContext,
    checkpoint_root: str | Path,
    environment_run: Callable[[], tuple[object, ...]],
    decode_result: Callable[[Mapping[str, object]], object],
    resume: bool = False,
    max_seconds: float | None = None,
) -> tuple[tuple[object, ...], dict[str, object]]:
    """Host one SEM assignment inside Noetrium's universal method machine."""

    if not isinstance(session, SEMMethodSession):
        raise TypeError("SEM UMM requires SEMMethodSession")
    if not isinstance(implementation, SEMMethodImplementation):
        raise TypeError("SEM UMM requires SEMMethodImplementation")
    checkpoint_store = bind_method_checkpoint_store(checkpoint_root)
    machine = bind_universal_method_machine(
        checkpoint_store=checkpoint_store,
        max_steps=4,
        checkpoint_interval=1,
        max_seconds=max_seconds,
    )
    captured: dict[str, object] = {}

    def execute(request: object) -> MethodNodeResult:
        items = tuple(environment_run())
        snapshot = session.checkpoint()
        records = tuple(_json_record(item) for item in items)
        captured["results"] = items
        return MethodNodeResult(
            value={
                "assignment_run_id": execution.run_id,
                "task_count": len(records),
                "task_results_digest": canonical_digest(records),
            },
            state_update={
                "task_results": records,
                "method_snapshot": _snapshot_record(snapshot),
            },
            checkpoint=True,
        )

    def return_summary(request: object) -> MethodNodeResult:
        return MethodNodeResult(value=getattr(request, "previous_value", None))

    program_identity = MethodProgramIdentity(
        implementation.identity,
        implementation.configuration_digest,
    )
    program = (
        MethodProgramBuilder(program_identity, entrypoint="assignment.execute")
        .compute(
            "assignment.execute",
            "sem.assignment.execute",
            execute,
            ("assignment.return",),
            max_visits=1,
        )
        .return_node("assignment.return", "sem.assignment.return", return_summary)
        .build(
            configuration={
                "assignment_run_id": execution.run_id,
                "treatment_id": implementation.treatment_id,
                "seed": implementation.seed,
                "noetrium_umm_commit": NOETRIUM_UMM_COMMIT,
            },
            metric_names=("task_count", "task_results_digest"),
        )
    )
    runtime = MethodRuntimeContext(
        execution=execution,
        binding_plan_digest=canonical_digest({"assignment": execution.run_id}),
        runtime_binding_digest=canonical_digest({
            "runtime": "noetrium.universal-method-machine",
            "commit": NOETRIUM_UMM_COMMIT,
        }),
        schema_digest=canonical_digest({"input": "json", "state": "json", "output": "json"}),
    )
    result = run_method_program(
        program,
        runtime=runtime,
        input_value={
            "assignment_run_id": execution.run_id,
            "treatment_id": implementation.treatment_id,
            "seed": implementation.seed,
        },
        resume=resume,
        machine=machine,
    )
    if result.status.value != "succeeded":
        raise RuntimeError(
            f"SEM UMM assignment failed: {result.failure_code or result.status.value}: {result.failure}"
        )
    if "results" in captured:
        items = tuple(captured["results"])
    else:
        state = result.state
        rows = state.get("task_results", ())
        if not isinstance(rows, (tuple, list)):
            raise RuntimeError("SEM UMM resume checkpoint has no task results")
        items = tuple(decode_result(row) for row in rows if isinstance(row, Mapping))
        snapshot_value = state.get("method_snapshot")
        if not isinstance(snapshot_value, Mapping):
            raise RuntimeError("SEM UMM resume checkpoint has no method snapshot")
        session.restore(_snapshot_from_record(snapshot_value))
    checkpoint = checkpoint_store.load(execution.run_id)
    metadata: dict[str, object] = {
        "status": result.status.value,
        "resumed": bool(resume and "results" not in captured),
        "run_id": result.run_id,
        "program_digest": result.program_digest,
        "run_digest": result.run_digest,
        "step_count": result.step_count,
        "visit_counts": list(result.visit_counts),
        "evidence_status": result.evidence_status.value,
        "state_digest": canonical_digest(result.state),
        "checkpoint": (
            {"checkpoint_id": checkpoint.checkpoint_id, "sequence": checkpoint.sequence}
            if checkpoint is not None
            else None
        ),
    }
    return items, metadata


__all__ = [
    "SEMMethodImplementation",
    "SEMMethodSessionRuntime",
    "NOETRIUM_UMM_COMMIT",
    "open_sem_method_session",
    "run_sem_assignment_program",
]