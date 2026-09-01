"""Immutable domain records produced by experiment execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalforge.json_types import freeze_json
from evalforge.providers.base import (
    NormalizedRequest,
    ProviderErrorDetail,
    ProviderResponse,
    UsageMetadata,
)


class GenerationRecord(BaseModel):
    """One provider attempt, including failures, captured before evaluation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    generation_id: str = Field(min_length=1)
    experiment: str = Field(min_length=1)
    configuration: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    normalized_request: NormalizedRequest
    resolved_model: str | None = Field(default=None, min_length=1)
    raw_response: Any | None = None
    normalized_response: Any | None = None
    usage: UsageMetadata | None = None
    estimated_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    started_at: datetime
    ended_at: datetime
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    status: Literal["success", "provider_error"]
    origin: Literal["fresh", "cache", "replay"] = "fresh"
    error: ProviderErrorDetail | None = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> GenerationRecord:
        """Keep provider outcomes and timing internally consistent."""
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")
        if self.status == "success" and self.error is not None:
            raise ValueError("successful generation cannot contain a provider error")
        if self.status == "provider_error":
            if self.error is None:
                raise ValueError("provider_error generation must contain an error")
            if self.normalized_response is not None or self.raw_response is not None:
                raise ValueError("provider_error generation cannot contain a response")
            if self.usage is not None or self.estimated_cost_usd is not None:
                raise ValueError("provider_error generation cannot contain usage or cost")
        return self

    @model_validator(mode="after")
    def validate_request_linkage(self) -> GenerationRecord:
        """Ensure denormalized identity fields agree with the request."""
        for record_field, request_field in (
            ("experiment", "experiment"),
            ("configuration", "configuration"),
            ("case_id", "case_id"),
            ("model", "model"),
        ):
            record_value = getattr(self, record_field)
            request_value = getattr(self.normalized_request, request_field)
            if record_value != request_value:
                raise ValueError(f"{record_field} must match normalized_request.{request_field}")
        return self

    @classmethod
    def from_provider_response(
        cls, *, response: ProviderResponse | None = None, **kwargs: Any
    ) -> GenerationRecord:
        """Build a record while retaining both provider response forms."""
        if response is not None:
            kwargs.update(
                raw_response=response.raw_output
                if response.raw_output is not None
                else response.output,
                normalized_response=response.output,
                usage=response.usage,
                estimated_cost_usd=response.estimated_cost_usd,
                resolved_model=response.resolved_model,
            )
        return cls(**kwargs)

    @property
    def request(self) -> NormalizedRequest:
        """Compatibility alias for the normalized request."""
        return self.normalized_request

    @property
    def response(self) -> ProviderResponse | None:
        """Compatibility view of the normalized response metadata."""
        if self.normalized_response is None and self.raw_response is None:
            return None
        return ProviderResponse(
            output=self.normalized_response,
            raw_output=self.raw_response,
            resolved_model=self.resolved_model,
            usage=self.usage,
            estimated_cost_usd=self.estimated_cost_usd,
        )

    @field_validator("raw_response", "normalized_response", mode="before")
    @classmethod
    def freeze_responses(cls, value: Any) -> Any:
        return freeze_json(value) if value is not None else None

    def model_dump_jsonl(self) -> str:
        """Serialize this record as one portable JSON object line."""
        import json

        from evalforge.json_types import thaw_json

        return json.dumps(
            thaw_json(self.model_dump(mode="python")),
            ensure_ascii=False,
            default=lambda value: value.isoformat(),
        )
