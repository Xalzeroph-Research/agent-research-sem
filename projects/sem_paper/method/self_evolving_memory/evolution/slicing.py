from __future__ import annotations

"""Ontology-neutral incident slicing policy over immutable telemetry facts."""

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Sequence

from .telemetry import MemoryIncident

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text)}


@dataclass(frozen=True, slots=True)
class NeutralSlice:
    slice_id: str
    support: int
    incident_ids: tuple[str, ...]
    examples: tuple[str, ...]
    shared_tokens: tuple[str, ...]


class AutomaticSliceDiscovery:
    """Ontology-free incident slices; no node/edit recommendation is emitted."""

    def discover(
        self,
        incidents: Sequence[MemoryIncident],
        *,
        max_slices: int = 8,
        threshold: float = 0.30,
    ) -> tuple[NeutralSlice, ...]:
        if max_slices <= 0 or not 0.0 <= threshold <= 1.0:
            raise ValueError("neutral slice limits are invalid")
        clusters: list[dict[str, Any]] = []
        for incident in incidents:
            tokens = _tokens(incident.intent)
            best_index: int | None = None
            best_score = 0.0
            for index, cluster in enumerate(clusters):
                union = cluster["union"]
                score = len(tokens & union) / max(1, len(tokens | union))
                if score > best_score:
                    best_score, best_index = score, index
            if best_index is None or best_score < threshold:
                if len(clusters) >= max_slices:
                    continue
                clusters.append({"union": set(tokens), "intersection": set(tokens), "items": [incident]})
            else:
                cluster = clusters[best_index]
                cluster["union"].update(tokens)
                cluster["intersection"].intersection_update(tokens)
                cluster["items"].append(incident)
        slices: list[NeutralSlice] = []
        for cluster in clusters:
            items = cluster["items"]
            material = "|".join(incident.incident_id for incident in items).encode("utf-8")
            slices.append(
                NeutralSlice(
                    slice_id="slice_" + hashlib.sha256(material).hexdigest()[:12],
                    support=len(items),
                    incident_ids=tuple(incident.incident_id for incident in items[:12]),
                    examples=tuple(incident.intent for incident in items[:4]),
                    shared_tokens=tuple(sorted(cluster["intersection"])[:12]),
                )
            )
        return tuple(sorted(slices, key=lambda item: (-item.support, item.slice_id)))
