from __future__ import annotations

"""Matched SEM scientific estimands over typed study reports.

Durable auxiliary evidence lives in ``scientific_auxiliary`` and inferential
statistics live in ``scientific_statistics``. This module owns only estimand
aggregation and the small orchestration seam used by scientific closure.
"""

import math

from research_platform.platform.kernel import canonical_digest
from research_platform.experimentation.study.api import ExperimentPlan, StudyMatrixExecutionReport

from .metrics import SEM_PAPER_SCIENTIFIC_METRIC_NAMES
from .scientific_auxiliary import (
    SCIENTIFIC_AUXILIARY_METRIC_NAMES,
    SCIENTIFIC_AUXILIARY_SCHEMA_VERSION,
    SCIENTIFIC_AUXILIARY_SAMPLE_SCHEMA_VERSION,
    DirectoryScientificAuxiliarySampleStore,
    ScientificAuxiliaryEvidence,
    ScientificAuxiliaryEvidenceProducer,
    ScientificAuxiliarySample,
    ScientificAuxiliarySampleEvidence,
    decode_scientific_auxiliary_evidence,
    decode_scientific_auxiliary_sample_evidence,
    finalize_scientific_auxiliary_evidence,
    load_scientific_auxiliary_evidence,
    load_scientific_auxiliary_sample_evidence,
    validate_scientific_auxiliary_evidence,
)
from .scientific_metric_contracts import (
    ScientificMetricComputationError,
    ScientificMetricReport,
    ScientificStatisticalReport,
    StatisticalComparison,
)
from .scientific_statistics import (
    SemPaperScientificStatisticsProvider,
    provider_implementation,
)


class SemPaperScientificMetricProvider:
    def __init__(self, statistics: SemPaperScientificStatisticsProvider | None = None) -> None:
        self._statistics = statistics or SemPaperScientificStatisticsProvider()

    def compute(
        self,
        *,
        plan: ExperimentPlan,
        report: StudyMatrixExecutionReport,
        auxiliary_evidence: ScientificAuxiliaryEvidence | None = None,
    ) -> ScientificMetricReport:
        plan.assert_consistent()
        if report.plan_digest != plan.plan_digest:
            raise ScientificMetricComputationError("scientific metric report is not bound to the experiment plan")
        if report.protocol_digest != plan.protocol_digest:
            raise ScientificMetricComputationError("scientific metric report protocol digest mismatches the plan")

        bindings = {item.variant.variant_id: item for item in plan.bindings}
        seed_groups: dict[str, dict[str, str]] = {}
        for variant_id, binding in bindings.items():
            implementation = provider_implementation(binding.provider_id)
            if implementation not in {"FixedSeed", "SelfEvolve"}:
                continue
            seed_groups.setdefault(binding.seed_id, {})[implementation] = variant_id

        blockers: list[str] = []
        expected_seeds: set[str] = set()
        for seed_id, implementations in sorted(seed_groups.items()):
            if {"FixedSeed", "SelfEvolve"}.issubset(implementations):
                expected_seeds.add(seed_id)
            else:
                blockers.append(f"incomplete_fixed_self_pair:{seed_id}")

        # Build estimands from the same matched environment units used by the
        # inferential statistics.  Seed-C / Seed-X are matched architecture
        # factors inside each repetition, not independent lifetime units.
        observation_metrics: dict[tuple[str, int], dict[str, float]] = {}
        for observation in report.observations:
            key = (observation.assignment.variant_id, observation.assignment.repetition)
            if key in observation_metrics:
                blockers.append(
                    f"duplicate_metric_observation:{observation.assignment.variant_id}:"
                    f"{observation.assignment.repetition}"
                )
                continue
            observation_metrics[key] = dict(observation.metrics)

        matched_lifetime_deltas: list[float] = []
        matched_self_utilities: list[float] = []
        for repetition in range(plan.protocol.repetitions):
            seed_deltas: dict[str, float] = {}
            seed_self_utilities: dict[str, float] = {}
            for seed_id in sorted(expected_seeds):
                implementations = seed_groups[seed_id]
                fixed_metrics = observation_metrics.get((implementations["FixedSeed"], repetition))
                self_metrics = observation_metrics.get((implementations["SelfEvolve"], repetition))
                fixed = fixed_metrics.get("utility_mean") if fixed_metrics else None
                self_value = self_metrics.get("utility_mean") if self_metrics else None
                if fixed is None or self_value is None:
                    blockers.append(f"missing_utility_mean:{seed_id}:{repetition}")
                    continue
                if (
                    float(fixed_metrics.get("task_blocked_total", 0.0)) > 0
                    or float(self_metrics.get("task_blocked_total", 0.0)) > 0
                ):
                    blockers.append(f"blocked_fixed_self_pair:{seed_id}:{repetition}")
                    continue
                seed_deltas[seed_id] = float(self_value) - float(fixed)
                seed_self_utilities[seed_id] = float(self_value)

            if set(seed_deltas) != expected_seeds:
                blockers.append(
                    "incomplete_matched_environment_unit:FixedSeed:SelfEvolve:"
                    f"{repetition}:expected={','.join(sorted(expected_seeds))}:"
                    f"actual={','.join(sorted(seed_deltas))}"
                )
                continue
            if not expected_seeds:
                continue
            matched_lifetime_deltas.append(
                sum(seed_deltas[seed_id] for seed_id in sorted(expected_seeds))
                / len(expected_seeds)
            )
            matched_self_utilities.append(
                sum(seed_self_utilities[seed_id] for seed_id in sorted(expected_seeds))
                / len(expected_seeds)
            )

        values: dict[str, float] = {}
        if matched_lifetime_deltas:
            values["LTE_SR"] = sum(matched_lifetime_deltas) / len(matched_lifetime_deltas)
            values["CLU"] = sum(matched_self_utilities) / len(matched_self_utilities)
            # Frozen v0.16 definition: LPI = P(Delta_life > 0), not a mean
            # relative effect.  The empirical probability is over independent
            # pre-registered lifetime/environment units.
            values["LPI"] = (
                sum(1 for delta in matched_lifetime_deltas if delta > 0.0)
                / len(matched_lifetime_deltas)
            )

        if auxiliary_evidence is not None:
            if auxiliary_evidence.plan_digest != plan.plan_digest:
                blockers.append("auxiliary_evidence_plan_digest_mismatch")
            if auxiliary_evidence.protocol_digest != plan.protocol_digest:
                blockers.append("auxiliary_evidence_protocol_digest_mismatch")
            if auxiliary_evidence.binding_digest != plan.binding_digest:
                blockers.append("auxiliary_evidence_binding_digest_mismatch")
            for name, value in auxiliary_evidence.values:
                if not math.isfinite(float(value)):
                    blockers.append(f"non_finite_auxiliary_metric:{name}")
                else:
                    values[name] = float(value)

        missing = tuple(name for name in SEM_PAPER_SCIENTIFIC_METRIC_NAMES if name not in values)
        auxiliary_digest = auxiliary_evidence.digest if auxiliary_evidence is not None else None
        manifest_digest = canonical_digest(
            {
                "plan_digest": plan.plan_digest,
                "protocol_digest": plan.protocol_digest,
                "binding_digest": plan.binding_digest,
                "auxiliary_evidence_digest": auxiliary_digest,
                "values": tuple(sorted(values.items())),
                "missing": missing,
                "blockers": tuple(blockers),
            }
        )
        return ScientificMetricReport(
            plan_digest=plan.plan_digest,
            protocol_digest=plan.protocol_digest,
            metric_manifest_digest=manifest_digest,
            values=tuple(sorted(values.items())),
            missing=missing,
            blockers=tuple(blockers),
            auxiliary_evidence_digest=auxiliary_digest,
        )

    def compute_statistics(
        self,
        *,
        plan: ExperimentPlan,
        report: StudyMatrixExecutionReport,
    ) -> ScientificStatisticalReport:
        return self._statistics.compute(plan=plan, report=report)


__all__ = [
    "SCIENTIFIC_AUXILIARY_METRIC_NAMES",
    "SCIENTIFIC_AUXILIARY_SCHEMA_VERSION",
    "SCIENTIFIC_AUXILIARY_SAMPLE_SCHEMA_VERSION",
    "DirectoryScientificAuxiliarySampleStore",
    "ScientificAuxiliaryEvidence",
    "ScientificAuxiliaryEvidenceProducer",
    "ScientificAuxiliarySample",
    "ScientificAuxiliarySampleEvidence",
    "ScientificMetricComputationError",
    "ScientificMetricReport",
    "ScientificStatisticalReport",
    "StatisticalComparison",
    "SemPaperScientificMetricProvider",
    "decode_scientific_auxiliary_evidence",
    "decode_scientific_auxiliary_sample_evidence",
    "finalize_scientific_auxiliary_evidence",
    "load_scientific_auxiliary_evidence",
    "load_scientific_auxiliary_sample_evidence",
    "validate_scientific_auxiliary_evidence",
]
