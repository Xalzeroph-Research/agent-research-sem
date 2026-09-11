# Agent Research SEM

Self-Evolving Memory (SEM) is a downstream research method implemented on the
Noetrium platform. The latest method protocol is authoritative for the
scientific definition; this repository does not redefine it from a fixture.

## Ownership boundary

- Noetrium owns typed contracts, method/runtime boundaries, memory-graph
  validation and atomic activation, environment providers, qualified model
  providers, experiment plans, checkpoints, recovery, and evidence plumbing.
- SEM owns treatment semantics, evidence interpretation, architecture-independent
  monitoring, candidate proposals, historical backfill, and scientific audits.
- Minecraft action planning belongs to the agent/environment adapter. The SEM
  memory core never owns Minecraft action names or task-specific plans.
- Scripted runs are conformance smoke tests. They cannot establish Minecraft
  performance claims.

## Canonical treatments

| Treatment | Persistent memory | Topology evolution |
|---|---:|---:|
| no_memory | no | no |
| flat_episodic | yes | no |
| fixed_typed | yes, fixed Typed Memory DAG | no |
| sem | yes | proposal-blind CREATE/RETIRE/SPLIT/MERGE |

Runtime adoption has no online positive-utility gate. Utility, transfer,
recovery, cost, and negative transfer belong to the disjoint held-out audit
channel and never enter runtime memory materialization.

## Noetrium public interfaces used by SEM

SEM imports generic contracts through generated public facades:

- noetrium.contracts.systems.components: VersionedMemoryGraph,
  MemoryGraphSnapshot, typed nodes, edges, operations, and atomic graph state.
- noetrium.contracts.systems.participant__method: MethodSession,
  MethodEndpointPort, MethodSessionRuntime, MethodServices, snapshots,
  task outcomes, and recall contracts.
- noetrium.contracts.systems.participant__agent: AgentMemoryPort,
  AgentMemoryContext, AgentStepReceipt, and durable memory checkpoints.
- noetrium.contracts.systems.environment__minecraft: typed environment,
  observation, action, effect, and evidence boundaries.
- noetrium.contracts.systems.model__request and the Noetrium qualified
  project-model binding: immutable model identity, request context, prompt
  identity, request recording, and qualified closure verification.

The supported project-facing bindings are:

- noetrium.platform.bind_method_endpoint(implementation, runtime) binds
  SEM's method implementation to Noetrium's session runtime.
- noetrium.platform.bind_bundled_minecraft_environment(...) binds the
  typed Minecraft environment/provider.
- noetrium.platform.bind_qualified_project_model(...) binds a published,
  qualified model closure and records model requests.
- noetrium.platform.bind_directory_run_artifact_store(...) seals durable
  assignment artifacts; build_project_run_checkpoint_store(...) provides
  Noetrium checkpoint persistence.
- noetrium.platform.bind_universal_method_machine(...) hosts the method
  control loop, and bind_method_checkpoint_store(...) provides crash-durable
  method checkpoints.
- noetrium.platform.run_method_program(...) and run_method_program_async(...)
  execute the same MethodProgram ABI for sync and async downstream methods.

open_sem_method_session() uses the first binding and never imports
Noetrium's private semantic-plane implementation namespace.
SemMethodAgentMemoryAdapter is the only cognition-to-SEM memory seam.

The current SEM integration is validated against Noetrium main commit,
which contains the Universal Research Harness. Recorded commit:
`6e1d9021`. The assignment
runner uses the public facade only; it does not import `noetrium_platform`.

## Quick start

Use Python 3.11+ with the Noetrium checkout available on PYTHONPATH:

~~~bash
export PYTHONPATH=/path/to/agent-research-platform-system:/path/to/agent-research-sem
python -m projects.sem_paper.cli doctor
python -m projects.sem_paper.cli protocol
python -m projects.sem_paper.cli smoke
python -m projects.sem_paper.cli evobench --streams-per-track 2
python -m projects.sem_paper.cli analyze --results-dir results/real \
  --figure-dir results/real/figures
~~~

A real Minecraft pilot/matrix additionally requires a vanilla server, the
Noetrium Minecraft provider, a published qualified model closure, durable
model-request evidence, assignment world reset, verified action receipts, and
closed task evidence:

~~~bash
python -m projects.sem_paper.cli real-pilot \
  --model-qualified-closure /path/to/qualified-closure.json \
  --model-request-root results/model-requests
python -m projects.sem_paper.cli real --repetitions 3 \
  --model-qualified-closure /path/to/qualified-closure.json \
  --model-request-root results/model-requests
~~~

Without those conditions the result remains exploratory/smoke evidence and
must not be reported as the confirmatory SEM claim.

See docs/SEM_PROTOCOL.md, docs/SEM_IMPLEMENTATION_ALIGNMENT.md,
docs/NOETRIUM_SEM_INTEGRATION_MATRIX.md, and docs/SEM_EVO_BENCHMARK.md.
