"""Milestone 3 deterministic evaluator and evaluation-artifact tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalforge.artifacts import ArtifactError, read_evaluations, write_evaluations
from evalforge.config import load_manifest
from evalforge.dataset import TestCase
from evalforge.engine import execute_experiment
from evalforge.evaluators import (
    EvaluationInputError,
    EvaluationResult,
    FieldAccuracyEvaluator,
    JsonSchemaEvaluator,
    evaluate_generations,
)
from evalforge.evaluators.common import flatten_expected, get_path, json_pointer, values_equal
from evalforge.providers import ProviderResponse


def write_example(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cases.jsonl").write_text(
        '{"id":"case-1","input":{"text":"invoice"},"expected":{"value":"x"}}\n'
        '{"id":"case-2","input":{"text":"invoice"},"expected":{"value":"y"}}\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "eval.yaml"
    manifest.write_text(
        """name: execution-test
dataset:
  path: cases.jsonl
  version: '1.0'
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
output_schema:
  type: object
  required: [value]
  properties:
    value:
      type: string
evaluators:
  - type: json_schema
  - type: field_accuracy
quality_gates:
  schema_validity:
    minimum: 0.0
""",
        encoding="utf-8",
    )
    return manifest


class FixedProvider:
    def __init__(self, output):
        self.output = output

    def generate(self, request):
        return ProviderResponse(output=self.output)


def run_one(tmp_path: Path, output, *, run_id: str = "generation"):
    manifest = load_manifest(write_example(tmp_path))
    run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id=run_id,
        provider_factory=lambda config: FixedProvider(output),
    )
    return manifest, run


def test_valid_json_and_field_output_pass(tmp_path: Path) -> None:
    manifest, run = run_one(tmp_path, {"value": "x"})
    case = run.dataset.cases[0]

    schema_result = JsonSchemaEvaluator().evaluate(run.generations[0], case)
    field_result = FieldAccuracyEvaluator().evaluate(run.generations[0], case)

    assert schema_result.status == "passed"
    assert schema_result.score == 1.0
    assert field_result.status == "passed"
    assert field_result.score == 1.0
    assert manifest.config.name == "execution-test"


@pytest.mark.parametrize("output", ["{bad", '{"value": NaN}', '{"value": 1, "value": 2}'])
def test_malformed_json_is_failed_not_evaluator_error(tmp_path: Path, output: str) -> None:
    _, run = run_one(tmp_path, output)
    case = run.dataset.cases[0]

    result = JsonSchemaEvaluator().evaluate(run.generations[0], case)
    field_result = FieldAccuracyEvaluator().evaluate(run.generations[0], case)

    assert result.status == "failed"
    assert result.error is None
    assert result.score == 0.0
    assert field_result.status == "failed"
    assert field_result.score == 0.0
    assert "JSON" in result.reason


def test_missing_mistyped_and_extra_fields_are_structured(tmp_path: Path) -> None:
    _, missing_run = run_one(tmp_path / "missing", {})
    _, extra_run = run_one(tmp_path / "extra", {"value": "x", "extra": True})
    _, mistyped_run = run_one(tmp_path / "mistyped", {"value": 1})
    evaluator = FieldAccuracyEvaluator()

    missing = evaluator.evaluate(missing_run.generations[0], missing_run.dataset.cases[0])
    extra = evaluator.evaluate(extra_run.generations[0], extra_run.dataset.cases[0])
    mistyped = evaluator.evaluate(mistyped_run.generations[0], mistyped_run.dataset.cases[0])

    assert missing.status == "failed"
    assert missing.score == 0.0
    assert missing.details["mismatches"][0]["kind"] == "missing"
    assert extra.status == "passed"
    assert extra.score == 1.0
    assert extra.details["extra_fields"] == ("/extra",)
    assert mistyped.status == "failed"
    assert mistyped.details["mismatches"][0]["kind"] == "mismatch"


def test_json_strings_are_parsed_and_numeric_comparison_is_tolerant() -> None:
    assert values_equal(1, 1.0000005)
    assert not values_equal(1, 1.01)
    assert not values_equal(True, 1)
    assert not values_equal("1", 1)
    assert values_equal(None, None)
    assert not values_equal(None, "null")
    assert values_equal([1, {"nested": ["x", True]}], [1.0000005, {"nested": ["x", True]}])
    assert not values_equal([1], [True])
    assert not values_equal([{"n": 1}], [{"n": True}])


def test_paths_use_tokens_internally_and_rfc6901_for_details(tmp_path: Path) -> None:
    case = TestCase(
        id="case-1",
        input={"text": "invoice"},
        expected={"a.b": {"c/d": {"e~f": 1}}},
    )
    output = {"a.b": {"c/d": {"e~f": 1}}, "a": {"b": {"c/d": {"e~f": 2}}}}
    _, special_run = run_one(tmp_path / "special", output)
    result = FieldAccuracyEvaluator().evaluate(special_run.generations[0], case)

    tokens = flatten_expected(case.expected)
    assert ("a.b", "c/d", "e~f") in tokens
    assert get_path(output, ("a.b", "c/d", "e~f")) == (True, 1)
    assert json_pointer(("a.b", "c/d", "e~f")) == "/a.b/c~1d/e~0f"
    assert result.status == "passed"
    assert result.details["extra_fields"] == ("/a/b/c~1d/e~0f",)


def test_provider_error_becomes_not_evaluated(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="provider-error",
        provider_factory=lambda config: FixedProvider(None),
    )
    # Replace the generated success with a real isolated provider error fixture
    # by using the existing deterministic provider's failure seam.
    from evalforge.providers import DeterministicMockProvider

    error_run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="provider-error-real",
        provider_factory=lambda config: DeterministicMockProvider(
            config.model, fail_case_ids={"case-1"}
        ),
    )
    results = evaluate_generations(manifest, error_run.dataset, error_run.generations)

    assert run.generations[0].status == "success"
    assert error_run.generations[0].status == "provider_error"
    assert results[0].status == "not_evaluated"
    assert results[0].score is None
    assert results[0].error is None


def test_evaluator_exception_isolated_from_other_evaluators(tmp_path: Path) -> None:
    _, run = run_one(tmp_path, {"value": "x"})

    class ExplodingEvaluator:
        name = "field_accuracy"
        version = "test"

        def evaluate(self, generation, case):
            raise RuntimeError("boom")

    results = evaluate_generations(
        load_manifest(tmp_path / "eval.yaml"),
        run.dataset,
        run.generations,
        evaluator_overrides={"field_accuracy": ExplodingEvaluator()},
    )

    assert len(results) == 8
    assert sum(result.status == "evaluator_error" for result in results) == 4
    assert sum(result.status == "passed" for result in results) == 4


def test_evaluation_ids_are_stable_and_collision_resistant(tmp_path: Path) -> None:
    manifest, run = run_one(tmp_path, {"value": "x"})
    first = evaluate_generations(manifest, run.dataset, run.generations)
    second = evaluate_generations(manifest, run.dataset, run.generations)

    assert [result.evaluation_id for result in first] == [result.evaluation_id for result in second]
    assert len({result.evaluation_id for result in first}) == len(first)
    assert first[0].evaluation_id != first[2].evaluation_id


def test_evaluation_artifact_round_trip_and_no_overwrite(tmp_path: Path) -> None:
    manifest, run = run_one(tmp_path, {"value": "x"})
    results = evaluate_generations(manifest, run.dataset, run.generations)
    path = run.artifact_dir / "evaluations.jsonl"
    write_evaluations(path, results)

    assert read_evaluations(path) == results
    with pytest.raises(ArtifactError, match="already exists"):
        write_evaluations(path, results)


def test_path_based_offline_evaluation_integration(tmp_path: Path) -> None:
    manifest, run = run_one(tmp_path, {"value": "x"})
    artifact_dir = run.artifact_dir
    output_path = artifact_dir / "evaluations.jsonl"

    results = evaluate_generations(
        artifact_dir / "manifest.snapshot.yaml",
        artifact_dir / "dataset.snapshot.jsonl",
        artifact_dir / "generations.jsonl",
        artifact_path=output_path,
    )

    assert results
    assert read_evaluations(output_path) == results
    assert manifest.path.exists()


def test_evaluation_preflight_rejects_mixed_or_corrupt_snapshots(tmp_path: Path) -> None:
    manifest, run = run_one(tmp_path, {"value": "x"})
    generation = run.generations[0]

    with pytest.raises(EvaluationInputError, match="unknown case ID"):
        evaluate_generations(
            manifest,
            run.dataset,
            (generation.model_copy(update={"case_id": "missing"}),),
        )
    with pytest.raises(EvaluationInputError, match="duplicate generation ID"):
        evaluate_generations(manifest, run.dataset, (generation, generation))
    with pytest.raises(EvaluationInputError, match="mismatched provider"):
        evaluate_generations(
            manifest,
            run.dataset,
            (generation.model_copy(update={"provider": "other"}),),
        )
    with pytest.raises(EvaluationInputError, match="mismatched experiment"):
        evaluate_generations(
            manifest,
            run.dataset,
            (generation.model_copy(update={"experiment": "other"}),),
        )
    with pytest.raises(EvaluationInputError, match="mismatched prompt"):
        evaluate_generations(
            manifest,
            run.dataset,
            (
                generation.model_copy(
                    update={
                        "normalized_request": generation.normalized_request.model_copy(
                            update={"prompt": "other"}
                        )
                    }
                ),
            ),
        )
    with pytest.raises(EvaluationInputError, match="dataset version mismatch"):
        evaluate_generations(
            manifest,
            run.dataset.model_copy(update={"version": "2.0"}),
            (generation,),
        )


def test_evaluation_result_invariants() -> None:
    base = {
        "evaluation_id": "e",
        "generation_id": "g",
        "case_id": "c",
        "evaluator": "x",
        "evaluator_version": "1",
        "reason": "reason",
    }
    with pytest.raises(ValueError, match="passed evaluation must contain"):
        EvaluationResult(**base, status="passed")
    with pytest.raises(ValueError, match="failed evaluation must contain"):
        EvaluationResult(**base, status="failed")
    with pytest.raises(ValueError, match="not_evaluated evaluation cannot"):
        EvaluationResult(**base, status="not_evaluated", score=0.0)
    with pytest.raises(ValueError, match="must contain an error"):
        EvaluationResult(**base, status="evaluator_error")
