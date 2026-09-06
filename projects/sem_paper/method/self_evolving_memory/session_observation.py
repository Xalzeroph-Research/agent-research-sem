from __future__ import annotations

from research_platform.platform.kernel import ExecutionContext
from research_platform.participant.method.api import (
    MethodObservation,
    MethodObservationOutboxFactoryPort,
    MethodObservationOutboxPort,
    MethodObservationSink,
)

from .session_snapshot_contracts import SessionMutationRecord


class SessionMutationObservationPublisher:
    """Observability authority for committed SEM session mutations only."""

    METHOD_ID = "self_evolving_memory"

    def __init__(
        self,
        session_id: str,
        sink: MethodObservationSink,
        outbox_factory: MethodObservationOutboxFactoryPort,
    ) -> None:
        self.session_id = session_id
        self._outbox: MethodObservationOutboxPort = outbox_factory.create(sink)

    @staticmethod
    def _payload(record: SessionMutationRecord) -> dict[str, object]:
        return {
            "revision": record.revision,
            "mutation_type": record.mutation_type,
            "before_state_digest": record.before_state_digest,
            "after_state_digest": record.after_state_digest,
            "before_evidence_digest": record.before_evidence_digest,
            "after_evidence_digest": record.after_evidence_digest,
            "evidence_sequence": record.evidence_sequence,
            "architecture_generation": record.architecture_generation,
            "source_revision": record.source_revision,
        }

    def emit(self, record: SessionMutationRecord, context: ExecutionContext | None) -> None:
        if context is None:
            return
        observation = MethodObservation.build(
            context,
            self.METHOD_ID,
            self.session_id,
            "session_mutation",
            self._payload(record),
        )
        self._outbox.deliver(observation)

    def flush(self) -> tuple[str, ...]:
        return self._outbox.flush()

    def snapshot(self) -> tuple[MethodObservation, ...]:
        return self._outbox.snapshot()

    def restore(self, observations: tuple[MethodObservation, ...]) -> None:
        self._outbox.restore(observations)

    def pending_count(self) -> int:
        return self._outbox.pending_count()


__all__ = ["SessionMutationObservationPublisher"]
