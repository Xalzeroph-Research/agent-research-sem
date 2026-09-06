# SEM final execution runbook

This runbook describes the executable final path. It does not manufacture
qualified model or live-world evidence. A run may complete operationally while
remaining ineligible for a scientific claim; that distinction is intentional.

## Frozen execution contract

The production protocol is Core-6:

| Seed | Fixed | RuleBased | SelfEvolve |
| --- | --- | --- | --- |
| Seed-C | Fixed-C | Rule-C | Self-C |
| Seed-X | Fixed-X | Rule-X | Self-X |

Each arm runs for 12 repetitions. The compiled `ExperimentPlan` binds every
arm to a provider, seed, ablation policy and comparator role. The matrix
executor rejects undeclared, missing or duplicate assignments and returns
plan/binding digests with the observations and aggregates.

## Non-Minecraft conformance run

This is the deterministic portability check for the complete matrix:

```bash
python scripts/run_sem_non_minecraft_experiment.py \
  --run-id sem-core6-reference \
  --matrix-profile core-6 \
  --repetitions 12 \
  --output-dir runs/sem_paper_non_minecraft/sem-core6-reference
```

Expected matrix-level output is 6 variants × 12 repetitions = 72
observations. This run validates plan compilation, adapter dispatch,
checkpointable workload execution and artifact separation. It is not a
Minecraft live-evidence receipt and cannot unlock a paper claim by itself.

## Minecraft production run

First install the bridge dependencies and prepare the exact Java/Minecraft
assets described in the repository README. Then run the strict production
entrypoint:

```bash
python scripts/run_sem_minecraft_experiment.py --mode baseline \
  --run-id sem-core6-minecraft \
  --server-jar "$SEM_MC_SERVER_JAR" \
  --qualified-model-closure "$SEM_MC_QUALIFIED_MODEL_CLOSURE" \
  --live-evidence "$SEM_MC_LIVE_EVIDENCE" \
  --scientific-auxiliary-evidence "$SEM_MC_SCIENTIFIC_AUXILIARY_EVIDENCE" \
  --accept-minecraft-eula
```

The qualified closure must identify the exact model deployment and runtime.
The live receipt must be a PASS receipt from the persistent-world T2B gate,
with Core-6/repetition, source-tree, protocol, plan, binding and metric
manifest digests matching this run. The auxiliary receipt must contain the
four non-workload estimands and evidence references for held-out edit-local
effect, trajectory divergence, historical backfill and governance integrity.

## Minecraft cognition loop

The Minecraft workload now runs through the platform cognition runtime:

```text
observe -> recall -> select registered skill -> execute bounded action
        -> verify/evidence -> persist experience -> replan
```

The model receives the registered action catalog and retrieved typed skill
recipes as prompt context. A workload binding shares the skill library across
its tasks and checkpoints it with the environment and method state. Reactive
provider modes may request `replan`, a contract-validated `preempt` action, or
`abort`; malformed or unregistered urgent actions fail closed. This keeps
Mindcraft-style planning, interruption and reusable experience inside the
platform's Action ABI, verification and evidence boundaries.

The migration intentionally does not enable arbitrary model-generated code or
shell execution. All Minecraft effects still cross the registered action
contract and return an applied/rejected/verified receipt.

## Resume

Resume only with the original run id, output directory and durable index:

```bash
python scripts/run_sem_minecraft_experiment.py --mode baseline \
  --run-id "$SEM_RUN_ID" \
  --output-dir "$SEM_RUN_ROOT" \
  --resume-index "$SEM_RUN_ROOT/resume_index.json" \
  --qualified-model-closure "$SEM_MC_QUALIFIED_MODEL_CLOSURE" \
  --live-evidence "$SEM_MC_LIVE_EVIDENCE" \
  --scientific-auxiliary-evidence "$SEM_MC_SCIENTIFIC_AUXILIARY_EVIDENCE"
```

The resume identity includes the run specification, protocol, task manifest,
candidate digest and repetition count. A changed identity fails closed.

## Release gates

Run these checks from the exact checkout used for execution:

```bash
python scripts/architecture_gate.py
python scripts/sem_paper_architecture_audit.py
python scripts/verify_sem_paper_live_evidence.py "$SEM_MC_LIVE_EVIDENCE" \
  --source-tree-digest "$SEM_PAPER_SOURCE_TREE_DIGEST" \
  --require-claim-eligibility
python scripts/verify_sem_paper_scientific_auxiliary_evidence.py \
  "$SEM_MC_SCIENTIFIC_AUXILIARY_EVIDENCE" \
  --source-tree-digest "$SEM_PAPER_SOURCE_TREE_DIGEST" \
  --plan-digest "$SEM_PAPER_PLAN_DIGEST" \
  --protocol-digest "$SEM_PAPER_PROTOCOL_DIGEST" \
  --binding-digest "$SEM_PAPER_BINDING_DIGEST"
```

`scientific_closure.json` is the authoritative project result. It contains
the metric report, complete-case paired statistics, multiplicity correction,
live-evidence receipt, auxiliary-evidence validation and final claim gate. A
run with missing or mismatched evidence remains an auditable blocked result;
it must not be relabeled as a successful paper experiment.
