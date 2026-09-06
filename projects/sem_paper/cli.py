from __future__ import annotations

import argparse
import json

from projects.sem_paper.api import PROJECT_MANIFEST
from projects.sem_paper.composition import run_confirmatory_smoke
from projects.sem_paper.composition.runner import run_real_matrix, run_real_pilot
from projects.sem_paper.experiments import (
    build_benchmark,
    build_sem_paper_confirmatory_protocol,
    compile_sem_paper_experiment_plan,
    is_confirmatory_protocol,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sem")
    parser.add_argument("command", choices=("doctor", "protocol", "smoke", "real-pilot", "real"))
    args = parser.parse_args(argv)
    if args.command == "doctor":
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
    elif args.command == "real":
        report = run_real_matrix()
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
                "exploratory_real_matrix"
                if not __import__("os").environ.get("MC_REQUIRE_WORLD_RESET") == "1"
                else "confirmatory_real_matrix"
            ),
            "world_reset_per_assignment": bool(
                __import__("os").environ.get("MC_ASSIGNMENT_RESET_COMMAND", "").strip()
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