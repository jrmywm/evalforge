"""Provider boundary and normalized request/response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evalforge.json_types import FrozenDict, freeze_json


class NormalizedRequest(BaseModel):
    """Provider-independent input sent to a model provider."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    experiment: str = Field(min_length=1)
    configuration: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str = ""
    input: FrozenDict = Field(min_length=1)
    output_schema: FrozenDict = Field(min_length=1)
    inference_parameters: FrozenDict = Field(default_factory=FrozenDict)
    provider_options: FrozenDict = Field(default_factory=FrozenDict)
    seed: int | None = None

    @field_validator(
        "input", "output_schema", "inference_parameters", "provider_options", mode="before"
    )
    @classmethod
    def freeze_mapping(cls, value: Any) -> FrozenDict:
        return freeze_json(value)


class UsageMetadata(BaseModel):
    """Normalized token usage, when a provider can report it."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ProviderResponse(BaseModel):
    """Provider output normalized independently of a concrete SDK."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    output: Any
    raw_output: Any | None = None
    resolved_model: str | None = Field(default=None, min_length=1)
    usage: UsageMetadata | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("output", "raw_output", mode="before")
    @classmethod
    def freeze_output(cls, value: Any) -> Any:
        return freeze_json(value) if value is not None else None


class ProviderErrorDetail(BaseModel):
    """Structured, serializable details for a failed provider call."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    details: FrozenDict = Field(default_factory=FrozenDict)

    @field_validator("details", mode="before")
    @classmethod
    def freeze_details(cls, value: Any) -> FrozenDict:
        return freeze_json(value or {})


class Provider(Protocol):
    """Minimal provider interface used by the execution engine."""

    def generate(self, request: NormalizedRequest) -> ProviderResponse:
        """Generate one normalized response for a request."""


def utc_now() -> datetime:
    """Return an aware UTC timestamp for generation records."""
    return datetime.now().astimezone()
