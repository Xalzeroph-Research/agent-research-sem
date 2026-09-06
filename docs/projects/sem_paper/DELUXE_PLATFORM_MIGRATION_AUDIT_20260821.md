# Paper-1 Deluxe migration audit — 2026-08-21

## Authority of this audit

The legacy Deluxe design is specified by:

- `memory-evolving/v034_work/DELUXE_COMPLETION_MATRIX.md`;
- `memory-evolving/v034_work/DELUXE_IMPLEMENTATION_REPORT.md`;
- `docs/research/memory/SEM_METHOD_CORE_V14.md`;
- `docs/research/memory/SEM_EVOLUTION_DECOMPOSITION_V22.md`;
- `docs/research/memory/SELF_EVOLVING_MEMORY_PLUGIN.md`.

The legacy report claims an 81-test Standard/Deluxe implementation, but that
claim belongs to the old `v034_work` tree. It is not evidence that the current
`agent-research-platform-system` tree has a runnable Deluxe treatment. This
document prevents the old completion claim from being silently promoted to the
new platform.

## Current platform fact

The current Paper-1 implementation under
`projects/sem_paper/method/self_evolving_memory` has the following verified
surface:

- append-only `J_mem` evidence API and pinned read snapshots;
- read-only lexical/recency serving;
- Core/Standard/Deluxe authority equality (no tier may gain scientific write,
  acceptance, verifier or audit-materialization authority);
- explicit evolution stages: eligibility, diagnosis, synthesis, compilation,
  evaluation, acceptance and adoption;
- generation-pinned clean materialization and atomic adoption;
- project-owned composition behind the generic Method ABI.

It does **not** currently expose the old Deluxe runtime tier, capability
registry, working-set selection, Memory Fault recovery, fine-grained budgets,
Deluxe evidence governance, identifiability diagnostics, leaf-only GC, or the
Deluxe candidate/basin evaluation path. `rg` over the current project contains
no implementation of `runtime_tier`, `CapabilityRegistry`, `WorkingSet`,
`MemoryFault`, or `FineGrainedBudgetPolicy`.

Therefore the next work is a migration, not a claim that Deluxe is already
implemented.

## Root cause found before live serving integration

The current `MemoryReadSnapshot` is a flat append-only evidence view:
`iter_node_documents()` exposes one document per evidence row, but it does not
provide a pinned architecture snapshot or a node-to-record partition. The old
`TieredMemoryQueryEngine` requires both: it ranks architecture capabilities and
then retrieves records from each selected architecture node.

Treating every evidence row as an architecture node would silently change the
method semantics and make the Deluxe result incomparable. The new Deluxe API
therefore defines an explicit `DeluxeReadSnapshot` / `DeluxeServingSource` seam
for a node-partitioned read model. D2 must first implement that adapter from
the authoritative project memory representation; it must not fake the mapping
on top of the flat Core view.

## Migration matrix

| Legacy capability | Legacy owner | Current status | New ownership/action |
|---|---|---|---|
| Grounded `J_mem` / private `J_audit` / `J_eval` separation | `memory_runtime`, `evidence` | Core exists; audit/eval stores exist in project | Retain project scientific ownership; add explicit Deluxe read contracts only |
| Evidence index/backfill | `evidence/index.py` | Missing as current project runtime | Project serving provider; index must be rebuildable from the pinned evidence cut |
| Neutral slicing, profiler, tuning-first and guards | `evolution/*` | Basic evolution stages exist; old diagnostics absent | Project evolution subpackages; no platform import and no new adoption authority |
| Capability virtualization and progressive disclosure | `memory_runtime/capabilities.py`, `capabilities.py` | Missing | Project Deluxe serving subsystem behind `SessionServingFactory` |
| Architecture-open working set | `memory_runtime/working_set.py` | Missing | Project Deluxe serving subsystem; generated from current architecture/read model |
| Memory Fault recovery | `memory_runtime/memory_fault.py` | Missing | Project Deluxe serving subsystem; one bounded recovery after a real hard-set miss |
| Fine-grained budget | `memory_runtime/budget.py` | Missing | Project Deluxe serving subsystem; observational budget facts also go through injected telemetry |
| Multi-resolution retrieval | `memory_runtime/resolution.py`, `tiered_query.py` | Current hybrid planner is only a simple lexical/recency planner | Port the legacy retrieval behavior against current `MemoryReadSnapshot` |
| Memory and architecture lineage | `memory_runtime/lineage.py` | Session mutation lineage exists; rich memory lineage missing | Project evidence/serving lineage, rebuilt from authoritative materialized state |
| Evidence reconstructibility governance | `memory_runtime/evidence_governance.py` | Missing | Project evidence governance; no lossy deletion of `J_mem` |
| Identifiability E0–E3 | `evolution/identifiability.py` | Missing | Project evaluation/diagnosis; never acceptance authority |
| Leaf-only architecture GC | `evolution/gc.py` | Missing | Project evolution candidate generation; adoption remains existing atomic authority |
| Deluxe candidate evaluator | `evolution/deluxe_candidate.py` | Existing evaluator port only | Project evaluation implementation using generic branch/comparability proof |
| Adaptive slow clock / probes / hypotheses | `evolution/slow_clock.py`, `probes.py`, `hypothesis.py` | Missing | Project evolution diagnostics; fixed Control Plane remains authoritative |
| Deluxe IR operations | `memory_ir/deluxe_compiler.py` | Core architecture contracts, serializer, validator and typed edit compiler migrated; advanced Deluxe operations still absent | Keep advanced operations disabled until typed materialization and evaluation ports are migrated; no opaque target may enter live Deluxe serving |
| Basin analysis and trajectory export | `analysis/basin.py`, `analysis/trajectory.py` | Missing | Experiment/evaluation project artifacts, not live memory authority |

## Non-negotiable boundaries during migration

1. `J_mem` remains the only materialization input. `J_audit` and `J_eval` may
   diagnose or evaluate but cannot enter method memory construction.
2. Deluxe may change serving providers and observation richness, but not
   scientific authority. `validate_tier_authority()` must remain true.
3. A capability card is a derived read surface, not a second memory store and
   not a new effect authority.
4. Working-set selection and budget allocation are serving policies, not
   correctness filters and not a substitute for the method's evidence model.
5. Memory Fault recovery is bounded and evidence-producing; it must not silently
   expand the query, drop records, or lower a quality requirement.
6. Candidate compilation, evaluation, acceptance and adoption remain separate
   ports. Only the existing adoption authority may publish an architecture
   generation.
7. Project logging, exception and metric policy is injected through platform
   ports. The project may create detailed internal records, but it cannot write
   platform ledgers directly from arbitrary leaf modules.
8. The MC environment remains an injected participant/environment provider. It
   must not know Deluxe retrieval, evolution, prompt or evidence semantics.

## Implementation order

The migration will proceed in four verified slices:

### Slice D1 — current-project Deluxe contracts and read model

Port the legacy data contracts for tier, capability card/lifecycle, query
budget, working set, Memory Fault and lineage so they consume the current
`MemoryReadSnapshot` and current architecture identity. Add contract tests and
an import/source-authority audit before changing the live serving path.

### Slice D2 — authoritative node projection, then Deluxe serving path

First implement the node-partitioned architecture/evidence read adapter behind
`DeluxeServingSource`. Then implement capability discovery → progressive
disclosure → working set → multi-resolution retrieval → bounded Memory Fault as
one injected `SessionServingFactory`. Core and existing Standard providers
remain explicit baselines; no implicit fallback is introduced.

The explicit `DeluxeMemoryServingService` is now implemented and tested over
`DeluxeServingSource`. It validates generation/architecture identity, rejects
records outside the pinned architecture, and preserves the old capability,
budget, working-set, resolution and one-fault-recovery flow. The migrated
`architecture` package now owns the v034 memory-IR contracts and validator, and
`NodePartitionedDeluxeSnapshot` provides the strict projection boundary. It is
intentionally not bound to the default session factory yet, because the
authoritative project materializer still emits the flat Core evidence state;
the explicit node projection must be added to that materializer before live
Deluxe serving is enabled.

### Slice D3 — Deluxe evolution/evaluation path

Port neutral probes, hypotheses, identifiability, slow clock, GC candidate
generation, rich candidate evaluation and trajectory/report artifacts. Reuse
the current evolution ports and branch comparability proof; do not copy the old
controller or adoption implementation.

### Slice D4 — project composition and execution ladder

Bind the Deluxe provider as an explicit Paper-1 treatment, then implement the
unmodified-baseline → local contract smoke → server MC smoke → small study →
full study ladder. Every stage must write platform-observable logs, failures,
metrics and artifacts before a higher stage is allowed.

## Current gate

D1 read-side contracts are now implemented under
`projects/sem_paper/method/self_evolving_memory/deluxe/api` and
`.../deluxe/runtime`. The current-project memory-IR contracts and strict
architecture-to-Deluxe projection are under
`projects/sem_paper/method/self_evolving_memory/architecture`. The focused
Deluxe suites have 14 passing tests, and the new packages have no imports from
the legacy tree. D2 is not yet a live Deluxe serving treatment: the default
serving path remains unchanged until the project materializer publishes an
explicit node-partitioned snapshot and proves pinned-snapshot, budget, fault
and lineage behavior end to end.

The migrated serializer/validator was also run against both legacy seed
contracts (`seed_c_v018` and `seed_x_v018`): both parse, validate, and produce
acyclic topological orders with four nodes. This is a migration check only;
the v034 files remain reference inputs and are not runtime authority.

The explicit Deluxe session composition is now reachable through the real SEM
session assembly. It requires a `DeluxeSnapshotFactory`, and an adopted typed
generation source rejects session-generation drift before serving. The current
adoption mutation still serializes the legacy flat `PreparedGeneration`; live
Deluxe adoption is therefore not yet claimed complete.

The current code is therefore Core/partial Standard plus a verified Deluxe
read-side foundation, not Deluxe-complete. No experiment, live Minecraft run,
or scientific result is claimed by this audit.

## Round 111 status: live pinned projection

The missing D2 session seam is now implemented. A real SEM session can compose
`build_live_typed_snapshot_factory`, which derives a node-partitioned Deluxe
read snapshot from the session's atomic `(generation, J_mem read view)` cut.
The read source is immutable for that cut and later evidence writes cannot
mutate an already-open Deluxe snapshot.

The typed materializer now rejects records without `source_refs`, and live
materialization rejects references not present in the pinned `J_mem` cut or
the same typed generation. This closes a grounding/traceability hole without
allowing `J_audit` or `J_eval` into method materialization.

D2 is now structurally wired and tested, but Deluxe is still not complete:
there is no project production architecture/builder configuration, no D3
identifiability and candidate-evaluation path, and no D4 baseline-to-server
execution ladder. No live or scientific claim is made.

The related Paper workload path also now retains bounded diagnostic sink errors
in its run result instead of silently dropping them. This is a handoff
mechanism only; it does not grant the workload or Deluxe serving layer any
platform logging or failure-storage authority.

## Round 113 status: Deluxe result provenance and grounding audit

The Deluxe serving result now carries the selected materialized record IDs and
their direct source references. A project-owned read-only
`audit_deluxe_grounding` operation traverses derived-record ancestry and
reports whether both the queried records and the complete pinned materialized
generation terminate in `J_mem` evidence. It explicitly counts `J_audit` leaks
and unknown references.

This is an evidence audit, not a verifier, acceptance gate, memory writer or
serving filter. It does not alter the retrieved context and it does not make
the existing flat/adopted generation appear Deluxe-ready. The focused Deluxe
read-contract suite now covers a valid transitive `J_mem` ancestry and a mixed
audit/unknown ancestry failure.

## Round 114 status: current-contract identifiability foundation

The first D3 diagnostic slice is now migrated under
`evolution/identifiability.py`. It ports the legacy E0-E3 comparison idea
against the current project-owned `architecture.MemoryArchitectureSpec` and a
minimal record protocol, with no import from `memory_ir`, `memory_runtime` or
the old v034 tree.

The engine produces content-addressed semantic, topology, behavior and
structural-provenance fingerprints. It distinguishes exact identity from
semantic/behavioral/provenance similarity and is explicitly read-only: it
does not choose edits, accept candidates, verify experiments, write `J_mem`,
or become an adoption gate. J_mem/J_audit admissibility remains owned by the
existing grounding audit.

Focused verification: two identifiability tests passed, and the broader MC,
Deluxe, architecture and dependency regression remains green. This is the D3
diagnostic foundation only; neutral probes, hypotheses, candidate evaluation,
basin/trajectory artifacts, and the baseline-to-server execution ladder are
still incomplete.

## Round 115 status: current-contract neutral diagnostic plane

The next D3 slice now rebuilds the legacy neutral observation plane in
`evolution/diagnostics.py` against the current project architecture. It
provides:

- typed query/task observations and node runtime counters;
- explicit retrieval-miss, unresolved-intent, conflict and retrieval-cost
  incidents;
- immutable telemetry snapshots and block deltas;
- ontology-free incident slices;
- a fixed, bounded structural probe vocabulary;
- evidence-linked structural hypotheses; and
- an adaptive observation slow clock driven only by neutral runtime density
  and explicit adoption observations.

The diagnostic plane is deliberately not a new authority. It has no
`J_mem` write, candidate acceptance, verifier, adoption, or experiment
comparison capability. Structural probes report facts only; sampled structural
facts carry both total and sampled counts. The current implementation imports
neither `memory_ir`, `memory_runtime`, `mc_runtime` nor `v034_work`.

Focused verification: three D3 diagnostic tests passed, Python compilation
passed, and the targeted legacy-import scan was clean. Candidate evaluation,
leaf-only GC, basin/trajectory artifacts, production architecture building and
the baseline-to-server execution ladder remain incomplete. No Minecraft
process, model call, server run or scientific result was performed.

## Round 116 status: paired candidate evaluation and MC world-branch composition

The candidate evaluation boundary now has a current-project implementation in
`evolution/evaluator.py`. `PairedBranchEvaluator` consumes an injected branch
runner, executes control and candidate separately, reuses the platform
`ComparabilityProof`, and exports the current SEM `EvaluationProof` with
control/candidate/delta metrics. It has no acceptance or adoption capability;
invalid comparability remains explicit evidence for the evolution pipeline.

The Paper composition layer now provides
`MinecraftPairedBranchRunner`. It requires an explicit source-world cut before
either branch can run, materializes both branches from that same cut, delegates
service/participant/method/workload binding to an injected executor, and always
attempts branch cleanup while preserving both workload and cleanup failures.
The runner does not own Java process supervision, MC bridge semantics, memory
writes, or candidate policy. The platform comparability proof also rejects
reused control/candidate branch identities.

Focused verification: 22 candidate/branch/platform tests passed and Python
compilation passed. The concrete executor that binds generic service runtime,
Mineflayer session, Planner, SEM method and workload is still pending; this
slice has not started Minecraft or executed any experiment.

## Round 117 status: generic MC session to Paper workload adapter

The Paper composition layer now includes
`MinecraftWorkloadEnvironmentAdapter`. It translates the generic
`EnvironmentSession` `Observation`/`ActionResult` contracts into the existing
Paper workload ABI, preserves the verified-action fact and refuses an
observation that omits or malforms its authoritative `state` mapping. It does
not infer an empty state, synthesize success, or own the environment session
lifecycle.

Focused verification: nine workload/branch/adapter tests passed, Python
compilation passed, and `git diff --check` passed. The concrete branch executor
that binds server service, MC session, SEM session, evidence ingestion, Planner
and task manifest is still pending; no live process or experiment was run.

## Round 118 status: branch task-manifest executor

The Paper composition layer now includes
`MinecraftWorkloadBranchExecutor`. An injected branch binding supplies the
generic environment-to-workload adapter, SEM `MethodSession`, evidence port,
per-task Planner, task manifest, diagnostic sink and explicit branch-write
facts. The executor runs the existing workload loop for every task, closes the
binding even after a task failure, and exports stable aggregate metrics
(`success_rate`, `utility_mean`, total steps/duration and memory-query count)
into the branch result.

It does not create an LLM client, start/stop a server, own a world cut, or
decide scientific acceptance. Missing/failed binding closure is surfaced as a
distinct error. This is the reusable local/smoke executor seam; the concrete
server-service, participant, SEM Deluxe and model factories remain to be
bound.

Focused verification: six workload-executor/adapter/branch tests passed and
Python compilation passed. No Minecraft process, model call or experiment was
run.

## Round 119 status: current-project architecture presets and typed builder seam

The missing production architecture configuration is now owned by the current
SEM namespace in `architecture/presets.py`. It exposes the two research factors
that were previously only available as v034 YAML reference contracts:
`SemPaperArchitecturePreset.C` and `.X`. Both are constructed from the current
`MemoryArchitectureSpec`, validated by the current validator, and retain their
declared DAG, typed schema, event-source relation and semantic transform
objective. The legacy files remain migration evidence; they are not imported
by the current runtime.

The typed materialization path now has an explicit
`ArchitectureDrivenTypedNodeBuilder`. It walks the current architecture in
topological order, routes only declared J_mem event types or upstream typed
records, and delegates every node transform to an injected
`TypedSemanticNodeTransformPort`. It has no empty/flat fallback and rejects a
transform result assigned to the wrong node. A current-project configuration
factory now composes the selected preset, exact materialization contracts and
this builder, and `build_sem_paper_live_deluxe_snapshot_factory` exposes the
real pinned live Deluxe read seam.

During verification, the Deluxe projection exposed a semantic bug: repeated
schema field types were being advertised as duplicate capability output types.
The projection now preserves field schemas but publishes a stable first-seen
set of output kinds. This fixes valid architectures with repeated `TEXT`
fields without changing their memory payloads.

Focused verification: 19 architecture/materialization/projection tests passed,
30 current Deluxe/MC/evolution tests passed, full package compilation passed,
`git diff --check` passed, and the current SEM package has no imports from
`memory_ir`, `memory_runtime`, `mc_runtime` or `v034_work`.

This round still does not provide a concrete model-backed semantic transformer,
server/participant binding, or live Deluxe/MC execution. No Minecraft process,
model call, server run, benchmark or scientific result was performed.

## Round 120 status: host OS route, target paths and durability ownership

The platform now has a real `runtime/host` OS route and a real `scope/path`
target-path contract. The route publishes host identity and host conventions;
the path contract accepts either POSIX or Windows paths when a control-plane
record targets a different host. Business contracts no longer duplicate
`Path.is_absolute()` or POSIX-only `startswith('/')` validation.

Local service composition selects the exact Linux process provider only on a
Linux host and fails explicitly elsewhere. It cannot silently run Linux
`/proc` identity code on Windows. The Minecraft JSONL bridge receives the same
OS route for process-group creation semantics.

Windows durability audit found and fixed two byte-level defects: capture and
raw-observation append descriptors now use binary mode, preventing `0x0A` from
being expanded to CRLF; request/prompt/forensics locks share the platform lock
authority, with Windows named Mutex ownership that remains safe if a marker
file is cleaned while the owner is live. Failed telemetry commits release the
writer handle while retaining the pending batch for a later retry.

Verification: architecture source/seam gates passed (48 tests), the focused
OS/path/forensics/prompt/durability slice passed (74 tests), and the focused
capture/telemetry/path slice passed after the binary fixes. Full Windows
regression is not declared clean because several existing tests directly
exercise Linux `/proc`/`killpg`, require Windows symlink privilege, or leave
test-owned SQLite connections open; none of these are used as evidence of a
successful server or Minecraft experiment. No live server, model, or
scientific experiment was run.

## Round 121 status: recursive governance gate composition

The platform now registers `governance/gate` as a real subsystem. Its API is a
small recursive `GatePort` contract with immutable request, finding and report
values. `CompositeGate` receives explicit child gates, aggregates their
reports without losing provenance and turns child execution exceptions into
fail-closed findings without persisting exception secrets. The architecture
analyzer is currently the first child composed by the governance root; project
and subsystem-specific quality gates can be injected by their own composition
roots.

This is a structural governance slice, not a new scientific constraint or a
second rule engine. The existing architecture analyzer remains the source of
architecture findings, and the CLI now consumes it through the gate contract.
Architecture gate, catalog mirror, server identity, host/path routing and gate
tests passed; no server, model or Minecraft experiment was run.

## Round 122 status: explicit Deluxe treatment binding for Paper-1

The Paper-1 composition root now accepts one explicit
`DeluxeSnapshotFactory` and forwards it to both the fixed and self-evolving
method treatments. The production entrypoint selects
`build_deluxe_session_serving` and binds the fixed Seed-C typed snapshot
factory, so the control branch no longer silently uses the Core/Hybrid
serving provider while the candidate branch uses Deluxe.

This is a composition correction, not a scientific result. It preserves the
existing narrow method ports and keeps typed materialization rooted in the
pinned `J_mem` cut. It does not implement Meta synthesis, live structural
evolution, qualified model deployment, or live Minecraft execution. The
server-only regression must verify the new forwarding seam before any live
run is attempted.

## Round 130 status: Deluxe runtime/evaluation migration slice

The current SEM namespace now owns the first remaining Deluxe backlog
surfaces rather than importing the v034 tree:

- rebuildable `J_mem`-only evidence indexing;
- lossless HOT/WARM/COLD evidence retention governance;
- memory ancestor/depth/reconstructibility and architecture-generation
  lineage;
- leaf-only architecture-GC candidate generation through the normal
  `RETIRE_NODE` proposal boundary;
- fixed long-window candidate stability/adoption diagnostics;
- read-only trajectory and broad-seed basin analysis;
- conditional, disabled-by-default `REWIRE_SOURCE` and contract-preserving
  `SUBSTITUTE_NODE` compilation;
- per-task workload metrics and a derived Deluxe runtime report.

These are migration and observability surfaces, not additional scientific
authority. The default Meta grammar, verifier, candidate gate and forward
adoption authority are unchanged. The exact server revision must still pass
compile/regression, install the pinned Mineflayer dependencies, pass the live
T2B gate, and then bind a qualified real SelfEvolve pipeline before Deluxe
scientific execution can be claimed.
