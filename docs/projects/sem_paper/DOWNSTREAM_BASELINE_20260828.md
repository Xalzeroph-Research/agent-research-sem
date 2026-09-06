# SEM Downstream Baseline — 2026-08-28

This repository is the single active downstream SEM repository derived from the reusable Agent Research Platform Git history.

- Upstream repository: `Xalzeroph/Noetrium`
- Downstream GitHub repository: `Xalzeroph-Research/agent-research-sem` (true fork)
- Upstream platform tag: `v0.43.1`
- Upstream platform commit: `f9c1740dddd2cde6f0e13c0042637b8bb0eb4938`
- Current upstream tracking head: `8941ce502e485d3c108be83c708461426ca6c7bb`
- Upstream adoption merge: `2c4dc3e`
- First restored downstream baseline: `cb291d0`
- Preserved pre-split SEM tag: `sem-presplit-20260828`
- Preservation commit: `3710a3585e27`
- Canonical downstream branch: `main`

## Ownership after the split

The upstream owns all reusable `research_platform/` code, including the reusable Minecraft provider. SEM must not carry a private override of that package tree.

SEM owns `projects/sem_paper/`, project model/deployment profiles, experiment manifests, scientific application scripts, SEM-specific tests, server-fleet reproducibility records, and scientific evidence interpretation.

The dependency direction is one-way: SEM may import public platform contracts; the platform must never import `projects.sem_paper`.

## Scientific identity

Primary model identity is `Qwen/Qwen3.8-27B` at revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, BF16, context length 262144. Logical roles are `planner`, `semantic`, `meta`, and `diagnostic`; each role retains an independently frozen prompt identity and qualified endpoint binding.

The upstream 0.43.1 line contains the reusable live-hardening fixes needed by the Minecraft provider. Project-level Minecraft task semantics, workload bindings, checkpoints, evidence rules, and scientific claims remain downstream-owned.

Full Core-6 remains unstarted as claim-eligible scientific execution until the current deployment, role-binding, evolution-authority, smoke, repository, and evidence gates close.
