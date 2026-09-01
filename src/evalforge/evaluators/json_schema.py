"""Deterministic JSON parsing and JSON Schema evaluation."""

from __future__ import annotations

import jsonschema

from evalforge.dataset import TestCase
from evalforge.evaluators.base import EvaluationResult, make_evaluation_id
from evalforge.evaluators.common import parse_generation_output
from evalforge.json_types import thaw_json
from evalforge.models import GenerationRecord


class JsonSchemaEvaluator:
    """Check that a generation is valid JSON and satisfies its request schema."""

    name = "json_schema"
    version = "1.0"

    def evaluate(self, generation: GenerationRecord, case: TestCase) -> EvaluationResult:
        evaluation_id = make_evaluation_id(generation, self.name, self.version)
        if generation.status == "provider_error":
            return EvaluationResult(
                evaluation_id=evaluation_id,
                generation_id=generation.generation_id,
                case_id=case.id,
                evaluator=self.name,
                evaluator_version=self.version,
                status="not_evaluated",
                reason="provider error; generation was not evaluated",
            )
        output, parse_error = parse_generation_output(generation)
        if parse_error:
            return EvaluationResult(
                evaluation_id=evaluation_id,
                generation_id=generation.generation_id,
                case_id=case.id,
                evaluator=self.name,
                evaluator_version=self.version,
                status="failed",
                reason=parse_error,
                details={"kind": "json_parse_error"},
                score=0.0,
            )
        schema = thaw_json(generation.normalized_request.output_schema)
        validator = jsonschema.validators.validator_for(schema)(schema)
        errors = sorted(
            validator.iter_errors(output),
            key=lambda error: tuple(str(part) for part in error.path),
        )
        details = {
            "schema_errors": tuple(
                {
                    "path": ".".join(str(part) for part in error.path),
                    "message": error.message,
                }
                for error in errors
            )
        }
        if errors:
            return EvaluationResult(
                evaluation_id=evaluation_id,
                generation_id=generation.generation_id,
                case_id=case.id,
                evaluator=self.name,
                evaluator_version=self.version,
                status="failed",
                score=0.0,
                reason="output does not satisfy the configured JSON Schema",
                details=details,
            )
        return EvaluationResult(
            evaluation_id=evaluation_id,
            generation_id=generation.generation_id,
            case_id=case.id,
            evaluator=self.name,
            evaluator_version=self.version,
            status="passed",
            score=1.0,
            reason="output is valid JSON and satisfies the configured JSON Schema",
            details=details,
        )
