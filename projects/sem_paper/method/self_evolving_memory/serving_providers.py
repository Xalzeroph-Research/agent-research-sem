from __future__ import annotations

from .retrieval_planner import HybridLexicalRecencyQueryPlanner, LatestEvidenceQueryPlanner
from .serving import MemoryServingService
from .deluxe.runtime.serving import DeluxeMemoryServingService
from .session_serving_api import DeluxeServingSessionSource, ServingSessionSource


def build_hybrid_session_serving(source: ServingSessionSource) -> MemoryServingService:
    return MemoryServingService(
        source,
        HybridLexicalRecencyQueryPlanner(max_nodes=8),
    )


def build_latest_evidence_session_serving(source: ServingSessionSource) -> MemoryServingService:
    return MemoryServingService(
        source,
        LatestEvidenceQueryPlanner(),
    )


def build_deluxe_session_serving(source: DeluxeServingSessionSource) -> DeluxeMemoryServingService:
    """Explicit Deluxe treatment; source must expose typed node partitions."""
    return DeluxeMemoryServingService(source)


__all__ = [
    "build_hybrid_session_serving",
    "build_latest_evidence_session_serving",
    "build_deluxe_session_serving",
]
