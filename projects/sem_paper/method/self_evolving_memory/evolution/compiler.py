from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib

from research_platform.platform.kernel import canonical_digest

from ..architecture import ArchitectureCompiler, MemoryArchitectureSpec, architecture_digest
from ..architecture.edits import CreateNodeEdit, MergeNodesEdit, RetireNodeEdit, SplitNodeEdit
from .contracts import CandidateArchitecture, EditKind, PrimitiveEdit, PrimitiveEditKind, StructuralIntent, StructuralIntentPayload

class StructuralCompiler:
    """Compile one explicit structural intent without silent defaults.

    Typed architecture intents are reconciled against the deterministic
    before/after architecture diff so the primitive edit evidence describes
    the target specification exactly.  The legacy generic payload shape is
    still accepted only when every required field is explicit.
    """

    _TYPED_EDIT_BY_KIND = {
        EditKind.CREATE: CreateNodeEdit,
        EditKind.RETIRE: RetireNodeEdit,
        EditKind.SPLIT: SplitNodeEdit,
        EditKind.MERGE: MergeNodesEdit,
    }
    _EXPECTED_DIFF = {
        EditKind.CREATE: (1, 0),
        EditKind.RETIRE: (0, 1),
        EditKind.SPLIT: (2, 1),
        EditKind.MERGE: (1, 2),
    }

    def __init__(self, target_builder) -> None:
        if not callable(target_builder):
            raise TypeError("structural compiler target_builder must be callable")
        self.target_builder = target_builder

    @staticmethod
    def _payload(intent: StructuralIntent) -> StructuralIntentPayload:
        if not isinstance(intent.payload, Mapping):
            raise TypeError("structural edit intent requires an explicit object payload")
        return intent.payload

    @staticmethod
    def _text(payload: StructuralIntentPayload, key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"structural edit payload requires non-empty {key}")
        return value

    @classmethod
    def _text_items(cls, payload: StructuralIntentPayload, key: str) -> tuple[str, ...]:
        value = payload.get(key)
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            raise ValueError(f"structural edit payload {key} requires at least two node ids")
        items = tuple(value)
        if any(not isinstance(item, str) or not item.strip() for item in items):
            raise ValueError(f"structural edit payload {key} must contain non-empty node ids")
        if len(items) != len(set(items)):
            raise ValueError(f"structural edit payload {key} must be unique")
        return items

    @classmethod
    def _legacy_primitives(cls, intent: StructuralIntent, payload: StructuralIntentPayload) -> tuple[PrimitiveEdit, ...]:
        if intent.edit is EditKind.CREATE:
            return (
                PrimitiveEdit(
                    PrimitiveEditKind.CREATE,
                    cls._text(payload, "node_id"),
                    payload.get("spec"),
                ),
            )
        if intent.edit is EditKind.RETIRE:
            return (PrimitiveEdit(PrimitiveEditKind.RETIRE, cls._text(payload, "node_id")),)
        if intent.edit is EditKind.SPLIT:
            parent = cls._text(payload, "parent")
            children = cls._text_items(payload, "children")
            if parent in children:
                raise ValueError("SPLIT parent cannot also be a child")
            return tuple(
                PrimitiveEdit(PrimitiveEditKind.CREATE, child)
                for child in children
            ) + (PrimitiveEdit(PrimitiveEditKind.RETIRE, parent),)
        if intent.edit is EditKind.MERGE:
            sources = cls._text_items(payload, "sources")
            target = cls._text(payload, "target")
            if target in sources:
                raise ValueError("MERGE target cannot also be a source")
            return (PrimitiveEdit(PrimitiveEditKind.CREATE, target),) + tuple(
                PrimitiveEdit(PrimitiveEditKind.RETIRE, source)
                for source in sources
            )
        raise ValueError("NO_EDIT cannot be compiled")

    @classmethod
    def _architecture_plan(
        cls,
        intent: StructuralIntent,
        payload: StructuralIntentPayload,
    ) -> tuple[MemoryArchitectureSpec, tuple[PrimitiveEdit, ...]] | None:
        has_typed_fields = "architecture" in payload or "architecture_edit" in payload
        if not has_typed_fields:
            return None
        current = payload.get("architecture")
        architecture_edit = payload.get("architecture_edit")
        if not isinstance(current, MemoryArchitectureSpec):
            raise TypeError("typed structural intent requires the observed MemoryArchitectureSpec")
        expected_edit_type = cls._TYPED_EDIT_BY_KIND.get(intent.edit)
        if expected_edit_type is None:
            raise ValueError("NO_EDIT cannot carry an architecture_edit")
        if not isinstance(architecture_edit, expected_edit_type):
            raise TypeError(
                f"{intent.edit.value} intent requires {expected_edit_type.__name__}"
            )

        target = ArchitectureCompiler().compile_edit(current, architecture_edit)
        current_ids = set(current.node_map())
        target_nodes = target.node_map()
        target_ids = set(target_nodes)
        created = tuple(sorted(target_ids - current_ids))
        retired = tuple(sorted(current_ids - target_ids))
        expected_created, expected_retired = cls._EXPECTED_DIFF[intent.edit]
        if len(created) != expected_created or len(retired) != expected_retired:
            raise ValueError(
                "typed architecture edit produced an unexpected primitive node diff"
            )
        primitives = tuple(
            PrimitiveEdit(PrimitiveEditKind.CREATE, node_id, target_nodes[node_id])
            for node_id in created
        ) + tuple(
            PrimitiveEdit(PrimitiveEditKind.RETIRE, node_id)
            for node_id in retired
        )
        return target, primitives

    def compile(self, intent: StructuralIntent, base_generation: str) -> CandidateArchitecture:
        if not isinstance(intent, StructuralIntent):
            raise TypeError("structural compiler requires a StructuralIntent")
        if not isinstance(base_generation, str) or not base_generation.strip():
            raise ValueError("structural compiler base_generation must be a non-empty string")
        if intent.edit is EditKind.NO_EDIT:
            raise ValueError("NO_EDIT cannot be compiled")

        payload = self._payload(intent)
        architecture_plan = self._architecture_plan(intent, payload)
        if architecture_plan is None:
            expected_target = None
            edits = self._legacy_primitives(intent, payload)
        else:
            expected_target, edits = architecture_plan

        built = self.target_builder(base_generation, edits, intent)
        if not isinstance(built, tuple) or len(built) != 2:
            raise TypeError("structural target_builder must return (target_spec, contracts)")
        target_spec, contracts = built
        if expected_target is not None:
            if not isinstance(target_spec, MemoryArchitectureSpec):
                raise TypeError("typed architecture target_builder returned a non-architecture target")
            if architecture_digest(target_spec) != architecture_digest(expected_target):
                raise ValueError("structural target_builder drifted from the typed architecture edit")
        if not isinstance(contracts, Sequence) or isinstance(contracts, (str, bytes, bytearray)):
            raise TypeError("structural target_builder contracts must be a finite sequence")
        contract_tuple = tuple(contracts)

        digest = canonical_digest(target_spec)
        candidate_id = "candidate_" + hashlib.sha256(
            (base_generation + digest + intent.edit.value).encode("utf-8")
        ).hexdigest()[:20]
        return CandidateArchitecture(
            base_generation,
            candidate_id,
            target_spec,
            digest,
            edits,
            contract_tuple,
        )


class OperationalVerifier:
    """Operational safety only; never semantic utility or acceptance."""

    def verify(self, candidate: CandidateArchitecture) -> None:
        if not isinstance(candidate, CandidateArchitecture):
            raise TypeError("operational verifier requires a CandidateArchitecture")
        if not candidate.primitive_edits:
            raise ValueError("candidate has no primitive edits")
        if any(
            edit.kind not in {PrimitiveEditKind.CREATE, PrimitiveEditKind.RETIRE}
            for edit in candidate.primitive_edits
        ):
            raise ValueError("unsupported primitive edit")
        create_ids = tuple(
            edit.target for edit in candidate.primitive_edits
            if edit.kind is PrimitiveEditKind.CREATE
        )
        retire_ids = tuple(
            edit.target for edit in candidate.primitive_edits
            if edit.kind is PrimitiveEditKind.RETIRE
        )
        if len(create_ids) != len(set(create_ids)) or len(retire_ids) != len(set(retire_ids)):
            raise ValueError("candidate primitive edit targets must be unique within each operation")
        if set(create_ids) & set(retire_ids):
            raise ValueError("candidate cannot create and retire the same node")
        if not candidate.materialization_contracts:
            raise ValueError("candidate must provide complete target materialization plan")

        if isinstance(candidate.target_spec, MemoryArchitectureSpec):
            target_ids = set(candidate.target_spec.node_map())
            if any(node_id not in target_ids for node_id in create_ids):
                raise ValueError("candidate CREATE primitive is absent from target architecture")
            if any(node_id in target_ids for node_id in retire_ids):
                raise ValueError("candidate RETIRE primitive is still present in target architecture")
            contract_ids = tuple(
                getattr(contract, "node_id", None)
                for contract in candidate.materialization_contracts
            )
            if any(not isinstance(node_id, str) or not node_id.strip() for node_id in contract_ids):
                raise ValueError("typed architecture candidate requires node-scoped materialization contracts")
            if len(contract_ids) != len(set(contract_ids)):
                raise ValueError("typed architecture candidate has duplicate materialization contracts")
            if set(contract_ids) != target_ids:
                raise ValueError("typed architecture materialization plan must cover every target node exactly")
