# Paper-1 Project Documents

This directory is the documentation owner for the current self-evolving-memory
Minecraft paper project. It contains project-level production audits and
scientific execution decisions. The executable project composition lives in
`projects/sem_paper`; reusable Minecraft, model, server and observability
capabilities remain platform-owned under `research_platform`.

Project execution follows the verified ladder:

```text
unmodified baseline reproduction -> small smoke -> full paired experiment
```

Every run must retain its manifest, logs, failure evidence and comparability
decision under the project evidence path; an operational success is not a
scientific result by itself.

## Current completeness authority

Read [PAPER_IMPLEMENTATION_COMPLETENESS_AUDIT_20260823.md](PAPER_IMPLEMENTATION_COMPLETENESS_AUDIT_20260823.md)
before changing the experiment. It separates contract/test/production/evidence
status and lists the currently open platform, method, baseline, MC and non-MC
surfaces. The machine-readable companion is
`../../scripts/sem_paper_architecture_audit.py`.

The implemented delta after that audit is recorded in
[SEM_PORTABLE_RUNTIME_MILESTONE_20260824.md](SEM_PORTABLE_RUNTIME_MILESTONE_20260824.md).
It closes the concrete non-Minecraft execution and MC checkpoint/resume gaps,
while keeping real evolution, the full matrix, full metric registry and live
execution evidence explicitly open.

## Evolution authority

The current SelfEvolve/RuleBased authority split and deterministic paired acceptance policy are documented in [SEM_EVOLUTION_AUTHORITY_V1.md](SEM_EVOLUTION_AUTHORITY_V1.md). SelfEvolve reflects on each fresh authoritative evidence cut and delegates the maintain-vs-evolve decision to the qualified Meta role; RuleBased retains its fixed comparator thresholds.
