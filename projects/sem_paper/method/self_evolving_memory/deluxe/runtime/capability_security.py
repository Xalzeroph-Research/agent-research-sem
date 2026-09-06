from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Iterable

from ..api import CapabilityCard


@dataclass(frozen=True, slots=True)
class CapabilityToken:
    token_id: str
    role: str
    capability_ids: frozenset[str]


@dataclass(slots=True)
class CapabilityAuthorizer:
    """Optional role-scoped disclosure authorization from the legacy Deluxe path."""

    role_allowlist: dict[str, set[str]] = field(
        default_factory=lambda: {"executor": {"*"}, "meta": set(), "validator": set()}
    )

    def issue(self, *, role: str, cards: Iterable[CapabilityCard]) -> CapabilityToken:
        if not role.strip():
            raise ValueError("capability authorization role must be non-empty")
        allowed = self.role_allowlist.get(role, set())
        ids = frozenset(
            card.capability_id
            for card in cards
            if "*" in allowed or card.capability_id in allowed
        )
        raw = f"{role}|{'|'.join(sorted(ids))}".encode("utf-8")
        return CapabilityToken("ctok_" + hashlib.sha256(raw).hexdigest()[:12], role, ids)

    @staticmethod
    def authorize(token: CapabilityToken, capability_id: str) -> bool:
        return capability_id in token.capability_ids


__all__ = ["CapabilityAuthorizer", "CapabilityToken"]
