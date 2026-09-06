from __future__ import annotations

import hashlib
import json

from research_platform.participant.method.api import MethodRuntimeBinding, MethodSnapshot

from research_platform.platform.kernel import canonical_bytes
from .session_snapshot_contracts import (
    IMPLEMENTATION_VERSION,
    SCHEMA_VERSION,
    SEMSessionStateSnapshot,
    SEMSnapshotPayload,
    SessionLineageSnapshot,
    SessionMutationRecord,
)
from .session_snapshot_document import payload_from_document, snapshot_document
from .session_snapshot_validation import validate_snapshot_payload


class SEMSnapshotCodec:
    """MethodSnapshot envelope only; document mapping and invariants are separate authorities."""

    def __init__(self, method_binding: MethodRuntimeBinding) -> None:
        method_identity = method_binding.implementation
        if method_identity.method_id != "self_evolving_memory":
            raise ValueError("SEM snapshot codec requires self_evolving_memory identity")
        if method_identity.implementation_version != IMPLEMENTATION_VERSION:
            raise ValueError("SEM snapshot codec implementation version mismatch")
        if method_identity.schema_version != SCHEMA_VERSION:
            raise ValueError("SEM snapshot codec schema version mismatch")
        self._method_identity = method_identity
        self._runtime_binding_digest = method_binding.digest()

    @staticmethod
    def _encode(payload: SEMSnapshotPayload) -> bytes:
        return canonical_bytes(snapshot_document(payload))

    def dump(self, session_id: str, payload: SEMSnapshotPayload) -> MethodSnapshot:
        validate_snapshot_payload(payload)
        encoded = self._encode(payload)
        return MethodSnapshot(
            self._method_identity.method_id,
            self._method_identity.implementation_version,
            self._method_identity.schema_version,
            self._runtime_binding_digest,
            session_id,
            hashlib.sha256(encoded).hexdigest(),
            encoded,
        )

    def _verify_envelope(self, snapshot: MethodSnapshot, session_id: str) -> None:
        if (
            snapshot.method_id != self._method_identity.method_id
            or snapshot.implementation_version != self._method_identity.implementation_version
            or snapshot.schema_version != self._method_identity.schema_version
            or snapshot.method_runtime_binding_digest != self._runtime_binding_digest
        ):
            raise ValueError("SEM snapshot identity/schema mismatch; only the current schema is accepted")
        if snapshot.session_id != session_id:
            raise ValueError("SEM snapshot belongs to a different session")
        if hashlib.sha256(snapshot.opaque_payload).hexdigest() != snapshot.payload_sha256:
            raise ValueError("SEM snapshot payload hash mismatch")

    def load(self, snapshot: MethodSnapshot, *, session_id: str) -> SEMSnapshotPayload:
        self._verify_envelope(snapshot, session_id)
        payload = payload_from_document(json.loads(snapshot.opaque_payload.decode("utf-8")))
        validate_snapshot_payload(payload)
        return payload


__all__ = [
    "IMPLEMENTATION_VERSION",
    "SCHEMA_VERSION",
    "SEMSnapshotCodec",
    "SEMSessionStateSnapshot",
    "SEMSnapshotPayload",
    "SessionLineageSnapshot",
    "SessionMutationRecord",
]
