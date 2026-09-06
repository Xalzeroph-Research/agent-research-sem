from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from noetrium.contracts import BenchmarkTaskSet, TaskDefinition, canonical_digest


class BenchmarkAdapterError(ValueError):
    pass


def load_benchmark_tasks(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    source = Path(path)
    if not source.is_file():
        raise BenchmarkAdapterError(f"benchmark source is missing: {source}")
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkAdapterError("benchmark source is not valid JSON") from exc
    rows = document.get("tasks") if isinstance(document, Mapping) else document
    if not isinstance(rows, list):
        raise BenchmarkAdapterError("benchmark source must contain a tasks array")
    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise BenchmarkAdapterError("benchmark task must be an object")
        if not str(row.get("task_id", "")).strip() or not str(row.get("goal", "")).strip():
            raise BenchmarkAdapterError("benchmark task requires task_id and goal")
        normalized.append(dict(row))
    return tuple(normalized)


def minedojo_adapter() -> JsonTaskBenchmarkAdapter:
    """Metadata adapter for MineDojo programmatic task exports."""
    return JsonTaskBenchmarkAdapter("minedojo", "programmatic-export-v1")


def memory_agent_bench_adapter() -> JsonTaskBenchmarkAdapter:
    """Metadata adapter for MemoryAgentBench task exports."""
    return JsonTaskBenchmarkAdapter("memory-agent-bench", "multi-turn-export-v1")


class JsonTaskBenchmarkAdapter:
    """Import task metadata without importing benchmark runtime code.

    Execution remains owned by SEM/Noetrium; benchmark packages cannot bypass
    the environment action/effect/evidence boundary.
    """

    def __init__(self, benchmark_id: str, revision_id: str = "external-v1") -> None:
        if not benchmark_id.strip() or not revision_id.strip():
            raise ValueError("benchmark identity is required")
        self.benchmark_id = benchmark_id
        self.revision_id = revision_id

    def build(self, path: str | Path) -> BenchmarkTaskSet:
        rows = load_benchmark_tasks(path)
        source_digest = canonical_digest(rows)
        tasks = tuple(
            TaskDefinition(
                task_id=str(row["task_id"]),
                revision_id=self.revision_id,
                family=str(row.get("family", "external")),
                schema_id="sem.external-benchmark.task.v1",
                content_digest=canonical_digest(row),
            )
            for row in sorted(rows, key=lambda item: str(item["task_id"]))
        )
        return BenchmarkTaskSet(
            benchmark_id=self.benchmark_id,
            revision_id=self.revision_id,
            source_digest=source_digest,
            task_schema_id="sem.external-benchmark.task.v1",
            tasks=tasks,
        )


@dataclass(frozen=True, slots=True)
class ExternalBenchmarkSpec:
    benchmark_id: str
    revision_id: str
    venue: str
    source_url: str
    scope: str
    role: str
    runtime_status: str = "metadata_only"


EXTERNAL_BENCHMARKS = (
    ExternalBenchmarkSpec(
        "memory-agent-bench", "iclr-2026", "ICLR 2026",
        "https://openreview.net/forum?id=DT7JyQC3MR",
        "incremental multi-turn memory", "memory_core",
    ),
    ExternalBenchmarkSpec(
        "memory-arena", "icml-2026", "ICML 2026",
        "https://arxiv.org/abs/2602.16313",
        "multi-session agent-environment loop", "agentic_closed_loop",
    ),
    ExternalBenchmarkSpec(
        "longmemeval", "iclr-2025", "ICLR 2025",
        "https://arxiv.org/abs/2410.10813",
        "long-term conversational memory", "regression_memory",
    ),
    ExternalBenchmarkSpec(
        "beam", "iclr-2026", "ICLR 2026",
        "https://openreview.net/forum?id=y59hf5lrMn",
        "long-context memory stress", "capacity_stress",
    ),
)


def external_benchmark_catalog() -> tuple[ExternalBenchmarkSpec, ...]:
    return EXTERNAL_BENCHMARKS

@dataclass(frozen=True, slots=True)
class ExternalBenchmarkPreparation:
    benchmark: ExternalBenchmarkSpec
    task_set: BenchmarkTaskSet
    execution_owner: str = "sem+noetrium"
    claim_status: str = "metadata_prepared"

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark.benchmark_id,
            "revision_id": self.benchmark.revision_id,
            "source_url": self.benchmark.source_url,
            "source_digest": self.task_set.source_digest,
            "task_count": len(self.task_set.tasks),
            "execution_owner": self.execution_owner,
            "claim_status": self.claim_status,
        }


def external_benchmark_spec(benchmark_id: str) -> ExternalBenchmarkSpec:
    for spec in EXTERNAL_BENCHMARKS:
        if spec.benchmark_id == benchmark_id:
            return spec
    raise BenchmarkAdapterError(f"unknown external benchmark: {benchmark_id}")


def prepare_external_benchmark(
    benchmark_id: str,
    path: str | Path,
) -> ExternalBenchmarkPreparation:
    spec = external_benchmark_spec(benchmark_id)
    task_set = JsonTaskBenchmarkAdapter(
        spec.benchmark_id, spec.revision_id
    ).build(path)
    return ExternalBenchmarkPreparation(spec, task_set)

__all__ = [
    "BenchmarkAdapterError",
    "JsonTaskBenchmarkAdapter",
    "ExternalBenchmarkSpec",
    "ExternalBenchmarkPreparation",
    "EXTERNAL_BENCHMARKS",
    "external_benchmark_catalog",
    "external_benchmark_spec",
    "prepare_external_benchmark",
    "load_benchmark_tasks",
    "minedojo_adapter",
    "memory_agent_bench_adapter",
]
