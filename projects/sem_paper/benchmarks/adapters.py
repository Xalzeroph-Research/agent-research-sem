from __future__ import annotations

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
