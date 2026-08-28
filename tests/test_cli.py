"""Smoke and error contract tests for the EvalForge CLI."""

from pathlib import Path

from typer.testing import CliRunner

from evalforge.cli import app

runner = CliRunner()


def test_help_is_available() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Evaluate LLM configurations" in result.output


def test_version_is_available() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_validate_example_manifest() -> None:
    result = runner.invoke(app, ["validate", "examples/invoice/eval.yaml"])

    assert result.exit_code == 0
    assert "Validated experiment: invoice-extraction-regression" in result.output
    assert "Test cases: 20" in result.output


def test_validate_invalid_manifest_exits_with_code_2(tmp_path: Path) -> None:
    manifest_path = tmp_path / "invalid.yaml"
    manifest_path.write_text("invalid: yaml: syntax: [", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(manifest_path)])

    assert result.exit_code == 2
    assert "Validation failed:" in result.output


def test_validate_missing_dataset_exits_with_code_2(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        """name: test-experiment
dataset:
  path: non_existent.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
output_schema:
  type: object
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate", str(manifest_path)])

    assert result.exit_code == 2
    assert "Validation failed:" in result.output
