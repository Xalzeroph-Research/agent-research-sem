from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from noetrium.contracts import (
    BenchmarkTaskSet,
    ExperimentPlan,
    StudyVariantSpec,
    StudyProtocol,
    TaskDefinition,
    VariantBinding,
    VariantKind,
    canonical_digest,
)
from noetrium_platform.research.experimentation.study.runtime import (
    DeterministicStudyAssignment,
)

CORE6_VARIANTS = (
    ("fixed-c", VariantKind.CONTROL, "fixed_memory", "Seed-C"),
    ("rule-c", VariantKind.TREATMENT, "rule_based", "Seed-C"),
    ("self-c", VariantKind.TREATMENT, "self_evolving", "Seed-C"),
    ("fixed-x", VariantKind.CONTROL, "fixed_memory", "Seed-X"),
    ("rule-x", VariantKind.TREATMENT, "rule_based", "Seed-X"),
    ("self-x", VariantKind.TREATMENT, "self_evolving", "Seed-X"),
)
SEM_METRICS = (
    "success_rate", "utility_mean", "steps_total", "duration_s_total",
    "memory_queries_total", "task_failed_total", "task_blocked_total",
)
MANIFEST_PATH = Path(__file__).with_name("manifests") / "sem_primary_tasks_v1.json"


def load_task_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("tasks"), list):
        raise ValueError("SEM task manifest must contain a tasks array")
    return value


def task_manifest_digest() -> str:
    return canonical_digest(load_task_manifest())


def build_benchmark() -> BenchmarkTaskSet:
    document = load_task_manifest()
    source_digest = canonical_digest(document)
    tasks = tuple(
        TaskDefinition(
            task_id=str(row["task_id"]),
            revision_id="v1",
            family=str(row["family"]),
            schema_id="sem.minecraft.task.v1",
            content_digest=canonical_digest(row),
        )
        for row in sorted(document["tasks"], key=lambda item: str(item["task_id"]))
    )
    return BenchmarkTaskSet(
        benchmark_id=str(document["manifest_id"]),
        revision_id="v1",
        source_digest=source_digest,
        task_schema_id="sem.minecraft.task.v1",
        tasks=tasks,
    )


def build_sem_paper_confirmatory_protocol(
    *,
    study_id: str = "sem-core6",
    workload_id: str = "minecraft-primary-core-six",
    repetitions: int = 12,
) -> StudyProtocol:
    if repetitions != 12:
        raise ValueError("SEM confirmatory Core-6 repetitions are frozen at 12")
    variants = tuple(
        StudyVariantSpec(
            variant_id=variant_id,
            kind=kind,
            implementation_id=f"sem-paper.{implementation}",
            configuration_digest=canonical_digest(
                {"treatment": implementation, "seed": seed}
            ),
            budget_tier="core",
        )
        for variant_id, kind, implementation, seed in CORE6_VARIANTS
    )
    return StudyProtocol(
        study_id=study_id,
        workload_id=workload_id,
        variants=variants,
        repetitions=repetitions,
        seed_schedule_digest=canonical_digest(
            {"seed_identity": ("Seed-C", "Seed-X"), "repetitions": repetitions}
        ),
        metric_names=SEM_METRICS,
        task_manifest_digest=task_manifest_digest(),
        budget_tiers=("core",),
    )


def compile_sem_paper_experiment_plan(
    protocol: StudyProtocol | None = None,
) -> ExperimentPlan:
    protocol = protocol or build_sem_paper_confirmatory_protocol()
    assignments = DeterministicStudyAssignment().assignments(protocol)
    bindings = tuple(
        VariantBinding(
            variant=variant,
            intervention_digest=canonical_digest(
                {"variant_id": variant.variant_id, "seed": _seed(variant.variant_id)}
            ),
            provider_id=variant.implementation_id,
            ablation_policy_id="none",
            comparator_role="primary",
        )
        for variant in protocol.variants
    )
    return ExperimentPlan.compile(protocol, bindings, assignments)


def _seed(variant_id: str) -> str:
    return "Seed-X" if variant_id.endswith("-x") else "Seed-C"


def is_confirmatory_protocol(protocol: StudyProtocol) -> bool:
    return (
        protocol.study_id == "sem-core6"
        and protocol.workload_id == "minecraft-primary-core-six"
        and protocol.repetitions == 12
        and tuple(item.variant_id for item in protocol.variants)
        == tuple(item[0] for item in CORE6_VARIANTS)
        and set(protocol.budget_tiers) == {"core"}
    )


__all__ = [
    "CORE6_VARIANTS", "MANIFEST_PATH", "SEM_METRICS",
    "build_benchmark", "load_task_manifest", "task_manifest_digest",
    "build_sem_paper_confirmatory_protocol", "compile_sem_paper_experiment_plan",
    "is_confirmatory_protocol",
]