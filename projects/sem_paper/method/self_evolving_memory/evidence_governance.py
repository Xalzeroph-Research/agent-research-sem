from __future__ import annotations

"""Lossless retention classification for the grounded evidence substrate."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .evidence_api import EvidenceRecord


class EvidenceTier(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


@dataclass(frozen=True, slots=True)
class EvidenceRetentionDecision:
    evidence_id: str
    tier: EvidenceTier
    reconstructible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class EvidenceGovernanceConfig:
    hot_recent_events: int = 500
    warm_recent_events: int = 5000
    allow_lossless_cold_storage: bool = True

    def __post_init__(self) -> None:
        if self.hot_recent_events <= 0 or self.warm_recent_events <= self.hot_recent_events:
            raise ValueError("evidence retention windows are invalid")


class EvidenceGovernance:
    """Classify canonical J_mem storage temperature without lossy deletion."""

    def __init__(self, config: EvidenceGovernanceConfig | None = None) -> None:
        self.config = config or EvidenceGovernanceConfig()

    def classify(self, rows: Iterable[EvidenceRecord]) -> tuple[EvidenceRetentionDecision, ...]:
        values = tuple(rows)
        output: list[EvidenceRetentionDecision] = []
        for index, row in enumerate(values):
            if not isinstance(row, EvidenceRecord):
                raise TypeError("EvidenceGovernance accepts only canonical J_mem records")
            age = len(values) - index - 1
            tier = (
                EvidenceTier.HOT
                if age < self.config.hot_recent_events
                else EvidenceTier.WARM
                if age < self.config.warm_recent_events
                else EvidenceTier.COLD
            )
            output.append(
                EvidenceRetentionDecision(
                    row.evidence_id,
                    tier,
                    True,
                    "grounded_j_mem_retained_losslessly",
                )
            )
        return tuple(output)

    def reconstructibility_report(self, rows: Iterable[EvidenceRecord]) -> dict[str, object]:
        decisions = self.classify(rows)
        return {
            "total": len(decisions),
            "reconstructible": sum(item.reconstructible for item in decisions),
            "hot": sum(item.tier is EvidenceTier.HOT for item in decisions),
            "warm": sum(item.tier is EvidenceTier.WARM for item in decisions),
            "cold": sum(item.tier is EvidenceTier.COLD for item in decisions),
            "lossy_deletion_allowed": False,
            "lossless_cold_storage_allowed": self.config.allow_lossless_cold_storage,
        }


__all__ = [
    "EvidenceGovernance",
    "EvidenceGovernanceConfig",
    "EvidenceRetentionDecision",
    "EvidenceTier",
]
