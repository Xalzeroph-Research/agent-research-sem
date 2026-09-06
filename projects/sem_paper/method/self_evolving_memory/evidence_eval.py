from __future__ import annotations

from dataclasses import dataclass

from research_platform.platform.kernel import JsonValue


@dataclass(frozen=True, slots=True)
class EvalEvidence:
    eval_id: str
    payload: JsonValue


class EvalEvidenceStore:
    """J_eval authority. Private evaluation evidence cannot materialize method memory."""

    def __init__(self) -> None:
        self._rows: list[EvalEvidence] = []

    def append(self, row: EvalEvidence) -> None:
        self._rows.append(row)

    @property
    def rows(self) -> tuple[EvalEvidence, ...]:
        return tuple(self._rows)

    def snapshot(self) -> tuple[EvalEvidence, ...]:
        return self.rows

    def restore(self, rows: tuple[EvalEvidence, ...]) -> None:
        ids = tuple(row.eval_id for row in rows)
        if any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("evaluation evidence restore requires unique non-empty ids")
        self._rows = list(rows)
