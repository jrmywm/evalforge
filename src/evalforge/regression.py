"""Pure baseline-versus-candidate comparison."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evalforge.aggregation import ConfigurationSummary
from evalforge.json_types import FrozenDict


class MetricDelta(BaseModel):
    """Candidate-minus-baseline metric change."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    baseline: float | None = Field(default=None, allow_inf_nan=False)
    candidate: float | None = Field(default=None, allow_inf_nan=False)
    delta: float | None = Field(default=None, allow_inf_nan=False)
    relative_delta: float | None = Field(default=None, allow_inf_nan=False)


class RegressionResult(BaseModel):
    """Immutable comparison including stable case-level transitions."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    baseline: ConfigurationSummary
    candidate: ConfigurationSummary
    metrics: FrozenDict = Field(default_factory=FrozenDict)
    newly_failing: tuple[str, ...] = ()
    newly_passing: tuple[str, ...] = ()

    @classmethod
    def from_summaries(
        cls,
        baseline: ConfigurationSummary,
        candidate: ConfigurationSummary,
        metrics: dict[str, MetricDelta],
        newly_failing: tuple[str, ...],
        newly_passing: tuple[str, ...],
    ) -> RegressionResult:
        return cls(
            baseline=baseline,
            candidate=candidate,
            metrics=metrics,
            newly_failing=tuple(sorted(newly_failing)),
            newly_passing=tuple(sorted(newly_passing)),
        )

    @property
    def metric_deltas(self) -> FrozenDict:
        return self.metrics

    @field_validator("metrics", mode="before")
    @classmethod
    def _freeze_metrics(cls, value: Any) -> FrozenDict:
        if isinstance(value, FrozenDict):
            value = dict(value)
        if not isinstance(value, dict):
            return FrozenDict(value or {})
        return FrozenDict(
            {
                name: delta if isinstance(delta, MetricDelta) else MetricDelta.model_validate(delta)
                for name, delta in value.items()
            }
        )


def _delta(baseline: float | None, candidate: float | None) -> MetricDelta:
    if baseline is None or candidate is None:
        return MetricDelta(baseline=baseline, candidate=candidate)
    change = candidate - baseline
    relative = (
        0.0
        if baseline == 0 and candidate == 0
        else (None if baseline == 0 else change / abs(baseline))
    )
    return MetricDelta(
        baseline=baseline,
        candidate=candidate,
        delta=change,
        relative_delta=relative,
    )


def compare_summaries(
    baseline: ConfigurationSummary, candidate: ConfigurationSummary
) -> RegressionResult:
    """Compare quality, latency, and pass/fail case outcomes."""
    metrics: dict[str, MetricDelta] = {}
    for name in ("schema_validity", "field_accuracy"):
        baseline_metric = baseline.metric(name)
        candidate_metric = candidate.metric(name)
        metrics[name] = _delta(
            baseline_metric.score if baseline_metric else None,
            candidate_metric.score if candidate_metric else None,
        )
    metrics["p95_latency_ms"] = _delta(baseline.latency.p95_ms, candidate.latency.p95_ms)

    return RegressionResult.from_summaries(
        baseline,
        candidate,
        metrics,
        *compare_case_passes(set(baseline.passed_case_ids), set(candidate.passed_case_ids)),
    )


def compare_case_passes(
    baseline_passes: set[str], candidate_passes: set[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return stable baseline-pass/candidate-fail and inverse transitions."""
    return tuple(sorted(baseline_passes - candidate_passes)), tuple(
        sorted(candidate_passes - baseline_passes)
    )
