# SEM protocol

## Ownership

Noetrium is the upstream platform. It owns stable lifecycle, identity,
environment, participant, study, run-control, and evidence contracts.

SEM owns the memory algorithm, Fixed/Rule/Self treatment semantics, Minecraft
task workload, metrics, and scientific claim rules. The downstream package
imports Noetrium only through noetrium.contracts and the documented study
runtime surface.

## Frozen confirmatory design

The Core-6 matrix is:

| family | Seed-C | Seed-X |
|---|---:|---:|
| Fixed memory | control | control |
| Rule-based evolution | treatment | treatment |
| Self-evolving memory | treatment | treatment |

There are 12 repetitions, six manifest tasks per assignment, and seven typed
metrics. The compiled ExperimentPlan is the only execution authority.

## Environment boundary

The local scripted Minecraft provider implements the Noetrium
EnvironmentProviderPort and EnvironmentSession lifecycle. It is a
deterministic conformance fixture. Real Mineflayer/RCON execution can replace
the fixture at the compiled plan boundary.

Benchmark, replay, synthetic, tool, and multi-agent are not environment
categories and are not implemented as environments here.

## Evidence status

sem smoke produces protocol-bound smoke evidence. It is deliberately not
claim-ready evidence: a scientific claim requires a qualified real provider,
frozen deployment/model bindings, and published evidence through Noetrium's
run/evidence contracts.
