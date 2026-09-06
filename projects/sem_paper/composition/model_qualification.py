from __future__ import annotations


class SemPaperModelQualificationError(ValueError):
    """The platform model-qualification handoff is not claim-eligible for SEM."""


_CANARY_REQUEST_IDENTITY_FIELDS = frozenset({"probe_digest", "request_body_digest"})
_CANARY_BINDING_IDENTITY_FIELDS = (
    "runtime_canary_evidence_digests",
    "runtime_canary_digest",
    "canary_evidence_digests",
    "canary_closure_digest",
)


def platform_canary_provenance_contract_ready() -> bool:
    """Return whether the installed platform exposes reconstructable canary provenance."""

    try:
        from research_platform.model.serving.api import RuntimeCanaryEvidence
        from research_platform.model.serving.endpoint.api import QualifiedModelEndpointBinding
    except (ImportError, AttributeError):
        return False
    canary_fields = set(getattr(RuntimeCanaryEvidence, "__dataclass_fields__", {}))
    binding_fields = set(getattr(QualifiedModelEndpointBinding, "__dataclass_fields__", {}))
    return bool(_CANARY_REQUEST_IDENTITY_FIELDS & canary_fields) and bool(
        set(_CANARY_BINDING_IDENTITY_FIELDS) & binding_fields
    )


def _require_digest(value: object, field: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise SemPaperModelQualificationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def qualified_binding_canary_evidence_digests(binding: object) -> tuple[str, ...]:
    """Extract the content-derived canary authority carried by one platform binding."""

    for field in _CANARY_BINDING_IDENTITY_FIELDS:
        value = getattr(binding, field, None)
        if value is None:
            continue
        if isinstance(value, str):
            raw = (value,)
        elif isinstance(value, (tuple, list)):
            raw = tuple(value)
        else:
            raise SemPaperModelQualificationError(
                f"qualified model binding {field} has an invalid type"
            )
        if not raw:
            continue
        digests = tuple(sorted(_require_digest(item, field) for item in raw))
        if len(digests) != len(set(digests)):
            raise SemPaperModelQualificationError(
                "qualified model binding contains duplicate runtime canary identities"
            )
        return digests
    raise SemPaperModelQualificationError(
        "qualified model binding does not carry runtime canary evidence identity"
    )



__all__ = [
    "SemPaperModelQualificationError",
    "platform_canary_provenance_contract_ready",
    "qualified_binding_canary_evidence_digests",
]
