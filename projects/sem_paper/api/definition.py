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
PROJECT_VERSION = "3.0.0"

SEM_METHOD_IDENTITIES = {
    treatment: MethodProjectDefinition(
        role="memory",
        identity=MethodIdentity("self_evolving_memory", "3.0.0", "1", "1"),
        configuration_digest=canonical_digest(
            {
                "treatment": treatment,
                "architecture": "semantic-memory-graph.v1",
                "activation": "atomic-versioned",
            }
        ),
    )
    for treatment in ("no_memory", "flat_episodic", "fixed_typed", "sem")
}


def _interface(name: str) -> str:
    return canonical_digest({"contract": name, "version": "1"})


PROJECT_MANIFEST = ProjectManifest(
    project=ProjectSpec(
        identity=ProjectIdentity(PROJECT_ID, PROJECT_VERSION),
        program_id="agent-research",
        name="Self-Evolving Memory",
        description=(
            "Semantic memory architectures that evolve from structural demand "
            "and verified historical evidence."
        ),
        tags=("agent", "memory", "semantic-evolution"),
    ),
    template_revision="noetrium-downstream-v1",
    provenance=ProjectToolProvenance(
        "noetrium",
        "0.44.0",
        canonical_digest({"platform": "noetrium", "version": "0.44.0"}),
    ),
    capability_requirements=(
        ProjectCapabilityRequirement(
            "method-runtime", "participant", "method", 1,
            _interface("participant.method"),
        ),
        ProjectCapabilityRequirement(
            "environment-runtime", "environment", "session", 1,
            _interface("environment.session"),
        ),
        ProjectCapabilityRequirement(
            "study-runtime", "research", "study", 1,
            _interface("research.study"),
        ),
    ),
    method_requirements=tuple(
        ProjectMethodRequirement("self_evolving_memory", treatment)
        for treatment in ("no_memory", "flat_episodic", "fixed_typed", "sem")
    ),
    study_ids=("sem-method-conformance",),
)

__all__ = ["PROJECT_ID", "PROJECT_VERSION", "PROJECT_MANIFEST", "SEM_METHOD_IDENTITIES"]