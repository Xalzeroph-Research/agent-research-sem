from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..api import LineageEdge, MemoryLineageRecord


@dataclass(slots=True)
class MemoryLineageGraph:
    """Rebuildable derived lineage over current project memory records."""

    outgoing: dict[str, set[str]] = field(default_factory=dict)
    incoming: dict[str, set[str]] = field(default_factory=dict)
    relation: dict[tuple[str, str], str] = field(default_factory=dict)

    def add_record(self, record: MemoryLineageRecord) -> None:
        for source_ref in record.source_refs:
            self.outgoing.setdefault(source_ref, set()).add(record.record_id)
            self.incoming.setdefault(record.record_id, set()).add(source_ref)
            self.relation[(source_ref, record.record_id)] = "DERIVED_FROM"

    def rebuild(self, store: Mapping[str, Sequence[MemoryLineageRecord]]) -> None:
        self.outgoing.clear()
        self.incoming.clear()
        self.relation.clear()
        for records in store.values():
            for record in records:
                self.add_record(record)

    def edges(self) -> tuple[LineageEdge, ...]:
        return tuple(
            LineageEdge(source, derived, self.relation[(source, derived)])
            for source, derived in sorted(self.relation)
        )

    def snapshot(self) -> dict[str, object]:
        """Return a deterministic, read-only projection of derived lineage."""

        return {
            "edges": [
                {
                    "source_ref": edge.source_ref,
                    "derived_ref": edge.derived_ref,
                    "relation": edge.relation,
                }
                for edge in self.edges()
            ],
            "edge_count": len(self.relation),
        }

    def ancestors(self, ref: str, *, max_depth: int = 12) -> tuple[str, ...]:
        if not ref.strip() or max_depth <= 0:
            raise ValueError("lineage ancestor query is invalid")
        seen: set[str] = set()
        frontier = {ref}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for item in frontier:
                for parent in self.incoming.get(item, ()):
                    if parent not in seen:
                        seen.add(parent)
                        next_frontier.add(parent)
            if not next_frontier:
                break
            frontier = next_frontier
        return tuple(sorted(seen))

    def derivation_depth(self, ref: str, *, max_depth: int = 64) -> int:
        if not ref.strip() or max_depth <= 0:
            raise ValueError("lineage depth query is invalid")
        depth = 0
        frontier = {ref}
        seen = set(frontier)
        while frontier and depth < max_depth:
            next_frontier: set[str] = set()
            for item in frontier:
                for parent in self.incoming.get(item, ()):
                    if parent not in seen:
                        seen.add(parent)
                        next_frontier.add(parent)
            if not next_frontier:
                break
            frontier = next_frontier
            depth += 1
        return depth

    def verify_reconstructible(self, ref: str) -> bool:
        return all(
            not ancestor.startswith("audit:") and "J_audit" not in ancestor
            for ancestor in self.ancestors(ref)
        )


@dataclass(slots=True)
class ArchitectureLineageGraph:
    """Forward-only lineage of adopted architecture generations."""

    parents: dict[int, int | None] = field(default_factory=dict)
    edit_labels: dict[int, str] = field(default_factory=dict)

    def record_transition(self, previous_generation: int, new_generation: int, edit_label: str) -> None:
        if previous_generation < 0 or new_generation <= previous_generation or not edit_label.strip():
            raise ValueError("architecture lineage transition is invalid")
        if new_generation in self.parents and self.parents[new_generation] != previous_generation:
            raise ValueError("architecture lineage generation has conflicting parents")
        self.parents[new_generation] = previous_generation
        self.parents.setdefault(previous_generation, None if previous_generation == 0 else self.parents.get(previous_generation))
        self.edit_labels[new_generation] = edit_label

    def path_to_root(self, generation: int) -> tuple[int, ...]:
        if generation < 0:
            raise ValueError("architecture generation cannot be negative")
        path: list[int] = []
        seen: set[int] = set()
        current = generation
        while current not in seen:
            path.append(current)
            seen.add(current)
            parent = self.parents.get(current)
            if parent is None:
                break
            current = parent
        return tuple(path)

    def snapshot(self) -> dict[str, object]:
        return {
            "edges": [
                {"source_ref": edge.source_ref, "derived_ref": edge.derived_ref, "relation": edge.relation}
                for edge in self.edges()
            ]
        }


__all__ = ["ArchitectureLineageGraph", "MemoryLineageGraph"]
