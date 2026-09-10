from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any


@dataclass(frozen=True, slots=True)
class AssignmentRecord:
    assignment_id: str
    treatment_id: str
    repetition: int
    payload: Mapping[str, Any]
    status: str = "succeeded"


def load_assignment_records(root: str | Path) -> tuple[AssignmentRecord, ...]:
    root = Path(root)
    records: list[AssignmentRecord] = []
    if not root.exists():
        return ()
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        assignment = payload.get("assignment")
        if not isinstance(assignment, Mapping) or not isinstance(payload.get("tasks"), list):
            continue
        variant = payload.get("variant", {})
        treatment = str(assignment.get("variant_id") or variant.get("variant_id") or "")
        if not treatment:
            continue
        records.append(AssignmentRecord(
            str(assignment.get("assignment_id", path.stem)),
            treatment,
            int(assignment.get("repetition", 0)),
            payload,
            str(payload.get("status", "succeeded")),
        ))
    return tuple(records)


def _mean(values: Iterable[float]) -> float:
    values = tuple(float(value) for value in values)
    return statistics.fmean(values) if values else 0.0


def _quantile(values: Iterable[float], probability: float) -> float:
    values = sorted(float(value) for value in values)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = probability * (len(values) - 1)
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (index - low)


def bootstrap_mean_ci(
    values: Iterable[float],
    *,
    samples: int = 2000,
    seed: int = 17,
) -> tuple[float, float, float]:
    values = tuple(float(value) for value in values)
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    means = [
        _mean(rng.choice(values) for _ in range(len(values)))
        for _ in range(max(1, samples))
    ]
    return _mean(values), _quantile(means, 0.025), _quantile(means, 0.975)


def paired_permutation_ci(
    deltas: Iterable[float],
    *,
    samples: int = 4096,
    seed: int = 23,
) -> tuple[float, float, float]:
    deltas = tuple(float(value) for value in deltas)
    if not deltas:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    means = [
        _mean(
            value if rng.randrange(2) else -value
            for value in deltas
        )
        for _ in range(max(1, samples))
    ]
    return _mean(deltas), _quantile(means, 0.025), _quantile(means, 0.975)


def _task_metrics(payload: Mapping[str, Any]) -> dict[str, float]:
    tasks = tuple(row for row in payload.get("tasks", ()) if isinstance(row, Mapping))
    if not tasks:
        return {}
    success = [float(bool(row.get("success"))) for row in tasks]
    long_horizon = [
        float(bool(row.get("success")))
        for row in tasks
        if str(row.get("family", "")) == "long_horizon_mixed"
        or int(row.get("steps", 0)) >= 40
    ]
    memory_used = [
        float(bool(row.get("success")))
        for row in tasks
        if int(row.get("memory_queries", 0)) > 0
    ]
    diagnostics = payload.get("diagnostics", {})
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    candidates = float(diagnostics.get("candidate_count", 0))
    adopted = float(diagnostics.get("adopted_count", 0))
    rejected = float(diagnostics.get("rejected_count", 0))
    evidence = float(diagnostics.get("evidence_count", 0))
    backfill = float(diagnostics.get("historical_backfill_count", 0))
    query_cost = float(diagnostics.get("memory_queries", 0))
    evolution_cost = candidates + adopted
    utility = _mean(float(row.get("utility", 0.0)) for row in tasks)
    return {
        "success_rate": _mean(success),
        "long_horizon_success_rate": _mean(long_horizon),
        "knowledge_memory_usage_success": _mean(memory_used),
        "historical_backfill_coverage": backfill / max(evidence, 1.0),
        "accepted_edit_rate": adopted / max(candidates, 1.0),
        "useful_abstraction_rate": float(
            diagnostics.get("useful_abstraction_rate", 0.0)
        ),
        "architecture_churn": evolution_cost,
        "reversal_rate": float(diagnostics.get("reversal_rate", 0.0)),
        "evolution_delay": float(diagnostics.get("evolution_delay", 0.0)),
        "sustained_target_effect": float(
            diagnostics.get("sustained_target_effect", 0.0)
        ),
        "functional_coverage": (
            float(diagnostics.get("active_node_count", 0))
            / max(float(diagnostics.get("node_count", 0)), 1.0)
        ),
        "invalid_proposal_rejection_rate": rejected / max(candidates, 1.0),
        "source_compatibility_failure_rate": float(
            diagnostics.get("source_compatibility_failure_rate", 0.0)
        ),
        "provenance_completeness": float(
            diagnostics.get("provenance_completeness", 1.0 if evidence else 0.0)
        ),
        "audit_leakage_rate": float(diagnostics.get("audit_leakage_rate", 0.0)),
        "candidate_isolation_integrity": float(
            diagnostics.get("candidate_isolation_integrity", 1.0)
        ),
        "materialization_confluence": float(
            diagnostics.get("materialization_confluence", 1.0)
        ),
        "risk_cost_utility": utility - 0.01 * query_cost - 0.01 * evolution_cost,
        "utility_mean": utility,
        "steps_total": float(sum(int(row.get("steps", 0)) for row in tasks)),
        "duration_s_total": float(sum(float(row.get("duration_s", 0.0)) for row in tasks)),
        "memory_queries_total": float(sum(
            int(row.get("memory_queries", 0)) for row in tasks
        )),
        "verified_actions_total": float(sum(
            int(row.get("verified_actions", 0)) for row in tasks
        )),
        "evidence_closed_total": float(sum(
            int(bool(row.get("evidence_closed"))) for row in tasks
        )),
    }


def _family_metrics(records: Iterable[AssignmentRecord]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        for row in record.payload.get("tasks", ()):
            if not isinstance(row, Mapping):
                continue
            family = str(row.get("family", "unknown"))
            grouped[family].append(float(bool(row.get("success"))))
    return {
        family: {
            "task_count": len(values),
            "success_rate": _mean(values),
            "mean_ci95": bootstrap_mean_ci(values),
        }
        for family, values in sorted(grouped.items())
    }


def analyze_run(records: Iterable[AssignmentRecord]) -> dict[str, Any]:
    records = tuple(records)
    good = tuple(r for r in records if r.status != "failed" and r.payload.get("tasks"))
    failed = tuple(r for r in records if r.status == "failed")
    mv: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in good:
        for metric, value in _task_metrics(r.payload).items():
            mv[r.treatment_id][metric].append(value)
    treatments = {
        t: {m: {"mean": _mean(v), "ci95": list(bootstrap_mean_ci(
            v, seed=sum(map(ord, m)))), "assignment_values": v}
            for m, v in sorted(ms.items())}
        for t, ms in sorted(mv.items())
    }
    by_key = {(r.treatment_id, r.repetition): _task_metrics(r.payload) for r in good}
    fixed_id = "fixed_memory" if any(r.treatment_id == "fixed_memory" for r in good) else "fixed_typed"
    sem_id = "full_sem" if any(r.treatment_id == "full_sem" for r in good) else "sem"
    fixed = {r.repetition: _task_metrics(r.payload) for r in good if r.treatment_id == fixed_id}
    paired = {}
    for metric in sorted({m for v in by_key.values() for m in v}):
        ds = [by_key[(sem_id, rep)].get(metric, 0.0) - fixed[rep].get(metric, 0.0)
              for rep in sorted(fixed) if (sem_id, rep) in by_key]
        if ds:
            paired[metric] = {f"{sem_id}_minus_{fixed_id}": list(paired_permutation_ci(ds)),
                              "deltas": ds}
    observed = {r.treatment_id for r in records}
    core = {"no_memory", "flat_episodic", "fixed_typed", "sem"}
    from projects.sem_paper.experiments.protocol import FULL_PAPER_IDS
    full = set(FULL_PAPER_IDS)
    expected = full if observed & full else core if core <= observed else observed
    counts = Counter(r.treatment_id for r in records)
    expected_count = len(expected) * 3
    missing = {c: max(0, 3-counts.get(c, 0)) for c in sorted(expected) if counts.get(c, 0) < 3}
    complete = bool(expected) and len(records) == expected_count and set(counts) == expected and not missing
    def safe(r):
        q = r.payload.get("world_reset_receipt")
        return (r.status == "succeeded"
                and r.payload.get("environment_id") == "minecraft.mineflayer.jsonl.v1"
                and r.payload.get("world_reset_per_assignment") is True
                and isinstance(q, Mapping) and q.get("status") == "succeeded"
                and bool(r.payload.get("qualified_model_bound"))
                and bool(r.payload.get("tasks"))
                and all(bool(x.get("evidence_closed")) for x in r.payload["tasks"] if isinstance(x, Mapping)))
    gate = complete and len(good) == expected_count and not failed and all(safe(r) for r in good)
    cm = {t: {m: _mean(v) for m, v in ms.items()} for t, ms in mv.items()}
    full_sem = cm.get("full_sem", {})
    ablation = {c: {m: float(v-full_sem.get(m, 0.0)) for m, v in ms.items()}
                for c, ms in sorted(cm.items()) if c.startswith("no_") or c == "create_only"}
    emap = {
        "semantic_representation": "functional_coverage", "structure_discovery": "architecture_churn",
        "edit_capability": "accepted_edit_rate", "historical_backfill": "historical_backfill_coverage",
        "trustworthiness": "provenance_completeness", "long_horizon_tasks": "long_horizon_success_rate",
        "transfer": "knowledge_memory_usage_success", "environment_drift": "sustained_target_effect",
        "stability": "reversal_rate", "cost": "risk_cost_utility"}
    experiments = {e: {"metric": m, "conditions": {c: float(ms.get(m, 0.0)) for c, ms in sorted(cm.items())}}
                   for e, m in emap.items()}
    return {
        "assignment_count": len(records), "successful_assignment_count": len(good),
        "failed_assignment_count": len(failed), "condition_counts": dict(sorted(counts.items())),
        "expected_condition_count": len(expected), "expected_assignment_count": expected_count,
        "missing_conditions": missing,
        "failed_assignments": [{"assignment_id": r.assignment_id, "condition": r.treatment_id,
            "repetition": r.repetition, "failure": r.payload.get("failure", {})} for r in failed],
        "treatments": treatments,
        "paired_sem_minus_fixed_typed": paired if sem_id == "sem" and fixed_id == "fixed_typed" else {},
        f"paired_{sem_id}_minus_{fixed_id}": paired,
        "family_metrics": _family_metrics(good), "ablation_deltas_vs_full_sem": ablation,
        "experiment_types": experiments, "complete_matrix": complete, "real_gate": gate,
        "claim_status": "claim_ready_candidate" if gate else "complete_matrix_not_claim_ready" if complete else "incomplete_matrix",
        "statistical_unit": "assignment",
        "notes": ["Confidence intervals are assignment-level bootstrap/permutation intervals.",
                  "Failed assignments are sealed and excluded from outcome estimates.",
                  "A real claim requires every expected assignment, a successful reset receipt, qualified model provenance, and closed task evidence.",
                  "Structural usefulness and sustained effects require held-out temporal audit fields."],
    }

def write_analysis(
    root: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    result = analyze_run(load_assignment_records(root))
    if output_path is None:
        output_path = Path(root) / "analysis_summary.json"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def render_required_figures(
    root: str | Path,
    output_dir: str | Path,
) -> tuple[Path, ...]:
    """Render the seven design-document figures from sealed assignment JSON."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to render SEM figures") from exc
    records = load_assignment_records(root)
    analysis = analyze_run(records)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def save(number: int, title: str, draw: Any) -> None:
        figure, axis = plt.subplots(figsize=(8, 4.5))
        draw(axis)
        axis.set_title(title)
        figure.tight_layout()
        path = output_dir / f"figure_{number}.png"
        figure.savefig(path, dpi=160)
        plt.close(figure)
        paths.append(path)

    def overview(axis: Any) -> None:
        axis.axis("off")
        axis.text(0.02, 0.5, "Experience -> Evidence -> Typed DAG -> Neutral Observation\n"
                      "-> Meta Proposal -> Trusted Validation -> Backfill -> Forward Activation",
                      va="center", fontsize=12)
    save(1, "SEM method overview", overview)

    def architecture(axis: Any) -> None:
        for treatment, values in sorted(analysis["treatments"].items()):
            axis.plot([0, 1], [0, values.get("architecture_churn", {}).get("mean", 0)],
                      marker="o", label=treatment)
        axis.set_xlabel("initial to final")
        axis.set_ylabel("architecture churn")
        axis.legend()
    save(2, "Memory architecture evolution", architecture)

    def performance(axis: Any) -> None:
        names = sorted(analysis["treatments"])
        values = [
            analysis["treatments"][name]["success_rate"]["mean"]
            for name in names
        ]
        axis.bar(names, values)
        axis.set_ylim(0, 1)
        axis.set_ylabel("task success rate")
        axis.tick_params(axis="x", rotation=20)
    save(3, "Long-horizon performance", performance)

    def timeline(axis: Any) -> None:
        names = sorted(analysis["treatments"])
        values = [
            analysis["treatments"][name]["architecture_churn"]["mean"]
            for name in names
        ]
        axis.bar(names, values)
        axis.set_ylabel("candidate + adopted events")
        axis.tick_params(axis="x", rotation=20)
    save(4, "Architecture evolution timeline", timeline)

    def transfer(axis: Any) -> None:
        families = sorted(analysis["family_metrics"])
        values = [
            analysis["family_metrics"][family]["success_rate"]
            for family in families
        ]
        axis.plot(families, values, marker="o")
        axis.set_ylim(0, 1)
        axis.set_ylabel("success rate")
        axis.tick_params(axis="x", rotation=35)
    save(5, "Transfer and environment drift", transfer)

    def cost(axis: Any) -> None:
        names = sorted(analysis["treatments"])
        values = [
            analysis["treatments"][name]["risk_cost_utility"]["mean"]
            for name in names
        ]
        axis.bar(names, values)
        axis.set_ylabel("risk-cost-utility")
        axis.tick_params(axis="x", rotation=20)
    save(6, "Evolution cost and stability", cost)

    def backfill(axis: Any) -> None:
        names = sorted(analysis["treatments"])
        values = [
            analysis["treatments"][name]["historical_backfill_coverage"]["mean"]
            for name in names
        ]
        axis.bar(names, values)
        axis.set_ylabel("historical backfill coverage")
        axis.tick_params(axis="x", rotation=20)
    save(7, "Historical backfill effect", backfill)
    return tuple(paths)


__all__ = [
    "AssignmentRecord",
    "analyze_run",
    "bootstrap_mean_ci",
    "load_assignment_records",
    "paired_permutation_ci",
    "render_required_figures",
    "write_analysis",
]
