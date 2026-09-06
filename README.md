# Agent Research SEM

Self-Evolving Memory (SEM) is a downstream research project implemented on
the Noetrium platform.

## Repository boundary

- Noetrium owns lifecycle, identity, environment/provider, action/effect,
  assignment isolation, run control, and evidence contracts.
- SEM owns the memory method, Fixed/Rule/Self treatment semantics, the
  SEM-EvoBench task streams, metrics, and claim eligibility.
- The local scripted Minecraft adapter is a deterministic conformance fixture.
  Its output is not a scientific claim.
- Benchmark, replay, synthetic, tool, and multi-agent are separate concepts,
  not environment implementations.

## Quick start

Use Python 3.11 or newer with Noetrium 0.44.x available:

    set PYTHONPATH=E:\Agent-Research-Workspace\projects\active\agent-research-platform-system
    python -m projects.sem_paper.cli evobench --streams-per-track 2
    python -m projects.sem_paper.cli benchmark-catalog

The primary benchmark is SEM-EvoBench v1: four tracks, six ordered episodes per
stream, matched fixed_memory/rule_based/self_evolving arms, delayed candidate
validation, paired-control deltas, and raw lifecycle traces.

The old Minecraft Core-6 matrix remains a compatibility path only. It is
archived and its earlier evidence is not pooled with SEM-EvoBench.

External benchmark metadata can be prepared with:

    python -m projects.sem_paper.cli external-prepare --benchmark-id memory-agent-bench --task-export export.json

External preparation does not execute a benchmark. See
docs/SEM_EVO_BENCHMARK.md and docs/BENCHMARK_INTEGRATION_20260906.md.
