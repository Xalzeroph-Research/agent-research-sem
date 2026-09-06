from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol
import math

from research_platform.environment.minecraft.api import MinecraftWorldBranch, MinecraftWorldCut, MinecraftWorldCutPort
from research_platform.platform.kernel import ExecutionContext
from research_platform.experimentation.evaluation.api import BranchReceipt
from research_platform.experimentation.study.api import VariantBinding

from projects.sem_paper.method.self_evolving_memory.evolution import (
    BranchRole,
    BranchRunnerPort,
    CandidateArchitecture,
)


class MinecraftBranchExecutionError(RuntimeError):
    """A branch workload or its mandatory cleanup failed."""

    def __init__(self, phase: str, cause: BaseException, cleanup_cause: BaseException | None = None) -> None:
        message = f"Minecraft branch {phase} failed"
        detail = str(cause).strip()
        if detail:
            message += f": {detail}"
        if cleanup_cause is not None:
            message += " with cleanup failure"
            cleanup_detail = str(cleanup_cause).strip()
            if cleanup_detail:
                message += f": {cleanup_detail}"
        super().__init__(message)
        self.phase = phase
        self.cause = cause
        self.cleanup_cause = cleanup_cause


@dataclass(frozen=True, slots=True)
class MinecraftBranchExecutionResult:
    """Project workload facts, separate from environment and method stores."""

    workload_id: str
    environment_generation: str
    task_manifest_digest: str
    metrics: tuple[tuple[str, float], ...]
    branch_writes: tuple[str, ...] = ()
    lifetime_writes: tuple[str, ...] = ()
    private_to_method_flows: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (self.workload_id, self.environment_generation, self.task_manifest_digest)
        if any(not value.strip() for value in required):
            raise ValueError("Minecraft branch execution identity is incomplete")
        names: set[str] = set()
        for name, value in self.metrics:
            if not name.strip() or name in names:
                raise ValueError("Minecraft branch metrics must have unique non-empty names")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"Minecraft branch metric is not finite: {name}")
            names.add(name)


class MinecraftBranchExecutorPort(Protocol):
    """Composition seam that binds service, participant, method and workload."""

    def execute(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        branch: MinecraftWorldBranch,
        variant_binding: VariantBinding | None = None,
    ) -> MinecraftBranchExecutionResult: ...


class MinecraftPairedBranchRunner(BranchRunnerPort):
    """Run paired branches from one explicitly prepared Minecraft world cut.

    The runner owns branch identity and world-cut cleanup only. The injected
    executor owns generic service lifecycle, Mineflayer session binding,
    project method binding and workload execution. No Minecraft provider knows
    about Deluxe or candidate acceptance.
    """

    def __init__(
        self,
        *,
        world_cuts: MinecraftWorldCutPort,
        executor: MinecraftBranchExecutorPort,
        session_id: str,
        context: ExecutionContext | None,
        branch_id_factory: Callable[[BranchRole], str],
        destination_factory: Callable[[str], str],
    ) -> None:
        if not session_id.strip():
            raise ValueError("Minecraft paired branch session_id is required")
        self.world_cuts = world_cuts
        self.executor = executor
        self.session_id = session_id
        self.context = context
        self.branch_id_factory = branch_id_factory
        self.destination_factory = destination_factory
        self._cut: MinecraftWorldCut | None = None

    def prepare_source_cut(self) -> MinecraftWorldCut:
        if self._cut is not None:
            raise MinecraftBranchExecutionError("prepare", RuntimeError("source cut is already prepared"))
        try:
            cut = self.world_cuts.capture(session_id=self.session_id, context=self.context)
        except Exception as exc:
            raise MinecraftBranchExecutionError("capture", exc) from exc
        self._cut = cut
        return cut

    def bind_source_cut(self, cut: MinecraftWorldCut) -> MinecraftWorldCut:
        """Bind a previously persisted cut for exact workload resume."""

        if self._cut is not None:
            raise MinecraftBranchExecutionError(
                "prepare",
                RuntimeError("source cut is already prepared"),
            )
        if not isinstance(cut, MinecraftWorldCut):
            raise MinecraftBranchExecutionError(
                "prepare",
                TypeError("resume source cut has an invalid contract"),
            )
        self._cut = cut
        return cut

    def run(
        self,
        *,
        role: BranchRole,
        candidate: CandidateArchitecture | None,
        variant_binding: VariantBinding | None = None,
    ) -> BranchReceipt:
        cut = self._cut
        if cut is None:
            raise MinecraftBranchExecutionError("prepare", RuntimeError("source cut is not prepared"))
        if role is BranchRole.CONTROL and candidate is not None:
            raise MinecraftBranchExecutionError("validate", ValueError("control branch cannot receive a candidate"))
        if role is BranchRole.CANDIDATE and candidate is None:
            raise MinecraftBranchExecutionError("validate", ValueError("candidate branch requires a candidate"))

        branch_id = self.branch_id_factory(role)
        destination = self.destination_factory(branch_id)
        if not branch_id.strip() or not destination.strip():
            raise MinecraftBranchExecutionError("identity", ValueError("branch identity is incomplete"))
        try:
            branch = self.world_cuts.materialize_branch(
                cut,
                branch_id=branch_id,
                destination_workdir=destination,
            )
        except Exception as exc:
            raise MinecraftBranchExecutionError("materialize", exc) from exc

        result: MinecraftBranchExecutionResult | None = None
        primary_error: BaseException | None = None
        try:
            if variant_binding is None:
                result = self.executor.execute(
                    role=role,
                    candidate=candidate,
                    branch=branch,
                )
            else:
                result = self.executor.execute(
                    role=role,
                    candidate=candidate,
                    branch=branch,
                    variant_binding=variant_binding,
                )
        except BaseException as exc:
            primary_error = exc

        cleanup_error: BaseException | None = None
        try:
            self.world_cuts.release_branch(branch)
        except BaseException as exc:
            cleanup_error = exc

        if primary_error is not None:
            if cleanup_error is not None:
                raise MinecraftBranchExecutionError("execute", primary_error, cleanup_error) from primary_error
            raise MinecraftBranchExecutionError("execute", primary_error) from primary_error
        if cleanup_error is not None:
            raise MinecraftBranchExecutionError("cleanup", cleanup_error) from cleanup_error
        if result is None:
            raise MinecraftBranchExecutionError("execute", RuntimeError("branch executor returned no result"))
        return BranchReceipt(
            branch_id=branch.branch_id,
            source_checkpoint_id=cut.cut_id,
            workload_id=result.workload_id,
            environment_generation=result.environment_generation,
            task_manifest_digest=result.task_manifest_digest,
            branch_writes=result.branch_writes,
            lifetime_writes=result.lifetime_writes,
            private_to_method_flows=result.private_to_method_flows,
            metrics=result.metrics,
        )


__all__ = [
    "MinecraftBranchExecutionError",
    "MinecraftBranchExecutionResult",
    "MinecraftBranchExecutorPort",
    "MinecraftPairedBranchRunner",
]
