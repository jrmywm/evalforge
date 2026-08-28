"""Validated experiment-manifest models and loading functions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import jsonschema
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from evalforge.json_types import (
    FrozenDict,
    canonical_digest,
    freeze_json,
    thaw_json,
)

KNOWN_METRIC_NAMES: frozenset[str] = frozenset(
    {"schema_validity", "field_accuracy", "p95_latency_ms"}
)

METRIC_EVALUATOR_REQUIREMENTS: dict[str, str | None] = {
    "schema_validity": "json_schema",
    "field_accuracy": "field_accuracy",
    "p95_latency_ms": None,
}


class ManifestError(ValueError):
    """Raised when an experiment manifest cannot be loaded or validated."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """YAML safe loader that rejects duplicate and invalid mapping keys."""


def _construct_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        try:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int, float, bool)):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"unsupported mapping key type: {type(key).__name__}",
                    key_node.start_mark,
                )
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"unhashable or invalid key: {error}",
                key_node.start_mark,
            ) from error
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


class DatasetReference(BaseModel):
    """Location and declared version of a dataset used by an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    path: str = Field(min_length=1)
    version: str = Field(min_length=1)

    @field_validator("path", "version", mode="after")
    @classmethod
    def validate_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cannot be whitespace-only")
        return value


class ModelConfig(BaseModel):
    """A named model configuration to compare in an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str = ""
    inference_parameters: FrozenDict = Field(default_factory=FrozenDict)

    @field_validator("provider", "model", mode="after")
    @classmethod
    def validate_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cannot be whitespace-only")
        return value

    @field_validator("inference_parameters", mode="before")
    @classmethod
    def freeze_inference_parameters(cls, value: Any) -> FrozenDict:
        if value is None:
            return FrozenDict()
        return freeze_json(value, path="inference_parameters")


class EvaluatorConfig(BaseModel):
    """A deterministic evaluator selected by an experiment."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: Literal["json_schema", "field_accuracy"]


class QualityGate(BaseModel):
    """Thresholds that determine whether a candidate may replace a baseline."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    maximum_regression: float | None = Field(default=None, ge=0, allow_inf_nan=False)

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

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1)
    dataset: DatasetReference
    configurations: FrozenDict
    output_schema: FrozenDict
    evaluators: tuple[EvaluatorConfig, ...] = Field(min_length=1)
    quality_gates: FrozenDict = Field(min_length=1)

    @field_validator("name", mode="after")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be whitespace-only")
        return value

    @field_validator("configurations", mode="before")
    @classmethod
    def validate_and_freeze_configurations(cls, value: Any) -> FrozenDict:
        if not isinstance(value, Mapping):
            raise ValueError("configurations must be a mapping")
        validated: dict[str, ModelConfig] = {}
        for name, config_data in value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"configuration names must be non-empty strings, got {name!r}")
            if isinstance(config_data, ModelConfig):
                validated[name] = config_data
            elif isinstance(config_data, dict):
                validated[name] = ModelConfig.model_validate(config_data)
            else:
                raise ValueError(
                    f"invalid model configuration for {name!r}: {type(config_data).__name__}"
                )
        return FrozenDict(validated)

    @field_validator("output_schema", mode="before")
    @classmethod
    def validate_and_freeze_output_schema(cls, value: Any) -> FrozenDict:
        if not isinstance(value, Mapping):
            raise ValueError("output_schema must be a mapping")
        frozen = freeze_json(value, path="output_schema")
        thawed = thaw_json(frozen)
        if not thawed:
            raise ValueError("output_schema cannot be empty")
        if "$schema" in thawed:
            schema_uri = thawed["$schema"]
            if not isinstance(schema_uri, str) or not jsonschema.validators.validator_for(
                thawed, default=None
            ):
                raise ValueError(f"unsupported or invalid $schema dialect: {schema_uri!r}")
        try:
            validator_cls = jsonschema.validators.validator_for(thawed)
            validator_cls.check_schema(thawed)
        except jsonschema.exceptions.SchemaError as error:
            raise ValueError(f"invalid JSON Schema in output_schema: {error.message}") from error
        except Exception as error:
            raise ValueError(f"invalid JSON Schema in output_schema: {error}") from error
        return frozen

    @field_validator("evaluators", mode="before")
    @classmethod
    def validate_and_freeze_evaluators(cls, value: Any) -> tuple[Any, ...]:
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return value

    @field_validator("quality_gates", mode="before")
    @classmethod
    def validate_and_freeze_quality_gates(cls, value: Any) -> FrozenDict:
        if not isinstance(value, Mapping):
            raise ValueError("quality_gates must be a mapping")
        validated: dict[str, QualityGate] = {}
        for name, gate_data in value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"quality gate names must be non-empty strings, got {name!r}")
            if isinstance(gate_data, QualityGate):
                validated[name] = gate_data
            elif isinstance(gate_data, dict):
                validated[name] = QualityGate.model_validate(gate_data)
            else:
                raise ValueError(f"invalid quality gate for {name!r}: {type(gate_data).__name__}")
        return FrozenDict(validated)

    @model_validator(mode="after")
    def validate_manifest_rules(self) -> ExperimentConfig:
        required_names = {"baseline", "candidate"}
        actual_names = set(self.configurations)
        if actual_names != required_names:
            raise ValueError(
                "configurations must contain exactly 'baseline' and 'candidate' "
                f"(received {sorted(actual_names)!r})"
            )

        evaluator_types = [e.type for e in self.evaluators]
        if len(evaluator_types) != len(set(evaluator_types)):
            raise ValueError(f"duplicate evaluator types are not allowed: {evaluator_types}")

        evaluator_set = set(evaluator_types)
        for gate_name in self.quality_gates:
            if gate_name not in KNOWN_METRIC_NAMES:
                raise ValueError(f"unknown quality gate metric: {gate_name!r}")
            required_evaluator = METRIC_EVALUATOR_REQUIREMENTS.get(gate_name)
            if required_evaluator and required_evaluator not in evaluator_set:
                raise ValueError(
                    f"quality gate {gate_name!r} requires evaluator {required_evaluator!r}"
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
        raw_data = yaml.load(raw_bytes, Loader=_UniqueKeySafeLoader)
    except (OSError, UnicodeDecodeError) as error:
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
        digest=canonical_digest(config.model_dump(mode="json")),
        config=config,
    )
