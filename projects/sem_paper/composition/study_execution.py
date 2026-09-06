from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from research_platform.environment.minecraft.api import MinecraftWorldCut, MinecraftWorldCutPort
from research_platform.experimentation.evaluation.api import BranchReceipt
from research_platform.experimentation.study.api import (
    StudyAssignment,
    StudyExecutionUnit,
    StudyMetricObservation,
    StudyProtocol,
    StudyUnitExecutionPort,
    VariantKind,
    VariantBinding,
)
from research_platform.platform.kernel import ExecutionContext

from projects.sem_paper.method.self_evolving_memory.evolution import (
    BranchRole,
    CandidateArchitecture,
    PairedBranchEvaluator,
)

from .minecraft_branch import MinecraftPairedBranchRunner
from .minecraft_workload_executor import MinecraftWorkloadBranchExecutor
from .candidate_method import (
    CandidateArchitectureResolverPort,
    build_seed_candidate,
    is_fixed_provider,
)


class SemPaperStudyUnitError(RuntimeError):
    """A project study unit cannot be represented by the bound adapter."""


class MinecraftSourceCutPublicationPort(Protocol):
    """Persist a source-cut descriptor before either paired branch starts."""

    def source_cut_published(self, *, repetition: int, cut: MinecraftWorldCut) -> None: ...


def _paired_assignments(
    protocol: StudyProtocol,
    unit: StudyExecutionUnit,
) -> tuple[StudyAssignment, StudyAssignment]:
    if unit.study_id != protocol.study_id:
        raise SemPaperStudyUnitError("study unit belongs to another study")
    if len(unit.assignments) != 2:
        raise SemPaperStudyUnitError(
            "the current SEM paired adapter requires exactly one control and one treatment assignment"
        )
    by_kind: dict[VariantKind, StudyAssignment] = {}
    variant_by_id = {item.variant_id: item for item in protocol.variants}
    for assignment in unit.assignments:
        variant = variant_by_id.get(assignment.variant_id)
        if variant is None:
            raise SemPaperStudyUnitError("study unit references an undeclared variant")
        if variant.kind in by_kind:
            raise SemPaperStudyUnitError(
                f"the current SEM paired adapter cannot represent two {variant.kind.value} variants"
            )
        by_kind[variant.kind] = assignment
    if set(by_kind) != {VariantKind.CONTROL, VariantKind.TREATMENT}:
        raise SemPaperStudyUnitError(
            "the current SEM paired adapter requires one control and one treatment variant"
        )
    return by_kind[VariantKind.CONTROL], by_kind[VariantKind.TREATMENT]


def _receipt_observation(
    assignment: StudyAssignment,
    receipt: BranchReceipt,
    protocol: StudyProtocol,
) -> StudyMetricObservation:
    metrics = dict(receipt.metrics)
    values: list[tuple[str, float]] = []
    for name in protocol.metric_names:
        if name not in metrics:
            raise SemPaperStudyUnitError(
                f"branch receipt is missing declared study metric: {name}"
            )
        values.append((name, float(metrics[name])))
    return StudyMetricObservation(assignment, tuple(values))


@dataclass(frozen=True, slots=True)
class SemPaperMinecraftStudyUnitAdapter(StudyUnitExecutionPort):
    """Run one complete SEM paired unit through a fresh MC source cut.

    The adapter owns only MC realization.  Assignment completeness, repetition
    grouping and aggregate computation remain in ``StudyMatrixExecutor``.
    """

    protocol: StudyProtocol
    candidate: CandidateArchitecture
    world_cuts: MinecraftWorldCutPort
    workload_executor: MinecraftWorkloadBranchExecutor
    session_id: str
    context: ExecutionContext | None
    branch_id_factory: Callable[[BranchRole, int], str]
    destination_factory: Callable[[str], str]
    source_cuts: Mapping[int, MinecraftWorldCut] = field(default_factory=dict)
    source_cut_publication: MinecraftSourceCutPublicationPort | None = None
    candidate_factory: CandidateArchitectureResolverPort | None = None

    def __post_init__(self) -> None:
        normalized = dict(self.source_cuts)
        if any(
            isinstance(repetition, bool)
            or not isinstance(repetition, int)
            or repetition < 0
            or repetition >= self.protocol.repetitions
            or not isinstance(cut, MinecraftWorldCut)
            for repetition, cut in normalized.items()
        ):
            raise ValueError("Minecraft resume source cuts do not match the study repetitions")
        object.__setattr__(self, "source_cuts", MappingProxyType(normalized))

    def execute(self, unit: StudyExecutionUnit) -> tuple[StudyMetricObservation, ...]:
        control_assignment, treatment_assignment = _paired_assignments(self.protocol, unit)
        runner = MinecraftPairedBranchRunner(
            world_cuts=self.world_cuts,
            executor=self.workload_executor,
            session_id=f"{self.session_id}:rep-{unit.repetition}",
            context=self.context,
            branch_id_factory=lambda role: self.branch_id_factory(role, unit.repetition),
            destination_factory=self.destination_factory,
        )
        cut = self.source_cuts.get(unit.repetition)
        if cut is None:
            cut = runner.prepare_source_cut()
        else:
            runner.bind_source_cut(cut)
        if self.source_cut_publication is not None:
            self.source_cut_publication.source_cut_published(
                repetition=unit.repetition,
                cut=cut,
            )
        evaluation = PairedBranchEvaluator(runner).evaluate_with_receipts(self.candidate)
        if not evaluation.proof.comparability.valid:
            raise SemPaperStudyUnitError(
                f"Minecraft study unit comparability proof failed: repetition={unit.repetition}"
            )
        return (
            _receipt_observation(control_assignment, evaluation.control, self.protocol),
            _receipt_observation(treatment_assignment, evaluation.candidate, self.protocol),
        )

    def execute_bound(
        self,
        unit: StudyExecutionUnit,
        bindings: tuple[VariantBinding, ...],
        plan_digest: str,
    ) -> tuple[StudyMetricObservation, ...]:
        """Execute all compiled arms from one immutable source world cut."""

        if len(plan_digest) != 64:
            raise SemPaperStudyUnitError("compiled study execution requires a plan digest")
        by_id = {item.variant.variant_id: item for item in bindings}
        if set(by_id) != {item.variant_id for item in unit.assignments}:
            raise SemPaperStudyUnitError("compiled study unit bindings do not cover every assignment")
        source_cut: MinecraftWorldCut | None = None
        observations: list[StudyMetricObservation] = []
        for assignment in unit.assignments:
            binding = by_id[assignment.variant_id]
            role = (
                BranchRole.CONTROL
                if is_fixed_provider(binding.provider_id)
                else BranchRole.CANDIDATE
            )
            candidate = (
                None
                if role is BranchRole.CONTROL
                else (
                    self.candidate_factory(binding)
                    if self.candidate_factory is not None
                    else build_seed_candidate(binding.seed_id)
                )
            )
            runner = MinecraftPairedBranchRunner(
                world_cuts=self.world_cuts,
                executor=self.workload_executor,
                session_id=f"{self.session_id}:rep-{unit.repetition}:{assignment.variant_id}",
                context=self.context,
                branch_id_factory=lambda selected_role, variant_id=assignment.variant_id: (
                    f"{self.branch_id_factory(selected_role, unit.repetition)}:{variant_id}"
                ),
                destination_factory=self.destination_factory,
            )
            if source_cut is None:
                source_cut = runner.prepare_source_cut()
                if self.source_cut_publication is not None:
                    self.source_cut_publication.source_cut_published(
                        repetition=unit.repetition,
                        cut=source_cut,
                    )
            else:
                runner.bind_source_cut(source_cut)
            receipt = runner.run(
                role=role,
                candidate=candidate,
                variant_binding=binding,
            )
            observations.append(_receipt_observation(assignment, receipt, self.protocol))
        return tuple(observations)


__all__ = [
    "MinecraftSourceCutPublicationPort",
    "SemPaperMinecraftStudyUnitAdapter",
    "SemPaperStudyUnitError",
]
