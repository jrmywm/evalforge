"""Validated experiment-manifest models and loading functions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ManifestError(ValueError):
    """Raised when an experiment manifest cannot be loaded or validated."""


class DatasetReference(BaseModel):
    """Location and declared version of a dataset used by an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ModelConfig(BaseModel):
    """A named model configuration to compare in an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str = ""
    inference_parameters: dict[str, Any] = Field(default_factory=dict)


class EvaluatorConfig(BaseModel):
    """A deterministic evaluator selected by an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["json_schema", "field_accuracy"]


class QualityGate(BaseModel):
    """Thresholds that determine whether a candidate may replace a baseline."""

    model_config = ConfigDict(extra="forbid", strict=True)

    minimum: float | None = None
    maximum: float | None = None
    maximum_regression: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def requires_at_least_one_threshold(self) -> QualityGate:
        """Reject gates that cannot make a decision."""
        if self.minimum is None and self.maximum is None and self.maximum_regression is None:
            raise ValueError("must define at least one threshold")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot be greater than maximum")
        return self


class ExperimentConfig(BaseModel):
    """The complete, strictly validated manifest for one experiment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    dataset: DatasetReference
    configurations: dict[str, ModelConfig]
    output_schema: dict[str, Any]
    evaluators: list[EvaluatorConfig] = Field(min_length=1)
    quality_gates: dict[str, QualityGate] = Field(min_length=1)

    @model_validator(mode="after")
    def requires_baseline_and_candidate(self) -> ExperimentConfig:
        """Require the two configurations used by the MVP regression workflow."""
        required_names = {"baseline", "candidate"}
        actual_names = set(self.configurations)
        if actual_names != required_names:
            raise ValueError(
                "configurations must contain exactly 'baseline' and 'candidate' "
                f"(received {sorted(actual_names)!r})"
            )
        return self


class LoadedManifest(BaseModel):
    """A manifest together with its resolved source path and content digest."""

    model_config = ConfigDict(frozen=True)

    path: Path
    digest: str
    config: ExperimentConfig


def load_manifest(path: Path) -> LoadedManifest:
    """Load a YAML manifest and return a strictly validated representation."""
    resolved_path = path.expanduser().resolve()
    if not resolved_path.is_file():
        raise ManifestError(f"manifest does not exist: {resolved_path}")

    try:
        raw_bytes = resolved_path.read_bytes()
        raw_data = yaml.safe_load(raw_bytes)
    except OSError as error:
        raise ManifestError(f"could not read manifest {resolved_path}: {error}") from error
    except yaml.YAMLError as error:
        raise ManifestError(f"invalid YAML in manifest {resolved_path}: {error}") from error

    if not isinstance(raw_data, dict):
        raise ManifestError(f"manifest {resolved_path} must contain a YAML mapping")

    try:
        config = ExperimentConfig.model_validate(raw_data)
    except ValidationError as error:
        raise ManifestError(f"invalid manifest {resolved_path}: {error}") from error

    return LoadedManifest(
        path=resolved_path,
        digest=hashlib.sha256(raw_bytes).hexdigest(),
        config=config,
    )


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest for JSON-compatible data."""
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
