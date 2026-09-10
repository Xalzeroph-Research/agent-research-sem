from __future__ import annotations

import argparse
import json
import os

from projects.sem_paper.api import PROJECT_MANIFEST
from projects.sem_paper.benchmarks import (
    benchmark_definition,
    build_benchmark_streams,
    compare_methods,
    external_benchmark_catalog,
    prepare_external_benchmark,
)
from projects.sem_paper.composition import (
    run_confirmatory_smoke,
    run_full_paper_matrix,
    run_full_paper_smoke,
)
from projects.sem_paper.composition.runner import run_real_matrix, run_real_pilot
from projects.sem_paper.experiments.analysis import (
    render_required_figures, write_analysis,
)
from projects.sem_paper.experiments import (
    build_benchmark,
    build_sem_paper_confirmatory_protocol,
    build_full_paper_protocol,
    compile_sem_paper_experiment_plan,
    compile_full_paper_experiment_plan,
    is_confirmatory_protocol,
    PAPER_COMPARISON_IDS,
    PAPER_ABLATION_IDS,
    PAPER_EXPERIMENT_TYPES,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sem")
    parser.add_argument(
        "command",
        choices=(
            "doctor", "protocol", "smoke", "evobench", "benchmark-catalog",
            "experiment-catalog", "full-paper-smoke", "full-paper",
            "external-prepare", "real-pilot", "real", "analyze",
        ),
    )
    parser.add_argument("--track", action="append", dest="tracks")
    parser.add_argument("--streams-per-track", type=int, default=2)
    parser.add_argument("--benchmark-id")
    parser.add_argument("--task-export")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--results-dir")
    parser.add_argument("--planner-mode", choices=("model", "scripted"))
    parser.add_argument("--model-qualified-closure")
    parser.add_argument("--model-request-root")
    parser.add_argument("--analysis-output")
    parser.add_argument("--figure-dir")
    args = parser.parse_args(argv)
    if args.repetitions is not None:
        os.environ["SEM_REPETITIONS"] = str(args.repetitions)
    if args.results_dir:
        os.environ["SEM_RESULTS_DIR"] = args.results_dir
    if args.planner_mode:
        os.environ["SEM_PLANNER_MODE"] = args.planner_mode
    if args.model_qualified_closure:
        os.environ["SEM_MODEL_QUALIFIED_CLOSURE"] = args.model_qualified_closure
    if args.model_request_root:
        os.environ["SEM_MODEL_REQUEST_ROOT"] = args.model_request_root
    if args.command == "experiment-catalog":
        protocol = build_full_paper_protocol(
            repetitions=args.repetitions or int(os.environ.get("SEM_REPETITIONS", "3"))
        )
        plan = compile_full_paper_experiment_plan(protocol)
        payload = {
            "comparisons": list(PAPER_COMPARISON_IDS),
            "ablations": list(PAPER_ABLATION_IDS),
            "experiment_types": list(PAPER_EXPERIMENT_TYPES),
            "conditions": len(protocol.variants),
            "tasks": len(build_benchmark().tasks),
            "repetitions": protocol.repetitions,
            "assignments": len(plan.assignments),
            "task_episodes": len(plan.assignments) * len(build_benchmark().tasks),
            "claim_status": "catalog_only",
        }
    elif args.command == "full-paper-smoke":
        report = run_full_paper_smoke()
        payload = {
            "protocol_digest": report.protocol_digest,
            "plan_digest": report.plan_digest,
            "observations": len(report.observations),
            "claim_status": "diagnostic_smoke_only",
        }
    elif args.command == "full-paper":
        report = run_full_paper_matrix(args.repetitions)
        payload = {
            "environment": "minecraft.mineflayer.jsonl.v1",
            "protocol_digest": report.protocol_digest,
            "plan_digest": report.plan_digest,
            "observations": len(report.observations),
            "aggregates": [
                {"variant_id": row.variant_id, "metric": row.metric_name,
                 "count": row.count, "mean": row.mean}
                for row in report.aggregates
            ],
            "claim_status": (
                "full_paper_real_matrix"
                if os.environ.get("MC_REQUIRE_WORLD_RESET") == "1"
                and os.environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip()
                else "exploratory_full_matrix"
            ),
        }
    elif args.command == "doctor":
        protocol = build_sem_paper_confirmatory_protocol()
        plan = compile_sem_paper_experiment_plan(protocol)
        payload = {
            "project": PROJECT_MANIFEST.identity.key,
            "manifest_digest": PROJECT_MANIFEST.semantic_digest,
            "protocol_digest": protocol.protocol_digest,
            "plan_digest": plan.plan_digest,
            "assignments": len(plan.assignments),
            "tasks": len(build_benchmark().tasks),
            "confirmatory": is_confirmatory_protocol(protocol),
            "claim_status": "smoke_only",
        }
    elif args.command == "protocol":
        protocol = build_sem_paper_confirmatory_protocol()
        plan = compile_sem_paper_experiment_plan(protocol)
        payload = {
            "protocol": protocol,
            "protocol_digest": protocol.protocol_digest,
            "plan_digest": plan.plan_digest,
            "assignments": [
                {"variant_id": item.variant_id, "repetition": item.repetition, "seed": item.seed}
                for item in plan.assignments
            ],
        }
    elif args.command == "benchmark-catalog":
        payload = {
            "benchmarks": [
                {
                    "benchmark_id": item.benchmark_id,
                    "revision_id": item.revision_id,
                    "venue": item.venue,
                    "source_url": item.source_url,
                    "scope": item.scope,
                    "role": item.role,
                    "runtime_status": item.runtime_status,
                }
                for item in external_benchmark_catalog()
            ],
            "claim_status": "catalog_only",
        }
    elif args.command == "external-prepare":
        if not args.benchmark_id or not args.task_export:
            parser.error("external-prepare requires --benchmark-id and --task-export")
        payload = prepare_external_benchmark(
            args.benchmark_id, args.task_export
        ).as_dict()
    elif args.command == "evobench":
        definition = benchmark_definition()
        streams = build_benchmark_streams(
            tracks=tuple(args.tracks or definition.tracks),
            streams_per_track=args.streams_per_track,
        )
        scores = compare_methods(streams)
        payload = {
            "benchmark_id": definition.benchmark_id,
            "revision_id": definition.revision_id,
            "benchmark_digest": definition.digest,
            "streams": len(streams),
            "scores": [score.as_dict() for score in scores],
            "claim_status": "diagnostic_only",
        }
    elif args.command == "analyze":
        root = args.results_dir or os.environ.get("SEM_RESULTS_DIR", "results/real")
        summary = write_analysis(root, output_path=args.analysis_output)
        figure_paths = ()
        if args.figure_dir:
            figure_paths = render_required_figures(root, args.figure_dir)
        payload = {
            **summary,
            "analysis_root": root,
            "figure_paths": [str(path) for path in figure_paths],
        }
    elif args.command == "real":
        report = run_real_matrix(args.repetitions)
        payload = {
            "environment": "minecraft.mineflayer.jsonl.v1",
            "protocol_digest": report.protocol_digest,
            "plan_digest": report.plan_digest,
            "observations": len(report.observations),
            "aggregates": [
                {"variant_id": row.variant_id, "metric": row.metric_name,
                 "count": row.count, "mean": row.mean}
                for row in report.aggregates
            ],
            "claim_status": (
                "confirmatory_real_matrix"
                if os.environ.get("MC_REQUIRE_WORLD_RESET") == "1"
                and os.environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip()
                else "exploratory_real_matrix"
            ),
            "world_reset_per_assignment": (
                os.environ.get("MC_REQUIRE_WORLD_RESET") == "1"
                and bool(os.environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip())
            ),
        }
    elif args.command == "real-pilot":
        plan, observation = run_real_pilot()
        payload = {
            "environment": "minecraft.mineflayer.jsonl.v1",
            "protocol_digest": plan.protocol_digest,
            "plan_digest": plan.plan_digest,
            "assignment": {
                "variant_id": observation.assignment.variant_id,
                "repetition": observation.assignment.repetition,
                "seed": observation.assignment.seed,
            },
            "metrics": dict(observation.metrics),
            "claim_status": "pilot_not_claim_ready",
        }
    else:
        report = run_confirmatory_smoke()
        payload = {
            "protocol_digest": report.protocol_digest,
            "observations": len(report.observations),
            "aggregates": [
                {"variant_id": row.variant_id, "metric": row.metric_name,
                 "count": row.count, "mean": row.mean}
                for row in report.aggregates
            ],
            "claim_status": "smoke_only",
        }
    print(json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())