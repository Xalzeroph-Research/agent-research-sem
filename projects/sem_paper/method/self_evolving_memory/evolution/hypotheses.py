from __future__ import annotations

"""Diagnostic hypothesis records without candidate/adoption authority."""

from dataclasses import dataclass, field
import hashlib
from typing import Sequence

@dataclass(frozen=True, slots=True)
class StructuralHypothesis:
    hypothesis_id: str
    observation_report_id: str
    text: str
    evidence_refs: tuple[str, ...]
    status: str = "PROPOSED"


@dataclass(slots=True)
class HypothesisRegistry:
    """In-memory diagnostic record; it has no candidate/adoption capability."""

    records: list[StructuralHypothesis] = field(default_factory=list)

    def add(
        self,
        *,
        observation_report_id: str,
        text: str,
        evidence_refs: Sequence[str],
        status: str = "PROPOSED",
    ) -> StructuralHypothesis:
        if not observation_report_id.strip() or not text.strip() or not status.strip():
            raise ValueError("structural hypothesis identity and text are required")
        refs = tuple(sorted(set(str(ref) for ref in evidence_refs if str(ref).strip())))
        raw = f"{observation_report_id}|{text}|{'|'.join(refs)}|{len(self.records)}".encode("utf-8")
        hypothesis = StructuralHypothesis(
            hypothesis_id="hyp_" + hashlib.sha256(raw).hexdigest()[:12],
            observation_report_id=observation_report_id,
            text=text,
            evidence_refs=refs,
            status=status,
        )
        self.records.append(hypothesis)
        return hypothesis

    def recent(self, limit: int = 12) -> tuple[StructuralHypothesis, ...]:
        if limit < 0:
            raise ValueError("hypothesis limit must be non-negative")
        return tuple(self.records[-limit:]) if limit else ()
