# SEM protocol

## Ownership

Noetrium is the upstream platform. It owns stable lifecycle, identity,
environment/provider, participant, study, run-control, assignment isolation,
action/effect, and evidence contracts.

SEM owns the memory algorithm, Fixed/Rule/Self treatment semantics, benchmark
task-stream semantics, metrics, analysis, and scientific claim rules. The
downstream package imports Noetrium only through noetrium.contracts and the
documented study runtime surface.

## Current primary protocol

The current SEM-owned protocol is SEM-EvoBench v1. It has four tracks:
memory_core, experience_transfer, agentic_closed_loop, and environment_drift.
Each track is a six-episode ordered stream with matched fixed_memory,
rule_based, and self_evolving treatments.

The executable definition, stream digests, paired-control scoring, candidate
validation, and raw traces live in projects/sem_paper/benchmarks/evo_protocol.py.
Use:

    python -m projects.sem_paper.cli evobench --streams-per-track 2

## Treatment and evidence rules

fixed_memory is immutable. rule_based adopts a bounded candidate immediately.
self_evolving requires later verified positive utility before adoption. The
candidate lifecycle is explicit: proposed, validated, adopted/rejected,
generation, and policy override.

The local scripted Minecraft provider implements the Noetrium environment
lifecycle and is a deterministic conformance fixture. It cannot confer a
scientific claim. Real Mineflayer execution can replace the fixture at the
compiled plan boundary only after assignment reset, effect receipts, recovery,
and evidence closure are verified.

## Legacy status

The old Minecraft Core-6 matrix remains available for compatibility through
the legacy protocol CLI, but it is archived and not claim-bearing. The audit
found treatment/identity and causal-closure defects in its earlier evidence.
Its results must not be pooled with SEM-EvoBench.

Benchmark, replay, synthetic, tool, and multi-agent are not environment
categories. External benchmark adapters import metadata only and keep
execution at the SEM method -> Noetrium environment -> effect/evidence
boundary.

See SEM_EVO_BENCHMARK.md and BENCHMARK_INTEGRATION_20260906.md for the
frozen benchmark and external comparison roles.
