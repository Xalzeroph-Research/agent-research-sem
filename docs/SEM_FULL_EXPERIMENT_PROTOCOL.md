# SEM Full Experiment Protocol

## Scope

This document is the executable implementation of the September 7 SEM research
design. The canonical upstream runtime is the Noetrium main checkout on node1;
the SEM runtime adapter records Noetrium code commit
'519d8aeb88b691358939763797ca080f27acda68' and the run manifest records the
full Noetrium checkout commit used at launch.

The suite separates claim-ready Minecraft measurements from diagnostic
mechanism views. A diagnostic view never upgrades a run to claim-ready.

## Conditions

The comparison set contains six methods:

1. 'fixed_memory': fixed typed memory.
2. 'rule_based_evolution': deterministic rule-based structural evolution.
3. 'full_sem': the complete SEM condition.
4. 'flat_memory': flat episodic memory.
5. 'skill_library': skill-library comparison profile.
6. 'planning_reference': planning reference without memory.

The mechanism set contains nine ablations:

1. 'no_create'
2. 'create_only'
3. 'no_historical_backfill'
4. 'no_neutral_monitor'
5. 'no_trusted_gate'
6. 'no_forward_maintenance'
7. 'no_context_adaptation'
8. 'no_granularity_adaptation'
9. 'no_residency_adaptation'

The executable protocol has 15 conditions. Every assignment records its
condition, base treatment, ablation policy, implementation digest and
checkpoint identity.

## Experiment families

The ten September 7 experiment types are represented by analysis views over
the same sealed assignment evidence:

| Type | Primary derived measure |
|---|---|
| semantic_representation | functional coverage |
| structure_discovery | architecture churn |
| edit_capability | accepted edit rate |
| historical_backfill | historical backfill coverage |
| trustworthiness | provenance completeness |
| long_horizon_tasks | long-horizon success rate |
| transfer | memory-use success |
| environment_drift | sustained target effect |
| stability | reversal rate |
| cost | risk-cost utility |

The raw Minecraft task stream remains the source of truth. Derived views do not
rewrite raw evidence and are reproducible with 'cli analyze'.

## Scale and commands

With 12 tasks and three repetitions, the complete suite is:

- 15 conditions
- 45 assignments
- 540 task episodes
- one fresh world reset per assignment
- one sealed result artifact per assignment

Run the catalog and diagnostic smoke:

    python -m projects.sem_paper.cli experiment-catalog --repetitions 3
    python -m projects.sem_paper.cli full-paper-smoke --repetitions 1

Run the real suite on node1 only after live model qualification:

    python -m projects.sem_paper.cli full-paper --repetitions 3
    python -m projects.sem_paper.cli analyze --results-dir "$SEM_RESULTS_DIR"

The node1 launch must use the current Noetrium Minecraft image, model
qualification closure, 'MC_REQUIRE_WORLD_RESET=1', the node1 reset command,
model request evidence, action-recovery evidence, and a unique results root.

## Claim gate

A result is claim-ready only when all of the following hold:

- all 45 assignments are present and matched to the frozen plan;
- the real vanilla Minecraft environment is used;
- the model planner is bound through a non-expired Noetrium closure;
- every assignment has a fresh-world reset receipt;
- actions have verified effect receipts and durable recovery evidence;
- every task has closed evidence with episode, world, observation, action,
  timestamp, source and provenance fields;
- Noetrium and SEM identities do not drift during execution;
- analysis is run from the sealed raw result root;
- failures and retries remain in the evidence ledger.

Any missing condition is reported as exploratory or diagnostic; it is never
silently treated as a paper result.
