from __future__ import annotations

"""Durable storage authority for one SEM session-state aggregate.

The session cell owns scientific mutation semantics.  This module owns only
the durable publication protocol: an append-first WAL, a checksummed primary
snapshot, a previous-good backup, revision/CAS identity, and recovery from the
latest valid durable candidate.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

from research_platform.platform.kernel import JsonObject, JsonValue, canonical_bytes
from research_platform.platform.kernel.durability.durable_file import atomic_replace_bytes
from research_platform.platform.kernel.durability.file_lock import (
    InterprocessFileLock,
    InterprocessLockBusy,
    InterprocessLockUnavailable,
)

from projects.sem_paper.method.self_evolving_memory.evidence_api import EvidenceRecord, EvidenceSnapshot
from projects.sem_paper.method.self_evolving_memory.evidence_memory import InMemoryEvidenceStore
from projects.sem_paper.method.self_evolving_memory.session_snapshot_contracts import (
    SEMSessionStateSnapshot,
    SessionLineageSnapshot,
    SessionMutationRecord,
)
from projects.sem_paper.method.self_evolving_memory.session_reducer import SEMSessionState


STATE_SCHEMA = "sem-session-state-durable.v2"
ENVELOPE_SCHEMA = "sem-session-state-envelope.v2"
DEFAULT_WAL_MAX_BYTES = 4 * 1024 * 1024


class DurableSEMSessionStateError(RuntimeError):
    """The durable state could not be safely read, recovered, or committed."""


def _document(snapshot: SEMSessionStateSnapshot) -> JsonObject:
    return {
        "schema": STATE_SCHEMA,
        "state": {
            "architecture_generation": snapshot.state.architecture_generation,
            "evidence_sequence": snapshot.state.evidence_sequence,
            "evolution_epoch": snapshot.state.evolution_epoch,
            "tasks_completed": snapshot.state.tasks_completed,
            "last_grounded_payload": snapshot.state.last_grounded_payload,
        },
        "evidence": {
            "sequence": snapshot.evidence.sequence,
            "digest": snapshot.evidence.digest,
            "rows": [
                {
                    "evidence_id": row.evidence_id,
                    "sequence": row.sequence,
                    "payload": row.payload,
                    "digest": row.digest,
                }
                for row in snapshot.evidence.rows
            ],
        },
        "lineage": {
            "revision": snapshot.lineage.revision,
            "mutation_tail": [
                {
                    "revision": row.revision,
                    "mutation_type": row.mutation_type,
                    "before_state_digest": row.before_state_digest,
                    "after_state_digest": row.after_state_digest,
                    "before_evidence_digest": row.before_evidence_digest,
                    "after_evidence_digest": row.after_evidence_digest,
                    "before_closed": row.before_closed,
                    "after_closed": row.after_closed,
                    "evidence_sequence": row.evidence_sequence,
                    "architecture_generation": row.architecture_generation,
                    "source_revision": row.source_revision,
                    "run_id": row.run_id,
                    "task_id": row.task_id,
                    "decision_cycle_id": row.decision_cycle_id,
                    "operation_id": row.operation_id,
                    "trace_id": row.trace_id,
                    "span_id": row.span_id,
                }
                for row in snapshot.lineage.mutation_tail
            ],
        },
    }


def _strict_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DurableSEMSessionStateError(
            f"SEM durable {field} must be an integer >= {minimum}"
        )
    return value


def _strict_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise DurableSEMSessionStateError(f"SEM durable {field} must be a boolean")
    return value


def _strict_text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise DurableSEMSessionStateError(f"SEM durable {field} must be text")
    return value


def _strict_digest(value: object, field: str) -> str:
    digest = _strict_text(value, field)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise DurableSEMSessionStateError(
            f"SEM durable {field} must be a lowercase SHA-256 digest"
        )
    return digest


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DurableSEMSessionStateError(f"SEM durable {field} must be text or null")
    return value


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, field)


def _exact_mapping(value: object, fields: set[str], label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or set(value) != fields:
        raise DurableSEMSessionStateError(f"SEM durable {label} fields are not exact")
    return value


def _decode(document: JsonObject) -> SEMSessionStateSnapshot:
    root = _exact_mapping(document, {"schema", "state", "evidence", "lineage"}, "root")
    if root["schema"] != STATE_SCHEMA:
        raise DurableSEMSessionStateError("unsupported SEM durable state schema")
    state = _exact_mapping(
        root["state"],
        {
            "architecture_generation",
            "evidence_sequence",
            "evolution_epoch",
            "tasks_completed",
            "last_grounded_payload",
        },
        "state",
    )
    evidence = _exact_mapping(root["evidence"], {"sequence", "digest", "rows"}, "evidence")
    lineage = _exact_mapping(root["lineage"], {"revision", "mutation_tail"}, "lineage")
    rows = evidence["rows"]
    mutation_tail = lineage["mutation_tail"]
    if not isinstance(rows, list) or not isinstance(mutation_tail, list):
        raise DurableSEMSessionStateError("SEM durable state collections must be arrays")

    evidence_rows: list[EvidenceRecord] = []
    for index, raw_row in enumerate(rows, start=1):
        row = _exact_mapping(
            raw_row,
            {"evidence_id", "sequence", "payload", "digest"},
            f"evidence row {index}",
        )
        evidence_rows.append(
            EvidenceRecord(
                _strict_text(row["evidence_id"], f"evidence row {index} id"),
                _strict_int(row["sequence"], f"evidence row {index} sequence", minimum=1),
                row["payload"],
                _strict_digest(row["digest"], f"evidence row {index} digest"),
            )
        )
    snapshot_evidence = EvidenceSnapshot(
        _strict_int(evidence["sequence"], "evidence sequence"),
        tuple(evidence_rows),
        _strict_digest(evidence["digest"], "evidence digest"),
    )
    try:
        InMemoryEvidenceStore.from_snapshot(snapshot_evidence)
    except (TypeError, ValueError) as exc:
        raise DurableSEMSessionStateError("SEM durable evidence snapshot is invalid") from exc

    mutation_fields = {
        "revision",
        "mutation_type",
        "before_state_digest",
        "after_state_digest",
        "before_evidence_digest",
        "after_evidence_digest",
        "before_closed",
        "after_closed",
        "evidence_sequence",
        "architecture_generation",
        "source_revision",
        "run_id",
        "task_id",
        "decision_cycle_id",
        "operation_id",
        "trace_id",
        "span_id",
    }
    mutations: list[SessionMutationRecord] = []
    for index, raw_row in enumerate(mutation_tail, start=1):
        row = _exact_mapping(raw_row, mutation_fields, f"lineage row {index}")
        mutations.append(
            SessionMutationRecord(
                revision=_strict_int(row["revision"], f"lineage row {index} revision", minimum=1),
                mutation_type=_strict_text(row["mutation_type"], f"lineage row {index} mutation_type"),
                before_state_digest=_strict_digest(row["before_state_digest"], f"lineage row {index} before_state_digest"),
                after_state_digest=_strict_digest(row["after_state_digest"], f"lineage row {index} after_state_digest"),
                before_evidence_digest=_strict_digest(row["before_evidence_digest"], f"lineage row {index} before_evidence_digest"),
                after_evidence_digest=_strict_digest(row["after_evidence_digest"], f"lineage row {index} after_evidence_digest"),
                before_closed=_strict_bool(row["before_closed"], f"lineage row {index} before_closed"),
                after_closed=_strict_bool(row["after_closed"], f"lineage row {index} after_closed"),
                evidence_sequence=_strict_int(row["evidence_sequence"], f"lineage row {index} evidence_sequence"),
                architecture_generation=_strict_text(row["architecture_generation"], f"lineage row {index} architecture_generation"),
                source_revision=_optional_int(row["source_revision"], f"lineage row {index} source_revision"),
                run_id=_optional_text(row["run_id"], f"lineage row {index} run_id"),
                task_id=_optional_text(row["task_id"], f"lineage row {index} task_id"),
                decision_cycle_id=_optional_text(row["decision_cycle_id"], f"lineage row {index} decision_cycle_id"),
                operation_id=_optional_text(row["operation_id"], f"lineage row {index} operation_id"),
                trace_id=_optional_text(row["trace_id"], f"lineage row {index} trace_id"),
                span_id=_optional_text(row["span_id"], f"lineage row {index} span_id"),
            )
        )
    lineage_revision = _strict_int(lineage["revision"], "lineage revision")
    revisions = tuple(row.revision for row in mutations)
    if revisions != tuple(sorted(revisions)) or len(revisions) != len(set(revisions)):
        raise DurableSEMSessionStateError("SEM durable lineage revisions are not ordered")
    if revisions and revisions[-1] != lineage_revision:
        raise DurableSEMSessionStateError("SEM durable lineage tail does not end at its revision")
    if not revisions and lineage_revision != 0:
        raise DurableSEMSessionStateError("SEM durable empty lineage must have revision zero")
    snapshot_lineage = SessionLineageSnapshot(lineage_revision, tuple(mutations))

    snapshot = SEMSessionStateSnapshot(
        SEMSessionState(
            architecture_generation=_strict_text(state["architecture_generation"], "architecture generation"),
            evidence_sequence=_strict_int(state["evidence_sequence"], "state evidence sequence"),
            evolution_epoch=_strict_int(state["evolution_epoch"], "evolution epoch"),
            tasks_completed=_strict_int(state["tasks_completed"], "tasks completed"),
            last_grounded_payload=_strict_text(state["last_grounded_payload"], "last grounded payload", allow_empty=True),
        ),
        snapshot_evidence,
        snapshot_lineage,
    )
    if snapshot.state.evidence_sequence != snapshot.evidence.sequence:
        raise DurableSEMSessionStateError("SEM state/evidence sequence mismatch")
    return snapshot

def _envelope(snapshot: SEMSessionStateSnapshot, revision: int) -> tuple[JsonObject, bytes, str]:
    payload = canonical_bytes(_document(snapshot))
    sha256 = hashlib.sha256(payload).hexdigest()
    value: JsonObject = {
        "schema": ENVELOPE_SCHEMA,
        "revision": revision,
        "payload": json.loads(payload.decode("utf-8")),
        "sha256": sha256,
    }
    return value, canonical_bytes(value), sha256


def _decode_envelope(
    value: object,
    *,
    source: Path,
) -> tuple[int, str, SEMSessionStateSnapshot, JsonObject]:
    envelope = _exact_mapping(
        value,
        {"schema", "revision", "payload", "sha256"},
        f"envelope {source}",
    )
    if envelope["schema"] != ENVELOPE_SCHEMA:
        raise DurableSEMSessionStateError(f"invalid SEM durable envelope: {source}")
    revision = _strict_int(envelope["revision"], "envelope revision")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise DurableSEMSessionStateError(f"invalid SEM durable envelope payload: {source}")
    sha256 = _strict_digest(envelope["sha256"], "envelope sha256")
    raw_payload = canonical_bytes(payload)
    if hashlib.sha256(raw_payload).hexdigest() != sha256:
        raise DurableSEMSessionStateError(f"SEM durable envelope checksum mismatch: {source}")
    return revision, sha256, _decode(payload), envelope


class FileSEMSessionStateStore:
    """Single-session durable store with WAL, backup recovery, and CAS."""

    def __init__(self, path: Path, *, wal_max_bytes: int = DEFAULT_WAL_MAX_BYTES) -> None:
        if wal_max_bytes <= 0:
            raise ValueError("SEM durable WAL max_bytes must be positive")
        self.path = path
        self.wal_path = path.with_name(path.name + ".wal")
        self.backup_path = path.with_name(path.name + ".bak")
        self.lock_path = path.with_name(path.name + ".lock")
        self.wal_max_bytes = wal_max_bytes
        self._observed_sha256: str | None = None
        self._observed_revision: int | None = None

    @contextmanager
    def _lock_file(self) -> Iterator[None]:
        try:
            with InterprocessFileLock(self.lock_path, blocking=True):
                yield
        except (InterprocessLockBusy, InterprocessLockUnavailable) as exc:
            raise DurableSEMSessionStateError(
                "SEM durable state interprocess lock is unavailable"
            ) from exc

    def _read_json(self, path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DurableSEMSessionStateError(f"SEM durable JSON cannot be read: {path}") from exc

    def _read_wal(self) -> list[tuple[int, str, SEMSessionStateSnapshot, JsonObject]]:
        if not self.wal_path.is_file():
            return []
        candidates: list[tuple[int, str, SEMSessionStateSnapshot, JsonObject]] = []
        try:
            lines = self.wal_path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeError) as exc:
            raise DurableSEMSessionStateError("SEM durable WAL cannot be read") from exc
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if not line.endswith("\n"):
                continue
            try:
                candidates.append(_decode_envelope(json.loads(line), source=self.wal_path))
            except (json.JSONDecodeError, DurableSEMSessionStateError) as exc:
                raise DurableSEMSessionStateError(
                    f"SEM durable WAL corrupt complete record at line {index}"
                ) from exc
        return candidates

    def _candidates(self) -> list[tuple[int, str, SEMSessionStateSnapshot, JsonObject]]:
        candidates: list[tuple[int, str, SEMSessionStateSnapshot, JsonObject]] = []
        recoverable_errors: list[DurableSEMSessionStateError] = []
        for path in (self.path, self.backup_path):
            if path.is_file():
                try:
                    candidates.append(_decode_envelope(self._read_json(path), source=path))
                except DurableSEMSessionStateError as exc:
                    # A torn primary/backup is recoverable when another durable
                    # candidate exists. WAL corruption remains fail-closed in
                    # _read_wal because it is the commit journal.
                    recoverable_errors.append(exc)
        candidates.extend(self._read_wal())
        if not candidates and recoverable_errors:
            raise recoverable_errors[0]
        return candidates

    def _latest(self) -> tuple[int, str, SEMSessionStateSnapshot, JsonObject] | None:
        candidates = self._candidates()
        if not candidates:
            return None
        highest_revision = max(row[0] for row in candidates)
        highest = [row for row in candidates if row[0] == highest_revision]
        if len({row[1] for row in highest}) != 1:
            raise DurableSEMSessionStateError("SEM durable candidates disagree at one revision")
        return highest[-1]

    def exists(self) -> bool:
        with self._lock_file():
            return any(path.is_file() for path in (self.path, self.backup_path, self.wal_path))

    def write(self, snapshot: SEMSessionStateSnapshot) -> None:
        with self._lock_file():
            current = self._latest()
            if current is not None:
                if self._observed_sha256 is None or self._observed_revision is None:
                    raise DurableSEMSessionStateError(
                        "SEM durable state requires read-before-write for an existing session"
                    )
                if (
                    current[0] != self._observed_revision
                    or current[1] != self._observed_sha256
                ):
                    raise DurableSEMSessionStateError(
                        "SEM durable state concurrent update detected; restore and retry"
                    )
                revision = current[0] + 1
                atomic_replace_bytes(self.backup_path, canonical_bytes(current[3]))
            else:
                revision = 1
            value, encoded, sha256 = _envelope(snapshot, revision)
            if self.wal_path.is_file() and self.wal_path.stat().st_size + len(encoded) + 1 > self.wal_max_bytes:
                atomic_replace_bytes(self.wal_path, encoded + b"\n")
            else:
                with self.wal_path.open("ab") as handle:
                    handle.write(encoded + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            atomic_replace_bytes(self.path, encoded)
            self._observed_sha256 = sha256
            self._observed_revision = revision

    def read(self) -> SEMSessionStateSnapshot:
        with self._lock_file():
            current = self._latest()
            if current is None:
                raise DurableSEMSessionStateError("SEM durable state does not exist")
            self._observed_sha256 = current[1]
            self._observed_revision = current[0]
            return current[2]

    def repair_primary(self) -> SEMSessionStateSnapshot:
        """Restore the primary snapshot from the latest valid WAL/backup candidate."""

        with self._lock_file():
            current = self._latest()
            if current is None:
                raise DurableSEMSessionStateError("SEM durable state has no recoverable candidate")
            atomic_replace_bytes(self.path, canonical_bytes(current[3]))
            self._observed_sha256 = current[1]
            self._observed_revision = current[0]
            return current[2]


__all__ = ["DurableSEMSessionStateError", "FileSEMSessionStateStore"]
