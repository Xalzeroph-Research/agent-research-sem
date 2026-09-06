# SEM architecture repair status

This change set closes the repository-local Paper architecture findings while
keeping live execution claims fail-closed.

Closed in the source tree:

- production SEM evolution is composed through the seven-stage,
  evidence-bound `PipelineSessionEvolutionFactory` seam;
- declaration-only topology leaves were removed and the catalog was regenerated;
- selected environment, experiment, checkpoint, workload, and model endpoint
  APIs use shared JSON boundary types instead of `object` payloads;
- the Core-6/ablation protocol and typed scientific metric registry are frozen;
- live evidence now has an immutable, digest-bearing receipt and a standalone
  verifier.

Live execution remains externally blocked in the current environment. The
observed preflight has Java 17 where Java >=21 is required, no resolvable
Mineflayer packages, and no checked-in Minecraft server jar. Therefore no
qualified model closure, T2B PASS, T3 unlock, or scientific claim is produced.
The `BLOCKED_BY_ENVIRONMENT` state is a valid evidence outcome but is never
claim-eligible; a real qualified deployment and persistent-world T2B run must
produce the PASS receipt outside this hosted environment.
