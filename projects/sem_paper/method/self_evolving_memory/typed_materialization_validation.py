from __future__ import annotations

from research_platform.platform.kernel import canonical_digest
from research_platform.platform.kernel.errors import describe_exception

from .architecture import MemoryArchitectureSpec, MemoryMode, SourceKind
from .architecture.records import NodePartitionedRecord
from .architecture.values import validate_payload
from .typed_materialization_errors import TypedMaterializationError


def validate_materialized_records(
        architecture: MemoryArchitectureSpec,
        records: tuple[NodePartitionedRecord, ...],
        *,
        evidence_ids: frozenset[str] | None = None,
    ) -> tuple[NodePartitionedRecord, ...]:
        known_nodes = architecture.node_map()
        seen: set[str] = set()
        record_ids = {record.record_id for record in records}
        record_ids_by_node: dict[str, set[str]] = {}
        records_by_node: dict[str, list[NodePartitionedRecord]] = {}
        for record in records:
            if record.node_id not in known_nodes:
                raise TypedMaterializationError(f"record {record.record_id} names unknown node {record.node_id}")
            if record.record_id in seen:
                raise TypedMaterializationError(f"duplicate typed materialized record {record.record_id}")
            if not record.source_refs:
                raise TypedMaterializationError(
                    f"typed materialized record {record.record_id} has no source_refs"
                )
            if evidence_ids is not None:
                unknown_refs = set(record.source_refs) - evidence_ids - record_ids
                if unknown_refs:
                    raise TypedMaterializationError(
                        f"typed materialized record {record.record_id} has unknown source_refs: "
                        f"{sorted(unknown_refs)}"
                    )
            seen.add(record.record_id)
            try:
                validate_payload(known_nodes[record.node_id], record.payload)
            except ValueError as exc:
                descriptor = describe_exception(exc)
                raise TypedMaterializationError(
                    f"{descriptor.error_type}[{descriptor.error_digest[:16]}]"
                ) from exc
            record_ids_by_node.setdefault(record.node_id, set()).add(record.record_id)
            records_by_node.setdefault(record.node_id, []).append(record)

        if evidence_ids is not None:
            allowed_refs_by_node: dict[str, frozenset[str]] = {}
            for node in architecture.nodes:
                allowed_refs: set[str] = set()
                for source in node.sources:
                    if source.kind is SourceKind.EVIDENCE:
                        allowed_refs.update(evidence_ids)
                    elif source.node_id is not None:
                        allowed_refs.update(record_ids_by_node.get(source.node_id, set()))
                allowed_refs_by_node[node.node_id] = frozenset(allowed_refs)

            for record in records:
                unknown_refs = set(record.source_refs) - allowed_refs_by_node[record.node_id]
                if unknown_refs:
                    raise TypedMaterializationError(
                        f"typed materialized record {record.record_id} references undeclared ancestry: "
                        f"{sorted(unknown_refs)}"
                    )

        normalized: list[NodePartitionedRecord] = []
        for node in architecture.nodes:
            node_records = records_by_node.get(node.node_id, ())
            if node.mode is MemoryMode.CURRENT:
                latest: dict[tuple[object, ...], NodePartitionedRecord] = {}
                for record in node_records:
                    key = tuple(canonical_digest(record.payload.get(field)) for field in node.primary_key)
                    previous = latest.get(key)
                    if previous is None or (record.sequence, record.record_id) > (previous.sequence, previous.record_id):
                        latest[key] = record
                normalized.extend(latest.values())
            elif node.mode is MemoryMode.AGGREGATE:
                keys: set[tuple[object, ...]] = set()
                for record in node_records:
                    key = tuple(canonical_digest(record.payload.get(field)) for field in node.primary_key)
                    if key in keys:
                        raise TypedMaterializationError(
                            f"aggregate node {node.node_id} emitted duplicate primary key"
                        )
                    keys.add(key)
                    normalized.append(record)
            else:
                normalized.extend(node_records)
        return tuple(sorted(normalized, key=lambda record: (record.node_id, record.sequence, record.record_id)))


__all__ = ["validate_materialized_records"]
