"""Deterministic expected-field comparison with structured mismatches."""

from __future__ import annotations

from evalforge.dataset import TestCase
from evalforge.evaluators.base import EvaluationResult, make_evaluation_id
from evalforge.evaluators.common import (
    flatten_actual,
    flatten_expected,
    get_path,
    json_pointer,
    parse_generation_output,
    values_equal,
)
from evalforge.json_types import thaw_json
from evalforge.models import GenerationRecord


class FieldAccuracyEvaluator:
    """Compare expected leaf fields, retaining missing/mismatched/extra details."""

    name = "field_accuracy"
    version = "1.0"
    numeric_tolerance = 1e-6  # finite values within this absolute tolerance match

    def evaluate(self, generation: GenerationRecord, case: TestCase) -> EvaluationResult:
        evaluation_id = make_evaluation_id(generation, self.name, self.version)
        base = dict(
            evaluation_id=evaluation_id,
            generation_id=generation.generation_id,
            case_id=case.id,
            evaluator=self.name,
            evaluator_version=self.version,
        )
        if generation.status == "provider_error":
            return EvaluationResult(
                **base,
                status="not_evaluated",
                reason="provider error; generation was not evaluated",
            )
        output, parse_error = parse_generation_output(generation)
        if parse_error:
            return EvaluationResult(
                **base,
                status="failed",
                score=0.0,
                reason=parse_error,
                details={"kind": "json_parse_error"},
            )
        expected = flatten_expected(thaw_json(case.expected))
        actual_paths = flatten_actual(output)
        mismatches: list[dict[str, object]] = []
        correct = 0
        for path, expected_value in expected.items():
            present, actual_value = get_path(output, path)
            if present and values_equal(expected_value, actual_value, self.numeric_tolerance):
                correct += 1
                continue
            mismatches.append(
                {
                    "path": json_pointer(path),
                    "kind": "missing" if not present else "mismatch",
                    "expected": expected_value,
                    "actual": actual_value if present else None,
                }
            )
        extra_fields = tuple(sorted(json_pointer(path) for path in actual_paths - set(expected)))
        score = correct / len(expected) if expected else 1.0
        details = {
            "expected_fields": len(expected),
            "correct_fields": correct,
            "mismatches": tuple(mismatches),
            "extra_fields": extra_fields,
            "numeric_tolerance": self.numeric_tolerance,
        }
        passed = not mismatches
        return EvaluationResult(
            **base,
            status="passed" if passed else "failed",
            score=score,
            reason="all expected fields match"
            if passed
            else "one or more expected fields do not match",
            details=details,
        )
