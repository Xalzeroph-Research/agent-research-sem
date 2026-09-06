"""Self-Evolving Memory (SEM) downstream research project.

The project owns method semantics, treatments, workloads, and scientific
interpretation. Noetrium owns lifecycle, identity, and evidence contracts.
"""
from .api import PROJECT_MANIFEST, PROJECT_ID, PROJECT_VERSION
from .experiments.protocol import (
    build_sem_paper_confirmatory_protocol,
    compile_sem_paper_experiment_plan,
)
from .method.self_evolving_memory import SEMMethodSession

__all__ = [
    "PROJECT_ID", "PROJECT_VERSION", "PROJECT_MANIFEST",
    "SEMMethodSession", "build_sem_paper_confirmatory_protocol",
    "compile_sem_paper_experiment_plan",
]