from __future__ import annotations

import hashlib
import threading

from .materialization import PreparedStatus


class GenerationLifecycleConflict(RuntimeError):
    pass


class GenerationAllocator:
    """Thread-safe prepared-generation lifecycle index.

    The architecture head + evolution ledger are authoritative for committed generations.
    This object owns allocation/abandonment while a candidate is PREPARED and can be
    reconciled from authoritative state after process restart.
    """

    def __init__(self) -> None:
        self._status: dict[str, PreparedStatus] = {}
        self._lock = threading.RLock()

    def allocate(self, candidate_id: str) -> str:
        generation = f"gen_{hashlib.sha256(candidate_id.encode()).hexdigest()[:16]}"
        with self._lock:
            if generation in self._status:
                raise RuntimeError("candidate generation already allocated")
            self._status[generation] = PreparedStatus.PREPARED
        return generation

    def commit(self, generation: str) -> None:
        """Finalize a locally prepared generation after authoritative commit."""
        with self._lock:
            if self._status.get(generation) != PreparedStatus.PREPARED:
                raise RuntimeError("generation not prepared")
            self._status[generation] = PreparedStatus.COMMITTED

    def reconcile_committed(self, generation: str) -> None:
        """Idempotently rebuild committed lifecycle state from authoritative state."""
        with self._lock:
            current = self._status.get(generation)
            if current is PreparedStatus.ABANDONED:
                raise GenerationLifecycleConflict(
                    "authoritative state reports committed generation but allocator reports abandoned"
                )
            if current in (None, PreparedStatus.PREPARED, PreparedStatus.COMMITTED):
                self._status[generation] = PreparedStatus.COMMITTED
                return
            raise GenerationLifecycleConflict(f"unknown generation lifecycle state: {current}")

    def abandon(self, generation: str) -> None:
        with self._lock:
            if self._status.get(generation) == PreparedStatus.PREPARED:
                self._status[generation] = PreparedStatus.ABANDONED

    def status(self, generation: str) -> PreparedStatus:
        with self._lock:
            return self._status[generation]

    def snapshot(self) -> dict[str, PreparedStatus]:
        with self._lock:
            return dict(self._status)
