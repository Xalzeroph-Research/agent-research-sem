from __future__ import annotations

"""Crash-resume composition for the SEM Minecraft experiment.

The entrypoint supplies artifact storage; this module owns the validated
scientific identity and the source-cut/checkpoint join.  It deliberately does
not start servers or execute workloads.
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import threading
from typing import Mapping, Protocol

from projects.sem_paper.method.self_evolving_memory.evolution import BranchRole
from research_platform.environment.minecraft.api import MinecraftWorldCut
from research_platform.experimentation.checkpoint.api import WorkloadCheckpointManifest
from research_platform.experimentation.run.api import RunArtifactKind
from research_platform.platform.kernel import JsonValue


class ExperimentConfigurationError(ValueError):
    """The live experiment inputs are incomplete or inconsistent."""


class MinecraftResumeArtifactPort(Protocol):
    """Minimal artifact publication seam required by the resume index."""

    def publish_json(
        self,
        name: str,
        payload: Mapping[str, JsonValue],
        *,
        kind: RunArtifactKind,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class MinecraftResumeIdentity:
    run_id: str
    study_id: str
    run_spec_digest: str
    protocol_digest: str
    task_manifest_digest: str
    candidate_digest: str
    repetitions: int

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.study_id.strip():
            raise ValueError("Minecraft resume identity is incomplete")
        for name in (
            "run_spec_digest",
            "protocol_digest",
            "task_manifest_digest",
            "candidate_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError(f"Minecraft resume {name} must be lowercase SHA-256")
        if type(self.repetitions) is not int or self.repetitions <= 0:
            raise ValueError("Minecraft resume repetitions must be a positive integer")


class MinecraftResumeIndex:
    """Crash-durable pointers joining source cuts to task-boundary checkpoints."""

    _SCHEMA = "sem-paper.minecraft-resume-index.v1"
    _BRANCH_ROLES = frozenset({BranchRole.CONTROL.value, BranchRole.CANDIDATE.value})
    _VARIANT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(
        self,
        *,
        artifacts: MinecraftResumeArtifactPort,
        identity: MinecraftResumeIdentity,
        source_cuts: Mapping[int, MinecraftWorldCut] | None = None,
        branch_checkpoints: Mapping[str, str] | None = None,
    ) -> None:
        self._artifacts = artifacts
        self.identity = identity
        self._source_cuts = dict(source_cuts or {})
        self._branch_checkpoints = dict(branch_checkpoints or {})
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        *,
        artifacts: MinecraftResumeArtifactPort,
        identity: MinecraftResumeIdentity,
        path: Path | None,
    ) -> "MinecraftResumeIndex":
        if path is None:
            return cls(artifacts=artifacts, identity=identity)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, Mapping):
                raise TypeError("resume index root must be a mapping")
            if set(document) != {
                "schema_version",
                "identity",
                "source_cuts",
                "branch_checkpoints",
            }:
                raise ValueError("resume index root schema mismatch")
            if document["schema_version"] != cls._SCHEMA:
                raise ValueError("unsupported resume index schema")
            identity_raw = document["identity"]
            if not isinstance(identity_raw, Mapping) or dict(identity_raw) != asdict(identity):
                raise ValueError("resume index scientific identity mismatch")
            cuts_raw = document["source_cuts"]
            checkpoints_raw = document["branch_checkpoints"]
            if not isinstance(cuts_raw, Mapping) or not isinstance(checkpoints_raw, Mapping):
                raise TypeError("resume index cut/checkpoint maps are invalid")
            source_cuts: dict[int, MinecraftWorldCut] = {}
            for repetition_text, raw in cuts_raw.items():
                if not isinstance(raw, Mapping):
                    raise TypeError("resume index source cut row is invalid")
                repetition = int(repetition_text)
                if repetition < 0 or repetition >= identity.repetitions:
                    raise ValueError("resume index repetition is outside the study")
                if repetition in source_cuts:
                    raise ValueError("resume index contains duplicate repetition keys")
                source_cuts[repetition] = MinecraftWorldCut(**dict(raw))
            branch_checkpoints: dict[str, str] = {}
            for branch_id, checkpoint_id in checkpoints_raw.items():
                if (
                    not isinstance(branch_id, str)
                    or not branch_id.strip()
                    or not isinstance(checkpoint_id, str)
                    or not checkpoint_id.strip()
                ):
                    raise ValueError("resume index checkpoint identity is invalid")
                repetition = cls._branch_repetition(identity, branch_id)
                if repetition is None:
                    raise ValueError("resume index contains an undeclared study branch")
                branch_checkpoints[branch_id] = checkpoint_id
            if any(
                cls._branch_repetition(identity, branch_id) not in source_cuts
                for branch_id in branch_checkpoints
            ):
                raise ValueError("resume checkpoint has no persisted source cut")
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            raise ExperimentConfigurationError(f"resume index is invalid: {exc}") from exc
        return cls(
            artifacts=artifacts,
            identity=identity,
            source_cuts=source_cuts,
            branch_checkpoints=branch_checkpoints,
        )

    @property
    def source_cuts(self) -> dict[int, MinecraftWorldCut]:
        return dict(self._source_cuts)

    @property
    def branch_checkpoints(self) -> dict[str, str]:
        return dict(self._branch_checkpoints)

    def _publish_state(
        self,
        source_cuts: Mapping[int, MinecraftWorldCut],
        branch_checkpoints: Mapping[str, str],
    ) -> None:
        """Durably publish one complete candidate index before memory commit."""

        self._artifacts.publish_json(
            "resume_index.json",
            {
                "schema_version": self._SCHEMA,
                "identity": asdict(self.identity),
                "source_cuts": {
                    str(repetition): asdict(cut)
                    for repetition, cut in sorted(source_cuts.items())
                },
                "branch_checkpoints": dict(sorted(branch_checkpoints.items())),
            },
            kind=RunArtifactKind.CHECKPOINT,
        )

    def persist(self) -> None:
        """Publish the validated recovery topology before live execution starts."""

        with self._lock:
            self._publish_state(self._source_cuts, self._branch_checkpoints)

    def source_cut_published(self, *, repetition: int, cut: MinecraftWorldCut) -> None:
        if repetition < 0 or repetition >= self.identity.repetitions:
            raise ValueError("published source cut repetition is outside the study")
        if not isinstance(cut, MinecraftWorldCut):
            raise TypeError("published source cut has an invalid contract")
        with self._lock:
            current = self._source_cuts.get(repetition)
            if current is not None and current != cut:
                raise ValueError("published source cut drifted for a frozen repetition")
            candidate_source_cuts = dict(self._source_cuts)
            candidate_source_cuts[repetition] = cut
            self._publish_state(candidate_source_cuts, self._branch_checkpoints)
            self._source_cuts = candidate_source_cuts

    def published(self, manifest: WorkloadCheckpointManifest) -> None:
        expected = (
            self.identity.run_id,
            self.identity.study_id,
            self.identity.task_manifest_digest,
        )
        actual = (manifest.run_id, manifest.study_id, manifest.task_manifest_digest)
        if actual != expected:
            raise ValueError("published workload checkpoint does not match resume identity")
        with self._lock:
            repetition = self._branch_repetition(self.identity, manifest.branch_id)
            if repetition is None:
                raise ValueError("published checkpoint belongs to an undeclared study branch")
            source_cut = self._source_cuts.get(repetition)
            if source_cut is None or source_cut.cut_id != manifest.source_cut_id:
                raise ValueError("published checkpoint does not match its persisted source cut")
            candidate_checkpoints = dict(self._branch_checkpoints)
            candidate_checkpoints[manifest.branch_id] = manifest.checkpoint_id
            self._publish_state(self._source_cuts, candidate_checkpoints)
            self._branch_checkpoints = candidate_checkpoints

    @classmethod
    def _branch_repetition(
        cls,
        identity: MinecraftResumeIdentity,
        branch_id: str,
    ) -> int | None:
        """Validate a base or compiled-variant branch identity.

        The generic paired adapter uses ``run:role:rep-N`` while compiled
        Core-6 arms use ``run:role:rep-N:variant-id``.  The resume index must
        accept both forms without becoming a free-form string map.
        """

        prefix = f"{identity.run_id}:"
        if not branch_id.startswith(prefix):
            return None
        parts = branch_id[len(prefix) :].split(":")
        if len(parts) not in (2, 3) or parts[0] not in cls._BRANCH_ROLES:
            return None
        repetition_text = parts[1]
        if not repetition_text.startswith("rep-"):
            return None
        try:
            repetition = int(repetition_text[4:])
        except ValueError:
            return None
        if not 0 <= repetition < identity.repetitions:
            return None
        if len(parts) == 3 and cls._VARIANT_ID.fullmatch(parts[2]) is None:
            return None
        return repetition


__all__ = [
    "ExperimentConfigurationError",
    "MinecraftResumeArtifactPort",
    "MinecraftResumeIdentity",
    "MinecraftResumeIndex",
]
