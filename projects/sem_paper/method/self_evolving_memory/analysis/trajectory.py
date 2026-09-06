from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from ..evolution.contracts import EvolutionOutcome


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    index: int
    status: str
    base_generation: str | None
    final_generation: str | None
    edit: str | None
    reason_code: str | None


def architecture_trajectory(records: Sequence[EvolutionOutcome]) -> tuple[TrajectoryPoint, ...]:
    return tuple(
        TrajectoryPoint(
            index,
            record.status,
            record.base_generation,
            record.final_generation,
            None if record.edit is None else record.edit.value,
            record.reason_code,
        )
        for index, record in enumerate(records)
    )


def trajectory_report(records: Sequence[EvolutionOutcome]) -> dict[str, Any]:
    points = architecture_trajectory(records)
    return {
        "points": [asdict(point) for point in points],
        "accepted_generations": [
            point.final_generation for point in points if point.status == "adopted"
        ],
        "accepted_edit_types": [
            point.edit for point in points if point.status == "adopted" and point.edit is not None
        ],
        "no_edit_count": sum(point.status == "no_edit" for point in points),
        "deferred_count": sum(point.status == "deferred" for point in points),
        "rejected_count": sum(point.status == "rejected" for point in points),
        "invalid_evaluation_count": sum(
            point.status == "invalid_evaluation" for point in points
        ),
    }


__all__ = ["TrajectoryPoint", "architecture_trajectory", "trajectory_report"]
