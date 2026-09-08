# SEM implementation alignment

Date: 2026-09-08

This document freezes the implementation boundary between the SEM method and
the Noetrium platform. The detailed capability review is in
docs/NOETRIUM_SEM_INTEGRATION_MATRIX.md. The latest method drafts define the scientific method;
the current branch code is an implementation of that definition and must not
redefine it.

## 1. Canonical ownership

Noetrium owns generic contracts, ports, immutable snapshots, graph validation,
atomic activation, runtime composition, environment providers, model
providers, experiment control, and evidence/audit infrastructure.

SEM owns evidence interpretation, architecture-independent demand detection,
typed semantic architecture, Transform IR, Meta-Architect proposals,
proposal-blind candidate validation, historical backfill policy, and
forward-only architecture evolution.

Minecraft action names, action whitelists, planner prompts, task manifests,
world reset commands, and Mineflayer execution remain in the agent and
environment adapter layers.

## 2. Treatment identity

The only canonical treatment identifiers are:

- no_memory: no persistent long-term memory ingest or recall;
- flat_episodic: persistent append and recall through one flat episodic view;
- fixed_typed: persistent ingest and recall through a fixed Typed Memory DAG,
  with no topology edits;
- sem: persistent ingest and recall with CREATE, RETIRE, SPLIT, and MERGE
  architecture evolution.

The old fixed_memory name is invalid because its implementation rejected
persistent ingest and therefore described no persistent memory, not fixed typed
memory.

MemoryEntry remains a valid representation for the flat_episodic baseline. It
is not the scientific SEM architecture. RuleBasedEvolver is a deterministic
control baseline and may share the same graph runtime, grammar, and validation
budget as SEM; it is not a replacement for Meta-Architect.

## 3. Runtime adoption and audit

Runtime adoption uses a proposal-blind gate. The gate checks:

- candidate base snapshot binding;
- bounded operation count;
- allowed edit vocabulary;
- evidence provenance;
- graph validity, types, acyclicity, and source compatibility;
- complexity and safety constraints;
- clean materialization and atomic activation.

A positive task utility delta is not an online hard requirement. Task success,
transfer, recovery, adaptation, cost, and negative transfer are measured by a
disjoint proposal-blind held-out audit. Audit evidence belongs to J_audit and
must never be materialized into J_mem.


## 3A. Evidence and monitor implementation

The current method plane now keeps J_mem and J_audit in a separate
EvidenceJournal. record_audit persists held-out audit evidence without
routing it into recall, node evidence, candidate backfill, or semantic
materialization.

ArchitectureIndependentMonitor records failure support, exposure, evidence
references, and recall hit statistics without emitting an edit operation or a
target node. Its state is included in the method checkpoint and restored
before forward execution resumes. These signals are diagnostic inputs to the
proposal boundary; they are not acceptance decisions and do not contain
held-out utility labels.

## 3B. Downstream scientific schema

SEM now exposes the method-owned canonical evidence fields, restricted
Transform IR, neutral architecture observations, proposal envelope, and
append-only evolution ledger. The candidate gate validates syntax, typed node
fields, transform vocabulary, graph/source preconditions, complexity, and
canonical no-op cases before delegating graph acyclicity and atomic activation
to Noetrium. Assignment artifacts also include episode, memory-query, and
evolution logs. Analysis is assignment-level and reports bootstrap and paired
permutation intervals; scripted and diagnostic outputs remain non-claim-ready.

## 4. Noetrium integration rule

SEM imports generic graph types through the generated public Noetrium
component facade:

noetrium.contracts.systems.components

The session boundary also uses the generated participant-method facade:
SEMMethodImplementation and SEMMethodSessionRuntime satisfy Noetrium's
MethodImplementation and MethodSessionRuntime contracts, and
open_sem_method_session binds them through Noetrium's MethodEndpointPort and
MethodServices. SemMethodAgentMemoryAdapter is the AgentMemoryPort boundary
presented to cognition. The runner must not instantiate a raw method session
around this endpoint.

SEM must not import components.reference implementation paths from its
method core. Concrete graph construction is a composition concern; semantic
policy remains downstream. Method endpoint binding and deployment-owned host
commands now enter through noetrium.platform; SEM does not import private
noetrium_platform runtime factories or call subprocess directly.

The public high-level Agent host is
`noetrium.platform.bind_agent_research_runtime`. It composes the existing
Noetrium cognition loop from SEM- or provider-owned observation, planner,
skill, action, memory, safety, completion, evidence, progress, and diagnostic
ports. Multimodal SEM variants may wrap the observation port with
`noetrium.platform.MultimodalAgentObservationPort`; the part source and model
codec remain provider-owned, so this seam supports arbitrary modality sets and
method schemas.

The runner uses noetrium.platform.bind_study_matrix_execution for study matrix
scheduling, and model planners use noetrium.platform.complete_project_model for
request recording and response provenance. These are upstream mechanics; SEM
retains task semantics, prompts, action vocabulary, and result interpretation.

If a required capability is absent from the public Noetrium contract, the
issue is upstream. Add or repair the Noetrium public API and regenerate the
downstream facade before changing SEM to use a private path. If the public
contract exists and SEM calls it incorrectly, the issue is downstream and
belongs in this repository.

## 5. Migration order

The migration is intentionally incremental:

1. public Noetrium memory graph contract;
2. Evidence Kernel and canonical evidence journal;
3. Typed Memory DAG and Transform IR;
4. architecture-independent Monitor;
5. Meta-Architect proposal boundary;
6. candidate compiler, clean materialization, and proposal-blind gate;
7. historical backfill;
8. forward-only atomic adoption and evolution ledger;
9. agent/environment adapter integration;
10. treatment-level and assignment-level validation.

The old SEM main branch is a read-only migration source. The canonical SEM development branch is main; the Noetrium canonical branch is
also main. Legacy role-assignment material and obsolete branches are retired.

## 6. Scientific claim boundary

Scripted fixtures and EvoBench validate method determinism, state transitions,
candidate isolation, and metric closure. They do not establish Minecraft
performance claims. Main claims require the frozen Minecraft protocol, real
model planner, fresh-world assignment reset, verified effect receipts, memory
evidence closure, and the complete matched repetition matrix.
