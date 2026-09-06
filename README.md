# Agent Research SEM

Self-Evolving Memory (SEM) is a downstream research project implemented on
the Noetrium platform.

The repository boundary is deliberate:

- Noetrium owns stable lifecycle, identity, environment, participant, study,
  run-control, and evidence contracts.
- SEM owns the memory method, treatment semantics, Minecraft task workload,
  candidate evolution policy, metrics, and claim eligibility.
- The local scripted Minecraft adapter is a deterministic conformance fixture.
  Its output is smoke evidence and is not a scientific claim.

## Quick start

Use Python 3.11 or newer from the repository root, with Noetrium 0.44.x
installed. For a local workspace checkout:

    set PYTHONPATH=E:\Agent-Research-Workspace\projects\active\agent-research-platform-system
    E:\Agent-Research-Workspace\shared\runtimes\python-3.12.10\python.exe -m projects.sem_paper.cli doctor
    E:\Agent-Research-Workspace\shared\runtimes\python-3.12.10\python.exe -m projects.sem_paper.cli protocol
    E:\Agent-Research-Workspace\shared\runtimes\python-3.12.10\python.exe -m projects.sem_paper.cli smoke

The confirmatory design is frozen as six arms (Fixed, Rule, Self × Seed-C,
Seed-X), 12 repetitions, and seven typed metrics. A real Minecraft provider
can replace the scripted adapter at the compiled Noetrium plan boundary without
changing the SEM method or study protocol.

No benchmark, replay, synthetic, tool, or multi-agent subsystem is treated as
an environment implementation. Those are separate research/platform concepts.
