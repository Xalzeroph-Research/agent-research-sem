# Noetrium capability and SEM integration matrix

Date: 2026-09-07

This document records the capability review performed against the Noetrium
public downstream catalog and the SEM canonical branch. The catalog currently
contains 166 registered system surfaces. Registration is not the same as
scientific adoption: SEM must use a public contract where Noetrium owns the
generic lifecycle, and must keep scientific memory semantics downstream.

## Boundary rule

Noetrium owns generic contracts, provider composition, lifecycle, identity,
durable state, effect certainty, checkpoint and recovery, runtime supervision,
and evidence transport. SEM owns the scientific meaning of memory evidence,
architecture-independent demand, semantic topology, Transform/Meta proposals,
candidate validation policy, historical backfill, and forward-only adoption.

SEM must never import private noetrium_platform implementation modules for a
capability that has a public noetrium.contracts facade. If a needed public
contract is absent, the issue is upstream and must be fixed in Noetrium first.

## Capability status

| Noetrium capability | Public surface | Current SEM state | Next change |
| --- | --- | --- | --- |
| Method identity/session/recall/outcome | participant/method | Used by SEMMethodSession | Keep the method ABI; bind runtime services explicitly |
| Agent cognition memory seam | participant/agent / AgentMemoryPort | Adapter existed but lacked checkpoint/restore and was not wired into environment calls | Use SemMethodAgentMemoryAdapter for all memory treatments except no_memory |
| Typed memory graph substrate | components / noetrium.contracts.systems.components | Used through the public facade | Populate typed node metadata; keep semantic policy in SEM |
| Typed node metadata | MemoryNodeRecord fields purpose/scope/mode/schema/access/sources/transform/maintenance_contract/provenance | Upstream public contract now available in af9ec480 | SEM constructors and edit materialization must preserve every field |
| Environment and Minecraft | environment/*, especially environment/minecraft | Generic action/observation types are used; real bridge still owns a local subprocess adapter | Move lifecycle, world cut/branch, readiness, and effect receipts behind the Noetrium environment seams |
| Study/variant/run planning | experimentation/study, run, variant | Frozen ExperimentPlan and study execution port are used | Add Noetrium run-control identity and durable lifecycle around each assignment |
| Checkpoint/branch/evaluation | experimentation/checkpoint, branch, evaluation | SEM has a method-local snapshot; environment checkpoint is only invoked locally | Compose method, environment, and run checkpoints through Noetrium authorities |
| External effect and recovery | reliability/effect, recovery, forensics | SEM has evidence and bridge recovery logic, but not the generic effect/recovery ports | Route action receipts and uncertain effects through Noetrium; keep SEM evidence interpretation downstream |
| Persistent server/session runtime | runtime/session, runtime/server/* | Not called by SEM core or runner | Inject the runtime composition; SEM must not call tmux directly |
| Process/toolchain/Python execution | runtime/process, runtime/toolchain, runtime/python | Real environment uses direct subprocess and host paths | Replace direct lifecycle ownership with Noetrium process/runtime bindings |
| Model request/serving/deployment | model/request, model/serving, model/deployment | Planner uses a direct HTTP request path | Adapt planner to the typed model request/serving boundary |
| Observability and telemetry | observability/* | SEM exposes diagnostics and raw assignment JSON | Publish lifecycle/diagnostic facts through Noetrium observation ports |
| Artifact/data/lineage | artifact/*, data/* | Evidence is method-local and JSON-backed | Use artifact/lineage for durable evidence bundles and held-out audit references |
| Governance/gates | governance/gate, governance/quality, governance/evolution | SEM owns proposal-blind scientific gate | Keep scientific gate downstream; use generic platform gates for composition and release checks |

## tmux and persistence

Noetrium provides a persistent-session runtime with a generic
PersistentSessionRuntimePort and a verified tmux implementation. The tmux
session keeps the outer runtime controller alive across SSH disconnects; it is
not proof that a model, environment, or study is healthy. RuntimeManager,
service/process identity, readiness, effect journals, and checkpoint/recovery
remain separate authorities.

Therefore:

- SEM does not import tmux classes or invoke tmux commands;
- the server/runtime composition may inject a persistent session around the
  frozen SEM run manifest;
- SEM receives only typed runtime, checkpoint, observation, and outcome facts;
- a tmux session cannot be used as a scientific success or task-completion
  signal.

## Ordered SEM migration

1. Completed: public graph facade and typed node metadata.
2. In progress: AgentMemoryPort adapter wiring and semantic metadata preservation.
3. Next: Noetrium run/checkpoint composition for method + environment + assignment.
4. Next: typed Minecraft environment/effect/recovery integration.
5. Next: typed model request/serving integration.
6. Next: persistent server runtime injection through the frozen run manifest.
7. Final: artifact/evidence lineage, observability publication, and matched
   scientific matrix validation.

The scripted fixture and EvoBench remain method conformance tests. They do not
establish real Minecraft scientific claims.
