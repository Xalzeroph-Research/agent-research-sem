from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from research_platform.platform.kernel import JsonValue

from ..json_snapshot import freeze_json_mapping


@dataclass(frozen=True, slots=True)
class NodePartitionedRecord:
    """One typed method-memory record already assigned to an architecture node."""

    node_id: str
    record_id: str
    sequence: int
    text: str
    payload: Mapping[str, JsonValue]
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.node_id, self.record_id)):
            raise ValueError("node-partitioned record identity is required")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("node-partitioned record sequence must be non-negative")
        if not isinstance(self.text, str):
            raise ValueError("node-partitioned record text must be a string")
        if not isinstance(self.payload, Mapping):
            raise TypeError("node-partitioned record payload must be a mapping")
        object.__setattr__(
            self,
            "payload",
            freeze_json_mapping(self.payload, label="node-partitioned record payload"),
        )
        if not isinstance(self.source_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.source_refs
        ):
            raise ValueError("node-partitioned record source_refs must be non-empty strings")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("node-partitioned record source_refs must be unique")


__all__ = ["NodePartitionedRecord"]
