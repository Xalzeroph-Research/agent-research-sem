from __future__ import annotations

from dataclasses import dataclass

from research_platform.platform.kernel import canonical_digest

from .architecture import MemoryArchitectureSpec
from .architecture.projection import NodePartitionedDeluxeSnapshot, project_deluxe_architecture
from .architecture.records import NodePartitionedRecord
from .architecture.serialization import architecture_from_dict, architecture_to_dict
from .architecture.validation import ArchitectureValidator
from .json_snapshot import thaw_json_mapping
from .typed_materialization_errors import TypedMaterializationError
from .typed_materialization_validation import validate_materialized_records


TYPED_GENERATION_SCHEMA_VERSION = "sem.typed_materialized_generation.v2"


@dataclass(frozen=True, slots=True)
class TypedMaterializedGeneration:
    generation: str
    base_generation: str
    candidate_id: str
    architecture: MemoryArchitectureSpec
    source_sequence: int
    source_snapshot_digest: str
    records: tuple[NodePartitionedRecord, ...]

    _DOCUMENT_FIELDS = frozenset(
        {
            "schema_version",
            "generation",
            "base_generation",
            "candidate_id",
            "architecture",
            "source_sequence",
            "source_snapshot_digest",
            "records",
            "document_digest",
        }
    )

    def to_document(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema_version": TYPED_GENERATION_SCHEMA_VERSION,
            "generation": self.generation,
            "base_generation": self.base_generation,
            "candidate_id": self.candidate_id,
            "architecture": architecture_to_dict(self.architecture),
            "source_sequence": self.source_sequence,
            "source_snapshot_digest": self.source_snapshot_digest,
            "records": [
                {
                    "node_id": record.node_id,
                    "record_id": record.record_id,
                    "sequence": record.sequence,
                    "text": record.text,
                    "payload": thaw_json_mapping(record.payload),
                    "source_refs": list(record.source_refs),
                }
                for record in self.records
            ],
        }
        return {**body, "document_digest": canonical_digest(body)}

    @classmethod
    def from_document(cls, document: dict[str, object]) -> "TypedMaterializedGeneration":
        if set(document) != cls._DOCUMENT_FIELDS:
            missing = tuple(sorted(cls._DOCUMENT_FIELDS - set(document)))
            unknown = tuple(sorted(set(document) - cls._DOCUMENT_FIELDS))
            raise TypedMaterializationError(
                f"typed generation document schema mismatch: missing={missing!r} unknown={unknown!r}"
            )
        if document["schema_version"] != TYPED_GENERATION_SCHEMA_VERSION:
            raise TypedMaterializationError("unsupported typed generation schema version")
        digest = document["document_digest"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise TypedMaterializationError("typed generation document digest is invalid")
        body = {key: value for key, value in document.items() if key != "document_digest"}
        if canonical_digest(body) != digest:
            raise TypedMaterializationError("typed generation document digest mismatch")

        architecture_document = document["architecture"]
        if not isinstance(architecture_document, dict):
            raise TypedMaterializationError("typed generation architecture document is invalid")
        architecture = architecture_from_dict(architecture_document)

        raw_records = document["records"]
        if not isinstance(raw_records, (list, tuple)):
            raise TypedMaterializationError("typed generation records must be a sequence")
        records: list[NodePartitionedRecord] = []
        record_fields = {"node_id", "record_id", "sequence", "text", "payload", "source_refs"}
        for raw in raw_records:
            if not isinstance(raw, dict) or set(raw) != record_fields:
                raise TypedMaterializationError("typed generation record schema mismatch")
            sequence = raw["sequence"]
            payload = raw["payload"]
            source_refs = raw["source_refs"]
            string_fields = (raw["node_id"], raw["record_id"], raw["text"])
            if any(not isinstance(value, str) for value in string_fields):
                raise TypedMaterializationError("typed generation record string fields are invalid")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
                raise TypedMaterializationError("typed generation record sequence must be a non-negative integer")
            if not isinstance(payload, dict) or not isinstance(source_refs, (list, tuple)):
                raise TypedMaterializationError("typed generation record payload/source_refs are invalid")
            if any(not isinstance(ref, str) or not ref.strip() for ref in source_refs):
                raise TypedMaterializationError("typed generation record source_refs must be non-empty strings")
            records.append(
                NodePartitionedRecord(
                    raw["node_id"],
                    raw["record_id"],
                    sequence,
                    raw["text"],
                    dict(payload),
                    tuple(source_refs),
                )
            )

        source_sequence = document["source_sequence"]
        if isinstance(source_sequence, bool) or not isinstance(source_sequence, int) or source_sequence < 0:
            raise TypedMaterializationError("typed generation source_sequence must be a non-negative integer")
        identity_fields = ("generation", "base_generation", "candidate_id", "source_snapshot_digest")
        identities = {name: document[name] for name in identity_fields}
        if any(not isinstance(value, str) or not value.strip() for value in identities.values()):
            raise TypedMaterializationError("typed generation identity fields must be non-empty strings")
        source_digest = identities["source_snapshot_digest"]
        if len(source_digest) != 64 or any(char not in "0123456789abcdef" for char in source_digest):
            raise TypedMaterializationError("typed generation source snapshot digest is invalid")

        cls_validator = ArchitectureValidator()
        cls_validator.verify(architecture)
        normalized_records = cls._validate_decoded_records(architecture, tuple(records))
        return cls(
            identities["generation"],
            identities["base_generation"],
            identities["candidate_id"],
            architecture,
            source_sequence,
            identities["source_snapshot_digest"],
            normalized_records,
        )

    @staticmethod
    def _validate_decoded_records(
        architecture: MemoryArchitectureSpec,
        records: tuple[NodePartitionedRecord, ...],
    ) -> tuple[NodePartitionedRecord, ...]:
        return validate_materialized_records(architecture, records)

    def deluxe_snapshot(self) -> NodePartitionedDeluxeSnapshot:
        return NodePartitionedDeluxeSnapshot(
            project_deluxe_architecture(self.architecture, generation=self.generation),
            self.records,
        )


__all__ = ["TYPED_GENERATION_SCHEMA_VERSION", "TypedMaterializedGeneration"]
