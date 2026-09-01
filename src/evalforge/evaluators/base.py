"""Evaluator protocol and immutable evaluation result contracts."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evalforge.dataset import TestCase
from evalforge.json_types import FrozenDict, canonical_digest, freeze_json
from evalforge.models import GenerationRecord


def make_evaluation_id(generation: GenerationRecord, evaluator: str, version: str) -> str:
    """Create a stable ID that separates evaluator implementations and versions."""
    return canonical_digest(
        {
            "generation_id": generation.generation_id,
            "evaluator": evaluator,
            "version": version,
        }
    )


class EvaluatorErrorDetail(BaseModel):
    """Structured details for an evaluator implementation failure."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: FrozenDict = Field(default_factory=FrozenDict)

    @field_validator("details", mode="before")
    @classmethod
    def freeze_details(cls, value: Any) -> FrozenDict:
        return freeze_json(value or {})


class EvaluationResult(BaseModel):
    """One evaluator decision for one stored generation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    evaluation_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    evaluator: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    status: Literal["passed", "failed", "not_evaluated", "evaluator_error"]
    score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1)
    details: FrozenDict = Field(default_factory=FrozenDict)
    error: EvaluatorErrorDetail | None = None

    @field_validator("details", mode="before")
    @classmethod
    def freeze_details(cls, value: Any) -> FrozenDict:
        return freeze_json(value or {})

    @model_validator(mode="after")
    def validate_result_state(self) -> EvaluationResult:
        """Prevent evaluator failures from looking like model failures."""
        if self.status in {"passed", "failed", "not_evaluated"} and self.error is not None:
            raise ValueError(f"{self.status} evaluation cannot contain evaluator error")
        if self.status == "passed" and self.score is None:
            raise ValueError("passed evaluation must contain a score")
        if self.status == "failed" and self.score is None:
            raise ValueError("failed evaluation must contain a score")
        if self.status == "not_evaluated" and self.score is not None:
            raise ValueError("not_evaluated evaluation cannot contain a score")
        if self.status == "evaluator_error":
            if self.error is None:
                raise ValueError("evaluator_error result must contain an error")
            if self.score is not None:
                raise ValueError("evaluator_error result cannot contain a score")
        return self


class Evaluator(Protocol):
    """A deterministic evaluator operating on stored generation records."""

    name: str
    version: str

    def evaluate(self, generation: GenerationRecord, case: TestCase) -> EvaluationResult:
        """Evaluate one generation without invoking a provider."""
