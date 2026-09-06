from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Iterator

from research_platform.platform.kernel.errors import describe_exception


class SEMSessionRestoreFaulted(RuntimeError):
    """Raised when a partially failed restore makes the live session unusable."""


@dataclass(frozen=True, slots=True)
class SEMSessionRestoreFault:
    error_type: str
    error_digest: str


class SEMSessionOperationGate:
    """Serialize Method-ABI operations and fail closed after restore uncertainty.

    Lock ordering is intentionally outermost: session gate -> session-state cell
    -> provider/outbox internals. Method-owned code never acquires this gate from
    inside the cell/provider layers, so there is no reverse lock edge.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._restore_fault: SEMSessionRestoreFault | None = None

    @contextmanager
    def operation(self, *, allow_restore_fault: bool = False) -> Iterator[None]:
        with self._lock:
            if not allow_restore_fault:
                self.assert_healthy()
            yield

    def assert_healthy(self) -> None:
        fault = self._restore_fault
        if fault is not None:
            raise SEMSessionRestoreFaulted(
                "SEM session restore state is uncertain; close and reopen the session "
                f"before continuing ({fault.error_type}[{fault.error_digest[:16]}])"
            )

    def mark_restore_failure(self, exc: BaseException) -> SEMSessionRestoreFault:
        descriptor = describe_exception(exc)
        fault = SEMSessionRestoreFault(descriptor.error_type, descriptor.error_digest)
        self._restore_fault = fault
        return fault

    @property
    def restore_fault(self) -> SEMSessionRestoreFault | None:
        return self._restore_fault


__all__ = [
    "SEMSessionOperationGate",
    "SEMSessionRestoreFault",
    "SEMSessionRestoreFaulted",
]
