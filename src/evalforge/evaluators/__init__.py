"""Built-in deterministic evaluators and evaluation orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from evalforge.artifacts import (
    read_dataset_snapshot,
    read_generations,
    read_manifest_snapshot,
    write_evaluations,
)
from evalforge.config import EvaluatorConfig, ExperimentConfig, LoadedManifest
from evalforge.dataset import DatasetSnapshot
from evalforge.evaluators.base import (
    EvaluationResult,
    Evaluator,
    EvaluatorErrorDetail,
    make_evaluation_id,
)
from evalforge.evaluators.field_accuracy import FieldAccuracyEvaluator
from evalforge.evaluators.json_schema import JsonSchemaEvaluator
from evalforge.models import GenerationRecord

BUILTIN_EVALUATOR_VERSIONS = {
    JsonSchemaEvaluator.name: JsonSchemaEvaluator.version,
    FieldAccuracyEvaluator.name: FieldAccuracyEvaluator.version,
}

__all__ = [
    "EvaluationInputError",
    "EvaluationResult",
    "Evaluator",
    "EvaluatorErrorDetail",
    "BUILTIN_EVALUATOR_VERSIONS",
    "FieldAccuracyEvaluator",
    "JsonSchemaEvaluator",
    "evaluate_experiment",
    "evaluate_generations",
    "make_evaluation_id",
]


class EvaluationInputError(ValueError):
    """Raised when stored snapshots do not describe one coherent experiment."""


def _config(manifest: LoadedManifest | ExperimentConfig | Path) -> ExperimentConfig:
    if isinstance(manifest, Path):
        return read_manifest_snapshot(manifest)
    return manifest.config if isinstance(manifest, LoadedManifest) else manifest


def _error_result(
    generation: GenerationRecord,
    spec: EvaluatorConfig,
    error: Exception,
    evaluator_version: str = "unknown",
) -> EvaluationResult:
    name = spec.type
    return EvaluationResult(
        evaluation_id=make_evaluation_id(generation, name, evaluator_version),
        generation_id=generation.generation_id,
        case_id=generation.case_id,
        evaluator=name,
        evaluator_version=evaluator_version,
        status="evaluator_error",
        reason="evaluator raised an unexpected exception",
        error=EvaluatorErrorDetail(
            type=type(error).__name__, message=str(error) or type(error).__name__
        ),
    )


def _validate_inputs(
    config: ExperimentConfig,
    dataset: DatasetSnapshot,
    generations: tuple[GenerationRecord, ...],
) -> None:
    """Reject mixed/corrupt snapshots before evaluator implementation code runs."""
    if dataset.version != config.dataset.version:
        raise EvaluationInputError(
            f"dataset version mismatch: manifest expects {config.dataset.version!r}, "
            f"received {dataset.version!r}"
        )
    case_map = {case.id: case for case in dataset.cases}
    if len(case_map) != len(dataset.cases):
        raise EvaluationInputError("dataset contains duplicate case IDs")
    generation_ids: set[str] = set()
    generation_keys: set[tuple[str, str]] = set()
    for generation in generations:
        if generation.generation_id in generation_ids:
            raise EvaluationInputError(f"duplicate generation ID: {generation.generation_id!r}")
        generation_ids.add(generation.generation_id)
        if generation.case_id not in case_map:
            raise EvaluationInputError(
                f"generation references unknown case ID: {generation.case_id!r}"
            )
        if generation.configuration not in config.configurations:
            raise EvaluationInputError(
                f"generation references unknown configuration: {generation.configuration!r}"
            )
        key = (generation.configuration, generation.case_id)
        if key in generation_keys:
            raise EvaluationInputError(f"duplicate generation for configuration/case: {key!r}")
        generation_keys.add(key)
        model_config = config.configurations[generation.configuration]
        request = generation.normalized_request
        expected = {
            "experiment": config.name,
            "configuration": generation.configuration,
            "case_id": generation.case_id,
            "provider": model_config.provider,
            "model": model_config.model,
            "prompt": model_config.prompt,
            "inference_parameters": model_config.inference_parameters,
            "provider_options": (
                model_config.provider_options.model_dump(mode="json")
                if model_config.provider_options is not None
                else {}
            ),
            "output_schema": config.output_schema,
        }
        actual = {
            "experiment": generation.experiment,
            "configuration": generation.configuration,
            "case_id": generation.case_id,
            "provider": generation.provider,
            "model": generation.model,
            "prompt": request.prompt,
            "inference_parameters": request.inference_parameters,
            "provider_options": request.provider_options,
            "output_schema": request.output_schema,
        }
        for field, expected_value in expected.items():
            if actual[field] != expected_value:
                raise EvaluationInputError(
                    f"stored generation {generation.generation_id!r} has mismatched {field}"
                )
        case = case_map[generation.case_id]
        if request.input != case.input:
            raise EvaluationInputError(
                f"stored generation {generation.generation_id!r} input does not match dataset case"
            )


def evaluate_generations(
    manifest: LoadedManifest | ExperimentConfig | Path,
    dataset: DatasetSnapshot | Path,
    generations: Iterable[GenerationRecord] | Path,
    *,
    artifact_path: Path | None = None,
    evaluator_overrides: Mapping[str, Evaluator] | None = None,
    evaluator_factory: Callable[[EvaluatorConfig], Evaluator] | None = None,
) -> tuple[EvaluationResult, ...]:
    """Evaluate stored generations only; this function has no provider access."""
    config = _config(manifest)
    resolved_dataset = (
        read_dataset_snapshot(dataset, version=config.dataset.version)
        if isinstance(dataset, Path)
        else dataset
    )
    stored = read_generations(generations) if isinstance(generations, Path) else tuple(generations)
    _validate_inputs(config, resolved_dataset, stored)
    cases = {case.id: case for case in resolved_dataset.cases}
    results: list[EvaluationResult] = []
    for generation in stored:
        case = cases.get(generation.case_id)
        for spec in config.evaluators:
            evaluator: Evaluator | None = None
            try:
                if evaluator_overrides and spec.type in evaluator_overrides:
                    evaluator = evaluator_overrides[spec.type]
                elif evaluator_factory is not None:
                    evaluator = evaluator_factory(spec)
                elif spec.type == "json_schema":
                    evaluator = JsonSchemaEvaluator()
                elif spec.type == "field_accuracy":
                    evaluator = FieldAccuracyEvaluator()
                else:
                    raise ValueError(f"unsupported evaluator {spec.type!r}")
                if case is None:
                    raise ValueError(f"generation references unknown case {generation.case_id!r}")
                results.append(evaluator.evaluate(generation, case))
            except Exception as error:  # isolate one evaluator/case failure
                results.append(
                    _error_result(
                        generation,
                        spec,
                        error,
                        getattr(evaluator, "version", "unknown"),
                    )
                )
    final = tuple(results)
    if artifact_path is not None:
        write_evaluations(artifact_path, final)
    return final


def evaluate_experiment(*args: Any, **kwargs: Any) -> tuple[EvaluationResult, ...]:
    """Public orchestration alias for evaluating stored generations."""
    return evaluate_generations(*args, **kwargs)
