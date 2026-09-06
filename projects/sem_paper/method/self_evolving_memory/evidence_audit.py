from __future__ import annotations

from dataclasses import dataclass

from research_platform.platform.kernel import JsonValue


@dataclass(frozen=True, slots=True)
class AuditEvidence:
    audit_id: str
    payload: JsonValue


class AuditEvidenceStore:
    """J_audit authority. No J_mem view or materialization capability is exposed."""

    def __init__(self) -> None:
        self._rows: list[AuditEvidence] = []

    def append(self, row: AuditEvidence) -> None:
        self._rows.append(row)

    @property
    def rows(self) -> tuple[AuditEvidence, ...]:
        return tuple(self._rows)

    def snapshot(self) -> tuple[AuditEvidence, ...]:
        return self.rows

    def restore(self, rows: tuple[AuditEvidence, ...]) -> None:
        ids = tuple(row.audit_id for row in rows)
        if any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("audit evidence restore requires unique non-empty ids")
        self._rows = list(rows)
