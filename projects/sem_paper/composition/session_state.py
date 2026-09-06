from __future__ import annotations

"""Composition of the SEM session-state authority and durable storage port."""

import hashlib
from pathlib import Path

from projects.sem_paper.method.self_evolving_memory.evidence_memory import InMemoryEvidenceStore
from projects.sem_paper.method.self_evolving_memory.session_cell import SEMSessionStateCell
from projects.sem_paper.method.self_evolving_memory.session_lineage import SessionLineageJournal
from projects.sem_paper.method.self_evolving_memory.session_live_state import SessionLiveState
from projects.sem_paper.method.self_evolving_memory.session_state_api import (
    SEMSessionSnapshotStoreFactoryPort,
    SEMSessionStateFactory,
    SEMSessionStatePort,
)

from .session_state_storage import DurableSEMSessionStateError, FileSEMSessionStateStore


class DurableSEMSessionStateFactory(SEMSessionStateFactory):
    BACKEND_ID = "sem.session_state.file.v2"

    def __init__(
        self,
        root: Path,
        *,
        lineage_limit: int = 64,
        wal_max_bytes: int = 4 * 1024 * 1024,
        store_factory: SEMSessionSnapshotStoreFactoryPort | None = None,
    ) -> None:
        if lineage_limit <= 0:
            raise ValueError("SEM durable lineage limit must be positive")
        self.root = root
        self.lineage_limit = lineage_limit
        self.wal_max_bytes = wal_max_bytes
        self.store_factory = store_factory or (
            lambda path: FileSEMSessionStateStore(path, wal_max_bytes=wal_max_bytes)
        )

    @property
    def backend_id(self) -> str:
        return self.BACKEND_ID

    def _path(self, session_id: str) -> Path:
        if not session_id.strip():
            raise ValueError("SEM durable session id is required")
        return self.root / f"{hashlib.sha256(session_id.encode('utf-8')).hexdigest()}.json"

    def create(self, session_id: str) -> SEMSessionStatePort:
        store = self.store_factory(self._path(session_id))
        if store.exists():
            snapshot = store.read()
            cell = SEMSessionStateCell.from_snapshot(
                session_id,
                snapshot,
                limit=self.lineage_limit,
                evidence=InMemoryEvidenceStore.from_snapshot(snapshot.evidence),
                on_mutation=store.write,
            )
        else:
            cell = SEMSessionStateCell(
                session_id,
                SessionLiveState.initial(session_id, InMemoryEvidenceStore()),
                SessionLineageJournal(limit=self.lineage_limit),
                on_mutation=store.write,
            )
            store.write(cell.snapshot_state())
        return cell


__all__ = ["DurableSEMSessionStateError", "DurableSEMSessionStateFactory", "FileSEMSessionStateStore"]
