from __future__ import annotations

"""Durable auxiliary scientific evidence authority and exact codecs."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import threading
from typing import Mapping
import uuid

from research_platform.platform.kernel import JsonDocument, canonical_digest
from research_platform.experimentation.study.api import ExperimentPlan

from .scientific_metric_contracts import ScientificMetricComputationError

SCIENTIFIC_AUXILIARY_SCHEMA_VERSION = "sem-scientific-auxiliary.v2"
SCIENTIFIC_AUXILIARY_SAMPLE_SCHEMA_VERSION = "sem-scientific-auxiliary-sample.v1"
SCIENTIFIC_AUXILIARY_METRIC_NAMES = ("TDP", "ELCE", "HPEF", "GAG")
_SCIENTIFIC_AUXILIARY_RANGES: dict[str, tuple[float | None, float | None]] = {
    "TDP": (0.0, None),
    "ELCE": (None, None),
    "HPEF": (0.0, 1.0),
    # Gate-to-Audit Generalization Gap is a signed effect difference, not a
    # probability. Negative values are valid when held-out effect exceeds the
    # gate estimate.
    "GAG": (None, None),
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificMetricComputationError(f"{field} must be a non-empty string")
    return value.strip()


def _required_digest(value: object, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ScientificMetricComputationError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScientificMetricComputationError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ScientificMetricComputationError(f"{field} must be a finite number")
    return number


def _validated_auxiliary_value(name: str, value: object) -> float:
    number = _finite_number(value, f"auxiliary metric {name}")
    lower, upper = _SCIENTIFIC_AUXILIARY_RANGES[name]
    if lower is not None and number < lower:
        raise ScientificMetricComputationError(f"auxiliary metric {name} must be >= {lower}")
    if upper is not None and number > upper:
        raise ScientificMetricComputationError(f"auxiliary metric {name} must be <= {upper}")
    return number

@dataclass(frozen=True, slots=True)
class ScientificAuxiliaryEvidence:
    """Typed evidence for estimands not derivable from workload aggregates."""

    schema_version: str
    evidence_id: str
    producer: str
    source_tree_digest: str
    plan_digest: str
    protocol_digest: str
    binding_digest: str
    values: tuple[tuple[str, float], ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCIENTIFIC_AUXILIARY_SCHEMA_VERSION:
            raise ScientificMetricComputationError(
                f"unsupported scientific auxiliary schema: {self.schema_version}"
            )
        _required_text(self.evidence_id, "evidence_id")
        _required_text(self.producer, "producer")
        for field in ("source_tree_digest", "plan_digest", "protocol_digest", "binding_digest"):
            _required_digest(getattr(self, field), field)
        names = tuple(name for name, _ in self.values)
        if names != tuple(sorted(SCIENTIFIC_AUXILIARY_METRIC_NAMES)):
            raise ScientificMetricComputationError(
                "scientific auxiliary values must contain exactly the four declared metrics"
            )
        for name, value in self.values:
            _required_text(name, "auxiliary metric name")
            _validated_auxiliary_value(name, value)
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ScientificMetricComputationError("scientific auxiliary evidence refs are required")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ScientificMetricComputationError("scientific auxiliary evidence refs must be unique")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True, slots=True)
class ScientificAuxiliarySample:
    """One typed producer observation for the four non-aggregate estimands."""

    seed_id: str
    trajectory_divergence: float
    held_out_causal_effect: float
    held_out_positive_edit_fraction: float
    gate_to_audit_generalization_gap: float

    def __post_init__(self) -> None:
        if not self.seed_id.strip():
            raise ScientificMetricComputationError("auxiliary sample seed_id is required")
        _validated_auxiliary_value("TDP", self.trajectory_divergence)
        _validated_auxiliary_value("ELCE", self.held_out_causal_effect)
        _validated_auxiliary_value("HPEF", self.held_out_positive_edit_fraction)
        _validated_auxiliary_value("GAG", self.gate_to_audit_generalization_gap)


@dataclass(frozen=True, slots=True)
class ScientificAuxiliarySampleEvidence:
    """One immutable run-produced seed sample before cross-seed finalization."""

    schema_version: str
    sample_id: str
    run_id: str
    seed_id: str
    source_tree_digest: str
    plan_digest: str
    trajectory_divergence: float
    held_out_causal_effect: float
    held_out_positive_edit_fraction: float
    gate_to_audit_generalization_gap: float
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCIENTIFIC_AUXILIARY_SAMPLE_SCHEMA_VERSION:
            raise ScientificMetricComputationError(
                f"unsupported scientific auxiliary sample schema: {self.schema_version}"
            )
        _required_text(self.sample_id, "sample_id")
        _required_text(self.run_id, "run_id")
        _required_text(self.seed_id, "seed_id")
        _required_digest(self.source_tree_digest, "source_tree_digest")
        _required_digest(self.plan_digest, "plan_digest")
        _validated_auxiliary_value("TDP", self.trajectory_divergence)
        _validated_auxiliary_value("ELCE", self.held_out_causal_effect)
        _validated_auxiliary_value("HPEF", self.held_out_positive_edit_fraction)
        _validated_auxiliary_value("GAG", self.gate_to_audit_generalization_gap)
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ScientificMetricComputationError(
                "scientific auxiliary sample evidence refs are required"
            )
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ScientificMetricComputationError(
                "scientific auxiliary sample evidence refs must be unique"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(self)

    def sample(self) -> ScientificAuxiliarySample:
        return ScientificAuxiliarySample(
            seed_id=self.seed_id,
            trajectory_divergence=self.trajectory_divergence,
            held_out_causal_effect=self.held_out_causal_effect,
            held_out_positive_edit_fraction=self.held_out_positive_edit_fraction,
            gate_to_audit_generalization_gap=self.gate_to_audit_generalization_gap,
        )


def decode_scientific_auxiliary_sample_evidence(
    document: JsonDocument,
) -> ScientificAuxiliarySampleEvidence:
    if not isinstance(document, Mapping):
        raise ScientificMetricComputationError(
            "scientific auxiliary sample evidence must be an object"
        )
    expected = {
        "schema_version",
        "sample_id",
        "run_id",
        "seed_id",
        "source_tree_digest",
        "plan_digest",
        "trajectory_divergence",
        "held_out_causal_effect",
        "held_out_positive_edit_fraction",
        "gate_to_audit_generalization_gap",
        "evidence_refs",
    }
    if set(document) != expected:
        raise ScientificMetricComputationError(
            "scientific auxiliary sample evidence fields are not exact"
        )
    raw_refs = document["evidence_refs"]
    if not isinstance(raw_refs, list) or any(not isinstance(item, str) for item in raw_refs):
        raise ScientificMetricComputationError(
            "scientific auxiliary sample evidence refs must be a string list"
        )
    return ScientificAuxiliarySampleEvidence(
        schema_version=_required_text(document["schema_version"], "schema_version"),
        sample_id=_required_text(document["sample_id"], "sample_id"),
        run_id=_required_text(document["run_id"], "run_id"),
        seed_id=_required_text(document["seed_id"], "seed_id"),
        source_tree_digest=_required_digest(document["source_tree_digest"], "source_tree_digest"),
        plan_digest=_required_digest(document["plan_digest"], "plan_digest"),
        trajectory_divergence=_validated_auxiliary_value("TDP", document["trajectory_divergence"]),
        held_out_causal_effect=_validated_auxiliary_value("ELCE", document["held_out_causal_effect"]),
        held_out_positive_edit_fraction=_validated_auxiliary_value("HPEF", document["held_out_positive_edit_fraction"]),
        gate_to_audit_generalization_gap=_validated_auxiliary_value("GAG", document["gate_to_audit_generalization_gap"]),
        evidence_refs=tuple(raw_refs),
    )

def load_scientific_auxiliary_sample_evidence(
    path: str | Path,
) -> ScientificAuxiliarySampleEvidence:
    target = Path(path).expanduser().resolve(strict=False)
    if not target.is_file():
        raise ScientificMetricComputationError(
            f"scientific auxiliary sample evidence is missing: {target}"
        )
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificMetricComputationError(
            f"scientific auxiliary sample evidence cannot be read: {target}"
        ) from exc
    return decode_scientific_auxiliary_sample_evidence(document)


class ScientificAuxiliaryEvidenceProducer:
    """Produce digest-bound auxiliary evidence from typed runtime samples.

    This is the production boundary for TDP/ELCE/HPEF/GAG.  It deliberately
    accepts no untyped JSON mapping and never fills a missing sample with a
    default.  A caller must provide one complete sample per declared seed.
    """

    def produce(
        self,
        *,
        plan: ExperimentPlan,
        source_tree_digest: str,
        samples: tuple[ScientificAuxiliarySample, ...],
        evidence_refs: tuple[str, ...],
        producer: str,
    ) -> ScientificAuxiliaryEvidence:
        plan.assert_consistent()
        if len(source_tree_digest) != 64 or any(
            char not in "0123456789abcdef" for char in source_tree_digest
        ):
            raise ScientificMetricComputationError("auxiliary producer source_tree_digest is invalid")
        if not samples:
            raise ScientificMetricComputationError("auxiliary producer requires runtime samples")
        expected_seeds = {
            binding.seed_id
            for binding in plan.bindings
            if binding.variant.kind.value in {"control", "treatment"}
        }
        actual_seeds = {sample.seed_id for sample in samples}
        if actual_seeds != expected_seeds:
            raise ScientificMetricComputationError(
                "auxiliary producer samples must cover exactly the primary study seeds"
            )
        if len(samples) != len(actual_seeds):
            raise ScientificMetricComputationError("auxiliary producer samples must be unique by seed")
        count = float(len(samples))
        values = (
            ("ELCE", sum(item.held_out_causal_effect for item in samples) / count),
            ("GAG", sum(item.gate_to_audit_generalization_gap for item in samples) / count),
            ("HPEF", sum(item.held_out_positive_edit_fraction for item in samples) / count),
            ("TDP", sum(item.trajectory_divergence for item in samples) / count),
        )
        return ScientificAuxiliaryEvidence(
            schema_version=SCIENTIFIC_AUXILIARY_SCHEMA_VERSION,
            evidence_id="aux_" + canonical_digest(
                {"plan": plan.plan_digest, "source": source_tree_digest, "values": values}
            )[:32],
            producer=_required_text(producer, "producer"),
            source_tree_digest=source_tree_digest,
            plan_digest=plan.plan_digest,
            protocol_digest=plan.protocol_digest,
            binding_digest=plan.binding_digest,
            values=values,
            evidence_refs=tuple(evidence_refs),
        )

def decode_scientific_auxiliary_evidence(document: JsonDocument) -> ScientificAuxiliaryEvidence:
    """Decode an exact JSON evidence document without accepting extra fields."""

    if not isinstance(document, Mapping):
        raise ScientificMetricComputationError("scientific auxiliary evidence must be an object")
    expected = {
        "schema_version",
        "evidence_id",
        "producer",
        "source_tree_digest",
        "plan_digest",
        "protocol_digest",
        "binding_digest",
        "values",
        "evidence_refs",
    }
    if set(document) != expected:
        raise ScientificMetricComputationError("scientific auxiliary evidence fields are not exact")
    raw_values = document["values"]
    if not isinstance(raw_values, Mapping) or set(raw_values) != set(SCIENTIFIC_AUXILIARY_METRIC_NAMES):
        raise ScientificMetricComputationError(
            "scientific auxiliary evidence values must contain exactly TDP, ELCE, HPEF and GAG"
        )
    raw_refs = document["evidence_refs"]
    if not isinstance(raw_refs, list) or any(not isinstance(item, str) for item in raw_refs):
        raise ScientificMetricComputationError("scientific auxiliary evidence refs must be a string list")
    return ScientificAuxiliaryEvidence(
        schema_version=_required_text(document["schema_version"], "schema_version"),
        evidence_id=_required_text(document["evidence_id"], "evidence_id"),
        producer=_required_text(document["producer"], "producer"),
        source_tree_digest=_required_digest(document["source_tree_digest"], "source_tree_digest"),
        plan_digest=_required_digest(document["plan_digest"], "plan_digest"),
        protocol_digest=_required_digest(document["protocol_digest"], "protocol_digest"),
        binding_digest=_required_digest(document["binding_digest"], "binding_digest"),
        values=tuple(
            (name, _validated_auxiliary_value(name, raw_values[name]))
            for name in sorted(SCIENTIFIC_AUXILIARY_METRIC_NAMES)
        ),
        evidence_refs=tuple(raw_refs),
    )


def load_scientific_auxiliary_evidence(path: str | Path) -> ScientificAuxiliaryEvidence:
    target = Path(path).expanduser().resolve(strict=False)
    if not target.is_file():
        raise ScientificMetricComputationError(f"scientific auxiliary evidence is missing: {target}")
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificMetricComputationError(
            f"scientific auxiliary evidence cannot be read: {target}"
        ) from exc
    return decode_scientific_auxiliary_evidence(document)


def validate_scientific_auxiliary_evidence(
    evidence: ScientificAuxiliaryEvidence,
    *,
    expected_source_tree_digest: str | None = None,
    expected_plan_digest: str | None = None,
    expected_protocol_digest: str | None = None,
    expected_binding_digest: str | None = None,
) -> ScientificAuxiliaryEvidence:
    for label, expected, actual in (
        ("source tree", expected_source_tree_digest, evidence.source_tree_digest),
        ("plan", expected_plan_digest, evidence.plan_digest),
        ("protocol", expected_protocol_digest, evidence.protocol_digest),
        ("binding", expected_binding_digest, evidence.binding_digest),
    ):
        if expected is not None and actual != expected:
            raise ScientificMetricComputationError(
                f"scientific auxiliary evidence {label} digest does not match the run"
            )
    return evidence


def _seed_filename(seed_id: str) -> str:
    if seed_id in {".", ".."} or any(char in seed_id for char in ("/", "\\", ":")):
        raise ScientificMetricComputationError("auxiliary sample seed_id is not filesystem-safe")
    return f"{seed_id}.json"


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_immutable_bytes(target: Path, payload: bytes) -> Path:
    """Publish once without an overwrite crash window.

    A matching existing document is idempotent. A different document at the
    same authority path is a conflict, never a last-writer-wins update.
    ``os.link`` supplies an atomic no-replace commit on Windows and POSIX.
    """

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if target.read_bytes() == payload:
            return target
        raise ScientificMetricComputationError(
            f"scientific evidence authority conflict: {target}"
        )
    temporary = target.with_name(
        f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.is_file() and target.read_bytes() == payload:
                return target
            raise ScientificMetricComputationError(
                f"scientific evidence authority conflict: {target}"
            )
        _fsync_directory(target.parent)
        return target
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


class DirectoryScientificAuxiliarySampleStore:
    """Immutable run-local authority for evaluator/audit-produced seed samples."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)

    def publish(self, sample: ScientificAuxiliarySampleEvidence) -> Path:
        target = self.root / _seed_filename(sample.seed_id)
        payload = asdict(sample)
        payload["evidence_refs"] = list(sample.evidence_refs)
        return _publish_immutable_bytes(target, _json_bytes(payload))

    def load_all(self) -> tuple[ScientificAuxiliarySampleEvidence, ...]:
        if not self.root.is_dir():
            return ()
        rows: list[ScientificAuxiliarySampleEvidence] = []
        seen: set[str] = set()
        for path in sorted(self.root.glob("*.json")):
            if not path.is_file():
                continue
            row = load_scientific_auxiliary_sample_evidence(path)
            if path.name != _seed_filename(row.seed_id):
                raise ScientificMetricComputationError(
                    f"auxiliary sample filename does not match seed identity: {path}"
                )
            if row.seed_id in seen:
                raise ScientificMetricComputationError(
                    f"duplicate auxiliary sample seed identity: {row.seed_id}"
                )
            seen.add(row.seed_id)
            rows.append(row)
        return tuple(rows)


def finalize_scientific_auxiliary_evidence(
    *,
    plan: ExperimentPlan,
    source_tree_digest: str,
    run_id: str,
    sample_store: DirectoryScientificAuxiliarySampleStore,
    output_path: str | Path,
    producer: str = "sem-paper.scientific-auxiliary-finalizer.v1",
) -> ScientificAuxiliaryEvidence:
    """Validate complete run-local samples and immutably publish the final receipt."""

    samples = sample_store.load_all()
    if not samples:
        raise ScientificMetricComputationError(
            "no run-local scientific auxiliary samples were published"
        )
    for item in samples:
        if item.run_id != run_id:
            raise ScientificMetricComputationError(
                f"auxiliary sample {item.sample_id!r} belongs to another run"
            )
        if item.source_tree_digest != source_tree_digest:
            raise ScientificMetricComputationError(
                f"auxiliary sample {item.sample_id!r} source digest does not match the run"
            )
        if item.plan_digest != plan.plan_digest:
            raise ScientificMetricComputationError(
                f"auxiliary sample {item.sample_id!r} plan digest does not match the run"
            )
    refs = tuple(
        dict.fromkeys(
            ref
            for item in sorted(samples, key=lambda row: row.seed_id)
            for ref in item.evidence_refs
        )
    )
    evidence = ScientificAuxiliaryEvidenceProducer().produce(
        plan=plan,
        source_tree_digest=source_tree_digest,
        samples=tuple(item.sample() for item in samples),
        evidence_refs=refs,
        producer=producer,
    )
    payload = {
        "schema_version": evidence.schema_version,
        "evidence_id": evidence.evidence_id,
        "producer": evidence.producer,
        "source_tree_digest": evidence.source_tree_digest,
        "plan_digest": evidence.plan_digest,
        "protocol_digest": evidence.protocol_digest,
        "binding_digest": evidence.binding_digest,
        "values": dict(evidence.values),
        "evidence_refs": list(evidence.evidence_refs),
    }
    target = Path(output_path).expanduser().resolve(strict=False)
    _publish_immutable_bytes(target, _json_bytes(payload))
    return evidence


__all__ = [
    "SCIENTIFIC_AUXILIARY_METRIC_NAMES",
    "SCIENTIFIC_AUXILIARY_SCHEMA_VERSION",
    "SCIENTIFIC_AUXILIARY_SAMPLE_SCHEMA_VERSION",
    "DirectoryScientificAuxiliarySampleStore",
    "ScientificAuxiliaryEvidence",
    "ScientificAuxiliaryEvidenceProducer",
    "ScientificAuxiliarySample",
    "ScientificAuxiliarySampleEvidence",
    "decode_scientific_auxiliary_evidence",
    "decode_scientific_auxiliary_sample_evidence",
    "finalize_scientific_auxiliary_evidence",
    "load_scientific_auxiliary_evidence",
    "load_scientific_auxiliary_sample_evidence",
    "validate_scientific_auxiliary_evidence",
]
