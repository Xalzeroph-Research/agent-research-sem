from __future__ import annotations

from research_platform.observability.logging.record.api import LoggingSystemPort

from projects.sem_paper.policies.logging import SemPaperLoggingSystem


def bind_project_logging(downstream: LoggingSystemPort) -> LoggingSystemPort:
    """Apply Paper-1 logging policy to an injected Logging System interface."""

    return SemPaperLoggingSystem(downstream)


__all__ = ["bind_project_logging"]
