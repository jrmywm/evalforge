"""Milestone 2 experiment execution and generation artifact orchestration."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalforge.artifacts import (
    ArtifactError,
    write_dataset_snapshot,
    write_generations,
    write_manifest_snapshot,
)
from evalforge.config import LoadedManifest, ModelConfig
from evalforge.dataset import DatasetSnapshot, load_dataset
from evalforge.json_types import canonical_digest
from evalforge.models import GenerationRecord
from evalforge.providers import (
    DeterministicMockProvider,
    NormalizedRequest,
    OpenAICompatibleProvider,
    Provider,
    ProviderErrorDetail,
    ProviderResponse,
)


@dataclass(frozen=True)
class ExperimentRun:
    """The immutable result of an execution-only experiment run."""

    run_id: str
    artifact_dir: Path
    manifest: LoadedManifest
    dataset: DatasetSnapshot
    generations: tuple[GenerationRecord, ...]


ProviderFactory = Callable[[ModelConfig], Provider]
_INFRASTRUCTURE_ERROR_TYPES = frozenset({"authentication_error", "network_error", "timeout"})


class ExecutionError(ValueError):
    """Raised when an experiment cannot be safely started or configured."""


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_run_id(run_id: str) -> str:
    """Validate a run ID as one conservative, non-traversing path component."""
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_id in {".", ".."}
        or not _SAFE_RUN_ID.fullmatch(run_id)
        or Path(run_id).is_absolute()
    ):
        raise ExecutionError(
            "run_id must be one nonempty ASCII path component using only letters, "
            "digits, '.', '_' or '-'; traversal and separators are not allowed"
        )
    return run_id


def _default_provider(model_config: ModelConfig) -> Provider:
    if model_config.provider == "mock":
        return DeterministicMockProvider(model_config.model)
    if model_config.provider == "openai_compatible":
        return OpenAICompatibleProvider(model_config.model, options=model_config.provider_options)
    raise ExecutionError(f"unknown provider {model_config.provider!r}")


def _provider_for(
    model_config: ModelConfig,
    providers: Mapping[str, Provider] | None,
    provider_factory: ProviderFactory | None,
) -> Provider:
    if provider_factory is not None:
        return provider_factory(model_config)
    if providers and model_config.provider in providers:
        return providers[model_config.provider]
    return _default_provider(model_config)


def _error_detail(error: Exception) -> ProviderErrorDetail:
    error_type = getattr(error, "error_type", type(error).__name__)
    return ProviderErrorDetail(
        type=str(error_type),
        message=str(error) or type(error).__name__,
        retryable=bool(getattr(error, "retryable", False)),
        details=getattr(error, "details", {}),
    )


def _request_for(
    manifest: LoadedManifest,
    configuration: str,
    model_config: ModelConfig,
    case_id: str,
    input_data: Any,
) -> NormalizedRequest:
    return NormalizedRequest(
        experiment=manifest.config.name,
        configuration=configuration,
        case_id=case_id,
        model=model_config.model,
        prompt=model_config.prompt,
        input=input_data,
        output_schema=manifest.config.output_schema,
        inference_parameters=model_config.inference_parameters,
        provider_options=(
            model_config.provider_options.model_dump(mode="json")
            if model_config.provider_options is not None
            else {}
        ),
    )


def execute_experiment(
    manifest: LoadedManifest,
    dataset: DatasetSnapshot | None = None,
    *,
    artifact_root: Path | None = None,
    run_id: str | None = None,
    providers: Mapping[str, Provider] | None = None,
    provider_factory: ProviderFactory | None = None,
) -> ExperimentRun:
    """Execute both configurations against every case and persist snapshots.

    Provider exceptions are converted into ``provider_error`` records and do
    not stop subsequent configuration/case attempts.  No evaluation is done
    here; generation records are the complete Milestone 2 output.
    """
    resolved_dataset = dataset or load_dataset(manifest)
    resolved_run_id = (
        validate_run_id(run_id) if run_id is not None else _new_run_id(manifest.config.name)
    )
    root = (artifact_root or (manifest.path.parent / "artifacts")).resolve()
    artifact_dir = (root / resolved_run_id).resolve()
    if artifact_dir.parent != root:
        raise ExecutionError("resolved run artifact directory must be directly under artifact_root")
    try:
        artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ArtifactError(f"artifact run directory already exists: {artifact_dir}") from error

    records: list[GenerationRecord] = []
    circuit_errors: dict[str, ProviderErrorDetail] = {}
    for configuration in ("baseline", "candidate"):
        model_config = manifest.config.configurations[configuration]
        provider = _provider_for(model_config, providers, provider_factory)
        if (
            model_config.provider == "openai_compatible"
            and providers is None
            and provider_factory is None
        ):
            circuit_key = canonical_digest(
                {
                    "provider": model_config.provider,
                    "model": model_config.model,
                    "provider_options": request_options(model_config),
                }
            )
        else:
            circuit_key = configuration
        for case in resolved_dataset.cases:
            request = _request_for(manifest, configuration, model_config, case.id, case.input)
            generation_id = canonical_digest(
                {
                    "provider": model_config.provider,
                    "request": request.model_dump(mode="json"),
                }
            )
            started_at = datetime.now(UTC)
            started_clock = time.perf_counter()
            response: ProviderResponse | None = None
            error: ProviderErrorDetail | None = None
            status = "success"
            circuit_error = circuit_errors.get(circuit_key)
            if circuit_error is not None:
                status = "provider_error"
                details = dict(circuit_error.details)
                details["circuit_open"] = True
                error = ProviderErrorDetail(
                    type=circuit_error.type,
                    message=(
                        "provider circuit open after infrastructure failure: "
                        f"{circuit_error.message}"
                    ),
                    retryable=circuit_error.retryable,
                    details=details,
                )
            else:
                try:
                    response = provider.generate(request)
                    if not isinstance(response, ProviderResponse):
                        response = ProviderResponse.model_validate(response)
                except Exception as provider_error:  # isolation is an execution invariant
                    status = "provider_error"
                    error = _error_detail(provider_error)
                    if error.type in _INFRASTRUCTURE_ERROR_TYPES:
                        circuit_errors[circuit_key] = error
            ended_at = datetime.now(UTC)
            latency_ms = max((time.perf_counter() - started_clock) * 1000.0, 0.0)
            records.append(
                GenerationRecord(
                    generation_id=generation_id,
                    experiment=manifest.config.name,
                    configuration=configuration,
                    case_id=case.id,
                    provider=model_config.provider,
                    model=model_config.model,
                    normalized_request=request,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    status=status,
                    origin="fresh",
                    error=error,
                    **(
                        {
                            "raw_response": response.raw_output
                            if response is not None and response.raw_output is not None
                            else (response.output if response is not None else None),
                            "normalized_response": response.output
                            if response is not None
                            else None,
                            "resolved_model": response.resolved_model
                            if response is not None
                            else None,
                            "usage": response.usage if response is not None else None,
                            "estimated_cost_usd": response.estimated_cost_usd
                            if response is not None
                            else None,
                        }
                    ),
                )
            )

    # Write each snapshot through a same-directory temporary file and replace,
    # so readers cannot mistake a partially written artifact for a run.
    write_manifest_snapshot(artifact_dir / "manifest.snapshot.yaml", manifest.config)
    write_dataset_snapshot(artifact_dir / "dataset.snapshot.jsonl", resolved_dataset)
    write_generations(artifact_dir / "generations.jsonl", records)
    return ExperimentRun(
        run_id=resolved_run_id,
        artifact_dir=artifact_dir,
        manifest=manifest,
        dataset=resolved_dataset,
        generations=tuple(records),
    )


def request_options(model_config: ModelConfig) -> dict[str, Any]:
    """Return secret-free provider options for endpoint circuit identity."""
    return (
        model_config.provider_options.model_dump(mode="json")
        if model_config.provider_options is not None
        else {}
    )


def run_experiment(*args: Any, **kwargs: Any) -> ExperimentRun:
    """Backward-friendly alias for :func:`execute_experiment`."""
    return execute_experiment(*args, **kwargs)


def _new_run_id(name: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "-" for character in name
    )
    return f"{safe_name}-{timestamp}"
