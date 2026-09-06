from __future__ import annotations

from collections.abc import Callable
import base64
from dataclasses import replace
import hashlib
import json
from typing import Protocol

from research_platform.environment.minecraft.api import (
    MinecraftBranchRuntimeFactoryPort,
    MinecraftBranchRuntimePort,
    MinecraftBranchRuntimeRequest,
    MinecraftWorldBranch,
)
from research_platform.participant.method.api import (
    MethodObservationSink,
    MethodServices,
    MethodSession,
    MethodSnapshot,
)
from research_platform.experimentation.checkpoint.api import WorkloadCheckpointComponentPort
from research_platform.platform.kernel import ExecutionContext, canonical_digest
from research_platform.platform.kernel import canonical_bytes
from research_platform.experimentation.run.api import RunArtifactKind, RunArtifactStorePort
from research_platform.experimentation.study.api import VariantBinding, VariantKind

from projects.sem_paper.method.self_evolving_memory.evolution import BranchRole, CandidateArchitecture

from .minecraft_evidence import SEMMinecraftEvidenceIngestor, MinecraftEvidenceAdapter
from .minecraft_cognition_checkpoint import MinecraftCognitionCheckpointState
from projects.sem_paper.method.self_evolving_memory.evidence_audit import AuditEvidence, AuditEvidenceStore
from projects.sem_paper.method.self_evolving_memory.evidence_eval import EvalEvidenceStore
from projects.sem_paper.method.self_evolving_memory.evidence_eval import EvalEvidence
from .minecraft_runtime_adapter import MinecraftWorkloadEnvironmentAdapter
from .candidate_method import is_fixed_provider
from .minecraft_workload import (
    MinecraftEvidencePort,
    MinecraftPlannerPort,
    MinecraftTaskSpec,
    MinecraftTaskRunResult,
    MinecraftWorkloadDiagnosticsPort,
    MinecraftWorkloadEnvironmentPort,
    MinecraftCognitionFactoryPort,
    minecraft_task_manifest_digest,
    validate_task_manifest,
)
from .project import SemPaperProjectComposition


class SemPaperWorkloadBindingError(RuntimeError):
    """A Paper workload binding failed before or during resource cleanup."""

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        cause: BaseException | None = None,
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.cause = cause
        self.cleanup_errors = cleanup_errors


class SemPaperBranchRuntimeRequestFactoryPort(Protocol):
    def build(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
    ) -> MinecraftBranchRuntimeRequest: ...


class SemPaperPlannerFactoryPort(Protocol):
    def create(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        task: MinecraftTaskSpec,
        method: MethodSession,
    ) -> MinecraftPlannerPort: ...


class SemPaperMethodObservationSinkFactoryPort(Protocol):
    def create(
        self,
        *,
        role: BranchRole,
        branch: MinecraftWorldBranch,
    ) -> MethodObservationSink: ...


class MinecraftEvaluationEvidencePort(Protocol):
    """Project evaluation seam; it never exposes the method memory store."""

    def record(
        self,
        *,
        task: MinecraftTaskSpec,
        result: MinecraftTaskRunResult,
        context: ExecutionContext,
    ) -> None: ...


class _EvalEvidenceAdapter:
    def __init__(self, store: EvalEvidenceStore) -> None:
        self._store = store

    def record(
        self,
        *,
        task: MinecraftTaskSpec,
        result: MinecraftTaskRunResult,
        context: ExecutionContext,
    ) -> None:
        payload = {
            "task_id": task.task_id,
            "family": task.family,
            "lineage_id": task.lineage_id,
            "success": result.success,
            "utility": result.utility,
            "steps": result.steps,
            "duration_s": result.duration_s,
            "failure_reason": result.failure_reason,
            "failure_scope": result.failure_scope,
            "run_id": context.run_id,
            "study_id": context.study_id,
            "branch_id": context.branch_id,
            "environment_generation": context.generation("environment"),
        }
        self._store.append(
            EvalEvidence(
                eval_id="mceval_" + canonical_digest(payload)[:32],
                payload=payload,
            )
        )


class _MinecraftEnvironmentCheckpointComponent(WorkloadCheckpointComponentPort):
    component_id = "environment.session"
    codec_id = "minecraft.environment.session.bytes"
    schema_version = "1"

    def __init__(self, environment: MinecraftWorkloadEnvironmentAdapter) -> None:
        self._environment = environment

    def capture(self) -> bytes:
        return self._environment.checkpoint()

    def restore(self, payload: bytes) -> None:
        self._environment.restore(payload)


class _MethodSnapshotCheckpointComponent(WorkloadCheckpointComponentPort):
    component_id = "method.session"
    codec_id = "participant.method.snapshot.json"
    schema_version = "1"

    def __init__(self, method: MethodSession) -> None:
        self._method = method

    def capture(self) -> bytes:
        snapshot = self._method.checkpoint()
        document = {
            "method_id": snapshot.method_id,
            "implementation_version": snapshot.implementation_version,
            "schema_version": snapshot.schema_version,
            "method_runtime_binding_digest": snapshot.method_runtime_binding_digest,
            "session_id": snapshot.session_id,
            "payload_sha256": snapshot.payload_sha256,
            "opaque_payload_base64": base64.b64encode(snapshot.opaque_payload).decode("ascii"),
        }
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def restore(self, payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8"))
            opaque = base64.b64decode(str(document["opaque_payload_base64"]), validate=True)
            snapshot = MethodSnapshot(
                method_id=str(document["method_id"]),
                implementation_version=str(document["implementation_version"]),
                schema_version=str(document["schema_version"]),
                method_runtime_binding_digest=str(document["method_runtime_binding_digest"]),
                session_id=str(document["session_id"]),
                payload_sha256=str(document["payload_sha256"]),
                opaque_payload=opaque,
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid method checkpoint component document") from exc
        self._method.restore(snapshot)


class _AuditEvidenceCheckpointComponent(WorkloadCheckpointComponentPort):
    component_id = "evidence.audit"
    codec_id = "sem-paper.audit-evidence.json"
    schema_version = "1"

    def __init__(self, store: AuditEvidenceStore) -> None:
        self._store = store

    def capture(self) -> bytes:
        return canonical_bytes({"rows": self._store.snapshot()})

    def restore(self, payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8"))
            rows = tuple(
                AuditEvidence(audit_id=str(row["audit_id"]), payload=row.get("payload"))
                for row in document["rows"]
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid audit evidence checkpoint document") from exc
        self._store.restore(rows)


class _EvalEvidenceCheckpointComponent(WorkloadCheckpointComponentPort):
    component_id = "evidence.eval"
    codec_id = "sem-paper.eval-evidence.json"
    schema_version = "1"

    def __init__(self, store: EvalEvidenceStore) -> None:
        self._store = store

    def capture(self) -> bytes:
        return canonical_bytes({"rows": self._store.snapshot()})

    def restore(self, payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8"))
            rows = tuple(
                EvalEvidence(eval_id=str(row["eval_id"]), payload=row.get("payload"))
                for row in document["rows"]
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid evaluation evidence checkpoint document") from exc
        self._store.restore(rows)


class SemPaperMinecraftWorkloadBinding:
    """One fully opened Paper workload binding over a branch runtime."""

    def __init__(
        self,
        *,
        workload_id: str,
        task_manifest_digest: str,
        context: ExecutionContext,
        tasks: tuple[MinecraftTaskSpec, ...],
        environment: MinecraftWorkloadEnvironmentPort,
        method: MethodSession,
        evidence: MinecraftEvidencePort,
        diagnostics: MinecraftWorkloadDiagnosticsPort | None,
        runtime: MinecraftBranchRuntimePort,
        source_cut_id: str,
        environment_session: MinecraftWorkloadEnvironmentAdapter,
        method_generation: str,
        audit_store: AuditEvidenceStore,
        eval_store: EvalEvidenceStore,
        artifact_store: RunArtifactStorePort | None,
        evidence_artifact_prefix: str | None,
        branch_writes: tuple[str, ...],
        cognition_factory: MinecraftCognitionFactoryPort | None,
    ) -> None:
        self.workload_id = workload_id
        self.environment_generation = runtime.environment_generation
        if not self.environment_generation.strip():
            raise ValueError("Paper workload binding requires environment generation evidence")
        self.task_manifest_digest = task_manifest_digest
        self.context = context
        self.run_id = context.run_id
        self.study_id = context.study_id or ""
        self.branch_id = context.branch_id or ""
        self.source_cut_id = source_cut_id
        self.method_generation = method_generation
        self.tasks = tasks
        self.environment = environment
        self.method = method
        self.evidence = evidence
        self.diagnostics = diagnostics
        self.cognition_factory = cognition_factory
        self.cognition_checkpoints = (
            MinecraftCognitionCheckpointState() if cognition_factory is not None else None
        )
        self.branch_writes = branch_writes
        self.lifetime_writes: tuple[str, ...] = ()
        self.private_to_method_flows: tuple[str, ...] = ()
        self.audit_store = audit_store
        self.eval_store = eval_store
        self.evaluation: MinecraftEvaluationEvidencePort = _EvalEvidenceAdapter(eval_store)
        self.artifact_store = artifact_store
        self.evidence_artifact_prefix = evidence_artifact_prefix
        self._runtime = runtime
        base_components: tuple[WorkloadCheckpointComponentPort, ...] = (
            _MinecraftEnvironmentCheckpointComponent(environment_session),
            _MethodSnapshotCheckpointComponent(method),
            _AuditEvidenceCheckpointComponent(audit_store),
            _EvalEvidenceCheckpointComponent(eval_store),
        )
        self._checkpoint_components = (
            base_components
            if self.cognition_checkpoints is None
            else base_components + (self.cognition_checkpoints,)
        )
        self._evidence_exported = False
        self._method_closed = False
        self._runtime_closed = False
        self._closed = False

    def planner_for(self, task: MinecraftTaskSpec) -> MinecraftPlannerPort:
        raise RuntimeError("planner binding was not attached")

    def record_result(
        self,
        *,
        task: MinecraftTaskSpec,
        result: MinecraftTaskRunResult,
        context: ExecutionContext,
    ) -> None:
        self.evaluation.record(task=task, result=result, context=context)

    def checkpoint_components(self) -> tuple[WorkloadCheckpointComponentPort, ...]:
        return self._checkpoint_components

    @property
    def audit_rows(self):
        return self.audit_store.snapshot()

    @property
    def eval_rows(self):
        return self.eval_store.snapshot()

    def _export_evidence(self) -> None:
        if self.artifact_store is None or self.evidence_artifact_prefix is None:
            return
        rows_by_name: dict[str, tuple[object, ...]] = {
            "j_audit.jsonl": self.audit_rows,
            "j_eval.jsonl": self.eval_rows,
        }
        artifact_manifest: dict[str, dict[str, object]] = {}
        for name, rows in rows_by_name.items():
            body = "".join(
                json.dumps(
                    {
                        "id": getattr(row, "audit_id", None) or getattr(row, "eval_id"),
                        "payload": row.payload,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
                for row in rows
            )
            encoded = body.encode("utf-8")
            self.artifact_store.publish_text(
                f"{self.evidence_artifact_prefix}/{name}",
                body,
                kind=RunArtifactKind.EVIDENCE,
            )
            artifact_manifest[name] = {
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "size_bytes": len(encoded),
                "row_count": len(rows),
            }
        self.artifact_store.publish_json(
            f"{self.evidence_artifact_prefix}/evidence_manifest.json",
            {
                "schema_version": "sem-paper.minecraft-evidence-manifest.v2",
                "run_id": self.run_id,
                "study_id": self.study_id,
                "workload_id": self.workload_id,
                "branch_id": self.branch_id,
                "source_cut_id": self.source_cut_id,
                "task_manifest_digest": self.task_manifest_digest,
                "audit_count": len(self.audit_rows),
                "eval_count": len(self.eval_rows),
                "audit_ids": [row.audit_id for row in self.audit_rows],
                "eval_ids": [row.eval_id for row in self.eval_rows],
                "artifacts": artifact_manifest,
            },
            kind=RunArtifactKind.EVIDENCE,
        )

    def close(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        if not self._evidence_exported:
            try:
                self._export_evidence()
                self._evidence_exported = True
            except BaseException as exc:
                errors.append(exc)
        if not self._method_closed:
            try:
                self.method.close()
                self._method_closed = True
            except BaseException as exc:
                errors.append(exc)
        if not self._runtime_closed:
            try:
                self._runtime.close()
                self._runtime_closed = True
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise SemPaperWorkloadBindingError(
                f"Paper workload close failed ({len(errors)} cleanup errors)",
                phase="close",
                cleanup_errors=tuple(errors),
            ) from errors[0]
        self._closed = True

class _BoundSemPaperMinecraftWorkload(SemPaperMinecraftWorkloadBinding):
    def __init__(self, *, planner_factory: SemPaperPlannerFactoryPort, role: BranchRole, candidate: CandidateArchitecture | None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._planner_factory = planner_factory
        self._role = role
        self._candidate = candidate

    def planner_for(self, task: MinecraftTaskSpec) -> MinecraftPlannerPort:
        return self._planner_factory.create(
            role=self._role,
            candidate=self._candidate,
            task=task,
            method=self.method,
        )


class SemPaperMinecraftWorkloadBindingFactory:
    """Project-owned workload binder over the environment branch port."""

    def __init__(
        self,
        *,
        composition: SemPaperProjectComposition,
        branch_runtime_factory: MinecraftBranchRuntimeFactoryPort,
        request_factory: SemPaperBranchRuntimeRequestFactoryPort,
        planner_factory: SemPaperPlannerFactoryPort,
        observation_sink_factory: SemPaperMethodObservationSinkFactoryPort,
        tasks: tuple[MinecraftTaskSpec, ...],
        context: ExecutionContext,
        workload_id_factory: Callable[[BranchRole, MinecraftWorldBranch], str],
        diagnostics: MinecraftWorkloadDiagnosticsPort | None = None,
        artifact_store: RunArtifactStorePort | None = None,
        cognition_factory: MinecraftCognitionFactoryPort | None = None,
    ) -> None:
        if not tasks:
            raise ValueError("Paper workload binding requires an explicit non-empty task manifest")
        if not callable(workload_id_factory):
            raise ValueError("Paper workload_id_factory is required")
        self._composition = composition
        self._branch_runtime_factory = branch_runtime_factory
        self._request_factory = request_factory
        self._planner_factory = planner_factory
        self._observation_sink_factory = observation_sink_factory
        self._tasks = validate_task_manifest(tasks)
        self._context = context
        self._task_manifest_digest = minecraft_task_manifest_digest(self._tasks)
        self._workload_id_factory = workload_id_factory
        self._diagnostics = diagnostics
        self._artifact_store = artifact_store
        self._cognition_factory = cognition_factory

    def open(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
        variant_binding: VariantBinding | None = None,
    ) -> SemPaperMinecraftWorkloadBinding:
        if role is BranchRole.CONTROL and candidate is not None:
            raise SemPaperWorkloadBindingError("control workload received a candidate", phase="validate")
        if role is BranchRole.CANDIDATE:
            if candidate is None:
                raise SemPaperWorkloadBindingError("candidate workload has no candidate", phase="validate")
            if (
                variant_binding is None
                and self._composition.bindings.candidate_method_materializer is None
            ):
                raise SemPaperWorkloadBindingError(
                    "candidate method materializer is not composed",
                    phase="method_materialization",
                )
        if variant_binding is not None:
            expected_role = (
                BranchRole.CONTROL
                if variant_binding.variant.kind is VariantKind.CONTROL
                else BranchRole.CANDIDATE
            )
            if role is not expected_role:
                raise SemPaperWorkloadBindingError(
                    "Minecraft role does not match the compiled variant binding",
                    phase="validate",
                )
            if self._composition.bindings.variant_method_endpoint_factory is None:
                raise SemPaperWorkloadBindingError(
                    "compiled variant binding has no endpoint factory",
                    phase="method_materialization",
                )
        request = self._request_factory.build(role=role, candidate=candidate, branch=branch)
        runtime = self._branch_runtime_factory.open(request)
        method: MethodSession | None = None
        try:
            if variant_binding is not None:
                endpoint = self._composition.bindings.variant_method_endpoint_factory.endpoint_for(
                    binding=variant_binding,
                    candidate=None if is_fixed_provider(variant_binding.provider_id) else candidate,
                )
            elif role is BranchRole.CONTROL:
                endpoint = self._composition.bindings.fixed_memory
            else:
                materializer = self._composition.bindings.candidate_method_materializer
                if materializer is None or candidate is None:
                    raise SemPaperWorkloadBindingError(
                        "candidate endpoint cannot be materialized",
                        phase="method_materialization",
                    )
                endpoint = materializer.materialize(candidate)
            observation_sink = self._observation_sink_factory.create(role=role, branch=branch)
            services = MethodServices(observation_sink=observation_sink)
            environment_session = runtime.open_session(services)
            environment_adapter = MinecraftWorkloadEnvironmentAdapter(environment_session)
            method = endpoint.open_session(
                session_id=f"{branch.branch_id}:method",
                services=services,
            )
            audit = AuditEvidenceStore()
            evaluation = EvalEvidenceStore()
            evidence = SEMMinecraftEvidenceIngestor(method, audit, MinecraftEvidenceAdapter())
            branch_writes = (
                f"{branch.branch_id}:j_mem",
                f"{branch.branch_id}:j_audit",
                f"{branch.branch_id}:j_eval",
            )
            evidence_prefix = (
                f"evidence/{branch.branch_id.replace(':', '_')}"
                if self._artifact_store is not None
                else None
            )
            return _BoundSemPaperMinecraftWorkload(
                planner_factory=self._planner_factory,
                role=role,
                candidate=candidate,
                workload_id=self._workload_id_factory(role, branch),
                task_manifest_digest=self._task_manifest_digest,
                context=replace(
                    self._context,
                    condition_id=role.value,
                    branch_id=branch.branch_id,
                    task_id=None,
                    decision_cycle_id=None,
                ),
                tasks=self._tasks,
                environment=environment_adapter,
                method=method,
                source_cut_id=branch.cut_id,
                environment_session=environment_adapter,
                method_generation=method.checkpoint().method_runtime_binding_digest,
                evidence=evidence,
                diagnostics=self._diagnostics,
                runtime=runtime,
                audit_store=audit,
                eval_store=evaluation,
                artifact_store=self._artifact_store,
                evidence_artifact_prefix=evidence_prefix,
                branch_writes=branch_writes,
                cognition_factory=self._cognition_factory,
            )
        except BaseException as exc:
            errors: list[BaseException] = []
            if method is not None:
                try:
                    method.close()
                except BaseException as cleanup_exc:
                    errors.append(cleanup_exc)
            try:
                runtime.close()
            except BaseException as cleanup_exc:
                errors.append(cleanup_exc)
            if errors:
                raise SemPaperWorkloadBindingError(
                    "Paper workload open failed and cleanup failed",
                    phase="open",
                    cause=exc,
                    cleanup_errors=tuple(errors),
                ) from exc
            raise SemPaperWorkloadBindingError(
                "Paper workload open failed",
                phase="open",
                cause=exc,
            ) from exc


__all__ = [
    "SemPaperBranchRuntimeRequestFactoryPort",
    "SemPaperMethodObservationSinkFactoryPort",
    "MinecraftEvaluationEvidencePort",
    "SemPaperMinecraftWorkloadBinding",
    "SemPaperMinecraftWorkloadBindingFactory",
    "SemPaperPlannerFactoryPort",
    "SemPaperWorkloadBindingError",
]
