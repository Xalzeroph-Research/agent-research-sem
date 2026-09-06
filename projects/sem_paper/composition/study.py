from __future__ import annotations

from research_platform.experimentation.study.api import (
    StudyProtocol,
    StudyVariantSpec,
    VariantKind,
)
from research_platform.platform.kernel import canonical_digest
from research_platform.platform.kernel import JsonInput
from research_platform.experimentation.study.api import ExperimentPlan, VariantBinding


SEM_PAPER_METRIC_NAMES = (
    "success_rate",
    "utility_mean",
    "steps_total",
    "duration_s_total",
    "memory_queries_total",
    "task_failed_total",
    "task_blocked_total",
)

CORE6_REPETITIONS = 12
CONFIRMATORY_MATRIX_PROFILE = "core-6"
CONFORMANCE_MATRIX_PROFILE = "paired-conformance"

CORE6_VARIANTS = (
    ("Fixed-C", VariantKind.CONTROL, "FixedSeed", "Seed-C"),
    ("Rule-C", VariantKind.TREATMENT, "RuleBasedEvolver", "Seed-C"),
    ("Self-C", VariantKind.TREATMENT, "SelfEvolve", "Seed-C"),
    ("Fixed-X", VariantKind.CONTROL, "FixedSeed", "Seed-X"),
    ("Rule-X", VariantKind.TREATMENT, "RuleBasedEvolver", "Seed-X"),
    ("Self-X", VariantKind.TREATMENT, "SelfEvolve", "Seed-X"),
)

# Historical pre-repair extended matrix retained only as a migration marker.
# It is NOT the frozen Paper-1 confirmatory contract and is deliberately no
# longer executable through ``build_sem_paper_study_protocol``.
CLAIM_READY_VARIANTS = CORE6_VARIANTS + (
    ("External-C", VariantKind.EXTERNAL_BASELINE, "ExternalBaseline", "Seed-C", ()),
    ("External-X", VariantKind.EXTERNAL_BASELINE, "ExternalBaseline", "Seed-X", ()),
    ("Self-NoAdoption-C", VariantKind.ABLATION, "SelfEvolveNoAdoption", "Seed-C", ("adoption",)),
    ("Self-NoAdoption-X", VariantKind.ABLATION, "SelfEvolveNoAdoption", "Seed-X", ("adoption",)),
    ("Self-NoReconciliation-C", VariantKind.ABLATION, "SelfEvolveNoReconciliation", "Seed-C", ("reconciliation",)),
    ("Self-NoReconciliation-X", VariantKind.ABLATION, "SelfEvolveNoReconciliation", "Seed-X", ("reconciliation",)),
)


FROZEN_HALF_N_MECHANISM_CONTROLS = (
    "No-CREATE",
    "CREATE-only/no-reorganization",
    "NoHistoricalBackfill",
    "EveryTaskMeta-or-NoDwell",
)


def build_sem_paper_study_protocol(
    *,
    study_id: str,
    workload_id: str,
    task_manifest_digest: str,
    seed_identity: JsonInput,
    fixed_configuration: JsonInput,
    candidate_configuration: JsonInput,
    repetitions: int | None = None,
    matrix_profile: str = CONFORMANCE_MATRIX_PROFILE,
) -> StudyProtocol:
    """Create a typed protocol shared by MC and non-MC adapters.

    Low-level profile builder used by the named protocol authorities below.
    Production entrypoints must call ``build_sem_paper_confirmatory_protocol``
    or ``build_sem_paper_conformance_protocol`` rather than selecting a profile
    string themselves.
    """

    if not task_manifest_digest.strip():
        raise ValueError("SEM Paper study protocol requires a task manifest digest")
    if matrix_profile == "claim-ready":
        raise ValueError(
            "matrix_profile='claim-ready' is retired: it encoded a pre-freeze 12-arm matrix "
            "with non-authoritative ablations. Use core-6 for the confirmatory full-N study; "
            "frozen half-N mechanism controls are separate follow-on studies."
        )
    if matrix_profile == CONFIRMATORY_MATRIX_PROFILE:
        declared_variants = CORE6_VARIANTS
        variants = tuple(
            StudyVariantSpec(
                variant_id=variant_id,
                kind=kind,
                implementation_id=f"sem-paper.{implementation}",
                configuration_digest=canonical_digest({"seed": seed, "configuration": fixed_configuration if implementation == "FixedSeed" else candidate_configuration}),
                budget_tier=(
                    "core"
                    if kind in {VariantKind.CONTROL, VariantKind.TREATMENT}
                    else "external"
                    if kind is VariantKind.EXTERNAL_BASELINE
                    else "ablation"
                ),
                ablates=ablates if len(variant) == 5 else (),
            )
            for variant in declared_variants
            for variant_id, kind, implementation, seed, *rest in (variant,)
            for ablates in (rest[0] if rest else (),)
        )
        budget_tiers = ("core",)
        if repetitions is not None and repetitions != CORE6_REPETITIONS:
            raise ValueError(
                f"confirmatory Core-6 repetitions are frozen at {CORE6_REPETITIONS}"
            )
        repetitions = CORE6_REPETITIONS
    elif matrix_profile == CONFORMANCE_MATRIX_PROFILE:
        variants = (
            StudyVariantSpec("control", VariantKind.CONTROL, "sem-paper.fixed-memory", canonical_digest(fixed_configuration)),
            StudyVariantSpec("candidate", VariantKind.TREATMENT, "sem-paper.candidate-memory", canonical_digest(candidate_configuration)),
        )
        budget_tiers = ("standard",)
        repetitions = 1 if repetitions is None else repetitions
    else:
        raise ValueError(f"unknown matrix profile: {matrix_profile}")
    return StudyProtocol(
        study_id=study_id,
        workload_id=workload_id,
        variants=variants,
        repetitions=repetitions,
        seed_schedule_digest=canonical_digest(
            {
                "seed_identity": seed_identity,
                "matrix_profile": matrix_profile,
                "repetitions": repetitions,
            }
        ),
        metric_names=SEM_PAPER_METRIC_NAMES,
        task_manifest_digest=task_manifest_digest,
        budget_tiers=budget_tiers,
    )


def build_sem_paper_confirmatory_protocol(
    *,
    study_id: str,
    workload_id: str,
    task_manifest_digest: str,
    seed_identity: JsonInput,
    fixed_configuration: JsonInput,
    candidate_configuration: JsonInput,
) -> StudyProtocol:
    """Build the one frozen full-N Core-6 confirmatory protocol."""

    return build_sem_paper_study_protocol(
        study_id=study_id,
        workload_id=workload_id,
        task_manifest_digest=task_manifest_digest,
        seed_identity=seed_identity,
        fixed_configuration=fixed_configuration,
        candidate_configuration=candidate_configuration,
        repetitions=CORE6_REPETITIONS,
        matrix_profile=CONFIRMATORY_MATRIX_PROFILE,
    )


def build_sem_paper_conformance_protocol(
    *,
    study_id: str,
    workload_id: str,
    task_manifest_digest: str,
    seed_identity: JsonInput,
    fixed_configuration: JsonInput,
    candidate_configuration: JsonInput,
    repetitions: int = 1,
) -> StudyProtocol:
    """Build a bounded non-claim paired protocol for portability/smoke tests."""

    return build_sem_paper_study_protocol(
        study_id=study_id,
        workload_id=workload_id,
        task_manifest_digest=task_manifest_digest,
        seed_identity=seed_identity,
        fixed_configuration=fixed_configuration,
        candidate_configuration=candidate_configuration,
        repetitions=repetitions,
        matrix_profile=CONFORMANCE_MATRIX_PROFILE,
    )


def compile_sem_paper_experiment_plan(protocol: StudyProtocol) -> ExperimentPlan:
    """Compile every declared arm into an explicit runtime binding."""
    bindings = tuple(
        VariantBinding(
            variant=item,
            seed_id=(
                f"Seed-{item.variant_id.rsplit('-', 1)[-1]}"
                if item.variant_id.rsplit("-", 1)[-1] in {"C", "X"}
                else item.variant_id
            ),
            provider_id=item.implementation_id,
            ablation_policy_id=(item.ablates[0] if item.ablates else "none"),
            comparator_role=(
                "external"
                if item.kind is VariantKind.EXTERNAL_BASELINE
                else "ablation"
                if item.kind is VariantKind.ABLATION
                else "primary"
            ),
        )
        for item in protocol.variants
    )
    return ExperimentPlan.compile(protocol, bindings)


def is_claim_ready_protocol(protocol: StudyProtocol) -> bool:
    """Recognize the retired pre-freeze extended matrix for migration only.

    A true return value does *not* confer claim eligibility. Scientific closure
    accepts only :func:`is_confirmatory_protocol`.
    """

    kinds = {item.kind for item in protocol.variants}
    implementations = {item.implementation_id.rsplit(".", 1)[-1] for item in protocol.variants}
    return (
        len(protocol.variants) == len(CLAIM_READY_VARIANTS)
        and VariantKind.EXTERNAL_BASELINE in kinds
        and VariantKind.ABLATION in kinds
        and {"ExternalBaseline", "SelfEvolveNoAdoption", "SelfEvolveNoReconciliation"}
        <= implementations
        and protocol.repetitions == CORE6_REPETITIONS
    )


def is_confirmatory_protocol(protocol: StudyProtocol) -> bool:
    """Return whether ``protocol`` is the frozen full-N Core-6 contract."""

    expected = {
        (variant_id, kind, f"sem-paper.{implementation}")
        for variant_id, kind, implementation, _seed in CORE6_VARIANTS
    }
    actual = {
        (item.variant_id, item.kind, item.implementation_id)
        for item in protocol.variants
    }
    return (
        actual == expected
        and len(protocol.variants) == len(CORE6_VARIANTS)
        and protocol.repetitions == CORE6_REPETITIONS
        and set(protocol.budget_tiers) == {"core"}
    )


__all__ = [
    "CORE6_REPETITIONS",
    "CONFIRMATORY_MATRIX_PROFILE",
    "CONFORMANCE_MATRIX_PROFILE",
    "CORE6_VARIANTS",
    "CLAIM_READY_VARIANTS",
    "FROZEN_HALF_N_MECHANISM_CONTROLS",
    "SEM_PAPER_METRIC_NAMES",
    "build_sem_paper_study_protocol",
    "build_sem_paper_confirmatory_protocol",
    "build_sem_paper_conformance_protocol",
    "compile_sem_paper_experiment_plan",
    "is_claim_ready_protocol",
    "is_confirmatory_protocol",
]
