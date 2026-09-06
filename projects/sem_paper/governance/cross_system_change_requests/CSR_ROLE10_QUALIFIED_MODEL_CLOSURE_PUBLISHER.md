# CrossSystemChangeRequest — Qualified Model Deployment Closure Publisher

- request_id: `CSR-ROLE10-20260829-QUALIFIED-MODEL-CLOSURE-PUBLISHER`
- requester role/system: `ROLE 10 — SEM Composition / Experiment Integration`
- target owner/system: `ROLE 06B — Model / Deployment / Qualification / Serving`
- status: `TARGET_OWNER_COMMITTED — BLOCKED_ON_PROVENANCE_ABI_SUPERVISOR_MERGE_AND_LIVE_PUBLICATION`

## Concrete problem and failing call path

SEM baseline production is already fail-closed on a platform-qualified model binding. `scripts/sem_paper_minecraft_application.py` delegates closure schema authority to the platform loader, reconstructs the platform-published closure with `load_qualified_model_deployment_closure()`, and calls `PersistedQualifiedModelEndpointBinding(...).binding_for(role="planner", prompt_generation="sem-paper-planner-generation-v1")`.

ROLE 06B has now committed and pushed the v3 runtime-canary authority at `437221aa5e858a1957c021a9b4d9ede1418fdef2` (`feat(model): require live canary qualified closures`). Its selected model/qualification/serving suite reports `133 passed` and the owner worktree is clean. ROLE 10 also verified a conflict-free merge-tree against the downstream branch. The commit is not yet in platform `master`, and its public ABI still lacks durable probe/request-body identity plus content-derived canary identity in `QualifiedModelEndpointBinding`; therefore the handoff remains non-claim-eligible until the target owner closes those ABI gaps, the supervisor merges the platform dependency DAG, and a real Server1 closure is published through that committed authority.

Server1 live observation on 2026-08-29 confirms that `sem-qwen38-qualification-tp2` is serving `sem-qwen38-27b` successfully at `127.0.0.1:30080`, but HTTP health is deliberately not accepted as qualification evidence. `/data1/research-platform/state/model-serving` contains no published qualified closure.

### Server1 qualification inputs observed by ROLE 10

These are live inputs for ROLE 06B qualification, not a downstream substitute for qualification:

- container id: `1a2519404f2116dc7cd524fe8b0391042b2474f145c13dc2b6adaee43b762efd`;
- immutable image digest: `vllm/vllm-openai@sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967`;
- vLLM `0.27.1`, Torch `2.13.0+cu130`, NCCL package `2.30.7`;
- serving profile: `sem-qwen38-27b`, tensor parallel `2`, `bfloat16`, max model length `262144`, endpoint `127.0.0.1:30080`;
- model `config.json` SHA-256 `191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab`;
- tokenizer config SHA-256 `b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27`.

A planner canary also exposed a qualification-critical request contract. With the serving default reasoning mode and `max_tokens=32`, the request returned only hidden reasoning/blank visible content with `finish_reason=length`. The same canary with `chat_template_kwargs={"enable_thinking": false}` returned exactly `{"status":"ok"}` with `finish_reason=stop`. ROLE 10 therefore froze non-thinking mode in production planner commit `d797550ea1b5751be125bf2d53ffac522d8c7134`. ROLE 06B qualification must canary the same effective request semantics; a generic `/health` or `/v1/models` success is insufficient.

## Current public contract

- `research_platform.model.serving.endpoint.providers.qualified_closure_file.load_qualified_model_deployment_closure`
- `research_platform.model.serving.endpoint.providers.qualified_binding.PersistedQualifiedModelEndpointBinding`
- `research_platform.model.serving.api.QualifiedDeploymentManifest`
- `research_platform.model.serving.api.QualificationCertificate`
- `research_platform.model.serving.api.RuntimeQualificationReceipt`
- generic deployment qualification CLI stages: `deployment qualify`, `apply-qualification`, `runtime-qualify`

The consumer contract explicitly states that qualification/deployment systems publish the closure and downstream projects only consume it.

## Required capability / semantic gap

ROLE 06B must provide one platform-owned production authority that turns exact measured deployment facts into an immutable, durable `qualified-model-deployment-closure.v1` and associated runtime qualification evidence. The publisher must bind, rather than infer:

- immutable model identity/revision and model artifact digests;
- exact serving runtime/container image digest and engine build identity;
- CUDA/NCCL/Torch/runtime identities;
- tensor-parallel degree and exact GPU UUID placement;
- host identity digest;
- deployment id and deployment generation;
- endpoint route generation and live readiness/canary evidence;
- measured resource envelope;
- qualified role `planner`;
- runtime qualification receipt and evidence refs;
- immutable closure digest / publication identity.

A mutable image tag, operator URL, model name, successful `/health`, or manually authored JSON must never substitute for the authority above.

## Authority impact

Model qualification/deployment/serving remains the sole producer authority. ROLE 10 remains a read-only consumer of the published closure and binds it into SEM run/scientific provenance. No duplicate downstream model authority is requested.

## Persistence impact

Publication must be durable, publish-once/idempotent for identical content, reject conflicting overwrite, checksum its referenced evidence, and preserve the exact deployment/runtime generation used by the closure. Relative runtime-evidence paths must remain relocatable with the closure bundle or be explicitly materialized as an immutable evidence package.

## Failure / recovery / effect impact

The publisher must fail closed on artifact drift, container/runtime drift, GPU placement drift, route-generation drift, stale heartbeat/readiness, missing canary evidence, missing role qualification, partial publication, or restart to a new deployment generation. Recovery must never reuse an old receipt for a newly started process/container generation.

## Expected consumers

- ROLE 10 SEM Minecraft baseline/preflight composition
- generic downstream projects requiring `QualifiedModelEndpointBinding`
- operator/release qualification gates
- model-serving recovery/admission paths

## Breaking-change impact

`YES` if required. There is no valid production writer to preserve. Prefer one authoritative typed publication path over compatibility shims or a second closure schema.

## Proposed acceptance tests

1. Unit round-trip: publisher → persisted closure → existing loader → `binding_for("planner", "sem-paper-planner-generation-v1")` succeeds and all digests agree.
2. Tamper tests: model artifacts, runtime/container identity, host identity, GPU UUIDs, certificate digest, route generation, runtime receipt digest, and role each fail closed independently.
3. Publication tests: identical replay is idempotent; conflicting replay is rejected; interrupted/partial publication never exposes a valid closure.
4. Lifecycle test: container/process restart changes generation and invalidates the previous live receipt until requalification.
5. Linux/GPU live test on authoritative Server1 using frozen Qwen3.8-27B revision and exact container digest; the canary must use the SEM planner request contract, including `chat_template_kwargs={"enable_thinking": false}`, and reject blank/length-truncated visible output.
6. ROLE 10 integration test consumes only the published closure and records the resulting `QualifiedModelEndpointBinding` digest into the run manifest.

## Read-only integration review of in-progress ROLE 06B publisher

ROLE 10 reviewed the target worktree read-only on 2026-08-29 at base HEAD `26443d6` while the publisher/codec changes were still uncommitted. The direction is correct: strict v2 codec, closure digest, deployment/route alignment, interprocess publication lock, runtime receipt readback, role coverage, and publish-once closure semantics are present. The following items still need to close before handoff:

1. The focused target suite currently reports `9 passed, 1 failed`. `test_identical_replay_is_idempotent_and_conflict_is_rejected` fails because `DirectoryRuntimeQualificationEvidenceStore.publish()` compares a JSON-loaded payload containing lists against the in-memory payload containing tuples, so an identical replay is misclassified as conflicting evidence. Canonicalize both sides before equality/digest comparison.
2. Closure publication accepts a directly constructed `RuntimeQualificationReceipt` and checks only `created_at > 0`; neither publication nor `PersistedQualifiedModelEndpointBinding` enforces receipt freshness. A stale but structurally valid receipt can therefore be rebound later. Freshness/expiry must be an explicit persisted policy/identity and fail closed at publication and/or binding time.
3. `ServiceHeartbeat` carries `pid`, `process_start_marker`, `argv_digest`, readiness and timestamp, but `RuntimeQualificationReceipt` does not persist the process-instance identity. The durable closure therefore cannot prove that a later binding still refers to the process/container instance that passed the canary. Bind a process/deployment generation digest derived from the live heartbeat/runtime generation and invalidate it on restart.
4. `evidence_refs` are currently only required to be non-empty strings. The closure publisher must resolve or otherwise verify immutable/content-addressed canary/performance evidence and bind those evidence digests into the durable authority; opaque strings alone do not satisfy the requested evidence checksum invariant.
5. The in-progress codec intentionally moves to `qualified-model-deployment-closure.v2`. ROLE 10 does not require v1 compatibility, but after ROLE 06B lands this breaking contract, downstream audit/consumer tests must migrate atomically to v2 before claim-eligible execution.

These are integration acceptance findings only. ROLE 10 must not patch the target-owned model-serving files.
## Second read-only integration review

A second read-only review was performed after ROLE 06B committed `8caf794 feat(model): publish immutable qualified closures` and `6552de5 fix(model): stabilize qualification publication lock keys`, with additional target-owned fixes still uncommitted. The focused closure/runtime-qualification/generation/transport suite now reports `24 passed`.

The earlier replay, freshness, and process-generation findings are materially addressed in the in-progress target tree: runtime receipts persist `process_pid`, `process_start_marker`, `argv_digest`, `heartbeat_timestamp`, and `valid_until`; stale receipts are rejected at publication and binding; digest-bound heartbeat evidence is reconstructed; process restart changes receipt identity; and runtime receipt storage uses a strict v3 codec.

One qualification-critical gap remains: digest-bound `canary:sha256:*` and `performance:sha256:*` references are accepted as optional extras, but the receipt/publication contract does not require a planner canary reference or performance evidence to be present. A heartbeat-only receipt can therefore still satisfy the closure publisher. Before handoff, the platform authority must require and verify the evidence classes needed by the qualified role, including the real planner canary whose request semantics match SEM (`chat_template_kwargs={"enable_thinking": false}`), rather than treating those refs as optional metadata.

The lifecycle/process-generation fixes landed in ROLE 06B commit `9722795261fc4c52857d3281370c399bfa425f74`. A platform-owned runtime-canary authority is now being developed in the target worktree but is not yet committed. ROLE 10 has independently removed its own hard-coded v1 schema gate so future closure schema acceptance is delegated to the platform loader/codec rather than duplicated downstream.
## Current independent evidence already completed by ROLE 10

Minecraft T2B is no longer the blocker. ROLE 10 has integrated ROLE 09 method commit `2aa1d7ea00d07e223fcbed6652ee630d84f1237d`, migrated its only historical `evolution.diagnostics.AutomaticSliceDiscovery` consumer to the responsibility-owned `evolution.slicing` authority, and rerun the live gate on exact runtime SHA `cc6faafbad8f06f517477ad5e5ca9eee5f3cec85`. Gate digest: `db6288c85fe804aa50dc0c42da224916a299c6d72e2a41705c49c96495d47302`; gate-result SHA-256: `6ba55b9eb2a4920aa1b63e4f416b0962ccd802a01220832121182b4cafc07406`; verified evidence bundle SHA-256: `11e4148583ab2661a8d9193990c0c9c152a1be8000ee9bb86b6aac1bf9c477ab`. Evidence commit `584fca57162b3d7d21522fecb0665442c7382935` passes the integrated Windows matrix (`461 passed, 2 skipped`) and Server1 matrix (`463 passed`) with both architecture audits returning `RC=0`. Older T2B artifacts remain preserved as history but are rejected by the source-current gate.

## Third read-only integration review

ROLE 10 reviewed the in-progress runtime-canary v3 authority after the lifecycle commit `9722795261fc4c52857d3281370c399bfa425f74`. The target tree now compiles and the focused canary/closure/qualification suite reports `31 passed`. The design materially closes the earlier coverage and consumer-revalidation gaps: closure publication requires passed canary coverage for every frozen `(deployment, role)`, binds route and process generation, persists canary evidence through a checksummed content-addressed store, and the loader/binding re-read and revalidate those canary artifacts.

One provenance gap remains before the SEM live handoff. `RuntimeCanaryEvidence.request_digest` is the digest of the complete endpoint request, while neither `request_body_digest` nor the `RuntimeCanaryProbe.digest()` is persisted in the evidence; the runtime-canary path also does not durably record the request body through the model-request ledger. A downstream verifier therefore cannot independently reconstruct from durable authorities that the canary request body was exactly the SEM planner contract (`chat_template_kwargs={"enable_thinking": false}`, JSON-object response mode, bounded output budget) without duplicating the platform-private request construction algorithm. Bind the immutable probe/request-body identity into durable canary evidence (for example `probe_digest` plus `request_body_digest`, backed by a content-addressed/frozen canary-suite authority) and verify it on closure load/binding. The Server1 acceptance can then compare those public identities against the SEM-owned expected probe rather than trusting an opaque full-request digest.

This is a provenance/auditability requirement, not a request to hard-code SEM-specific request fields into the generic platform. ROLE 10 should own the expected SEM probe; ROLE 06B should expose enough immutable public identity for ROLE 10 to verify that exact probe was the one executed.
## Fourth read-only integration review

ROLE 10 also verified its own production run-manifest path. The current SEM manifest already persists the qualified deployment generation, model-stack digest, qualification-certificate digest, runtime-qualification digest, host identity and prompt generation, and the run specification binds `canonical_digest(QualifiedModelEndpointBinding)`. Once runtime canary becomes part of qualification authority, however, the current platform `QualifiedModelEndpointBinding` still exposes no canary evidence identity. Consequently a scientifically frozen SEM run could prove which runtime receipt it used but not which runtime canary artifact(s) authorized that binding.

The platform binding/closure handoff should therefore expose the exact canary evidence identity used for the selected role (for example an immutable sorted tuple of runtime-canary evidence digests, or a single canonical canary-closure digest) and include it in the binding identity. ROLE 10 can then persist that identity directly in `run_manifest.json` and the run-spec `model_binding_digest`, avoiding a parallel downstream authority. This must be content-derived from the canary artifacts that the loader revalidated, not supplied independently by the caller.
## Fifth read-only integration review — final ROLE 10 handoff

The latest target-owner worktree remains based on `9722795261fc4c52857d3281370c399bfa425f74` and is still uncommitted. Its current model qualification/canary/endpoint subset compiles and reports `107 passed`. A new platform composition path, `qualify_and_publish_model_deployment_closure()`, now connects frozen deployments/routes/heartbeats, live role canaries, runtime qualification receipts, and atomic qualified-closure publication. This materially closes the earlier absence of a production orchestration path.

Two public provenance requirements remain unchanged and are visible in the current types. `RuntimeCanaryEvidence` still exposes only the full endpoint `request_digest`, not an independently verifiable `probe_digest` / `request_body_digest`; and `QualifiedModelEndpointBinding` still carries no content-derived runtime-canary evidence identity. These identities are required so ROLE 10 can prove that the exact SEM-owned non-thinking planner probe authorized the exact binding recorded in the scientific run manifest without duplicating platform-private request construction.

Final acceptance therefore requires the target owner to commit the v3 authority with those identities, keep its qualification/serving suites green, publish a real Server1 closure through that committed authority, and hand ROLE 10 the committed platform SHA plus persisted closure path/digest. Until then the downstream audit must remain fail-closed with exactly one blocker: `qualified planner deployment closure is missing`.

## Sixth read-only integration review — committed owner handoff candidate

ROLE 06B has now committed a clean candidate at `437221aa5e858a1957c021a9b4d9ede1418fdef2` (`feat(model): require live canary qualified closures`). Its model/qualification/serving regression selection covers 31 test files and reports `133 passed`; `research_platform/model/serving` also compiles cleanly. The commit is present on the pushed remote branch `refs/heads/system/06-participant-model-renovation`; ROLE 10 verified that the remote ref resolves exactly to `437221aa5e858a1957c021a9b4d9ede1418fdef2`.

The candidate still does not satisfy the final SEM provenance handoff. `RuntimeCanaryEvidence` persists `request_digest` for the complete endpoint request but exposes neither an immutable `probe_digest` nor an independently reconstructable `request_body_digest`. `QualifiedModelEndpointBinding` still exposes no content-derived runtime-canary evidence identity. Therefore a run can prove the runtime qualification receipt it consumed but cannot independently prove which exact SEM-owned canary probe authorized that binding.

ROLE 10 has hardened its own claim gate accordingly: `LIVE_EXECUTION_EVIDENCE` now remains open unless the installed platform public ABI exposes both a reconstructable canary request/probe identity and canary evidence identity in the qualified binding. This does not duplicate platform authority; it prevents an older or incomplete closure ABI from becoming claim-eligible downstream.

## Seventh read-only integration review — final verified acceptance state

ROLE 10 verified the pushed target-owner ref `refs/heads/system/06-participant-model-renovation` at exact commit `437221aa5e858a1957c021a9b4d9ede1418fdef2`. A no-write `git merge-tree --write-tree` between the downstream ROLE 10 branch and that owner ref returned `RC=0` with merge-base `e0003c98ffa873a8d25428de8416f028bae99a99`, so there is no Git conflict blocking integration. The owner branch also contains participant cognition receipt-recovery commits `e586b03` and `815f2bc`, and ROLE 10 validated its corresponding checkpoint adapter in a temporary integration worktree.

The remaining block is semantic authority, not code reachability. In the committed v3 ABI, `RuntimeCanaryEvidence.request_digest` still hashes the complete endpoint request while the evidence does not persist `probe_digest` or `request_body_digest`; `QualifiedModelEndpointBinding` still carries no explicit content-derived runtime-canary evidence identity. ROLE 10 therefore cannot independently prove that the exact SEM-owned non-thinking planner probe authorized the exact binding recorded in a scientific run without reconstructing platform-private request construction.

ROLE 10 has completed its side of the dependency: commit `36bc96b118dd7c3e05cfbf539b3fdeac12b2a63a` fails closed on that provenance handoff and persists cognition receipt checkpoint state; its Server1 T2B is current and verified. Current evidence commit `45d6cd06744f523780fb2b0508e01c01feab15a9` passes all SEM tests on Windows (`232 passed, 2 skipped`) and Server1 (`234 passed`) with both architecture audits returning `RC=0` and the same two live blockers: `qualified model closure authority lacks canary provenance handoff` and `qualified planner deployment closure is missing`.

Final target-owner acceptance requires only: (1) expose and verify reconstructable probe/request-body identity in durable runtime-canary evidence; (2) carry the revalidated canary authority into the public qualified binding identity; (3) merge the platform dependency DAG into `master`; and (4) publish and reload a real Server1 Qwen closure through that exact committed authority. ROLE 10 must not turn either missing condition into a downstream compatibility shim or manually authored closure.

## Eighth read-only integration review - request freezing landed, evidence handoff still open

ROLE 06B advanced the pushed owner branch to `70713c7d32b5e4b9cd785f386608e857cc3bddd7` (`fix(model): freeze runtime canary request identity`). ROLE 10 verified the branch is clean and the remote ref resolves exactly to that commit. The change freezes `RuntimeCanaryProbe.request_body` into canonical immutable JSON before execution, eliminating caller-side mutation drift. Platform `master` nevertheless remains at `e0003c98ffa873a8d25428de8416f028bae99a99`; the owner branch has not yet been merged.

This commit improves request determinism but does not close the scientific provenance handoff. `RuntimeCanaryEvidence` still persists only the digest of the complete endpoint request and does not carry an independently reconstructable probe/request-body identity. `QualifiedModelEndpointBinding` still carries no content-derived runtime-canary evidence identity. Consequently the downstream public ABI still cannot prove, from the final binding alone, which exact immutable SEM planner probe authorized a scientific run.

The ROLE 10 acceptance gate therefore remains intentionally fail-closed. No downstream shim, manually authored closure, or inference from private platform request construction is acceptable. The remaining target-owner work is to persist and verify the frozen probe/body identity in durable canary evidence, carry the revalidated canary authority into the public qualified binding, merge the platform dependency into `master`, and publish/reload the real Server1 Qwen closure through that exact committed authority.


## Ninth read-only integration review — ROLE09 consumer cutover closed

ROLE 09 explicitly left `projects/sem_paper/method/self_evolving_memory/evolution/diagnostics.py` as a temporary cross-owner import seam for ROLE 10. ROLE 10 has now consumed ROLE 09 commit `2aa1d7ea00d07e223fcbed6652ee630d84f1237d` on its integration branch and changed `projects/sem_paper/composition/evolution.py` to import `AutomaticSliceDiscovery` directly from `evolution.slicing`. A regression test rejects reintroduction of the historical diagnostics import, and the integrated tree contains zero ROLE 10 production references to that seam. The compatibility module is therefore cleanup-ready for ROLE 09; ROLE 10 does not delete the ROLE 09-owned file itself.

Because the ROLE 09 merge changes runtime-sensitive method code, ROLE 10 invalidated its prior T2B evidence and reran Server1 T2B on exact consumer-cutover SHA `cc6faafbad8f06f517477ad5e5ca9eee5f3cec85`. The new evidence is current at descendant evidence SHA `584fca57162b3d7d21522fecb0665442c7382935`. This ROLE09→ROLE10 handoff is closed; the only remaining live blocker is the platform-owned qualified-model canary provenance and real planner deployment closure.
