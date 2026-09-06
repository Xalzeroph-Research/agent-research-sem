"""Typed live-evidence boundary for SEM scientific claims.

The project can consume evidence produced by an outer qualification/runtime
system, but it cannot infer live validity from a URL, a local preflight, or a
placeholder artifact. A blocked or failed gate remains a first-class result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path

from research_platform.platform.kernel import JsonValue, canonical_digest


class LiveEvidenceStatus(StrEnum):
    PASS = "PASS"
    BLOCKED_BY_ENVIRONMENT = "BLOCKED_BY_ENVIRONMENT"
    FAILED = "FAILED"


class LiveEvidenceValidationError(ValueError):
    """A live-evidence receipt is absent, malformed, or not claim-eligible."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveEvidenceValidationError(f"live evidence {field} must be non-empty text")
    return value


def _optional_digest(value: object, field: str) -> str | None:
    if value is None:
        return None
    digest = _required_text(value, field)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise LiveEvidenceValidationError(f"live evidence {field} must be a lowercase SHA-256 digest")
    return digest


@dataclass(frozen=True, slots=True)
class LiveEvidenceReceipt:
    """Immutable receipt emitted by a qualified model plus live-world run."""

    schema_version: str
    evidence_id: str
    status: LiveEvidenceStatus
    run_id: str
    source_tree_digest: str
    qualified_closure_digest: str | None
    t2b_gate_digest: str | None
    protocol_digest: str
    matrix_profile: str
    repetitions: int
    claim_eligible: bool
    blockers: tuple[str, ...] = ()
    plan_digest: str | None = None
    binding_digest: str | None = None
    metric_manifest_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("schema_version", "evidence_id", "run_id", "matrix_profile"):
            _required_text(getattr(self, field), field)
        for field in (
            "source_tree_digest",
            "qualified_closure_digest",
            "t2b_gate_digest",
            "protocol_digest",
            "plan_digest",
            "binding_digest",
            "metric_manifest_digest",
        ):
            _optional_digest(getattr(self, field), field)
        if self.repetitions <= 0:
            raise LiveEvidenceValidationError("live evidence repetitions must be positive")
        if any(not blocker.strip() for blocker in self.blockers):
            raise LiveEvidenceValidationError("live evidence blockers cannot be blank")
        if self.status is LiveEvidenceStatus.PASS:
            if self.qualified_closure_digest is None or self.t2b_gate_digest is None:
                raise LiveEvidenceValidationError("PASS evidence requires qualified closure and T2B digests")
            if self.matrix_profile != "core-6" or self.repetitions < 12:
                raise LiveEvidenceValidationError(
                    "PASS evidence requires the frozen confirmatory Core-6 repetition contract"
                )
            if any(
                value is None
                for value in (
                    self.source_tree_digest,
                    self.protocol_digest,
                    self.qualified_closure_digest,
                    self.t2b_gate_digest,
                )
            ):
                raise LiveEvidenceValidationError(
                    "PASS evidence requires source, protocol, closure and T2B digests"
                )
            if self.blockers or not self.claim_eligible:
                raise LiveEvidenceValidationError("PASS evidence cannot carry blockers or a false claim flag")
            if self.schema_version.endswith(".v2") and any(
                value is None
                for value in (self.plan_digest, self.binding_digest, self.metric_manifest_digest)
            ):
                raise LiveEvidenceValidationError(
                    "v2 PASS evidence requires plan, binding and metric manifest digests"
                )
        elif self.claim_eligible:
            raise LiveEvidenceValidationError("non-PASS evidence cannot be claim-eligible")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


def decode_live_evidence(document: object) -> LiveEvidenceReceipt:
    if not isinstance(document, dict):
        raise LiveEvidenceValidationError("live evidence document must be an object")
    base_expected = {
        "schema_version", "evidence_id", "status", "run_id", "source_tree_digest",
        "qualified_closure_digest", "t2b_gate_digest", "protocol_digest", "matrix_profile",
        "repetitions", "claim_eligible", "blockers",
    }
    v2_fields = {"plan_digest", "binding_digest", "metric_manifest_digest"}
    if set(document) not in (base_expected, base_expected | v2_fields):
        raise LiveEvidenceValidationError("live evidence fields are not exact")
    blockers = document["blockers"]
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise LiveEvidenceValidationError("live evidence blockers must be a string list")
    if type(document["repetitions"]) is not int or type(document["claim_eligible"]) is not bool:
        raise LiveEvidenceValidationError("live evidence repetitions/claim_eligible types are invalid")
    try:
        status = LiveEvidenceStatus(document["status"])
    except ValueError as exc:
        raise LiveEvidenceValidationError("live evidence status is unsupported") from exc
    return LiveEvidenceReceipt(
        schema_version=_required_text(document["schema_version"], "schema_version"),
        evidence_id=_required_text(document["evidence_id"], "evidence_id"),
        status=status,
        run_id=_required_text(document["run_id"], "run_id"),
        source_tree_digest=_required_text(document["source_tree_digest"], "source_tree_digest"),
        qualified_closure_digest=document["qualified_closure_digest"],
        t2b_gate_digest=document["t2b_gate_digest"],
        protocol_digest=_required_text(document["protocol_digest"], "protocol_digest"),
        matrix_profile=_required_text(document["matrix_profile"], "matrix_profile"),
        repetitions=document["repetitions"],
        claim_eligible=document["claim_eligible"],
        blockers=tuple(blockers),
        plan_digest=(document.get("plan_digest") if "plan_digest" in document else None),
        binding_digest=(document.get("binding_digest") if "binding_digest" in document else None),
        metric_manifest_digest=(
            document.get("metric_manifest_digest")
            if "metric_manifest_digest" in document
            else None
        ),
    )


def load_live_evidence(path: str | Path) -> LiveEvidenceReceipt:
    target = Path(path).expanduser().resolve(strict=False)
    if not target.is_file():
        raise LiveEvidenceValidationError(f"live evidence receipt is missing: {target}")
    try:
        document: JsonValue = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveEvidenceValidationError(f"live evidence receipt cannot be read: {target}") from exc
    return decode_live_evidence(document)


def validate_live_evidence(
    receipt: LiveEvidenceReceipt,
    *,
    expected_source_tree_digest: str | None = None,
    expected_protocol_digest: str | None = None,
    expected_plan_digest: str | None = None,
    expected_binding_digest: str | None = None,
    expected_metric_manifest_digest: str | None = None,
    require_claim_eligibility: bool = False,
) -> LiveEvidenceReceipt:
    if expected_source_tree_digest is not None and receipt.source_tree_digest != expected_source_tree_digest:
        raise LiveEvidenceValidationError("live evidence source tree digest does not match the checkout")
    for field, expected, actual in (
        ("protocol", expected_protocol_digest, receipt.protocol_digest),
        ("plan", expected_plan_digest, receipt.plan_digest),
        ("binding", expected_binding_digest, receipt.binding_digest),
        ("metric manifest", expected_metric_manifest_digest, receipt.metric_manifest_digest),
    ):
        if expected is not None and actual != expected:
            raise LiveEvidenceValidationError(f"live evidence {field} digest does not match the run")
    if require_claim_eligibility and not (
        receipt.status is LiveEvidenceStatus.PASS and receipt.claim_eligible
    ):
        raise LiveEvidenceValidationError(
            f"live evidence is not claim-eligible: status={receipt.status.value}"
        )
    return receipt


__all__ = [
    "LiveEvidenceReceipt", "LiveEvidenceStatus", "LiveEvidenceValidationError",
    "decode_live_evidence", "load_live_evidence", "validate_live_evidence",
]
