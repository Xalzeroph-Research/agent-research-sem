from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext


class SEMSessionContextTracker:
    """Owns only the latest execution context used for observation attribution."""

    def __init__(self) -> None:
        self._current: ExecutionContext | None = None

    @property
    def current(self) -> ExecutionContext | None:
        return self._current

    def update(self, context: ExecutionContext) -> None:
        self._current = context


__all__ = ["SEMSessionContextTracker"]
