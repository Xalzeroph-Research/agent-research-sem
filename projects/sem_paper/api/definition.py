from __future__ import annotations

from noetrium.contracts import (
    ProjectCapabilityRequirement,
    ProjectIdentity,
    ProjectManifest,
    ProjectMethodRequirement,
    ProjectSpec,
    ProjectToolProvenance,
    MethodIdentity,
    MethodProjectDefinition,
    canonical_digest,
)

PROJECT_ID = "sem-paper"
PROJECT_VERSION = "2.0.0"

SEM_METHOD_IDENTITIES = {
    "fixed_memory": MethodProjectDefinition(
        role="memory",
        identity=MethodIdentity("self_evolving_memory", "2.0.0", "1", "1"),
        configuration_digest=canonical_digest({"treatment": "fixed_memory"}),
    ),
    "self_evolving": MethodProjectDefinition(
        role="memory",
        identity=MethodIdentity("self_evolving_memory", "2.0.0", "1", "1"),
        configuration_digest=canonical_digest({"treatment": "self_evolving"}),
    ),
}

def _interface(name: str) -> str:
    return canonical_digest({"contract": name, "version": "1"})

PROJECT_MANIFEST = ProjectManifest(
    project=ProjectSpec(
        identity=ProjectIdentity(PROJECT_ID, PROJECT_VERSION),
        program_id="agent-research",
        name="Self-Evolving Memory",
        description="A method study of memory evolution under bounded agent tasks.",
        tags=("agent", "memory", "sem"),
    ),
    template_revision="noetrium-downstream-v1",
    provenance=ProjectToolProvenance(
        "noetrium", "0.44.0", canonical_digest({"platform": "noetrium", "version": "0.44.0"})
    ),
    capability_requirements=(
        ProjectCapabilityRequirement("method-runtime", "participant", "method", 1, _interface("participant.method")),
        ProjectCapabilityRequirement("environment-runtime", "environment", "session", 1, _interface("environment.session")),
        ProjectCapabilityRequirement("study-runtime", "research", "study", 1, _interface("research.study")),
    ),
    method_requirements=(
        ProjectMethodRequirement("self_evolving_memory", "fixed_memory"),
        ProjectMethodRequirement("self_evolving_memory", "self_evolving"),
    ),
    study_ids=("sem-core6", "sem-conformance"),
)

__all__ = ["PROJECT_ID", "PROJECT_VERSION", "PROJECT_MANIFEST", "SEM_METHOD_IDENTITIES"]