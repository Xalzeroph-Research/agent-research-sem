from __future__ import annotations

from .retrieval_features import lexical_features
from .serving import MemoryReadSnapshot, QueryPlanner


class LatestEvidenceQueryPlanner(QueryPlanner):
    """Minimal deterministic baseline selecting only the newest grounded evidence."""

    def plan(self, intent: str, snapshot: MemoryReadSnapshot, *, limit: int) -> tuple[str, ...]:
        del intent, limit
        latest = snapshot.latest_node_id()
        return () if latest is None else (latest,)


class HybridLexicalRecencyQueryPlanner(QueryPlanner):
    """Deterministic relevance-first retrieval with a planner-owned rebuildable index."""

    def __init__(self, *, max_nodes: int = 8) -> None:
        if max_nodes <= 0:
            raise ValueError("max_nodes must be positive")
        self.max_nodes = max_nodes
        self._features: dict[str, frozenset[str]] = {}
        self._sequences: dict[str, int] = {}
        self._postings: dict[str, list[str]] = {}
        self._indexed_count = 0
        self._indexed_prefix_digest = snapshot_empty_prefix_digest()

    def _reset(self) -> None:
        self._features.clear()
        self._sequences.clear()
        self._postings.clear()
        self._indexed_count = 0
        self._indexed_prefix_digest = snapshot_empty_prefix_digest()

    def _ensure_index(self, snapshot: MemoryReadSnapshot) -> None:
        if self._indexed_count > snapshot.node_count:
            self._reset()
        elif snapshot.prefix_digest(self._indexed_count) != self._indexed_prefix_digest:
            self._reset()

        for document in snapshot.iter_node_documents(self._indexed_count):
            features = lexical_features(document.text)
            self._features[document.node_id] = features
            self._sequences[document.node_id] = document.sequence
            for feature in features:
                self._postings.setdefault(feature, []).append(document.node_id)

        self._indexed_count = snapshot.node_count
        self._indexed_prefix_digest = snapshot.prefix_digest(self._indexed_count)

    def plan(self, intent: str, snapshot: MemoryReadSnapshot, *, limit: int) -> tuple[str, ...]:
        budget = min(limit, self.max_nodes)
        query = lexical_features(intent)
        if not query:
            return self._fallback(snapshot)
        self._ensure_index(snapshot)
        candidates: set[str] = set()
        for feature in query:
            candidates.update(self._postings.get(feature, ()))
        if not candidates:
            return self._fallback(snapshot)

        def rank(node_id: str) -> tuple[int, int, int, str]:
            features = self._features[node_id]
            overlap = len(query.intersection(features))
            sequence = self._sequences[node_id]
            return overlap, -len(features), sequence, node_id

        ordered = sorted(candidates, key=rank, reverse=True)
        return tuple(ordered[:budget])

    @staticmethod
    def _fallback(snapshot: MemoryReadSnapshot) -> tuple[str, ...]:
        latest = snapshot.latest_node_id()
        return () if latest is None else (latest,)


def snapshot_empty_prefix_digest() -> str:
    # Keep retrieval planner independent of a concrete evidence backend implementation.
    import hashlib
    return hashlib.sha256().hexdigest()


__all__ = ["HybridLexicalRecencyQueryPlanner", "LatestEvidenceQueryPlanner"]
