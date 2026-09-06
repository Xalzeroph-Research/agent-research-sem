from __future__ import annotations

import hashlib
import json

from .contracts import MemoryArchitectureSpec, architecture_value_to_json


def canonical_architecture_dict(architecture: MemoryArchitectureSpec) -> dict[str, object]:
    return {
        "format_version": architecture.format_version,
        "architecture_id": architecture.architecture_id,
        "generation": architecture.generation,
        "nodes": [
            {
                "node_id": node.node_id,
                "label": node.label,
                "purpose": " ".join(node.purpose.split()),
                "scope": node.scope.value,
                "mode": node.mode.value,
                "schema": [
                    {"name": field.name, "type": field.dtype.canonical(), "required": field.required}
                    for field in node.schema
                ],
                "primary_key": list(node.primary_key),
                "access": sorted(access.value for access in node.access),
                "sources": [
                    {
                        "kind": source.kind.value,
                        "node_id": source.node_id,
                        "event_types": list(source.event_types),
                        "channel": source.evidence_channel.value,
                    }
                    for source in node.sources
                ],
                "transform": {
                    "ops": [
                        {
                            "op": operation.op.value,
                            "inputs": list(operation.inputs),
                            "params": architecture_value_to_json(operation.params),
                            "objective": None if operation.objective is None else operation.objective.text,
                        }
                        for operation in node.transform.ops
                    ],
                    "output_ref": node.transform.output_ref,
                    "source_requirements": [
                        {
                            "source_node_id": requirement.source_node_id,
                            "fields": [
                                (name, None if expected is None else expected.canonical())
                                for name, expected in requirement.required_fields
                            ],
                        }
                        for requirement in node.transform.source_requirements
                    ],
                },
                "selector": None
                if node.selector is None
                else {
                    "all_of": [
                        {"field": atom.field, "op": atom.op.value, "value": architecture_value_to_json(atom.value)}
                        for atom in node.selector.all_of
                    ],
                    "negated": node.selector.negated,
                },
            }
            for node in sorted(architecture.nodes, key=lambda item: item.node_id)
        ],
    }


def architecture_digest(architecture: MemoryArchitectureSpec) -> str:
    encoded = json.dumps(
        canonical_architecture_dict(architecture),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["architecture_digest", "canonical_architecture_dict"]
