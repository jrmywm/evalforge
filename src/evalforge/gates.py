"""Pure quality-gate evaluation for Milestone 4."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evalforge.aggregation import ConfigurationSummary
from evalforge.config import ExperimentConfig, LoadedManifest, QualityGate
from evalforge.regression import MetricDelta, RegressionResult


class GateFailure(BaseModel):
    """One deterministic reason a quality policy was not satisfied."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    metric: str = Field(min_length=1)
    rule: Literal["minimum", "maximum", "maximum_regression", "data_integrity"]
    reason: str = Field(min_length=1)
    observed: float | None = Field(default=None, allow_inf_nan=False)
    threshold: float | None = Field(default=None, allow_inf_nan=False)


class GateRuleResult(BaseModel):
    """Auditable result for one threshold or data-integrity rule."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    metric: str = Field(min_length=1)
    rule: Literal["minimum", "maximum", "maximum_regression", "data_integrity"]
    observed: float | None = Field(default=None, allow_inf_nan=False)
    threshold: float | None = Field(default=None, allow_inf_nan=False)
    passed: bool
    reason: str = Field(min_length=1)


class QualityGateResult(BaseModel):
    """Complete quality-gate decision; all failures are retained."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    decision: Literal["passed", "failed"]
    evaluated_rules: tuple[str, ...]
    rules: tuple[GateRuleResult, ...] = ()
    failures: tuple[GateFailure, ...] = ()

    @model_validator(mode="after")
    def validate_consistency(self) -> QualityGateResult:
        failed_rules = tuple(rule for rule in self.rules if not rule.passed)
        expected_decision = "failed" if failed_rules else "passed"
        if self.decision != expected_decision:
            raise ValueError("quality-gate decision must match failed rule evidence")

        expected_failures = tuple(
            (rule.metric, rule.rule, rule.reason, rule.observed, rule.threshold)
            for rule in failed_rules
        )
        actual_failures = tuple(
            (failure.metric, failure.rule, failure.reason, failure.observed, failure.threshold)
            for failure in self.failures
        )
        if actual_failures != expected_failures:
            raise ValueError("quality-gate failures must match failed rule evidence in order")

        expected_evaluated_rules = tuple(
            f"{rule.metric}.{rule.rule}" for rule in self.rules if rule.rule != "data_integrity"
        )
        if self.evaluated_rules != expected_evaluated_rules:
            raise ValueError("evaluated_rules must match non-integrity rule evidence in order")
        return self

    @property
    def passed(self) -> bool:
        return self.decision == "passed"

    @property
    def rule_results(self) -> tuple[GateRuleResult, ...]:
        return self.rules


def _config(manifest: ExperimentConfig | LoadedManifest) -> ExperimentConfig:
    return manifest.config if isinstance(manifest, LoadedManifest) else manifest


def _metric(summary: ConfigurationSummary, name: str) -> float | None:
    if name == "p95_latency_ms":
        return summary.latency.p95_ms
    aggregate = summary.metric(name)
    return aggregate.score if aggregate else None


def _integrity_rules(summary: ConfigurationSummary) -> list[GateRuleResult]:
    rules: list[GateRuleResult] = []
    for name in sorted(summary.evaluator_metrics):
        metric = summary.metric(name)
        if metric is None:
            continue
        for label, observed in (
            ("missing evaluations", metric.missing_count),
            ("evaluator errors", metric.evaluator_error_count),
        ):
            rules.append(
                GateRuleResult(
                    metric=f"{summary.configuration}.{name}",
                    rule="data_integrity",
                    observed=float(observed),
                    threshold=0.0,
                    passed=observed == 0,
                    reason=(
                        f"{summary.configuration} has no {label}"
                        if observed == 0
                        else f"{summary.configuration} has {observed} {label}"
                    ),
                )
            )
    return rules


def _rule_results(
    metric_name: str,
    gate: QualityGate,
    delta: MetricDelta | None,
    observed: float | None,
) -> list[GateRuleResult]:
    results: list[GateRuleResult] = []
    if gate.minimum is not None:
        passed = observed is not None and observed >= gate.minimum
        results.append(
            GateRuleResult(
                metric=metric_name,
                rule="minimum",
                reason=(
                    f"candidate {metric_name} meets minimum {gate.minimum}"
                    if passed
                    else (
                        f"candidate {metric_name} is unavailable"
                        if observed is None
                        else f"candidate {metric_name} {observed} is below minimum {gate.minimum}"
                    )
                ),
                observed=observed,
                threshold=gate.minimum,
                passed=passed,
            )
        )
    if gate.maximum is not None:
        passed = observed is not None and observed <= gate.maximum
        results.append(
            GateRuleResult(
                metric=metric_name,
                rule="maximum",
                reason=(
                    f"candidate {metric_name} meets maximum {gate.maximum}"
                    if passed
                    else (
                        f"candidate {metric_name} is unavailable"
                        if observed is None
                        else f"candidate {metric_name} {observed} exceeds maximum {gate.maximum}"
                    )
                ),
                observed=observed,
                threshold=gate.maximum,
                passed=passed,
            )
        )
    if gate.maximum_regression is not None:
        deterioration: float | None = None
        if delta is not None and delta.baseline is not None and delta.candidate is not None:
            deterioration = (
                delta.candidate - delta.baseline
                if metric_name == "p95_latency_ms"
                else delta.baseline - delta.candidate
            )
        passed = deterioration is not None and deterioration <= gate.maximum_regression
        results.append(
            GateRuleResult(
                metric=metric_name,
                rule="maximum_regression",
                reason=(
                    f"{metric_name} deterioration is within maximum {gate.maximum_regression}"
                    if passed
                    else (
                        f"{metric_name} regression is unavailable"
                        if deterioration is None
                        else (
                            f"{metric_name} deterioration {deterioration} exceeds "
                            f"maximum {gate.maximum_regression}"
                        )
                    )
                ),
                observed=deterioration,
                threshold=gate.maximum_regression,
                passed=passed,
            )
        )
    return results


def evaluate_quality_gates(
    manifest: ExperimentConfig | LoadedManifest,
    regression: RegressionResult,
) -> QualityGateResult:
    """Evaluate every configured rule, including integrity failures."""
    config = _config(manifest)
    rules = _integrity_rules(regression.baseline) + _integrity_rules(regression.candidate)
    evaluated_rules: list[str] = []
    for metric_name in sorted(config.quality_gates):
        gate = config.quality_gates[metric_name]
        evaluated_rules.extend(
            f"{metric_name}.{rule}"
            for rule in ("minimum", "maximum", "maximum_regression")
            if getattr(gate, rule) is not None
        )
        metric_delta = regression.metrics.get(metric_name)
        if not isinstance(metric_delta, MetricDelta):
            metric_delta = None
        rules.extend(
            _rule_results(
                metric_name,
                gate,
                metric_delta,
                _metric(regression.candidate, metric_name),
            )
        )
    failures = tuple(
        GateFailure(
            metric=rule.metric,
            rule=rule.rule,
            reason=rule.reason,
            observed=rule.observed,
            threshold=rule.threshold,
        )
        for rule in rules
        if not rule.passed
    )
    return QualityGateResult(
        decision="failed" if failures else "passed",
        evaluated_rules=tuple(evaluated_rules),
        rules=tuple(rules),
        failures=failures,
    )


def apply_quality_gates(*args: object, **kwargs: object) -> QualityGateResult:
    """Alias for :func:`evaluate_quality_gates`."""
    return evaluate_quality_gates(*args, **kwargs)  # type: ignore[arg-type]
