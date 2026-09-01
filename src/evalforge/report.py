"""Immutable experiment reports and deterministic Markdown rendering."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalforge import __version__
from evalforge.aggregation import ConfigurationSummary
from evalforge.analysis import ExperimentAnalysis
from evalforge.config import ExperimentConfig, LoadedManifest
from evalforge.dataset import DatasetSnapshot
from evalforge.engine import ExperimentRun
from evalforge.evaluators import BUILTIN_EVALUATOR_VERSIONS
from evalforge.evaluators.base import EvaluationResult
from evalforge.gates import QualityGateResult
from evalforge.json_types import FrozenDict, canonical_digest, freeze_json, thaw_json
from evalforge.models import GenerationRecord
from evalforge.providers import ProviderErrorDetail, UsageMetadata
from evalforge.regression import RegressionResult


class ReportEvaluator(BaseModel):
    """Identity of an evaluator used in the experiment."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ReportGeneration(BaseModel):
    """Portable generation evidence included in the report."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    generation_id: str = Field(min_length=1)
    configuration: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    resolved_model: str | None = Field(default=None, min_length=1)
    origin: Literal["fresh", "cache", "replay"]
    status: Literal["success", "provider_error"]
    started_at: datetime
    ended_at: datetime
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    usage: UsageMetadata | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    normalized_response: Any | None = None
    raw_response: Any | None = None
    provider_error: ProviderErrorDetail | None = None

    @field_validator("normalized_response", "raw_response", mode="before")
    @classmethod
    def freeze_responses(cls, value: Any) -> Any:
        return freeze_json(value) if value is not None else None

    @model_validator(mode="after")
    def validate_state(self) -> ReportGeneration:
        if self.ended_at < self.started_at:
            raise ValueError("report generation ended_at must not precede started_at")
        if self.status == "success" and self.provider_error is not None:
            raise ValueError("successful report generation cannot contain provider_error")
        if self.status == "provider_error":
            if self.provider_error is None:
                raise ValueError("provider-error report generation must contain provider_error")
            if self.normalized_response is not None or self.raw_response is not None:
                raise ValueError("provider-error report generation cannot contain a response")
            if self.usage is not None or self.estimated_cost_usd is not None:
                raise ValueError("provider-error report generation cannot contain usage or cost")
        return self


class ReportConfiguration(BaseModel):
    """Configuration identity, generation evidence, and summary."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str
    inference_parameters: FrozenDict = Field(default_factory=FrozenDict)
    provider_options: FrozenDict = Field(default_factory=FrozenDict)
    generation_count: int = Field(ge=0)
    status_counts: FrozenDict = Field(default_factory=FrozenDict)
    origin_counts: FrozenDict = Field(default_factory=FrozenDict)
    generations: tuple[ReportGeneration, ...] = ()
    summary: ConfigurationSummary

    @field_validator(
        "inference_parameters", "provider_options", "status_counts", "origin_counts", mode="before"
    )
    @classmethod
    def freeze_mappings(cls, value: Any) -> FrozenDict:
        return value if isinstance(value, FrozenDict) else FrozenDict(value or {})

    @model_validator(mode="after")
    def validate_generation_counts(self) -> ReportConfiguration:
        if len(self.generations) != self.generation_count:
            raise ValueError("generation_count must equal the number of generation records")
        generation_ids = [generation.generation_id for generation in self.generations]
        if len(set(generation_ids)) != len(generation_ids):
            raise ValueError("generation IDs must be unique within a configuration report")
        case_ids = [generation.case_id for generation in self.generations]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case IDs must be unique within a configuration report")
        if self.summary.configuration != self.name:
            raise ValueError("configuration summary must match report configuration")
        if self.summary.attempted_generations != self.generation_count:
            raise ValueError("configuration summary denominator must match generation_count")
        for generation in self.generations:
            if (
                generation.configuration != self.name
                or generation.provider != self.provider
                or generation.model != self.model
            ):
                raise ValueError("generation identity must match its report configuration")
        for label, counts in (
            ("status", self.status_counts),
            ("origin", self.origin_counts),
        ):
            if any(
                not isinstance(count, int) or isinstance(count, bool) or count < 0
                for count in counts.values()
            ):
                raise ValueError(f"{label}_counts must contain non-negative integer values")
            if sum(counts.values()) != self.generation_count:
                raise ValueError(f"{label}_counts must sum to generation_count")
        expected_status_counts = Counter(generation.status for generation in self.generations)
        expected_origin_counts = Counter(generation.origin for generation in self.generations)
        if dict(self.status_counts) != dict(expected_status_counts):
            raise ValueError("status_counts must equal generation statuses")
        if dict(self.origin_counts) != dict(expected_origin_counts):
            raise ValueError("origin_counts must equal generation origins")
        return self


class FailedCaseReport(BaseModel):
    """Complete evidence for a case that did not pass."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    configuration: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    tags: tuple[str, ...] = ()
    description: str | None = None
    expected: FrozenDict
    actual: Any | None = None
    raw_response: Any | None = None
    provider_error: ProviderErrorDetail | None = None
    evaluations: tuple[EvaluationResult, ...] = ()

    @field_validator("expected", mode="before")
    @classmethod
    def freeze_expected(cls, value: Any) -> FrozenDict:
        return value if isinstance(value, FrozenDict) else FrozenDict(value or {})

    @field_validator("actual", "raw_response", mode="before")
    @classmethod
    def freeze_outputs(cls, value: Any) -> Any:
        return freeze_json(value) if value is not None else None


class ExperimentReport(BaseModel):
    """Single immutable source model for JSON and Markdown reports."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    report_version: str = "1"
    evalforge_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    experiment: str = Field(min_length=1)
    manifest: ExperimentConfig
    manifest_digest: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    dataset_digest: str = Field(min_length=1)
    started_at: datetime
    ended_at: datetime
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    configurations: tuple[ReportConfiguration, ...] = Field(min_length=2)
    evaluators: tuple[ReportEvaluator, ...] = Field(min_length=1)
    evaluations: tuple[EvaluationResult, ...] = ()
    baseline_summary: ConfigurationSummary
    candidate_summary: ConfigurationSummary
    regression: RegressionResult
    gates: QualityGateResult
    failed_cases: tuple[FailedCaseReport, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> ExperimentReport:
        names = tuple(configuration.name for configuration in self.configurations)
        if names != ("baseline", "candidate"):
            raise ValueError("report configurations must be baseline and candidate")
        if self.baseline_summary.configuration != "baseline":
            raise ValueError("baseline_summary must describe baseline")
        if self.candidate_summary.configuration != "candidate":
            raise ValueError("candidate_summary must describe candidate")
        if self.experiment != self.manifest.name:
            raise ValueError("report experiment must match embedded manifest")
        if canonical_digest(self.manifest.model_dump(mode="json")) != self.manifest_digest:
            raise ValueError("manifest_digest does not match embedded manifest content")
        if self.ended_at < self.started_at:
            raise ValueError("report ended_at must not precede started_at")
        expected_duration = (self.ended_at - self.started_at).total_seconds() * 1000
        if abs(self.duration_ms - expected_duration) > 1e-6:
            raise ValueError("duration_ms must match the report execution window")
        if self.baseline_summary != self.configurations[0].summary:
            raise ValueError("baseline_summary must match baseline configuration summary")
        if self.candidate_summary != self.configurations[1].summary:
            raise ValueError("candidate_summary must match candidate configuration summary")
        for configuration in self.configurations:
            declared = self.manifest.configurations[configuration.name]
            declared_provider_options = (
                declared.provider_options.model_dump(mode="json")
                if declared.provider_options is not None
                else {}
            )
            if (
                configuration.provider != declared.provider
                or configuration.model != declared.model
                or configuration.prompt != declared.prompt
                or configuration.inference_parameters != declared.inference_parameters
                or configuration.provider_options != declared_provider_options
            ):
                raise ValueError("report configuration identity must match embedded manifest")
        if self.regression.baseline != self.baseline_summary:
            raise ValueError("regression baseline must match baseline_summary")
        if self.regression.candidate != self.candidate_summary:
            raise ValueError("regression candidate must match candidate_summary")
        evaluator_names = tuple(evaluator.name for evaluator in self.evaluators)
        if len(set(evaluator_names)) != len(evaluator_names):
            raise ValueError("report evaluators must be unique")
        expected_evaluators = tuple(spec.type for spec in self.manifest.evaluators)
        if evaluator_names != expected_evaluators:
            raise ValueError("report evaluators must match manifest evaluator specifications")
        for evaluator in self.evaluators:
            if evaluator.version != BUILTIN_EVALUATOR_VERSIONS[evaluator.name]:
                raise ValueError("report evaluator version does not match the built-in evaluator")

        generations = {
            generation.generation_id: generation
            for configuration in self.configurations
            for generation in configuration.generations
        }
        if len(generations) != sum(
            configuration.generation_count for configuration in self.configurations
        ):
            raise ValueError("report generation IDs must be globally unique")
        expected_pairs = {
            (generation_id, name) for generation_id in generations for name in evaluator_names
        }
        actual_pairs: set[tuple[str, str]] = set()
        evaluation_ids: set[str] = set()
        for evaluation in self.evaluations:
            generation = generations.get(evaluation.generation_id)
            if generation is None:
                raise ValueError("evaluation references an unknown report generation")
            if evaluation.case_id != generation.case_id:
                raise ValueError("evaluation case_id must match its generation")
            if evaluation.evaluator not in evaluator_names:
                raise ValueError("evaluation evaluator must be declared by the manifest")
            expected_version = BUILTIN_EVALUATOR_VERSIONS[evaluation.evaluator]
            if evaluation.evaluator_version != expected_version:
                raise ValueError("evaluation version must match the built-in evaluator")
            expected_evaluation_id = canonical_digest(
                {
                    "generation_id": evaluation.generation_id,
                    "evaluator": evaluation.evaluator,
                    "version": evaluation.evaluator_version,
                }
            )
            if evaluation.evaluation_id != expected_evaluation_id:
                raise ValueError(
                    "evaluation_id does not match report generation/evaluator identity"
                )
            pair = (evaluation.generation_id, evaluation.evaluator)
            if evaluation.evaluation_id in evaluation_ids or pair in actual_pairs:
                raise ValueError("report evaluations must have unique IDs and identities")
            if generation.status == "provider_error" and evaluation.status != "not_evaluated":
                raise ValueError("provider-error generation evaluations must be not_evaluated")
            if generation.status == "success" and evaluation.status == "not_evaluated":
                raise ValueError("successful generation evaluations cannot be not_evaluated")
            evaluation_ids.add(evaluation.evaluation_id)
            actual_pairs.add(pair)
        if actual_pairs != expected_pairs:
            raise ValueError("report evaluations must cover every generation/evaluator pair")

        for configuration in self.configurations:
            passed_case_ids = tuple(
                sorted(
                    generation.case_id
                    for generation in configuration.generations
                    if generation.status == "success"
                    and all(
                        evaluation.generation_id == generation.generation_id
                        and evaluation.status == "passed"
                        for evaluation in self.evaluations
                        if evaluation.generation_id == generation.generation_id
                    )
                )
            )
            if configuration.summary.passed_case_ids != passed_case_ids:
                raise ValueError("configuration summary passed cases must match evaluations")

        generation_by_case = {
            (generation.configuration, generation.case_id): generation
            for generation in generations.values()
        }
        expected_failed = tuple(
            (generation.configuration, generation.case_id)
            for generation in generations.values()
            if generation.status == "provider_error"
            or any(
                evaluation.generation_id == generation.generation_id
                and evaluation.status != "passed"
                for evaluation in self.evaluations
            )
        )
        actual_failed = tuple((case.configuration, case.case_id) for case in self.failed_cases)
        if len(set(actual_failed)) != len(actual_failed) or actual_failed != expected_failed:
            raise ValueError("failed_cases must stably match non-passing report evidence")
        for case in self.failed_cases:
            generation = generation_by_case.get((case.configuration, case.case_id))
            if generation is None:
                raise ValueError("failed case must reference a report generation")
            if case.provider_error != generation.provider_error:
                raise ValueError("failed-case provider error must match generation evidence")
            if (
                case.actual != generation.normalized_response
                or case.raw_response != generation.raw_response
            ):
                raise ValueError("failed-case responses must match generation evidence")
            expected_case_evaluations = tuple(
                sorted(
                    (
                        evaluation
                        for evaluation in self.evaluations
                        if evaluation.generation_id == generation.generation_id
                    ),
                    key=lambda evaluation: evaluation.evaluator,
                )
            )
            if case.evaluations != expected_case_evaluations:
                raise ValueError("failed-case evaluations must match report evaluation evidence")
        return self

    @property
    def baseline(self) -> ConfigurationSummary:
        return self.baseline_summary

    @property
    def candidate(self) -> ConfigurationSummary:
        return self.candidate_summary


def _config(manifest: LoadedManifest | ExperimentConfig) -> ExperimentConfig:
    return manifest.config if isinstance(manifest, LoadedManifest) else manifest


def _report_generation(record: GenerationRecord) -> ReportGeneration:
    return ReportGeneration(
        generation_id=record.generation_id,
        configuration=record.configuration,
        case_id=record.case_id,
        provider=record.provider,
        model=record.model,
        resolved_model=record.resolved_model,
        origin=record.origin,
        status=record.status,
        started_at=record.started_at,
        ended_at=record.ended_at,
        latency_ms=record.latency_ms,
        usage=record.usage,
        estimated_cost_usd=record.estimated_cost_usd,
        normalized_response=record.normalized_response,
        raw_response=record.raw_response,
        provider_error=record.error,
    )


def _report_configuration(
    config: ExperimentConfig,
    name: str,
    records: Iterable[GenerationRecord],
    summary: ConfigurationSummary,
) -> ReportConfiguration:
    records = tuple(records)
    return ReportConfiguration(
        name=name,
        provider=config.configurations[name].provider,
        model=config.configurations[name].model,
        prompt=config.configurations[name].prompt,
        inference_parameters=config.configurations[name].inference_parameters,
        provider_options=(
            config.configurations[name].provider_options.model_dump(mode="json")
            if config.configurations[name].provider_options is not None
            else {}
        ),
        generation_count=len(records),
        status_counts=dict(Counter(record.status for record in records)),
        origin_counts=dict(Counter(record.origin for record in records)),
        generations=tuple(_report_generation(record) for record in records),
        summary=summary,
    )


def _failed_cases(
    dataset: DatasetSnapshot,
    generations: Iterable[GenerationRecord],
    evaluations: Iterable[EvaluationResult],
    expected_evaluators: tuple[str, ...],
) -> tuple[FailedCaseReport, ...]:
    cases = {case.id: case for case in dataset.cases}
    by_generation: dict[str, list[EvaluationResult]] = {}
    for evaluation in evaluations:
        by_generation.setdefault(evaluation.generation_id, []).append(evaluation)
    failed: list[FailedCaseReport] = []
    for generation in generations:
        case = cases[generation.case_id]
        results = tuple(
            sorted(by_generation.get(generation.generation_id, ()), key=lambda x: x.evaluator)
        )
        if (
            generation.status == "success"
            and {result.evaluator for result in results} == set(expected_evaluators)
            and all(result.status == "passed" for result in results)
        ):
            continue
        failed.append(
            FailedCaseReport(
                configuration=generation.configuration,
                case_id=generation.case_id,
                tags=case.tags,
                description=case.description,
                expected=case.expected,
                actual=generation.normalized_response,
                raw_response=generation.raw_response,
                provider_error=generation.error,
                evaluations=results,
            )
        )
    return tuple(failed)


def build_experiment_report(
    run: ExperimentRun,
    evaluations: Iterable[EvaluationResult],
    analysis: ExperimentAnalysis,
) -> ExperimentReport:
    """Build one report model from stored execution and analysis results."""
    config = run.manifest.config
    evaluations = tuple(evaluations)
    if not run.generations:
        raise ValueError("cannot build a report without generation records")
    started_at = min(record.started_at for record in run.generations)
    ended_at = max(record.ended_at for record in run.generations)
    by_configuration = {
        name: tuple(record for record in run.generations if record.configuration == name)
        for name in ("baseline", "candidate")
    }
    return ExperimentReport(
        evalforge_version=__version__,
        run_id=run.run_id,
        experiment=config.name,
        manifest=config,
        manifest_digest=run.manifest.digest,
        dataset_version=run.dataset.version,
        dataset_digest=run.dataset.digest,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=(ended_at - started_at).total_seconds() * 1000,
        configurations=(
            _report_configuration(
                config, "baseline", by_configuration["baseline"], analysis.baseline
            ),
            _report_configuration(
                config, "candidate", by_configuration["candidate"], analysis.candidate
            ),
        ),
        evaluators=tuple(
            ReportEvaluator(name=spec.type, version=BUILTIN_EVALUATOR_VERSIONS[spec.type])
            for spec in config.evaluators
        ),
        evaluations=evaluations,
        baseline_summary=analysis.baseline,
        candidate_summary=analysis.candidate,
        regression=analysis.regression,
        gates=analysis.gates,
        failed_cases=_failed_cases(
            run.dataset,
            run.generations,
            evaluations,
            tuple(spec.type for spec in config.evaluators),
        ),
    )


def _json_value(value: Any) -> str:
    return json.dumps(thaw_json(value), ensure_ascii=False, sort_keys=True, default=str)


def _json_or_unavailable(value: Any) -> str:
    return _json_value(value) if value is not None else "unavailable"


def _markdown_cell(value: Any) -> str:
    """Escape text for a Markdown table cell without changing its meaning."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


def _markdown_inline(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("\n", "<br>")


def _number(value: Any) -> str:
    return "unavailable" if value is None else str(value)


def render_markdown(report: ExperimentReport) -> str:
    """Render Markdown exclusively from the already-built report model."""
    lines = [
        f"# EvalForge report: {_markdown_inline(report.experiment)}",
        "",
        f"**Decision:** `{report.gates.decision.upper()}`",
        "",
        f"- Run: `{report.run_id}`",
        f"- Manifest digest: `{report.manifest_digest}`",
        f"- Dataset: version `{report.dataset_version}`, digest `{report.dataset_digest}`",
        "",
        "## Configuration comparison",
        "",
        "| Configuration | Provider | Model | Cases passed | Schema validity | "
        "Field accuracy | P95 latency (ms) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for summary in (report.baseline_summary, report.candidate_summary):
        configuration = next(
            item for item in report.configurations if item.name == summary.configuration
        )
        schema_score = summary.metric("schema_validity")
        field_score = summary.metric("field_accuracy")
        lines.append(
            f"| {_markdown_cell(summary.configuration)} | "
            f"{_markdown_cell(configuration.provider)} | "
            f"{_markdown_cell(configuration.model)} | "
            f"{summary.case_pass_count}/{summary.attempted_generations} | "
            f"{_number(schema_score.score if schema_score else None)} | "
            f"{_number(field_score.score if field_score else None)} | "
            f"{_number(summary.latency.p95_ms)} |"
        )
    lines.extend(
        [
            "",
            "## Metric deltas",
            "",
            "| Metric | Baseline | Candidate | Delta | Relative delta |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, delta in report.regression.metrics.items():
        lines.append(
            f"| {name} | {_number(delta.baseline)} | {_number(delta.candidate)} | "
            f"{_number(delta.delta)} | {_number(delta.relative_delta)} |"
        )
    lines.extend(
        [
            "",
            "## Quality gates",
            "",
            "| Metric | Rule | Observed | Threshold | Result | Reason |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for rule in report.gates.rules:
        lines.append(
            f"| {_markdown_cell(rule.metric)} | {_markdown_cell(rule.rule)} | "
            f"{_number(rule.observed)} | "
            f"{_number(rule.threshold)} | "
            f"{'PASS' if rule.passed else 'FAIL'} | {_markdown_cell(rule.reason)} |"
        )
    lines.extend(["", "### Gate failures", ""])
    if report.gates.failures:
        lines.extend(
            f"- **{_markdown_inline(failure.metric)} / {_markdown_inline(failure.rule)}:** "
            f"{_markdown_inline(failure.reason)}"
            for failure in report.gates.failures
        )
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            "## Case transitions",
            "",
            f"- Newly failing: {', '.join(report.regression.newly_failing) or 'None'}",
            f"- Newly passing: {', '.join(report.regression.newly_passing) or 'None'}",
            "",
            "## Failed cases",
            "",
        ]
    )
    if not report.failed_cases:
        lines.append("None.")
    else:
        for case in report.failed_cases:
            lines.extend(
                [
                    f"### `{_markdown_inline(case.configuration)}` / "
                    f"`{_markdown_inline(case.case_id)}`",
                    f"Tags: {_markdown_inline(', '.join(case.tags) or 'None')}",
                    f"Description: {_markdown_inline(case.description or 'None')}",
                    f"Expected: `{_markdown_inline(_json_value(case.expected))}`",
                    f"Actual: `{_markdown_inline(_json_or_unavailable(case.actual))}`",
                    f"Raw response: `{_markdown_inline(_json_or_unavailable(case.raw_response))}`",
                ]
            )
            if case.provider_error is not None:
                lines.append(
                    f"Provider error: `{_markdown_inline(_json_value(case.provider_error))}`"
                )
            for evaluation in case.evaluations:
                lines.append(
                    f"- Evaluator `{_markdown_inline(evaluation.evaluator)}` "
                    f"v`{_markdown_inline(evaluation.evaluator_version)}`: "
                    f"`{_markdown_inline(evaluation.status)}`, "
                    f"score `{_number(evaluation.score)}` - {_markdown_inline(evaluation.reason)}"
                )
                if evaluation.details:
                    lines.append(
                        f"  Details: `{_markdown_inline(_json_value(evaluation.details))}`"
                    )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
