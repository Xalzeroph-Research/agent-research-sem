from __future__ import annotations

"""Pure statistical inference over immutable study reports; no evidence I/O."""

from dataclasses import replace
import math

from research_platform.experimentation.study.api import ExperimentPlan, StudyMatrixExecutionReport

from .scientific_metric_contracts import (
    ScientificMetricComputationError,
    ScientificStatisticalReport,
    StatisticalComparison,
)


def provider_implementation(provider_id: str) -> str:
    value = provider_id.rsplit(".", 1)[-1]
    return {
        "fixed-memory": "FixedSeed",
        "candidate-memory": "RuleBasedEvolver",
    }.get(value, value)


class SemPaperScientificStatisticsProvider:
    def compute(
        self,
        *,
        plan: ExperimentPlan,
        report: StudyMatrixExecutionReport,
    ) -> ScientificStatisticalReport:
        """Compute complete-case paired effects for every declared Core-6 arm pair.

        Primary LTE_SR remains the Self-vs-Fixed comparison. Rule-based arms are
        retained as explicit secondary comparisons and all pairwise p-values
        receive Holm adjustment; no arm is collapsed by ``VariantKind``.
        """

        plan.assert_consistent()
        if report.plan_digest != plan.plan_digest:
            raise ScientificMetricComputationError("statistical report is not bound to the experiment plan")
        if report.protocol_digest != plan.protocol_digest:
            raise ScientificMetricComputationError("statistical report protocol digest mismatches the plan")
        bindings = {item.variant.variant_id: item for item in plan.bindings}
        groups: dict[str, dict[str, str]] = {}
        for variant_id, binding in bindings.items():
            implementation = provider_implementation(binding.provider_id)
            if implementation in {"FixedSeed", "RuleBasedEvolver", "SelfEvolve"}:
                groups.setdefault(binding.seed_id, {})[implementation] = variant_id
        observations = {
            (item.assignment.variant_id, item.assignment.repetition): dict(item.metrics)
            for item in report.observations
        }
        # Repetition/environment-unit is the independent statistical unit.
        # Seed-C and Seed-X are matched factors *within* that unit and must be
        # averaged before variance/SE/CI/p-value estimation.  Pooling the two
        # seed deltas would pseudoreplicate N (e.g. 12 repetitions -> 24).
        seed_pair_values: dict[
            tuple[str, str], dict[int, dict[str, float]]
        ] = {}
        blockers: list[str] = []
        for seed_id, variants in sorted(groups.items()):
            implementations = tuple(
                name for name in ("FixedSeed", "RuleBasedEvolver", "SelfEvolve") if name in variants
            )
            for reference_index, reference in enumerate(implementations):
                for treatment in implementations[reference_index + 1 :]:
                    by_repetition = seed_pair_values.setdefault(
                        (treatment, reference), {}
                    )
                    for repetition in range(plan.protocol.repetitions):
                        reference_metrics = observations.get((variants[reference], repetition))
                        treatment_metrics = observations.get((variants[treatment], repetition))
                        reference_utility = reference_metrics.get("utility_mean") if reference_metrics else None
                        treatment_utility = treatment_metrics.get("utility_mean") if treatment_metrics else None
                        if reference_utility is None or treatment_utility is None:
                            blockers.append(f"missing_paired_observation:{seed_id}:{reference}:{treatment}:{repetition}")
                            continue
                        if (
                            float(reference_metrics.get("task_blocked_total", 0.0)) > 0
                            or float(treatment_metrics.get("task_blocked_total", 0.0)) > 0
                        ):
                            blockers.append(f"blocked_paired_observation:{seed_id}:{reference}:{treatment}:{repetition}")
                            continue
                        by_repetition.setdefault(repetition, {})[seed_id] = (
                            float(treatment_utility) - float(reference_utility)
                        )

        pair_values: dict[tuple[str, str], list[float]] = {}
        for pair, by_repetition in sorted(seed_pair_values.items()):
            treatment, reference = pair
            expected_seeds = {
                seed_id
                for seed_id, variants in groups.items()
                if treatment in variants and reference in variants
            }
            unit_values: list[float] = []
            for repetition in range(plan.protocol.repetitions):
                seed_values = by_repetition.get(repetition, {})
                if set(seed_values) != expected_seeds:
                    blockers.append(
                        "incomplete_matched_environment_unit:"
                        f"{reference}:{treatment}:{repetition}:"
                        f"expected={','.join(sorted(expected_seeds))}:"
                        f"actual={','.join(sorted(seed_values))}"
                    )
                    continue
                unit_values.append(
                    sum(seed_values[seed_id] for seed_id in sorted(expected_seeds))
                    / len(expected_seeds)
                )
            pair_values[pair] = unit_values

        missing: list[str] = []
        if not pair_values or not pair_values.get(("SelfEvolve", "FixedSeed")):
            missing.extend(("paired_effect", "paired_effect_ci"))

        raw_comparisons: list[StatisticalComparison] = []
        for (treatment, reference), values in sorted(pair_values.items()):
            if not values:
                continue
            count = len(values)
            estimate = sum(values) / count
            variance = sum((value - estimate) ** 2 for value in values) / (count - 1) if count > 1 else 0.0
            standard_error = math.sqrt(variance / count)
            margin = 1.96 * standard_error
            if standard_error <= 1e-12:
                raw_p = 0.0 if abs(estimate) > 1e-12 else 1.0
            else:
                raw_p = math.erfc(abs(estimate / standard_error) / math.sqrt(2.0))
            raw_comparisons.append(
                StatisticalComparison(
                    comparison_id=f"{treatment}_vs_{reference}",
                    treatment_provider=treatment,
                    reference_provider=reference,
                    estimate=estimate,
                    sample_count=count,
                    standard_error=standard_error,
                    ci_lower=estimate - margin,
                    ci_upper=estimate + margin,
                    raw_p_value=min(1.0, max(0.0, raw_p)),
                    adjusted_p_value=0.0,
                    correction_method="holm_bonferroni",
                )
            )

        ordered = sorted(enumerate(raw_comparisons), key=lambda item: item[1].raw_p_value)
        adjusted: dict[int, float] = {}
        previous = 0.0
        count_comparisons = len(ordered)
        for rank, (index, comparison) in enumerate(ordered):
            value = min(1.0, comparison.raw_p_value * (count_comparisons - rank))
            previous = max(previous, value)
            adjusted[index] = previous
        comparisons = tuple(
            replace(comparison, adjusted_p_value=adjusted[index])
            for index, comparison in enumerate(raw_comparisons)
        )
        rows = tuple(
            (
                "LTE_SR" if item.comparison_id == "SelfEvolve_vs_FixedSeed" else item.comparison_id,
                item.estimate,
                item.sample_count,
                item.standard_error,
                item.ci_lower,
                item.ci_upper,
            )
            for item in comparisons
        )
        return ScientificStatisticalReport(
            plan_digest=plan.plan_digest,
            effects=rows,
            missing=tuple(missing),
            blockers=tuple(dict.fromkeys(blockers)),
            comparisons=comparisons,
        )


__all__ = ["SemPaperScientificStatisticsProvider", "provider_implementation"]
