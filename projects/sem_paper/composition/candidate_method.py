from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from research_platform.participant.method.api import MethodCompositionPorts, MethodEndpointPort
from research_platform.experimentation.study.api import ExperimentPlan, VariantBinding
from research_platform.platform.kernel import canonical_digest

from projects.sem_paper.method.self_evolving_memory.architecture import (
    ArchitectureValidator,
    MemoryArchitectureSpec,
    SemPaperArchitecturePreset,
    build_sem_paper_architecture,
)
from projects.sem_paper.method.self_evolving_memory.evolution import CandidateArchitecture
from projects.sem_paper.method.self_evolving_memory.evolution import PrimitiveEdit, PrimitiveEditKind
from projects.sem_paper.method.self_evolving_memory.materialization import MaterializationContract
from projects.sem_paper.method.self_evolving_memory.runtime import SelfEvolvingMemoryRuntime
from projects.sem_paper.method.self_evolving_memory.session_evolution_api import SessionEvolutionFactory
from projects.sem_paper.method.self_evolving_memory.session_state_api import SEMSessionStateFactory
from projects.sem_paper.method.self_evolving_memory.session_serving_api import SessionServingFactory
from projects.sem_paper.method.self_evolving_memory.serving_providers import build_deluxe_session_serving
from projects.sem_paper.method.self_evolving_memory.typed_builders import (
    ArchitectureDrivenTypedNodeBuilder,
    TypedSemanticNodeTransformPort,
)
from projects.sem_paper.method.self_evolving_memory.typed_materialization import build_live_typed_snapshot_factory

from .method import build_self_evolving_treatment


class CandidateMethodMaterializationError(ValueError):
    """Candidate method materialization failed before a session was opened."""


class CandidateMethodMaterializerPort(Protocol):
    def materialize(self, candidate: CandidateArchitecture) -> MethodEndpointPort: ...


class CandidateArchitectureResolverPort(Protocol):
    """Resolve the candidate object for one compiled experiment arm."""

    def __call__(self, binding: VariantBinding) -> CandidateArchitecture: ...


class VariantMethodEndpointFactoryPort(Protocol):
    """Resolve a compiled experiment arm to its method endpoint."""

    def endpoint_for(
        self,
        *,
        binding: VariantBinding,
        candidate: CandidateArchitecture | None,
    ) -> MethodEndpointPort: ...


@dataclass(frozen=True, slots=True)
class TreatmentProviderIdentity:
    """Dry-composed runtime identity for one scientific arm."""

    variant_id: str
    seed_id: str
    provider_id: str
    variant_configuration_digest: str
    endpoint_binding_digest: str
    endpoint_artifact_digest: str


def is_fixed_provider(provider_id: str) -> bool:
    """Return whether a provider id denotes a fixed/control endpoint."""

    return provider_id.rsplit(".", 1)[-1] in {"FixedSeed", "fixed-memory"}


def validate_plan_provider_closure(
    *,
    plan: ExperimentPlan,
    factory: VariantMethodEndpointFactoryPort,
    candidate: CandidateArchitecture,
    candidate_factory: CandidateArchitectureResolverPort | None = None,
) -> tuple[TreatmentProviderIdentity, ...]:
    """Resolve every declared arm before external resources are opened.

    This is a semantic composition gate, not a symbol-presence check.  It
    proves that every binding can materialize a concrete endpoint and that
    the two fixed seed controls are not silently collapsed to one method
    identity.
    """

    plan.assert_consistent()
    identities: list[TreatmentProviderIdentity] = []
    for binding in plan.bindings:
        selected_candidate = (
            None
            if is_fixed_provider(binding.provider_id)
            else (
                candidate_factory(binding)
                if candidate_factory is not None
                else candidate
            )
        )
        endpoint = factory.endpoint_for(
            binding=binding,
            candidate=selected_candidate,
        )
        identities.append(
            TreatmentProviderIdentity(
                variant_id=binding.variant.variant_id,
                seed_id=binding.seed_id,
                provider_id=binding.provider_id,
                variant_configuration_digest=binding.variant.configuration_digest,
                endpoint_binding_digest=endpoint.binding_digest,
                endpoint_artifact_digest=endpoint.identity.artifact_digest,
            )
        )
    fixed = {
        item.seed_id: item
        for item in identities
        if is_fixed_provider(item.provider_id)
    }
    if {"Seed-C", "Seed-X"} <= set(fixed):
        if fixed["Seed-C"].endpoint_binding_digest == fixed["Seed-X"].endpoint_binding_digest:
            raise CandidateMethodMaterializationError(
                "Fixed-C and Fixed-X resolve to the same endpoint binding"
            )
        if fixed["Seed-C"].endpoint_artifact_digest == fixed["Seed-X"].endpoint_artifact_digest:
            raise CandidateMethodMaterializationError(
                "Fixed-C and Fixed-X resolve to the same method artifact identity"
            )
    return tuple(identities)


def build_candidate_resolver(
    *,
    fallback: CandidateArchitecture,
    override: CandidateArchitectureResolverPort | None = None,
) -> CandidateArchitectureResolverPort:
    """Build the one candidate resolver shared by preflight and execution.

    The compiled SEM matrix has two candidate seed identities.  When no
    caller-specific resolver is injected, materialize each seed from the same
    generation as the root candidate; unknown legacy bindings retain the
    explicitly supplied fallback for paired-conformance compatibility.
    """

    if override is not None:
        return override

    def resolve(binding: VariantBinding) -> CandidateArchitecture:
        if binding.seed_id in {"Seed-C", "Seed-X"}:
            return build_seed_candidate(
                binding.seed_id,
                base_generation=fallback.base_generation,
            )
        return fallback

    return resolve


class SemPaperVariantMethodEndpointFactory:
    """Explicit provider dispatch for the compiled study arms.

    The workload adapters must not infer a method from ``VariantKind``.  This
    resolver makes the provider identity the dispatch key and keeps the
    concrete endpoint factories at the project composition boundary.  The
    RuleBased and SelfEvolve factories are intentionally separate callables
    and must never share an object identity; provider identity is part of the
    scientific treatment boundary.
    """

    def __init__(
        self,
        *,
        fixed_endpoint: MethodEndpointPort,
        fixed_endpoints_by_seed: Mapping[str, MethodEndpointPort] | None = None,
        rule_based_materializer: CandidateMethodMaterializerPort,
        self_evolving_materializer: CandidateMethodMaterializerPort,
        external_baseline_materializer: CandidateMethodMaterializerPort | None = None,
        no_adoption_materializer: CandidateMethodMaterializerPort | None = None,
        no_reconciliation_materializer: CandidateMethodMaterializerPort | None = None,
    ) -> None:
        if rule_based_materializer is self_evolving_materializer:
            raise ValueError(
                "RuleBased and SelfEvolve providers must be distinct implementations"
            )
        self._fixed_endpoint = fixed_endpoint
        self._fixed_endpoints_by_seed = dict(fixed_endpoints_by_seed or {})
        self._fixed_endpoints_by_seed.setdefault("Seed-C", fixed_endpoint)
        self._rule_based_materializer = rule_based_materializer
        self._self_evolving_materializer = self_evolving_materializer
        self._external_baseline_materializer = external_baseline_materializer
        self._no_adoption_materializer = no_adoption_materializer
        self._no_reconciliation_materializer = no_reconciliation_materializer

    @staticmethod
    def _implementation_id(binding: VariantBinding) -> str:
        return binding.provider_id.rsplit(".", 1)[-1]

    def endpoint_for(
        self,
        *,
        binding: VariantBinding,
        candidate: CandidateArchitecture | None,
    ) -> MethodEndpointPort:
        implementation = self._implementation_id(binding)
        if is_fixed_provider(binding.provider_id):
            if candidate is not None:
                raise CandidateMethodMaterializationError(
                    "FixedSeed arm cannot receive a candidate architecture"
                )
            # The legacy paired-conformance profile uses a synthetic ``control``
            # seed id and intentionally binds the default fixed endpoint.
            if implementation == "fixed-memory":
                return self._fixed_endpoint
            endpoint = self._fixed_endpoints_by_seed.get(binding.seed_id)
            if endpoint is None:
                raise CandidateMethodMaterializationError(
                    f"FixedSeed arm {binding.variant.variant_id!r} has no endpoint for seed {binding.seed_id!r}"
                )
            return endpoint
        if candidate is None:
            raise CandidateMethodMaterializationError(
                f"{implementation} arm requires a candidate architecture"
            )
        if implementation in {"RuleBasedEvolver", "candidate-memory"}:
            return self._rule_based_materializer.materialize(candidate)
        if implementation == "SelfEvolve":
            return self._self_evolving_materializer.materialize(candidate)
        materializer = {
            "ExternalBaseline": self._external_baseline_materializer,
            "SelfEvolveNoAdoption": self._no_adoption_materializer,
            "SelfEvolveNoReconciliation": self._no_reconciliation_materializer,
        }.get(implementation)
        if materializer is not None:
            return materializer.materialize(candidate)
        if implementation in {
            "ExternalBaseline",
            "SelfEvolveNoAdoption",
            "SelfEvolveNoReconciliation",
        }:
            raise CandidateMethodMaterializationError(
                f"claim-ready arm {implementation!r} has no independently injected provider"
            )
        raise CandidateMethodMaterializationError(
            f"no method endpoint provider is bound for implementation {implementation!r}"
        )


class SemPaperCandidateMethodMaterializer(CandidateMethodMaterializerPort):
    """Materialize a candidate architecture into a real Deluxe method endpoint.

    The candidate's typed architecture and complete materialization contracts
    are the only source of the candidate serving surface. No baseline endpoint
    is returned when candidate materialization is absent or invalid.
    """

    def __init__(
        self,
        *,
        method_system: MethodCompositionPorts,
        evolution_factory: SessionEvolutionFactory | None = None,
        evolution_factory_builder: Callable[[MemoryArchitectureSpec], SessionEvolutionFactory] | None = None,
        evolution_provider_id: str,
        transformer: TypedSemanticNodeTransformPort,
        runtime: SelfEvolvingMemoryRuntime | None = None,
        state_factory: SEMSessionStateFactory | None = None,
        serving_provider_id: str = "sem.serving.deluxe.candidate.v1",
    ) -> None:
        if not evolution_provider_id.strip() or not serving_provider_id.strip():
            raise ValueError("candidate method provider identities are required")
        if (evolution_factory is None) == (evolution_factory_builder is None):
            raise ValueError("candidate method requires exactly one evolution factory source")
        self._method_system = method_system
        self._evolution_factory = evolution_factory
        self._evolution_factory_builder = evolution_factory_builder
        self._evolution_provider_id = evolution_provider_id
        self._transformer = transformer
        self._runtime = runtime
        self._state_factory = state_factory
        self._serving_provider_id = serving_provider_id

    def materialize(self, candidate: CandidateArchitecture) -> MethodEndpointPort:
        if not candidate.base_generation.strip() or not candidate.candidate_id.strip():
            raise CandidateMethodMaterializationError("candidate identity is incomplete")
        if not isinstance(candidate.target_spec, MemoryArchitectureSpec):
            raise CandidateMethodMaterializationError(
                "Deluxe candidate requires a typed MemoryArchitectureSpec target"
            )
        if canonical_digest(candidate.target_spec) != candidate.target_spec_digest:
            raise CandidateMethodMaterializationError("candidate target spec digest is invalid")
        ArchitectureValidator().verify(candidate.target_spec)
        contracts = tuple(candidate.materialization_contracts)
        if not contracts or any(not isinstance(contract, MaterializationContract) for contract in contracts):
            raise CandidateMethodMaterializationError(
                "candidate must provide typed materialization contracts for every node"
            )
        node_ids = {node.node_id for node in candidate.target_spec.nodes}
        contract_ids = tuple(contract.node_id for contract in contracts)
        if len(contract_ids) != len(set(contract_ids)) or set(contract_ids) != node_ids:
            raise CandidateMethodMaterializationError(
                "candidate materialization contracts must cover exactly the target architecture"
            )
        snapshot_factory = build_live_typed_snapshot_factory(
            architecture=candidate.target_spec,
            contracts=contracts,
            builder=ArchitectureDrivenTypedNodeBuilder(self._transformer),
            candidate_id=candidate.candidate_id,
        )
        evolution_factory = (
            self._evolution_factory_builder(candidate.target_spec)
            if self._evolution_factory_builder is not None
            else self._evolution_factory
        )
        if evolution_factory is None:
            raise CandidateMethodMaterializationError("candidate evolution factory is not bound")
        return build_self_evolving_treatment(
            method_system=self._method_system,
            evolution_factory=evolution_factory,
            evolution_provider_id=self._evolution_provider_id,
            serving_factory=build_deluxe_session_serving,
            serving_provider_id=self._serving_provider_id,
            runtime=self._runtime,
            state_factory=self._state_factory,
            configuration_digest=candidate.target_spec_digest,
            deluxe_snapshot_factory=snapshot_factory,
        )


def build_seed_x_candidate(*, base_generation: str = "g0") -> CandidateArchitecture:
    """Build the current Paper-1 C→X structural candidate explicitly.

    The candidate is immutable experiment input: its typed target architecture
    and complete contracts are hashed before the paired branches run.  It is
    not an adoption or acceptance decision.
    """

    if not base_generation.strip():
        raise ValueError("SEM candidate base_generation is required")
    return build_seed_candidate("Seed-X", base_generation=base_generation)


def build_seed_candidate(seed_id: str, *, base_generation: str = "g0") -> CandidateArchitecture:
    """Build the typed candidate architecture for one frozen seed arm."""

    if not seed_id.strip() or not base_generation.strip():
        raise ValueError("SEM seed candidate identity is required")
    normalized = seed_id.strip().lower().replace("_", "-")
    if normalized not in {"seed-c", "seed-x"}:
        raise ValueError(f"unsupported SEM seed candidate: {seed_id!r}")
    preset = SemPaperArchitecturePreset.C if normalized == "seed-c" else SemPaperArchitecturePreset.X
    target = build_sem_paper_architecture(preset)
    contracts = tuple(
        MaterializationContract(node.node_id, node.selector, node.transform)
        for node in target.nodes
    )
    edits = () if preset is SemPaperArchitecturePreset.C else (
        PrimitiveEdit(PrimitiveEditKind.CREATE, "mem_spatial"),
        PrimitiveEdit(PrimitiveEditKind.CREATE, "mem_entity"),
        PrimitiveEdit(PrimitiveEditKind.RETIRE, "mem_world"),
        PrimitiveEdit(PrimitiveEditKind.CREATE, "mem_event"),
        PrimitiveEdit(PrimitiveEditKind.CREATE, "mem_pattern"),
        PrimitiveEdit(PrimitiveEditKind.RETIRE, "mem_experience"),
        PrimitiveEdit(PrimitiveEditKind.RETIRE, "mem_knowledge"),
        PrimitiveEdit(PrimitiveEditKind.RETIRE, "mem_procedure"),
    )
    digest = canonical_digest(target)
    return CandidateArchitecture(
        base_generation=base_generation,
        candidate_id=f"sem-paper:{normalized}-v018",
        target_spec=target,
        target_spec_digest=digest,
        primitive_edits=edits,
        materialization_contracts=contracts,
    )


__all__ = [
    "CandidateMethodMaterializationError",
    "CandidateMethodMaterializerPort",
    "CandidateArchitectureResolverPort",
    "VariantMethodEndpointFactoryPort",
    "TreatmentProviderIdentity",
    "is_fixed_provider",
    "validate_plan_provider_closure",
    "build_candidate_resolver",
    "SemPaperVariantMethodEndpointFactory",
    "SemPaperCandidateMethodMaterializer",
    "build_seed_candidate",
    "build_seed_x_candidate",
]
