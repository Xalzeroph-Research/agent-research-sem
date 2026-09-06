from __future__ import annotations

from collections.abc import Mapping

from research_platform.governance.system_registry.api import SystemIdentity
from research_platform.observability.logging.context.api import DiagnosticAddress
from research_platform.observability.logging.record.api import LogLevel, LogRecord, LogWriterPort, LoggingSystemPort
from research_platform.scope.api import ScopeIdentity
from research_platform.platform.kernel import JsonValue


class SemPaperLogWriter(LogWriterPort):
    """Paper-1 writer policy expressed purely through the Logging System API.

    The project enriches every record with stable project/paper context but does not
    know where records are stored or which logging runtime produced them.
    """

    def __init__(self, downstream: LogWriterPort) -> None:
        self._downstream = downstream

    @property
    def address(self) -> DiagnosticAddress:
        return self._downstream.address

    def child(
        self,
        *,
        address: DiagnosticAddress | None = None,
        component_id: str | None = None,
    ) -> "SemPaperLogWriter":
        return SemPaperLogWriter(
            self._downstream.child(address=address, component_id=component_id)
        )

    def log(
        self,
        level: LogLevel,
        *,
        event: str,
        message: str,
        attributes: Mapping[str, JsonValue] | None = None,
        correlation_refs: tuple[str, ...] = (),
        failure_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
    ) -> str:
        return self._downstream.log(
            level,
            event=event,
            message=message,
            attributes=self._attributes(attributes),
            correlation_refs=correlation_refs,
            failure_refs=failure_refs,
            artifact_refs=artifact_refs,
        )

    def exception(
        self,
        *,
        event: str,
        message: str,
        exc: BaseException,
        level: LogLevel = LogLevel.ERROR,
        attributes: Mapping[str, JsonValue] | None = None,
        correlation_refs: tuple[str, ...] = (),
        failure_refs: tuple[str, ...] = (),
    ) -> str:
        return self._downstream.exception(
            event=event,
            message=message,
            exc=exc,
            level=level,
            attributes=self._attributes(attributes),
            correlation_refs=correlation_refs,
            failure_refs=failure_refs,
        )

    def failure(
        self,
        *,
        event: str,
        message: str,
        failure_id: str,
        level: LogLevel = LogLevel.ERROR,
        attributes: Mapping[str, JsonValue] | None = None,
        correlation_refs: tuple[str, ...] = (),
    ) -> str:
        return self._downstream.failure(
            event=event,
            message=message,
            failure_id=failure_id,
            level=level,
            attributes=self._attributes(attributes),
            correlation_refs=correlation_refs,
        )

    @staticmethod
    def _attributes(attributes: Mapping[str, JsonValue] | None) -> dict[str, JsonValue]:
        result = dict(attributes or {})
        result.setdefault("project_id", "sem-paper-1")
        result.setdefault("paper_method", "self_evolving_memory")
        return result


class SemPaperLoggingSystem(LoggingSystemPort):
    """Project policy adapter over the platform logging system seam."""

    def __init__(self, downstream: LoggingSystemPort) -> None:
        self._downstream = downstream

    def bind(
        self,
        *,
        logger: str,
        address: DiagnosticAddress,
        attributes: Mapping[str, JsonValue] | None = None,
    ) -> SemPaperLogWriter:
        return SemPaperLogWriter(
            self._downstream.bind(
                logger=logger,
                address=address,
                attributes=self._attributes(attributes),
            )
        )

    def query(
        self,
        *,
        scope: ScopeIdentity | None = None,
        system: SystemIdentity | None = None,
        component_id: str | None = None,
        trace_id: str | None = None,
        level_at_least: LogLevel | None = None,
        event: str | None = None,
        limit: int = 1000,
    ) -> tuple[LogRecord, ...]:
        return self._downstream.query(
            scope=scope,
            system=system,
            component_id=component_id,
            trace_id=trace_id,
            level_at_least=level_at_least,
            event=event,
            limit=limit,
        )

    @staticmethod
    def _attributes(attributes: Mapping[str, JsonValue] | None) -> dict[str, JsonValue]:
        result = dict(attributes or {})
        result.setdefault("project_id", "sem-paper-1")
        result.setdefault("paper_method", "self_evolving_memory")
        return result


__all__ = ["SemPaperLogWriter", "SemPaperLoggingSystem"]
