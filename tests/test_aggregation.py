"""Milestone 4 aggregation, regression, and gate semantics."""

from pathlib import Path

import pytest

from evalforge.aggregation import (
    AggregationInputError,
    ConfigurationSummary,
    LatencySummary,
    MetricAggregate,
    UsageSummary,
    aggregate_experiment,
)
from evalforge.config import QualityGate, load_manifest
from evalforge.dataset import load_dataset
from evalforge.engine import execute_experiment
from evalforge.evaluators import (
    BUILTIN_EVALUATOR_VERSIONS,
    EvaluationResult,
    FieldAccuracyEvaluator,
    JsonSchemaEvaluator,
    evaluate_generations,
)
from evalforge.gates import GateFailure, GateRuleResult, QualityGateResult, evaluate_quality_gates
from evalforge.json_types import FrozenDict
from evalforge.providers import DeterministicMockProvider, ProviderResponse
from evalforge.regression import compare_summaries

EXAMPLE_MANIFEST = Path("examples/invoice/eval.yaml")


def collect(tmp_path: Path, *, fail_case_ids: set[str] | None = None):
    manifest = load_manifest(EXAMPLE_MANIFEST)
    run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="run",
        provider_factory=lambda config: DeterministicMockProvider(
            config.model, fail_case_ids=fail_case_ids
        ),
    )
    evaluations = evaluate_generations(manifest, run.dataset, run.generations)
    return manifest, run, evaluations


def test_summary_denominator_and_status_counts_include_provider_errors(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(tmp_path, fail_case_ids={"invoice-001"})
    baseline, candidate = aggregate_experiment(manifest, run.dataset, run.generations, evaluations)

    assert baseline.attempted_generations == 20
    assert baseline.provider_success_count == 19
    assert baseline.provider_error_count == 1
    schema = baseline.metric("schema_validity")
    assert schema is not None
    assert schema.denominator == 20
    assert schema.score == 19 / 20
    assert schema.not_evaluated_count == 1
    assert baseline.latency.successful_count == 19
    assert baseline.latency.excluded_provider_failure_count == 1
    assert baseline.usage.input_tokens_total is None
    assert baseline.usage.input_tokens_unavailable_count == 20
    assert candidate.provider_error_count == 1


def test_latency_statistics_use_exact_stored_durations(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(tmp_path)
    durations = tuple(
        record.model_copy(update={"latency_ms": float(index + 1)})
        for index, record in enumerate(run.generations)
    )
    baseline, _ = aggregate_experiment(manifest, run.dataset, durations, evaluations)

    assert baseline.latency.median_ms == 10.5
    assert baseline.latency.p95_ms == 19.0  # ceil(.95 * 20) - 1 => sorted index 18

    one_success = tuple(
        record.model_copy(
            update={
                "status": "provider_error",
                "error": {"type": "test", "message": "offline"},
                "normalized_response": None,
                "raw_response": None,
                "latency_ms": 999.0,
            }
        )
        if index
        else record.model_copy(update={"latency_ms": 7.0})
        for index, record in enumerate(run.generations)
    )
    one_evaluations = evaluate_generations(manifest, run.dataset, one_success)
    one_baseline, _ = aggregate_experiment(manifest, run.dataset, one_success, one_evaluations)
    assert one_baseline.latency.median_ms == 7.0
    assert one_baseline.latency.p95_ms == 7.0

    empty = tuple(
        record.model_copy(
            update={
                "status": "provider_error",
                "error": {"type": "test", "message": "offline"},
                "normalized_response": None,
                "raw_response": None,
                "latency_ms": 999.0,
            }
        )
        for record in run.generations
    )
    empty_evaluations = evaluate_generations(manifest, run.dataset, empty)
    empty_baseline, _ = aggregate_experiment(manifest, run.dataset, empty, empty_evaluations)
    assert empty_baseline.latency.median_ms is None
    assert empty_baseline.latency.p95_ms is None


def test_missing_and_evaluator_error_results_are_zero_and_force_gate_failure(
    tmp_path: Path,
) -> None:
    manifest, run, evaluations = collect(tmp_path)
    missing = evaluations[:-1]
    baseline, candidate = aggregate_experiment(manifest, run.dataset, run.generations, missing)
    assert candidate.metric("field_accuracy").missing_count == 1

    regression = compare_summaries(baseline, candidate)
    gates = evaluate_quality_gates(manifest, regression)
    assert not gates.passed
    assert any(f.rule == "data_integrity" and "missing" in f.reason for f in gates.failures)

    last = evaluations[-1]
    error_payload = last.model_dump(mode="python")
    error_payload.update(
        status="evaluator_error", score=None, error={"type": "test_error", "message": "boom"}
    )
    error = EvaluationResult(**error_payload)
    replaced = (*evaluations[:-1], error)
    baseline, candidate = aggregate_experiment(manifest, run.dataset, run.generations, replaced)
    field_metric = candidate.metric("field_accuracy")
    assert field_metric is not None and field_metric.evaluator_error_count == 1
    assert not evaluate_quality_gates(manifest, compare_summaries(baseline, candidate)).passed


def test_regression_deltas_and_case_transitions_are_stable_sorted() -> None:
    from evalforge.aggregation import (
        ConfigurationSummary,
        LatencySummary,
        MetricAggregate,
        UsageSummary,
    )

    metric = MetricAggregate(
        evaluator="field_accuracy",
        denominator=2,
        score_sum=1.0,
        score=0.5,
        passed_count=1,
        failed_count=1,
        not_evaluated_count=0,
        evaluator_error_count=0,
        missing_count=0,
    )
    latency = LatencySummary(
        median_ms=10.0, p95_ms=20.0, successful_count=2, excluded_provider_failure_count=0
    )
    usage = UsageSummary(
        input_tokens_unavailable_count=2,
        output_tokens_unavailable_count=2,
        total_tokens_unavailable_count=2,
        cost_unavailable_count=2,
    )
    kwargs = dict(
        attempted_generations=2,
        provider_success_count=2,
        provider_error_count=0,
        case_pass_count=1,
        case_fail_count=1,
        evaluator_metrics=FrozenDict({"field_accuracy": metric}),
        latency=latency,
        usage=usage,
    )
    baseline = ConfigurationSummary(configuration="baseline", passed_case_ids=("a",), **kwargs)
    candidate = ConfigurationSummary(configuration="candidate", passed_case_ids=("b",), **kwargs)
    result = compare_summaries(baseline, candidate)

    assert result.newly_failing == ("a",)
    assert result.newly_passing == ("b",)
    assert result.metrics["field_accuracy"].delta == 0.0
    assert result.metrics["field_accuracy"].relative_delta == 0.0
    assert result.metrics["p95_latency_ms"].delta == 0.0

    zero_baseline = baseline.model_copy(
        update={
            "evaluator_metrics": FrozenDict(
                {
                    "field_accuracy": metric.model_copy(
                        update={
                            "score_sum": 0.0,
                            "score": 0.0,
                            "passed_count": 0,
                            "failed_count": 2,
                        }
                    )
                }
            )
        }
    )
    zero_candidate = zero_baseline.model_copy(update={"configuration": "candidate"})
    zero_result = compare_summaries(zero_baseline, zero_candidate)
    assert zero_result.metrics["field_accuracy"].relative_delta == 0.0
    improved = zero_candidate.model_copy(
        update={"evaluator_metrics": FrozenDict({"field_accuracy": metric})}
    )
    assert (
        compare_summaries(zero_baseline, improved).metrics["field_accuracy"].relative_delta is None
    )


def test_gate_boundaries_pass_and_all_rule_failures_are_collected(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(tmp_path)
    baseline, candidate = aggregate_experiment(manifest, run.dataset, run.generations, evaluations)
    regression = compare_summaries(baseline, candidate)
    exact_policy = manifest.config.model_copy(
        update={
            "quality_gates": FrozenDict(
                {
                    "schema_validity": QualityGate(minimum=1.0),
                    "field_accuracy": QualityGate(minimum=candidate.metric("field_accuracy").score),
                    "p95_latency_ms": QualityGate(maximum=candidate.latency.p95_ms),
                }
            )
        }
    )
    exact_gates = evaluate_quality_gates(exact_policy, regression)
    assert exact_gates.passed
    minimum_rule = next(
        rule
        for rule in exact_gates.rules
        if rule.metric == "schema_validity" and rule.rule == "minimum"
    )
    assert minimum_rule.passed
    assert minimum_rule.observed == 1.0
    assert minimum_rule.threshold == 1.0

    failing_policy = manifest.config.model_copy(
        update={
            "quality_gates": FrozenDict(
                {
                    "schema_validity": QualityGate(minimum=2.0, maximum=2.0),
                    "field_accuracy": QualityGate(minimum=1.1, maximum=1.1),
                    "p95_latency_ms": QualityGate(maximum=0.0),
                }
            )
        }
    )
    failures = evaluate_quality_gates(failing_policy, regression).failures
    assert len(failures) == 3
    assert {(failure.metric, failure.rule) for failure in failures} == {
        ("field_accuracy", "minimum"),
        ("p95_latency_ms", "maximum"),
        ("schema_validity", "minimum"),
    }


def test_all_provider_failures_make_latency_unavailable_and_gate_fail(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(
        tmp_path, fail_case_ids={f"invoice-{index:03d}" for index in range(1, 21)}
    )
    baseline, candidate = aggregate_experiment(manifest, run.dataset, run.generations, evaluations)

    assert baseline.latency.median_ms is None
    assert baseline.latency.p95_ms is None
    assert baseline.latency.successful_count == 0
    gates = evaluate_quality_gates(manifest, compare_summaries(baseline, candidate))
    assert any(f.metric == "p95_latency_ms" for f in gates.failures)


def test_duplicate_or_unknown_evaluation_identity_is_input_error(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(tmp_path)
    with pytest.raises(AggregationInputError, match="duplicate evaluation"):
        aggregate_experiment(manifest, run.dataset, run.generations, (*evaluations, evaluations[0]))
    unknown_payload = evaluations[0].model_dump(mode="python")
    unknown_payload.update(generation_id="missing", evaluation_id="unknown")
    unknown = EvaluationResult(**unknown_payload)
    with pytest.raises(AggregationInputError, match="unknown generation"):
        aggregate_experiment(manifest, run.dataset, run.generations, (*evaluations, unknown))


def test_evaluation_id_and_builtin_version_are_verified(tmp_path: Path) -> None:
    manifest, run, evaluations = collect(tmp_path)
    tampered_id = evaluations[0].model_copy(update={"evaluation_id": "tampered"})
    with pytest.raises(AggregationInputError, match="invalid evaluation ID"):
        aggregate_experiment(
            manifest, run.dataset, run.generations, (tampered_id, *evaluations[1:])
        )

    tampered_version = evaluations[0].model_copy(update={"evaluator_version": "9.9"})
    with pytest.raises(AggregationInputError, match="unexpected evaluator version"):
        aggregate_experiment(
            manifest, run.dataset, run.generations, (tampered_version, *evaluations[1:])
        )

    skipped_success = evaluations[0].model_copy(
        update={"status": "not_evaluated", "score": None, "reason": "tampered skip"}
    )
    with pytest.raises(AggregationInputError, match="cannot be not_evaluated"):
        aggregate_experiment(
            manifest, run.dataset, run.generations, (skipped_success, *evaluations[1:])
        )


def test_builtin_evaluator_version_registry_matches_implementations() -> None:
    assert BUILTIN_EVALUATOR_VERSIONS == {
        JsonSchemaEvaluator.name: JsonSchemaEvaluator.version,
        FieldAccuracyEvaluator.name: FieldAccuracyEvaluator.version,
    }


def test_configuration_summary_invariants_reject_incoherent_values() -> None:
    metric = MetricAggregate(
        evaluator="field_accuracy",
        denominator=1,
        score_sum=1.0,
        score=1.0,
        passed_count=1,
        failed_count=0,
        not_evaluated_count=0,
        evaluator_error_count=0,
        missing_count=0,
    )
    usage = UsageSummary(
        input_tokens_unavailable_count=0,
        output_tokens_unavailable_count=0,
        total_tokens_unavailable_count=0,
        cost_unavailable_count=0,
    )
    with pytest.raises(ValueError, match="empty successful latency"):
        LatencySummary(
            median_ms=1.0,
            p95_ms=1.0,
            successful_count=0,
            excluded_provider_failure_count=1,
        )
    with pytest.raises(ValueError, match="latency successful count"):
        ConfigurationSummary(
            configuration="baseline",
            attempted_generations=1,
            provider_success_count=1,
            provider_error_count=0,
            case_pass_count=1,
            case_fail_count=0,
            passed_case_ids=("a",),
            evaluator_metrics=FrozenDict({"field_accuracy": metric}),
            latency=LatencySummary(
                median_ms=None,
                p95_ms=None,
                successful_count=0,
                excluded_provider_failure_count=1,
            ),
            usage=usage,
        )


def test_quality_gate_result_invariants_reject_contradictory_evidence() -> None:
    failed_rule = GateRuleResult(
        metric="field_accuracy",
        rule="minimum",
        observed=0.5,
        threshold=0.9,
        passed=False,
        reason="candidate field_accuracy 0.5 is below minimum 0.9",
    )
    failure = GateFailure(
        metric=failed_rule.metric,
        rule=failed_rule.rule,
        observed=failed_rule.observed,
        threshold=failed_rule.threshold,
        reason=failed_rule.reason,
    )
    with pytest.raises(ValueError, match="decision"):
        QualityGateResult(
            decision="passed",
            evaluated_rules=("field_accuracy.minimum",),
            rules=(failed_rule,),
            failures=(failure,),
        )

    with pytest.raises(ValueError, match="failures"):
        QualityGateResult(
            decision="failed",
            evaluated_rules=("field_accuracy.minimum",),
            rules=(failed_rule,),
            failures=(),
        )

    with pytest.raises(ValueError, match="evaluated_rules"):
        QualityGateResult(
            decision="failed",
            evaluated_rules=(),
            rules=(failed_rule,),
            failures=(failure,),
        )


def test_fixture_driven_candidate_regression_and_passing_candidate_are_stable(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(EXAMPLE_MANIFEST)
    dataset = load_dataset(manifest)
    expected = {case.id: dict(case.expected) for case in dataset.cases}
    regressions = {"invoice-001", "invoice-002"}

    class FixtureProvider:
        def __init__(self, model: str, broken: bool):
            self.model = model
            self.broken = broken

        def generate(self, request):
            output = dict(expected[request.case_id])
            if self.broken and request.case_id in regressions:
                output["total"] = output["total"] + 1.0
            return ProviderResponse(output=output)

    def run(run_id: str, broken: bool):
        result = execute_experiment(
            manifest,
            dataset,
            artifact_root=tmp_path / "artifacts",
            run_id=run_id,
            provider_factory=lambda config: FixtureProvider(
                config.model, broken and "candidate" in config.model
            ),
        )
        results = evaluate_generations(manifest, dataset, result.generations)
        summaries = aggregate_experiment(manifest, dataset, result.generations, results)
        regression = compare_summaries(*summaries)
        return regression, evaluate_quality_gates(manifest, regression)

    passing, passing_gates = run("passing", False)
    regressing, regressing_gates = run("regressing", True)
    repeat, repeat_gates = run("repeat", True)

    assert passing.newly_failing == ()
    assert passing_gates.passed
    assert regressing.newly_failing == tuple(sorted(regressions))
    assert regressing.newly_passing == ()
    assert not regressing_gates.passed
    assert any(
        failure.metric == "field_accuracy"
        and failure.rule == "maximum_regression"
        and "exceeds" in failure.reason
        for failure in regressing_gates.failures
    )
    assert regressing.newly_failing == repeat.newly_failing
    assert regressing.metrics["field_accuracy"].delta == repeat.metrics["field_accuracy"].delta
    assert regressing_gates.decision == repeat_gates.decision
