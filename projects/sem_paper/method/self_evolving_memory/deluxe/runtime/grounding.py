from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Collection

from ..api import DeluxeMemoryRecord, DeluxeReadSnapshot
from .serving import DeluxeServingResult


@dataclass(frozen=True, slots=True)
class DeluxeGroundingAudit:
    """Evidence-only audit of one Deluxe read and its materialized generation."""

    query_record_count: int
    materialized_record_count: int
    memory_evidence_count: int
    audit_evidence_count: int
    query_refs_nonempty: bool
    query_refs_memory_only: bool
    materialized_refs_nonempty: bool
    materialized_refs_memory_only: bool
    audit_materialization_leak_count: int
    unknown_source_ref_count: int

    @property
    def ok(self) -> bool:
        return bool(
            self.query_record_count > 0
            and self.query_refs_nonempty
            and self.query_refs_memory_only
            and self.materialized_record_count > 0
            and self.materialized_refs_nonempty
            and self.materialized_refs_memory_only
            and self.audit_materialization_leak_count == 0
            and self.unknown_source_ref_count == 0
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "query_record_count": self.query_record_count,
            "materialized_record_count": self.materialized_record_count,
            "memory_evidence_count": self.memory_evidence_count,
            "audit_evidence_count": self.audit_evidence_count,
            "query_refs_nonempty": self.query_refs_nonempty,
            "query_refs_memory_only": self.query_refs_memory_only,
            "materialized_refs_nonempty": self.materialized_refs_nonempty,
            "materialized_refs_memory_only": self.materialized_refs_memory_only,
            "audit_materialization_leak_count": self.audit_materialization_leak_count,
            "unknown_source_ref_count": self.unknown_source_ref_count,
            "ok": self.ok,
        }


def _record_ancestry(
    refs: Collection[str],
    *,
    records: dict[str, DeluxeMemoryRecord],
    memory_ids: frozenset[str],
    audit_ids: frozenset[str],
) -> tuple[bool, bool, int]:
    """Return (memory-only, audit-leak, unknown-reference-count)."""

    pending = list(refs)
    visited: set[str] = set()
    memory_only = True
    audit_leak = False
    unknown = 0
    while pending:
        ref = pending.pop()
        if ref in visited:
            continue
        visited.add(ref)
        if ref in audit_ids:
            audit_leak = True
            memory_only = False
        elif ref in memory_ids:
            continue
        elif ref in records:
            nested = tuple(records[ref].source_refs)
            if not nested:
                unknown += 1
                memory_only = False
            else:
                pending.extend(nested)
        else:
            unknown += 1
            memory_only = False
    return memory_only, audit_leak, unknown


def audit_deluxe_grounding(
    snapshot: DeluxeReadSnapshot,
    result: DeluxeServingResult,
    *,
    memory_evidence_ids: Collection[str],
    audit_evidence_ids: Collection[str] = (),
) -> DeluxeGroundingAudit:
    """Check that a Deluxe result and generation trace only to ``J_mem``.

    The audit consumes read contracts and evidence identifiers. It does not
    write memory, change serving, or become an acceptance/verifier authority.
    """

    records: dict[str, DeluxeMemoryRecord] = {
        record.record_id: record
        for node_id in snapshot.node_ids()
        for record in snapshot.iter_records(node_id)
    }
    memory_ids = frozenset(str(value) for value in memory_evidence_ids)
    audit_ids = frozenset(str(value) for value in audit_evidence_ids)
    materialized = tuple(records.values())
    query_ids = set(result.selected_record_ids)
    query_records = tuple(records[record_id] for record_id in query_ids if record_id in records)

    query_refs = tuple(ref for record in query_records for ref in record.source_refs)
    query_nonempty = bool(query_records) and all(bool(record.source_refs) for record in query_records)
    query_memory_only, _, query_unknown = _record_ancestry(
        query_refs,
        records=records,
        memory_ids=memory_ids,
        audit_ids=audit_ids,
    )
    materialized_refs = tuple(ref for record in materialized for ref in record.source_refs)
    materialized_nonempty = bool(materialized) and all(bool(record.source_refs) for record in materialized)
    materialized_memory_only, _, materialized_unknown = _record_ancestry(
        materialized_refs,
        records=records,
        memory_ids=memory_ids,
        audit_ids=audit_ids,
    )
    audit_leaks = sum(
        1
        for record in materialized
        if _record_ancestry(
            record.source_refs,
            records=records,
            memory_ids=memory_ids,
            audit_ids=audit_ids,
        )[1]
    )
    return DeluxeGroundingAudit(
        query_record_count=len(query_records),
        materialized_record_count=len(materialized),
        memory_evidence_count=len(memory_ids),
        audit_evidence_count=len(audit_ids),
        query_refs_nonempty=query_nonempty,
        query_refs_memory_only=query_memory_only,
        materialized_refs_nonempty=materialized_nonempty,
        materialized_refs_memory_only=materialized_memory_only,
        audit_materialization_leak_count=audit_leaks,
        unknown_source_ref_count=query_unknown + materialized_unknown,
    )


__all__ = ["DeluxeGroundingAudit", "audit_deluxe_grounding"]
