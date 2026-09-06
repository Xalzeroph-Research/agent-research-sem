from __future__ import annotations

from dataclasses import dataclass

from research_platform.governance.architecture.api.capabilities import (
    LOGGING_SYSTEM_V1,
    METHOD_COMPOSITION_PORTS_V1,
)
from research_platform.governance.architecture.api.capability_composition import (
    BindingPlan,
    CapabilityCompositionPlannerPort,
    CapabilityRequirement,
    CompositionContract,
    CompositionIdentity,
    CompositionSubject,
    RequirementAddress,
    interface_contract_digest,
)
from research_platform.observability.logging.record.api import (
    LoggingSystemBinding,
    LoggingSystemPort,
)
from research_platform.participant.method.api import (
    MethodCompositionPorts,
    MethodEndpointPort,
    MethodSystemBinding,
)
from research_platform.platform.kernel import canonical_digest
from research_platform.portfolio.project.api import ProjectDefinition
from research_platform.scope.api import ScopeIdentity, ScopeKind

from projects.sem_paper.api import PROJECT_DEFINITION
from projects.sem_paper.method.self_evolving_memory.runtime import SelfEvolvingMemoryRuntime
from projects.sem_paper.method.self_evolving_memory.session_evolution_api import SessionEvolutionFactory
from projects.sem_paper.method.self_evolving_memory.session_state_api import SEMSessionStateFactory
from projects.sem_paper.method.self_evolving_memory.session_serving_api import (
    DeluxeSnapshotFactory,
    SessionServingFactory,
)
from projects.sem_paper.method.self_evolving_memory.serving_providers import build_hybrid_session_serving

from .logging import bind_project_logging
from .method import build_fixed_memory_treatment, build_self_evolving_treatment
from .candidate_method import (
    CandidateMethodMaterializerPort,
    SemPaperVariantMethodEndpointFactory,
    VariantMethodEndpointFactoryPort,
)


@dataclass(frozen=True, slots=True)
class SemPaperCompositionPorts:
    """Platform seams and Paper-1 adapters supplied to the project root."""

    method_system: MethodSystemBinding
    logging: LoggingSystemBinding
    planner: CapabilityCompositionPlannerPort
    scope: ScopeIdentity
    evolution_factory: SessionEvolutionFactory
    evolution_provider_id: str
    serving_factory: SessionServingFactory = build_hybrid_session_serving
    serving_provider_id: str | None = None
    self_evolving_serving_factory: SessionServingFactory | None = None
    fixed_deluxe_snapshot_factory: DeluxeSnapshotFactory | None = None
    fixed_seed_x_deluxe_snapshot_factory: DeluxeSnapshotFactory | None = None
    self_evolving_deluxe_snapshot_factory: DeluxeSnapshotFactory | None = None
    fixed_runtime: SelfEvolvingMemoryRuntime | None = None
    self_evolving_runtime: SelfEvolvingMemoryRuntime | None = None
    state_factory: SEMSessionStateFactory | None = None
    candidate_method_materializer: CandidateMethodMaterializerPort | None = None
    rule_based_candidate_method_materializer: CandidateMethodMaterializerPort | None = None
    self_evolving_candidate_method_materializer: CandidateMethodMaterializerPort | None = None
    external_baseline_method_materializer: CandidateMethodMaterializerPort | None = None
    no_adoption_method_materializer: CandidateMethodMaterializerPort | None = None
    no_reconciliation_method_materializer: CandidateMethodMaterializerPort | None = None
    variant_method_endpoint_factory: VariantMethodEndpointFactoryPort | None = None


@dataclass(frozen=True, slots=True)
class SemPaperBindings:
    """Fully bound Paper-1 project surface; no session is opened here."""

    definition: ProjectDefinition
    logging: LoggingSystemPort
    fixed_memory: MethodEndpointPort
    self_evolving: MethodEndpointPort
    candidate_method_materializer: CandidateMethodMaterializerPort | None
    variant_method_endpoint_factory: VariantMethodEndpointFactoryPort | None


@dataclass(frozen=True, slots=True)
class SemPaperProjectComposition:
    """Paper-owned bindings and the frozen plan for imported platform seams."""

    bindings: SemPaperBindings
    plan: BindingPlan


def compose_sem_paper(ports: SemPaperCompositionPorts) -> SemPaperProjectComposition:
    """Bind platform interfaces to the Paper-1 method without running it."""

    if ports.scope.kind is not ScopeKind.PROJECT:
        raise ValueError("Paper-1 composition requires a project scope")
    subject = CompositionSubject.project_subject(
        PROJECT_DEFINITION.identity.project_id,
        PROJECT_DEFINITION.identity.version,
    )
    logging_requirement = CapabilityRequirement(
        RequirementAddress(subject, "logging-system"),
        ports.scope,
        LOGGING_SYSTEM_V1,
        interface_contract_digest(LoggingSystemPort),
    )
    method_requirement = CapabilityRequirement(
        RequirementAddress(subject, "method-composition-ports"),
        ports.scope,
        METHOD_COMPOSITION_PORTS_V1,
        interface_contract_digest(MethodCompositionPorts),
    )
    declared = {requirement.key for requirement in PROJECT_DEFINITION.capabilities}
    bound = {"observability:logging", "participant:method.runtime"}
    if declared != bound:
        raise ValueError(
            "Paper-1 capability declaration is not closed over its composition plan: "
            f"declared={sorted(declared)!r} bound={sorted(bound)!r}"
        )
    plan = ports.planner.freeze(
        CompositionIdentity(
            "project.sem-paper-1",
            ports.scope,
            owner=subject,
        ),
        (
            CompositionContract(
                subject,
                ports.scope,
                requirements=(logging_requirement, method_requirement),
            ),
        ),
        imported_offers=(
            ports.logging.offer,
            ports.method_system.offer,
        ),
    )
    variant_factory = ports.variant_method_endpoint_factory
    if variant_factory is None:
        rule_materializer = ports.rule_based_candidate_method_materializer
        self_materializer = ports.self_evolving_candidate_method_materializer
        if rule_materializer is not None and self_materializer is not None:
            fixed_c = build_fixed_memory_treatment(
                method_system=ports.method_system.ports,
                serving_factory=ports.serving_factory,
                serving_provider_id=ports.serving_provider_id,
                runtime=ports.fixed_runtime,
                state_factory=ports.state_factory,
                configuration_digest=canonical_digest({"seed": "Seed-C"}),
                deluxe_snapshot_factory=ports.fixed_deluxe_snapshot_factory,
            )
            fixed_by_seed = {"Seed-C": fixed_c}
            if ports.fixed_seed_x_deluxe_snapshot_factory is not None:
                fixed_by_seed["Seed-X"] = build_fixed_memory_treatment(
                    method_system=ports.method_system.ports,
                    serving_factory=ports.serving_factory,
                    serving_provider_id=ports.serving_provider_id,
                    runtime=ports.fixed_runtime,
                    state_factory=ports.state_factory,
                    configuration_digest=canonical_digest({"seed": "Seed-X"}),
                    deluxe_snapshot_factory=ports.fixed_seed_x_deluxe_snapshot_factory,
                )
            variant_factory = SemPaperVariantMethodEndpointFactory(
                fixed_endpoint=fixed_c,
                fixed_endpoints_by_seed=fixed_by_seed,
                rule_based_materializer=rule_materializer,
                self_evolving_materializer=self_materializer,
                external_baseline_materializer=ports.external_baseline_method_materializer,
                no_adoption_materializer=ports.no_adoption_method_materializer,
                no_reconciliation_materializer=ports.no_reconciliation_method_materializer,
            )
    bindings = SemPaperBindings(
        definition=PROJECT_DEFINITION,
        logging=bind_project_logging(ports.logging.logging),
        fixed_memory=build_fixed_memory_treatment(
            method_system=ports.method_system.ports,
            serving_factory=ports.serving_factory,
            serving_provider_id=ports.serving_provider_id,
            runtime=ports.fixed_runtime,
            state_factory=ports.state_factory,
            deluxe_snapshot_factory=ports.fixed_deluxe_snapshot_factory,
        ),
        self_evolving=build_self_evolving_treatment(
            method_system=ports.method_system.ports,
            evolution_factory=ports.evolution_factory,
            evolution_provider_id=ports.evolution_provider_id,
            serving_factory=ports.self_evolving_serving_factory or ports.serving_factory,
            serving_provider_id=ports.serving_provider_id,
            runtime=ports.self_evolving_runtime,
            state_factory=ports.state_factory,
            deluxe_snapshot_factory=ports.self_evolving_deluxe_snapshot_factory,
        ),
        candidate_method_materializer=ports.candidate_method_materializer,
        variant_method_endpoint_factory=variant_factory,
    )
    return SemPaperProjectComposition(bindings, plan)


__all__ = [
    "SemPaperBindings",
    "SemPaperCompositionPorts",
    "SemPaperProjectComposition",
    "compose_sem_paper",
]
