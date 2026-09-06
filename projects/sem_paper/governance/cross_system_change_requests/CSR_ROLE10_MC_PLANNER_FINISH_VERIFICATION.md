# CrossSystemChangeRequest ? Minecraft planner-finish verification

- request_id: `CSR-ROLE10-MC-PLANNER-FINISH-VERIFICATION-20260829`
- requester_system: `ROLE 10 / SEM Composition & Experiment Integration`
- target_system: `ROLE 05B / environment.minecraft`
- problem: The reusable Minecraft cognition completion adapter can accept a planner `finish` claim without an authoritative action verification receipt.
- root cause: `MinecraftAgentCompletion.is_complete()` implements `planner_finish` as `planner_finished and bool(last_receipt is None or last_receipt.accepted)`. Absence of a receipt is therefore treated as success, and an accepted-but-unverified receipt is also sufficient.
- current contract: Planner completion intent and environment/effect verification are conflated in the reusable Minecraft completion predicate.
- required capability: A planner completion intent must remain non-authoritative until a task-specific grounded state predicate or a positively verified/confirmed action receipt proves completion.
- proposed contract: For `planner_finish`, require a non-null receipt with `accepted is True`, `verified is True`, and effect certainty compatible with confirmed execution; alternatively retire `planner_finish` in favor of explicit grounded predicates. Missing/unknown verification must fail closed.
- affected callers: SEM cognition composition and any downstream caller using `AgentGoal.context.success.kind = planner_finish` through `MinecraftCognitionRunner`.
- authority impact: Moves completion authority from planner intent to environment/effect evidence; no new durable authority.
- persistence impact: Checkpointed task results must record only grounded completion; historical receipts using the old semantics must not be reused as claim evidence.
- failure/recovery impact: Resume/replay must not turn absent receipts into success. Unknown external effects require reconciliation rather than completion.
- scientific semantics impact: P0. The old behavior can manufacture positive task outcomes without world/effect proof and therefore bias scientific metrics.
- breaking change: Yes. Existing tests or smoke fixtures that expect finish-without-action to succeed must migrate to an explicit grounded success predicate.

ROLE 10 applies a downstream fail-closed guard for SEM only. It does not modify `research_platform/environment/minecraft/**`.
