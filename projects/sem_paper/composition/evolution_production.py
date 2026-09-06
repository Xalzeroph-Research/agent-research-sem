from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import threading

from research_platform.data.state.api import AggregateValue, AtomicStateStorePort
from research_platform.environment.minecraft.api import MinecraftWorldCutPort
from research_platform.model.request.prompt.api import (
    PromptBodyContext,
    PromptDynamicBlock,
    PromptRequestBindingPort,
)
from research_platform.model.serving.endpoint import (
    ModelEndpointPort,
    ModelEndpointRequest,
    ModelEndpointResponse,
)
from research_platform.platform.kernel import (
    ExecutionContext,
    ImmutableModelIdentity,
    JsonObject,
    canonical_digest,
)
from projects.sem_paper.method.self_evolving_memory.adoption import (
    AtomicAdoptionService,
    GenerationAllocator,
)
from projects.sem_paper.method.self_evolving_memory.architecture import (
    MemoryArchitectureSpec,
    architecture_from_dict,
    architecture_to_dict,
)
from projects.sem_paper.method.self_evolving_memory.architecture.contracts import (
    PredicateAtom,
    PredicateOp,
    PrimitiveType,
    RecordSelector,
)
from projects.sem_paper.method.self_evolving_memory.architecture.edits import (
    CreateNodeEdit,
    MergeNodesEdit,
    MemoryNodeDraft,
    RetireNodeEdit,
    SplitChildDraft,
    SplitNodeEdit,
)
from projects.sem_paper.method.self_evolving_memory.evolution import (
    ArchitectureObservationReport,
    BranchRole,
    CandidateArchitecture,
    EditKind,
    EvaluationProof,
    PairedBranchEvaluator,
    StructuralIntent,
)
from projects.sem_paper.method.self_evolving_memory.materialization import Materializer
from projects.sem_paper.method.self_evolving_memory.session_evolution_api import (
    EvolutionReconciliation,
    EvolutionReconciliationStatus,
    SessionAdoptionAuthority,
)
from research_platform.platform.kernel.errors import describe_exception

from .minecraft_branch import MinecraftBranchExecutorPort, MinecraftPairedBranchRunner


class QualifiedMetaProposalError(RuntimeError):
    def __init__(self, message: str, *, phase: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.phase = phase
        self.cause = cause


@dataclass(frozen=True, slots=True)
class QualifiedMetaProposalBinding:
    prompt_requests: PromptRequestBindingPort
    model: ImmutableModelIdentity
    deployment_id: str
    deployment_generation: str
    context_length: int
    endpoint: ModelEndpointPort
    context: ExecutionContext

    def __post_init__(self) -> None:
        if not self.deployment_id.strip() or len(self.deployment_generation) != 64:
            raise ValueError("SEM Meta proposal requires exact deployment identity")
        if self.context_length <= 0:
            raise ValueError("SEM Meta proposal context_length must be positive")


def _report_document(report: ArchitectureObservationReport) -> dict[str, object]:
    return {
        "generation": report.generation,
        "neutral_summary": report.neutral_summary,
        "evidence_refs": list(report.evidence_refs),
        "architecture": (
            architecture_to_dict(report.architecture)
            if report.architecture is not None
            else None
        ),
        "node_profiles": [asdict(item) for item in report.node_profiles],
        "pairs": [asdict(item) for item in report.pairs],
        "incident_counts": [list(item) for item in report.incident_counts],
        "unresolved_intent_clusters": [
            asdict(item) for item in report.unresolved_intent_clusters
        ],
    }


def _prompt_block(value: object) -> PromptDynamicBlock:
    return PromptDynamicBlock(
        "architecture_observation",
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        canonical_digest(value),
        10,
    )


def _qwen_json_body(context: PromptBodyContext) -> JsonObject:
    return {
        "messages": [{"role": "user", "content": context.compiled_text}],
        "model": context.model_id,
        "temperature": context.temperature,
        "top_p": context.top_p,
        "max_tokens": context.max_output_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "structural_intent_v2", "strict": True,
                "schema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["edit", "rationale", "evidence_refs"],
                    "properties": {
                        "edit": {"type": "string", "enum": ["NO_EDIT", "CREATE", "RETIRE", "SPLIT", "MERGE"]},
                        "rationale": {"type": "string"},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


class QualifiedMetaProposalAuthority:
    """Qualified Qwen Meta role; the model proposes intent, never executable edits."""

    scientific_ready = True
    runtime_ready = True

    def __init__(self, binding: QualifiedMetaProposalBinding) -> None:
        self._binding = binding

    @property
    def binding_digest(self) -> str:
        return canonical_digest({
            "provider": "sem.meta.qualified.v1",
            "deployment_id": self._binding.deployment_id,
            "deployment_generation": self._binding.deployment_generation,
            "model": self._binding.model,
            "prompt_generation": self._binding.prompt_requests.prompt_generation_id,
            "prompt_id": self._binding.prompt_requests.prompt_id,
            "prompt_digest": self._binding.prompt_requests.prompt_digest,
        })

    def propose(self, report: ArchitectureObservationReport) -> StructuralIntent | None:
        document = _report_document(report)
        report_digest = canonical_digest(document)
        request_id = ":".join((
            "sem-paper", "meta", self._binding.context.run_id,
            report.generation, report_digest[:24],
        ))
        request_context = replace(
            self._binding.context,
            condition_id="self-evolve-meta",
            task_id=None,
            decision_cycle_id=f"meta:{report_digest[:16]}",
        )
        try:
            bound = self._binding.prompt_requests.build(
                blocks=(_prompt_block(document),),
                context_length=self._binding.context_length,
                request_id=request_id,
                context=request_context,
                model=self._binding.model,
                body_builder=_qwen_json_body,
                source_artifact_refs=(f"sem:architecture:{canonical_digest(document['architecture'])}",),
                source_state_refs=tuple(report.evidence_refs),
            )
            response = self._binding.endpoint.complete(ModelEndpointRequest(
                request=bound.request,
                deployment_id=self._binding.deployment_id,
                deployment_generation=self._binding.deployment_generation,
                body=bound.body,
            ))
            payload = self._parse_response(response, request_id)
            return self._to_intent(payload, report)
        except BaseException as exc:
            if isinstance(exc, QualifiedMetaProposalError):
                raise
            raise QualifiedMetaProposalError(
                f"qualified Meta proposal failed: {type(exc).__name__}",
                phase="request_or_response",
                cause=exc,
            ) from exc

    def _parse_response(self, response: ModelEndpointResponse, request_id: str) -> dict[str, object]:
        if response.request_id != request_id or response.deployment_id != self._binding.deployment_id:
            raise QualifiedMetaProposalError("Meta response identity drift", phase="response_identity")
        if response.finish_reason != "stop":
            raise QualifiedMetaProposalError("Meta response did not complete normally", phase="response_completion")
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise QualifiedMetaProposalError("Meta response is not strict JSON", phase="parse", cause=exc) from exc
        if not isinstance(payload, dict) or set(payload) != {"edit", "rationale", "evidence_refs"}:
            raise QualifiedMetaProposalError("Meta response schema mismatch", phase="schema")
        if not isinstance(payload["edit"], str) or payload["edit"] not in {item.value for item in EditKind}:
            raise QualifiedMetaProposalError("Meta edit is invalid", phase="schema")
        if not isinstance(payload["rationale"], str) or not payload["rationale"].strip():
            raise QualifiedMetaProposalError("Meta rationale is required", phase="schema")
        refs = payload["evidence_refs"]
        if not isinstance(refs, list) or any(not isinstance(item, str) or not item.strip() for item in refs):
            raise QualifiedMetaProposalError("Meta evidence refs are invalid", phase="schema")
        if len(refs) != len(set(refs)):
            raise QualifiedMetaProposalError("Meta evidence refs contain duplicates", phase="schema")
        return payload

    @staticmethod
    def _merge_compatible(left, right) -> bool:
        return (
            left.selector is not None
            and right.selector is not None
            and left.selector.all_of == right.selector.all_of
            and left.selector.negated != right.selector.negated
            and left.scope == right.scope
            and left.mode == right.mode
            and left.schema == right.schema
            and left.primary_key == right.primary_key
            and left.sources == right.sources
            and left.transform == right.transform
        )

    @classmethod
    def _typed_edit(cls, edit: EditKind, report: ArchitectureObservationReport):
        architecture = report.architecture
        if architecture is None:
            return None
        node_map = architecture.node_map()
        if edit is EditKind.MERGE:
            for pair in sorted(report.pairs, key=lambda item: (-item.co_select_count, item.pair_id)):
                left, right = node_map.get(pair.left_node_id), node_map.get(pair.right_node_id)
                if left is not None and right is not None and cls._merge_compatible(left, right):
                    return MergeNodesEdit(
                        "MERGE_NODES", left.node_id, right.node_id,
                        f"{left.label}Merged",
                        "Meta-selected merge of grounded compatible sibling partitions.",
                        left.access | right.access,
                    )
            return None
        if edit is EditKind.RETIRE:
            candidates = [
                profile for profile in report.node_profiles
                if profile.query_count > 0 and profile.selected_count == 0
                and profile.result_count == 0
                and not architecture.downstream_ids(profile.node_id)
            ]
            return RetireNodeEdit("RETIRE_NODE", sorted(candidates, key=lambda x: (-x.query_count, x.node_id))[0].node_id) if candidates else None
        if edit is EditKind.SPLIT:
            if not report.unresolved_intent_clusters:
                return None
            cluster = sorted(
                report.unresolved_intent_clusters,
                key=lambda item: (-item.support, item.cluster_id),
            )[0]
            profiles = sorted(
                report.node_profiles,
                key=lambda item: (-item.empty_result_count, -item.query_count, item.node_id),
            )
            for profile in profiles:
                if profile.empty_result_count <= 0:
                    continue
                node = node_map.get(profile.node_id)
                if node is None:
                    continue
                field = next(
                    (item for item in node.schema if item.dtype.base in {PrimitiveType.TEXT, PrimitiveType.CATEGORY}),
                    None,
                )
                if field is not None:
                    return SplitNodeEdit(
                        "SPLIT_NODE",
                        node.node_id,
                        RecordSelector((PredicateAtom(field.name, PredicateOp.EQ, cluster.cluster_id),)),
                        SplitChildDraft(f"{node.label}Focused", "Meta-selected grounded unresolved-intent partition.", node.access),
                        SplitChildDraft(f"{node.label}Remainder", "Complement of the grounded unresolved-intent partition.", node.access),
                    )
            return None
        if edit is EditKind.CREATE:
            source = next((node for node in sorted(architecture.nodes, key=lambda item: item.node_id) if node.sources), None)
            if source is None:
                return None
            return CreateNodeEdit(
                "CREATE_NODE",
                MemoryNodeDraft(
                    label="MetaGroundedMemory",
                    purpose="Add a grounded reusable view selected by the qualified Meta role.",
                    scope=source.scope,
                    mode=source.mode,
                    schema=source.schema,
                    primary_key=source.primary_key,
                    access=source.access,
                    sources=source.sources,
                    transform=source.transform,
                    selector=source.selector,
                ),
            )
        return None

    @classmethod
    def _to_intent(cls, payload: dict[str, object], report: ArchitectureObservationReport) -> StructuralIntent:
        edit = EditKind(str(payload["edit"]))
        rationale = str(payload["rationale"]).strip()
        refs = tuple(str(item) for item in payload["evidence_refs"])
        if not set(refs).issubset(set(report.evidence_refs)):
            raise QualifiedMetaProposalError("Meta cited evidence outside the frozen report", phase="authority")
        if edit is EditKind.NO_EDIT:
            return StructuralIntent(edit, rationale, payload={"evidence_refs": refs})
        if not refs:
            raise QualifiedMetaProposalError("structural Meta edit requires report evidence", phase="authority")
        architecture_edit = cls._typed_edit(edit, report)
        if architecture_edit is None:
            return StructuralIntent(
                EditKind.NO_EDIT,
                f"qualified Meta intent {edit.value} had no grounded typed realization",
                payload={"evidence_refs": refs},
            )
        return StructuralIntent(
            edit,
            rationale,
            payload={
                "architecture": report.architecture,
                "architecture_edit": architecture_edit,
                "evidence_refs": refs,
            },
        )


@dataclass(frozen=True, slots=True)
class _MinecraftEvaluationRuntime:
    world_cuts: MinecraftWorldCutPort
    executor: MinecraftBranchExecutorPort
    run_id: str
    context: ExecutionContext
    destination_root: Path


class DeferredMinecraftPairedEvolutionEvaluator:
    """Production evaluator runtime shared read-only, then narrowed per SEM session."""

    scientific_ready = True

    def __init__(self) -> None:
        self._runtime: _MinecraftEvaluationRuntime | None = None
        self._lock = threading.RLock()

    @property
    def runtime_ready(self) -> bool:
        with self._lock:
            return self._runtime is not None

    @property
    def binding_digest(self) -> str:
        with self._lock:
            runtime = self._runtime
        return canonical_digest({
            "provider": "sem.minecraft.paired-evaluator.v2",
            "run_id": runtime.run_id if runtime is not None else None,
            "context": runtime.context if runtime is not None else None,
            "destination_root": str(runtime.destination_root) if runtime is not None else None,
        })

    def bind_runtime(
        self,
        *,
        world_cuts: MinecraftWorldCutPort,
        executor: MinecraftBranchExecutorPort,
        run_id: str,
        context: ExecutionContext,
        destination_root: Path,
    ) -> None:
        if not run_id.strip():
            raise ValueError("evolution evaluator run_id is required")
        runtime = _MinecraftEvaluationRuntime(world_cuts, executor, run_id, context, Path(destination_root))
        with self._lock:
            if self._runtime is not None and self._runtime != runtime:
                raise RuntimeError("evolution evaluator runtime is already bound")
            self._runtime = runtime

    def bind_session(self, session_id: str) -> "_SessionMinecraftPairedEvolutionEvaluator":
        if not session_id.strip():
            raise ValueError("evolution evaluator session_id is required")
        if not self.runtime_ready:
            raise RuntimeError("evolution evaluator runtime is not bound")
        return _SessionMinecraftPairedEvolutionEvaluator(self, session_id)

    def runtime(self) -> _MinecraftEvaluationRuntime:
        with self._lock:
            runtime = self._runtime
        if runtime is None:
            raise RuntimeError("evolution evaluator runtime is not bound")
        return runtime

    def evaluate(self, candidate: CandidateArchitecture) -> EvaluationProof:
        del candidate
        raise RuntimeError("evolution evaluator must be narrowed with bind_session before evaluation")


class _SessionMinecraftPairedEvolutionEvaluator:
    def __init__(self, parent: DeferredMinecraftPairedEvolutionEvaluator, session_id: str) -> None:
        self._parent = parent
        self._session_id = session_id

    def evaluate(self, candidate: CandidateArchitecture) -> EvaluationProof:
        runtime = self._parent.runtime()
        candidate_token = canonical_digest({
            "session_id": self._session_id,
            "candidate_id": candidate.candidate_id,
            "base_generation": candidate.base_generation,
            "target_spec_digest": candidate.target_spec_digest,
        })[:20]
        cut_holder: dict[str, str] = {}
        runner = MinecraftPairedBranchRunner(
            world_cuts=runtime.world_cuts,
            executor=runtime.executor,
            session_id=f"{runtime.run_id}:evolution-gate:{self._session_id}:{candidate_token}",
            context=replace(runtime.context, condition_id="evolution-gate"),
            branch_id_factory=lambda role: (
                f"{runtime.run_id}:evolution:{self._session_id}:{candidate_token}:"
                f"{cut_holder.get('cut', 'pending')[:16]}:{role.value}"
            ),
            destination_factory=lambda branch_id: str(
                runtime.destination_root / branch_id.replace(":", "_")
            ),
        )
        cut = runner.prepare_source_cut()
        cut_holder["cut"] = cut.cut_id
        return PairedBranchEvaluator(runner).evaluate(candidate)


class _SessionEvidenceSnapshotSource:
    def __init__(self, authority: SessionAdoptionAuthority) -> None:
        self._authority = authority

    def snapshot(self):
        _, evidence = self._authority.open_evidence_cut()
        return evidence.materialize()


class _BoundDurableSessionEvolutionAuthority:
    scientific_ready = True
    runtime_ready = True

    def __init__(
        self,
        *,
        authority: SessionAdoptionAuthority,
        state: AtomicStateStorePort,
    ) -> None:
        self._authority = authority
        self._state = state
        self._service = AtomicAdoptionService(
            state,
            Materializer(_SessionEvidenceSnapshotSource(authority)),
            GenerationAllocator(),
        )

    def _state_generation(self) -> str:
        architecture = self._state.read(AtomicAdoptionService.ARCH)
        ledger = self._state.read(AtomicAdoptionService.LEDGER)
        if architecture.generation != ledger.generation:
            raise RuntimeError("durable evolution architecture/ledger generation mismatch")
        return architecture.generation

    def current_architecture(self, expected_generation: str) -> MemoryArchitectureSpec:
        current = self._state.read(AtomicAdoptionService.ARCH)
        if current.generation != expected_generation:
            raise RuntimeError(
                "session generation does not match durable evolution authority"
            )
        payload = current.payload
        if not isinstance(payload, dict) or "target_spec" not in payload:
            raise RuntimeError("durable evolution architecture payload is invalid")
        return architecture_from_dict(payload["target_spec"])

    def adopt(self, candidate: CandidateArchitecture, proof: EvaluationProof) -> str:
        session_generation, _ = self._authority.open_evidence_cut()
        durable_generation = self._state_generation()
        if session_generation != durable_generation or candidate.base_generation != durable_generation:
            raise RuntimeError("evolution adoption base generation is not authoritative")
        return self._service.adopt(candidate, proof)

    def reconcile(
        self,
        *,
        task_key: str,
        base_generation: str,
        context: ExecutionContext,
    ) -> EvolutionReconciliation:
        del task_key, context
        try:
            receipt = self._service.reconciler.reconcile()
        except Exception as exc:
            descriptor = describe_exception(exc)
            return EvolutionReconciliation(
                EvolutionReconciliationStatus.UNRESOLVED,
                reason=f"{descriptor.error_type}[{descriptor.error_digest[:16]}]",
            )
        refs = (
            f"sem:architecture-digest:{receipt.architecture_digest}",
            f"sem:ledger-digest:{receipt.ledger_digest}",
        )
        if receipt.generation == base_generation:
            return EvolutionReconciliation(
                EvolutionReconciliationStatus.NO_AUTHORITATIVE_ADOPTION,
                authoritative_generation=base_generation,
                evidence_refs=refs,
            )
        return EvolutionReconciliation(
            EvolutionReconciliationStatus.ADOPTION_CONFIRMED,
            authoritative_generation=receipt.generation,
            evidence_refs=refs,
        )


class DurableSessionEvolutionAuthority:
    """Bind per-session SQLite authority to the session's pinned J_mem surface."""

    scientific_ready = True
    runtime_ready = True

    def __init__(
        self,
        root: Path,
        *,
        state_store_factory: Callable[[Path, tuple[AggregateValue, ...]], AtomicStateStorePort],
    ) -> None:
        self._root = Path(root)
        self._state_store_factory = state_store_factory
        self._root.mkdir(parents=True, exist_ok=True)
        self._bound: dict[str, _BoundDurableSessionEvolutionAuthority] = {}
        self._lock = threading.RLock()

    @property
    def binding_digest(self) -> str:
        return canonical_digest({"provider": "sem.session-evolution.sqlite.v1"})

    @staticmethod
    def _initial_architecture_payload(
        architecture: MemoryArchitectureSpec,
        source_sequence: int,
        source_digest: str,
    ) -> dict[str, object]:
        return {
            "target_spec": architecture_to_dict(architecture),
            "materialized_records": [],
            "source_sequence": source_sequence,
            "source_snapshot_digest": source_digest,
        }

    def bind(
        self,
        authority: SessionAdoptionAuthority,
        *,
        initial_architecture: MemoryArchitectureSpec,
    ) -> _BoundDurableSessionEvolutionAuthority:
        session_id = authority.session_id
        with self._lock:
            existing = self._bound.get(session_id)
            if existing is not None:
                return existing
            generation, evidence = authority.open_evidence_cut()
            state_path = self._root / f"{hashlib.sha256(session_id.encode('utf-8')).hexdigest()}.sqlite3"
            initial: tuple[AggregateValue, ...] = ()
            if not state_path.exists():
                architecture_payload = self._initial_architecture_payload(
                    initial_architecture, evidence.sequence, evidence.digest
                )
                ledger_payload: list[object] = []
                initial = (
                    AggregateValue(AtomicAdoptionService.ARCH, 0, generation, canonical_digest(architecture_payload), architecture_payload),
                    AggregateValue(AtomicAdoptionService.LEDGER, 0, generation, canonical_digest(ledger_payload), ledger_payload),
                )
            state = self._state_store_factory(state_path, initial)
            bound = _BoundDurableSessionEvolutionAuthority(
                authority=authority,
                state=state,
            )
            self._bound[session_id] = bound
            return bound


__all__ = [
    "DeferredMinecraftPairedEvolutionEvaluator",
    "DurableSessionEvolutionAuthority",
    "QualifiedMetaProposalAuthority",
    "QualifiedMetaProposalBinding",
    "QualifiedMetaProposalError",
]
