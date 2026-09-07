from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from noetrium.contracts import (
    BenchmarkTaskSet,
    DeterministicStudyAssignment,
    ExperimentPlan,
    StudyProtocol,
    StudyVariantSpec,
    TaskDefinition,
    VariantBinding,
    VariantKind,
    canonical_digest,
)

TREATMENT_IDS = ("no_memory", "flat_episodic", "fixed_typed", "sem")
PRIMARY_METRICS = (
    "success_rate",
    "utility_mean",
    "steps_total",
    "duration_s_total",
    "memory_queries_total",
    "memory_entries_total",
    "active_node_count",
    "architecture_generation",
    "candidate_count",
    "adopted_count",
    "rejected_count",
    "historical_backfill_count",
    "verified_actions_total",
    "evidence_closed_total",
)
MANIFEST_PATH = Path(__file__).with_name("manifests") / "sem_minecraft_tasks_v2.json"


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
    tasks = tuple(
        TaskDefinition(
            task_id=str(row["task_id"]),
            revision_id=str(document.get("revision_id", "v2")),
            family=str(row["family"]),
            schema_id="sem.minecraft.task.v2",
            content_digest=canonical_digest(row),
        )
        for row in sorted(document["tasks"], key=lambda item: str(item["task_id"]))
    )
    return BenchmarkTaskSet(
        benchmark_id=str(document["benchmark_id"]),
        revision_id=str(document.get("revision_id", "v2")),
        source_digest=canonical_digest(document),
        task_schema_id="sem.minecraft.task.v2",
        tasks=tasks,
    )


def build_sem_paper_confirmatory_protocol(
    *,
    study_id: str = "sem-minecraft-primary-v2",
    workload_id: str = "minecraft-memory-evolution-v2",
    repetitions: int = 3,
) -> StudyProtocol:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    variants = tuple(
        StudyVariantSpec(
            variant_id=treatment,
            kind=VariantKind.TREATMENT if treatment == "sem" else VariantKind.CONTROL,
            implementation_id=f"sem-paper.{treatment}",
            configuration_digest=canonical_digest(
                {"treatment": treatment, "benchmark": "minecraft-memory-evolution-v2"}
            ),
            budget_tier="primary",
        )
        for treatment in TREATMENT_IDS
    )
    return StudyProtocol(
        study_id=study_id,
        workload_id=workload_id,
        variants=variants,
        repetitions=repetitions,
        seed_schedule_digest=canonical_digest(
            {
                "scheme": "deterministic-hash-derived",
                "namespace": "sem-minecraft-primary-v2",
                "repetitions": repetitions,
            }
        ),
        metric_names=PRIMARY_METRICS,
        task_manifest_digest=task_manifest_digest(),
        budget_tiers=("primary",),
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
                {"variant_id": variant.variant_id, "protocol": protocol.protocol_digest}
            ),
            provider_id=variant.implementation_id,
            ablation_policy_id="none",
            comparator_role="primary",
        )
        for variant in protocol.variants
    )
    return ExperimentPlan.compile(protocol, bindings, assignments)


def is_confirmatory_protocol(protocol: StudyProtocol) -> bool:
    return (
        protocol.study_id == "sem-minecraft-primary-v2"
        and protocol.workload_id == "minecraft-memory-evolution-v2"
        and tuple(item.variant_id for item in protocol.variants) == TREATMENT_IDS
        and set(protocol.budget_tiers) == {"primary"}
    )


__all__ = [
    "MANIFEST_PATH",
    "PRIMARY_METRICS",
    "TREATMENT_IDS",
    "build_benchmark",
    "load_task_manifest",
    "task_manifest_digest",
    "build_sem_paper_confirmatory_protocol",
    "compile_sem_paper_experiment_plan",
    "is_confirmatory_protocol",
]
