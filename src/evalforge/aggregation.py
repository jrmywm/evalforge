"""Pure aggregation of stored generations and evaluator results."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalforge.artifacts import (
    read_dataset_snapshot,
    read_evaluations,
    read_generations,
    read_manifest_snapshot,
)
from evalforge.config import ExperimentConfig, LoadedManifest
from evalforge.dataset import DatasetSnapshot
from evalforge.evaluators import BUILTIN_EVALUATOR_VERSIONS
from evalforge.evaluators.base import EvaluationResult, make_evaluation_id
from evalforge.json_types import FrozenDict
from evalforge.models import GenerationRecord


class AggregationInputError(ValueError):
    """Raised when stored experiment inputs are mixed or internally inconsistent."""


class MetricAggregate(BaseModel):
    """One evaluator's score and complete population accounting."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    evaluator: str = Field(min_length=1)
    denominator: int = Field(ge=0)
    score_sum: float = Field(ge=0, allow_inf_nan=False)
    score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    not_evaluated_count: int = Field(ge=0)
    evaluator_error_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> MetricAggregate:
        if (
            sum(
                (
                    self.passed_count,
                    self.failed_count,
                    self.not_evaluated_count,
                    self.evaluator_error_count,
                    self.missing_count,
                )
            )
            != self.denominator
        ):
            raise ValueError("metric status counts must sum to denominator")
        if self.denominator == 0 and self.score is not None:
            raise ValueError("empty metric population cannot have a score")
        if self.denominator > 0 and self.score is None:
            raise ValueError("non-empty metric population must have a score")
        return self


class LatencySummary(BaseModel):
    """Successful-call latency statistics using nearest-rank P95."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    median_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    p95_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    successful_count: int = Field(ge=0)
    excluded_provider_failure_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_statistics(self) -> LatencySummary:
        if self.successful_count == 0 and (self.median_ms is not None or self.p95_ms is not None):
            raise ValueError("empty successful latency population must have unavailable statistics")
        if self.successful_count > 0 and (self.median_ms is None or self.p95_ms is None):
            raise ValueError("non-empty successful latency population must have statistics")
        return self

    @property
    def median_latency_ms(self) -> float | None:
        return self.median_ms

    @property
    def p95_latency_ms(self) -> float | None:
        return self.p95_ms


class UsageSummary(BaseModel):
    """Known token/cost totals with explicit unavailable populations."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    input_tokens_total: int | None = Field(default=None, ge=0)
    output_tokens_total: int | None = Field(default=None, ge=0)
    total_tokens_total: int | None = Field(default=None, ge=0)
    input_tokens_unavailable_count: int = Field(ge=0)
    output_tokens_unavailable_count: int = Field(ge=0)
    total_tokens_unavailable_count: int = Field(ge=0)
    cost_total_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cost_unavailable_count: int = Field(ge=0)


class ConfigurationSummary(BaseModel):
    """Immutable metrics for one baseline or candidate configuration."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    configuration: str = Field(min_length=1)
    attempted_generations: int = Field(ge=0)
    provider_success_count: int = Field(ge=0)
    provider_error_count: int = Field(ge=0)
    case_pass_count: int = Field(ge=0)
    case_fail_count: int = Field(ge=0)
    passed_case_ids: tuple[str, ...] = ()
    evaluator_metrics: FrozenDict = Field(default_factory=FrozenDict)
    latency: LatencySummary
    usage: UsageSummary

    @field_validator("evaluator_metrics", mode="before")
    @classmethod
    def freeze_metrics(cls, value: object) -> FrozenDict:
        if isinstance(value, FrozenDict):
            value = dict(value)
        if not isinstance(value, dict):
            return FrozenDict(value or {})
        return FrozenDict(
            {
                name: metric
                if isinstance(metric, MetricAggregate)
                else MetricAggregate.model_validate(metric)
                for name, metric in value.items()
            }
        )

    @model_validator(mode="after")
    def validate_counts(self) -> ConfigurationSummary:
        if self.provider_success_count + self.provider_error_count != self.attempted_generations:
            raise ValueError("provider status counts must sum to attempted generations")
        if self.case_pass_count + self.case_fail_count != self.attempted_generations:
            raise ValueError("case status counts must sum to attempted generations")
        if len(self.passed_case_ids) != self.case_pass_count:
            raise ValueError("passed_case_ids must match case_pass_count")
        if len(set(self.passed_case_ids)) != len(self.passed_case_ids):
            raise ValueError("passed_case_ids must be unique")
        if tuple(sorted(self.passed_case_ids)) != self.passed_case_ids:
            raise ValueError("passed_case_ids must be stable sorted IDs")
        if self.latency.successful_count != self.provider_success_count:
            raise ValueError("latency successful count must match provider successes")
        if (
            self.latency.successful_count + self.latency.excluded_provider_failure_count
            != self.attempted_generations
        ):
            raise ValueError("latency counts must sum to attempted generations")
        for field in (
            "input_tokens_unavailable_count",
            "output_tokens_unavailable_count",
            "total_tokens_unavailable_count",
            "cost_unavailable_count",
        ):
            unavailable = getattr(self.usage, field)
            if unavailable > self.attempted_generations:
                raise ValueError(f"{field} cannot exceed attempted generations")
            total_field = {
                "input_tokens_unavailable_count": "input_tokens_total",
                "output_tokens_unavailable_count": "output_tokens_total",
                "total_tokens_unavailable_count": "total_tokens_total",
                "cost_unavailable_count": "cost_total_usd",
            }[field]
            total = getattr(self.usage, total_field)
            if self.attempted_generations == 0 and total is not None:
                raise ValueError(f"empty usage population cannot have {total_field}")
            if self.attempted_generations > 0 and (
                (unavailable == self.attempted_generations and total is not None)
                or (unavailable < self.attempted_generations and total is None)
            ):
                raise ValueError(f"{total_field} availability does not match its unavailable count")
        expected_evaluators = {"schema_validity": "json_schema", "field_accuracy": "field_accuracy"}
        for name, metric in self.evaluator_metrics.items():
            if not isinstance(metric, MetricAggregate):
                raise ValueError(f"evaluator metric {name!r} must be a MetricAggregate")
            if name not in expected_evaluators or metric.evaluator != expected_evaluators[name]:
                raise ValueError(f"evaluator metric {name!r} has an incoherent evaluator alias")
            if metric.denominator != self.attempted_generations:
                raise ValueError(
                    f"evaluator metric {name!r} denominator must equal attempted generations"
                )
        return self

    @property
    def metrics(self) -> FrozenDict:
        return self.evaluator_metrics

    @property
    def median_latency_ms(self) -> float | None:
        return self.latency.median_ms

    @property
    def p95_latency_ms(self) -> float | None:
        return self.latency.p95_ms

    def metric(self, name: str) -> MetricAggregate | None:
        value = self.evaluator_metrics.get(name)
        return value if isinstance(value, MetricAggregate) else None


def _config(manifest: LoadedManifest | ExperimentConfig | Path) -> ExperimentConfig:
    if isinstance(manifest, Path):
        return read_manifest_snapshot(manifest)
    return manifest.config if isinstance(manifest, LoadedManifest) else manifest


def _resolve_inputs(
    manifest: LoadedManifest | ExperimentConfig | Path,
    dataset: DatasetSnapshot | Path,
    generations: Iterable[GenerationRecord] | Path,
    evaluations: Iterable[EvaluationResult] | Path,
) -> tuple[
    ExperimentConfig, DatasetSnapshot, tuple[GenerationRecord, ...], tuple[EvaluationResult, ...]
]:
    config = _config(manifest)
    resolved_dataset = (
        read_dataset_snapshot(dataset, version=config.dataset.version)
        if isinstance(dataset, Path)
        else dataset
    )
    stored_generations = (
        read_generations(generations) if isinstance(generations, Path) else tuple(generations)
    )
    stored_evaluations = (
        read_evaluations(evaluations) if isinstance(evaluations, Path) else tuple(evaluations)
    )
    return config, resolved_dataset, stored_generations, stored_evaluations


def _validate_inputs(
    config: ExperimentConfig,
    dataset: DatasetSnapshot,
    generations: tuple[GenerationRecord, ...],
    evaluations: tuple[EvaluationResult, ...],
) -> dict[str, dict[str, GenerationRecord]]:
    if dataset.version != config.dataset.version:
        raise AggregationInputError(
            "dataset version mismatch: "
            f"expected {config.dataset.version!r}, received {dataset.version!r}"
        )
    case_map = {case.id: case for case in dataset.cases}
    if len(case_map) != len(dataset.cases):
        raise AggregationInputError("dataset contains duplicate case IDs")
    generation_map: dict[str, dict[str, GenerationRecord]] = {"baseline": {}, "candidate": {}}
    by_id: dict[str, GenerationRecord] = {}
    for generation in generations:
        if generation.generation_id in by_id:
            raise AggregationInputError(f"duplicate generation ID: {generation.generation_id!r}")
        if generation.configuration not in generation_map:
            raise AggregationInputError(
                f"unknown generation configuration: {generation.configuration!r}"
            )
        if generation.case_id not in case_map:
            raise AggregationInputError(f"unknown generation case ID: {generation.case_id!r}")
        if generation.case_id in generation_map[generation.configuration]:
            raise AggregationInputError(
                f"duplicate generation for {generation.configuration}/{generation.case_id}"
            )
        expected_config = config.configurations[generation.configuration]
        if (
            generation.experiment != config.name
            or generation.provider != expected_config.provider
            or generation.model != expected_config.model
            or generation.normalized_request.experiment != config.name
            or generation.normalized_request.configuration != generation.configuration
            or generation.normalized_request.case_id != generation.case_id
            or generation.normalized_request.model != expected_config.model
            or generation.normalized_request.prompt != expected_config.prompt
            or generation.normalized_request.inference_parameters
            != expected_config.inference_parameters
            or generation.normalized_request.provider_options
            != (
                expected_config.provider_options.model_dump(mode="json")
                if expected_config.provider_options is not None
                else {}
            )
            or generation.normalized_request.output_schema != config.output_schema
            or generation.normalized_request.input != case_map[generation.case_id].input
        ):
            raise AggregationInputError(
                f"generation {generation.generation_id!r} does not match manifest or dataset"
            )
        generation_map[generation.configuration][generation.case_id] = generation
        by_id[generation.generation_id] = generation
    expected_cases = set(case_map)
    for configuration, items in generation_map.items():
        missing_cases = expected_cases - set(items)
        if missing_cases:
            raise AggregationInputError(
                f"missing generations for {configuration}: {sorted(missing_cases)!r}"
            )

    evaluator_names = {spec.type for spec in config.evaluators}
    seen_evaluations: set[tuple[str, str]] = set()
    evaluation_ids: set[str] = set()
    for evaluation in evaluations:
        if evaluation.evaluation_id in evaluation_ids:
            raise AggregationInputError(f"duplicate evaluation ID: {evaluation.evaluation_id!r}")
        evaluation_ids.add(evaluation.evaluation_id)
        generation = by_id.get(evaluation.generation_id)
        if generation is None:
            raise AggregationInputError(
                f"evaluation references unknown generation ID: {evaluation.generation_id!r}"
            )
        if evaluation.case_id != generation.case_id:
            raise AggregationInputError(
                f"evaluation {evaluation.evaluation_id!r} case does not match generation"
            )
        if evaluation.evaluator not in evaluator_names:
            raise AggregationInputError(f"unknown evaluator result: {evaluation.evaluator!r}")
        if generation.status == "provider_error" and evaluation.status != "not_evaluated":
            raise AggregationInputError(
                f"provider-error generation {generation.generation_id!r} must be not_evaluated"
            )
        if generation.status == "success" and evaluation.status == "not_evaluated":
            raise AggregationInputError(
                f"successful generation {generation.generation_id!r} cannot be not_evaluated"
            )
        expected_version = BUILTIN_EVALUATOR_VERSIONS[evaluation.evaluator]
        if evaluation.evaluator_version != expected_version:
            raise AggregationInputError(
                f"evaluation {evaluation.evaluation_id!r} has unexpected evaluator version"
            )
        expected_id = make_evaluation_id(
            generation, evaluation.evaluator, evaluation.evaluator_version
        )
        if evaluation.evaluation_id != expected_id:
            raise AggregationInputError(
                f"evaluation {evaluation.evaluation_id!r} has invalid evaluation ID"
            )
        identity = (evaluation.generation_id, evaluation.evaluator)
        if identity in seen_evaluations:
            raise AggregationInputError(f"duplicate evaluation identity: {identity!r}")
        seen_evaluations.add(identity)
    return generation_map


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= percentile <= 1.0:
        raise ValueError(f"percentile must be between 0.0 and 1.0, got {percentile}")
    index = max(0, min(len(values) - 1, math.ceil(percentile * len(values)) - 1))
    return sorted(values)[index]


def _usage_summary(generations: list[GenerationRecord]) -> UsageSummary:
    fields: dict[str, tuple[int, int]] = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        known = [
            getattr(record.usage, field)
            for record in generations
            if record.usage and getattr(record.usage, field) is not None
        ]
        fields[field] = (sum(known) if known else 0, len(generations) - len(known))
    known_costs = [
        record.estimated_cost_usd for record in generations if record.estimated_cost_usd is not None
    ]
    return UsageSummary(
        input_tokens_total=fields["input_tokens"][0]
        if fields["input_tokens"][1] < len(generations)
        else None,
        output_tokens_total=fields["output_tokens"][0]
        if fields["output_tokens"][1] < len(generations)
        else None,
        total_tokens_total=fields["total_tokens"][0]
        if fields["total_tokens"][1] < len(generations)
        else None,
        input_tokens_unavailable_count=fields["input_tokens"][1],
        output_tokens_unavailable_count=fields["output_tokens"][1],
        total_tokens_unavailable_count=fields["total_tokens"][1],
        cost_total_usd=sum(known_costs) if known_costs else None,
        cost_unavailable_count=len(generations) - len(known_costs),
    )


def _summary_for(
    configuration: str,
    generations: dict[str, GenerationRecord],
    evaluations: dict[tuple[str, str], EvaluationResult],
    evaluator_names: tuple[str, ...],
) -> ConfigurationSummary:
    records = list(generations.values())
    attempted = len(records)
    successful = sum(record.status == "success" for record in records)
    provider_errors = attempted - successful
    evaluator_metrics: dict[str, MetricAggregate] = {}
    case_passes = 0
    for evaluator_name in evaluator_names:
        metric_name = "schema_validity" if evaluator_name == "json_schema" else evaluator_name
        passed = failed = not_evaluated = evaluator_errors = missing = 0
        score_sum = 0.0
        for record in records:
            evaluation = evaluations.get((record.generation_id, evaluator_name))
            if evaluation is None:
                missing += 1
                continue
            if evaluation.status == "passed":
                passed += 1
            elif evaluation.status == "failed":
                failed += 1
            elif evaluation.status == "not_evaluated":
                not_evaluated += 1
            else:
                evaluator_errors += 1
            if evaluation.score is not None:
                score_sum += evaluation.score
        evaluator_metrics[metric_name] = MetricAggregate(
            evaluator=evaluator_name,
            denominator=attempted,
            score_sum=score_sum,
            score=score_sum / attempted if attempted else None,
            passed_count=passed,
            failed_count=failed,
            not_evaluated_count=not_evaluated,
            evaluator_error_count=evaluator_errors,
            missing_count=missing,
        )
    for record in records:
        if record.status == "success" and all(
            evaluations.get((record.generation_id, name), None)
            and evaluations[(record.generation_id, name)].status == "passed"
            for name in evaluator_names
        ):
            case_passes += 1
    latencies = [record.latency_ms for record in records if record.status == "success"]
    return ConfigurationSummary(
        configuration=configuration,
        attempted_generations=attempted,
        provider_success_count=successful,
        provider_error_count=provider_errors,
        case_pass_count=case_passes,
        case_fail_count=attempted - case_passes,
        passed_case_ids=tuple(
            sorted(
                record.case_id
                for record in records
                if record.status == "success"
                and all(
                    evaluations.get((record.generation_id, name), None)
                    and evaluations[(record.generation_id, name)].status == "passed"
                    for name in evaluator_names
                )
            )
        ),
        evaluator_metrics=evaluator_metrics,
        latency=LatencySummary(
            median_ms=statistics.median(latencies) if latencies else None,
            p95_ms=_percentile(latencies, 0.95),
            successful_count=len(latencies),
            excluded_provider_failure_count=provider_errors,
        ),
        usage=_usage_summary(records),
    )


def aggregate_experiment(
    manifest: LoadedManifest | ExperimentConfig | Path,
    dataset: DatasetSnapshot | Path,
    generations: Iterable[GenerationRecord] | Path,
    evaluations: Iterable[EvaluationResult] | Path,
) -> tuple[ConfigurationSummary, ConfigurationSummary]:
    """Aggregate stored inputs into baseline and candidate summaries."""
    config, resolved_dataset, stored_generations, stored_evaluations = _resolve_inputs(
        manifest, dataset, generations, evaluations
    )
    generation_map = _validate_inputs(
        config, resolved_dataset, stored_generations, stored_evaluations
    )
    evaluation_map = {(item.generation_id, item.evaluator): item for item in stored_evaluations}
    evaluator_names = tuple(spec.type for spec in config.evaluators)
    return (
        _summary_for("baseline", generation_map["baseline"], evaluation_map, evaluator_names),
        _summary_for("candidate", generation_map["candidate"], evaluation_map, evaluator_names),
    )


def aggregate(*args: object, **kwargs: object) -> tuple[ConfigurationSummary, ConfigurationSummary]:
    """Short alias for :func:`aggregate_experiment`."""
    return aggregate_experiment(*args, **kwargs)  # type: ignore[arg-type]
