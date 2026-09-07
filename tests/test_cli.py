"""Milestone 5 CLI, report, and demo acceptance tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from evalforge.artifacts import ArtifactError, read_experiment_report, write_markdown_report
from evalforge.cli import app
from evalforge.report import ExperimentReport, render_markdown

RUNNER = CliRunner()
PASS_MANIFEST = Path("examples/invoice/pass.yaml")
REGRESSION_MANIFEST = Path("examples/invoice/regression.yaml")
PORTFOLIO_MANIFEST = Path("examples/invoice/portfolio.yaml")
PORTFOLIO_FIXED_MANIFEST = Path("examples/invoice/portfolio-fixed.yaml")


def test_pass_demo_writes_round_trippable_reports(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PASS_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "pass",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Decision: PASS" in result.stdout
    artifact_dir = tmp_path / "artifacts" / "pass"
    report = read_experiment_report(artifact_dir / "experiment.json")
    markdown = (artifact_dir / "report.md").read_text(encoding="utf-8")
    assert report.gates.passed
    assert report.baseline_summary.case_pass_count == 20
    assert report.candidate_summary.case_pass_count == 20
    assert len(report.evaluations) == 80
    assert report.manifest.output_schema["type"] == "object"
    assert "field_accuracy" in report.manifest.quality_gates
    assert report.started_at <= report.ended_at
    assert "Decision:" in markdown
    assert "## Quality gates" in markdown
    assert "## Failed cases" in markdown
    assert (
        json.loads((artifact_dir / "experiment.json").read_text(encoding="utf-8"))["experiment"]
        == report.experiment
    )

    with pytest.raises(ArtifactError, match="already exists"):
        write_markdown_report(artifact_dir / "report.md", markdown)

    repeated = RUNNER.invoke(
        app,
        [
            "run",
            str(PASS_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "pass",
        ],
    )
    assert repeated.exit_code == 2
    assert "already exists" in repeated.stderr


def test_report_model_rejects_tampered_generation_count(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PASS_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "tamper",
        ],
    )
    assert result.exit_code == 0
    report = read_experiment_report(tmp_path / "artifacts" / "tamper" / "experiment.json")
    payload = report.model_dump(mode="python")
    payload["configurations"][0]["generation_count"] += 1
    with pytest.raises(ValidationError, match="generation_count"):
        ExperimentReport.model_validate(payload)


def test_markdown_escapes_hostile_cells_and_reasons(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PASS_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "markdown",
        ],
    )
    assert result.exit_code == 0
    report = read_experiment_report(tmp_path / "artifacts" / "markdown" / "experiment.json")
    first_configuration = report.configurations[0].model_copy(
        update={"provider": "mock|hostile", "model": "model\\hostile\nline"}
    )
    first_rule = report.gates.rules[0].model_copy(
        update={"metric": "metric|hostile", "reason": "reason | hostile\nline"}
    )
    hostile = report.model_copy(
        update={
            "configurations": (first_configuration, report.configurations[1]),
            "gates": report.gates.model_copy(
                update={"rules": (first_rule, *report.gates.rules[1:])}
            ),
        }
    )
    markdown = render_markdown(hostile)
    assert "mock\\|hostile" in markdown
    assert "model\\\\hostile<br>line" in markdown
    assert "metric\\|hostile" in markdown
    assert "reason \\| hostile<br>line" in markdown


def test_regression_demo_returns_one_and_explains_every_failure(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(REGRESSION_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "regression",
        ],
    )

    assert result.exit_code == 1, result.stdout
    artifact_dir = tmp_path / "artifacts" / "regression"
    report = read_experiment_report(artifact_dir / "experiment.json")
    markdown = (artifact_dir / "report.md").read_text(encoding="utf-8")
    assert not report.gates.passed
    assert report.regression.newly_failing == ("invoice-002", "invoice-005", "invoice-019")
    assert len(report.gates.failures) >= 1
    assert "field_accuracy" in markdown
    assert "invoice-002" in markdown
    assert "mismatches" in markdown
    assert "FAIL" in markdown


def test_portfolio_demo_blocks_new_failures_despite_higher_average(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PORTFOLIO_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "portfolio",
        ],
    )

    assert result.exit_code == 1, result.stdout
    report = read_experiment_report(tmp_path / "artifacts" / "portfolio" / "experiment.json")
    baseline_accuracy = report.baseline_summary.metric("field_accuracy")
    candidate_accuracy = report.candidate_summary.metric("field_accuracy")
    assert baseline_accuracy is not None and candidate_accuracy is not None
    assert candidate_accuracy.score > baseline_accuracy.score
    assert report.candidate_summary.case_pass_count == 18
    assert report.baseline_summary.case_pass_count == 14
    assert report.regression.newly_failing == ("invoice-adv-019", "invoice-adv-020")
    assert report.regression.newly_passing == (
        "invoice-adv-003",
        "invoice-adv-006",
        "invoice-adv-009",
        "invoice-adv-012",
        "invoice-adv-015",
        "invoice-adv-018",
    )
    assert any(
        failure.metric == "new_failure_count" and failure.observed == 2.0
        for failure in report.gates.failures
    )


def test_corrected_portfolio_candidate_resolves_regressions(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PORTFOLIO_FIXED_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "portfolio-fixed",
        ],
    )

    assert result.exit_code == 0, result.stdout
    report = read_experiment_report(tmp_path / "artifacts" / "portfolio-fixed" / "experiment.json")
    assert report.candidate_summary.case_pass_count == 20
    assert report.regression.newly_failing == ()
    assert report.gates.passed


def test_repeated_demos_have_equivalent_decisions_and_metrics(tmp_path: Path) -> None:
    first = RUNNER.invoke(
        app,
        ["run", str(PASS_MANIFEST), "--artifact-root", str(tmp_path), "--run-id", "first"],
    )
    second = RUNNER.invoke(
        app,
        ["run", str(PASS_MANIFEST), "--artifact-root", str(tmp_path), "--run-id", "second"],
    )
    assert first.exit_code == second.exit_code == 0
    first_report = read_experiment_report(tmp_path / "first" / "experiment.json")
    second_report = read_experiment_report(tmp_path / "second" / "experiment.json")
    assert first_report.gates.decision == second_report.gates.decision
    for metric_name in ("schema_validity", "field_accuracy"):
        assert (
            first_report.regression.metrics[metric_name]
            == second_report.regression.metrics[metric_name]
        )
    assert (
        first_report.baseline_summary.evaluator_metrics
        == second_report.baseline_summary.evaluator_metrics
    )


def test_invalid_manifest_returns_two_without_a_decision(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("name: [not valid", encoding="utf-8")
    result = RUNNER.invoke(
        app,
        ["run", str(invalid), "--artifact-root", str(tmp_path / "artifacts"), "--run-id", "bad"],
    )
    assert result.exit_code == 2
    assert "Run failed:" in result.stderr
    assert "Decision:" not in result.stdout
    assert not (tmp_path / "artifacts" / "bad").exists()


def test_provider_error_is_visible_separately_in_report(tmp_path: Path) -> None:
    manifest = tmp_path / "provider-error.yaml"
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"case-1","input":{"text":"[provider-error]"},"expected":{"value":"x"}}\n',
        encoding="utf-8",
    )
    manifest.write_text(
        """name: provider-error-demo
dataset:
  path: dataset.jsonl
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
    value: {type: string}
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 0.0
  p95_latency_ms:
    maximum: 1000.0
""",
        encoding="utf-8",
    )
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(manifest),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "errors",
        ],
    )
    assert result.exit_code == 1
    report = read_experiment_report(tmp_path / "artifacts" / "errors" / "experiment.json")
    assert report.baseline_summary.provider_error_count == 1
    assert report.candidate_summary.provider_error_count == 1
    assert all(case.provider_error is not None for case in report.failed_cases)
    assert all(
        evaluation.status == "not_evaluated"
        for case in report.failed_cases
        for evaluation in case.evaluations
    )


def test_cli_run_supports_concurrency(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(PASS_MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "concurrent-pass",
            "--concurrency",
            "4",
        ],
    )
    assert result.exit_code == 0, result.stdout
    report = read_experiment_report(
        tmp_path / "artifacts" / "concurrent-pass" / "experiment.json"
    )
    assert report.gates.passed
    assert report.baseline_summary.attempted_generations == 20
    assert report.candidate_summary.attempted_generations == 20
