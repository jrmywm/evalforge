"""Command-line interface for EvalForge."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from evalforge import __version__
from evalforge.aggregation import AggregationInputError
from evalforge.analysis import analyze_experiment
from evalforge.artifacts import ArtifactError, write_experiment_report, write_markdown_report
from evalforge.config import ManifestError, load_manifest
from evalforge.dataset import DatasetError, load_dataset
from evalforge.engine import ExecutionError, ExperimentRun, execute_experiment
from evalforge.evaluators import EvaluationInputError, evaluate_generations
from evalforge.report import build_experiment_report, render_markdown

app = typer.Typer(
    add_completion=False,
    help="Evaluate LLM configurations against a reproducible baseline.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print the package version and exit when requested."""
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True),
    ] = False,
) -> None:
    """Run and inspect local-first LLM evaluation experiments."""


@app.command()
def validate(
    manifest: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Validate an experiment manifest and its referenced JSONL dataset."""
    try:
        loaded_manifest = load_manifest(manifest)
        dataset = load_dataset(loaded_manifest)
    except (DatasetError, ManifestError) as error:
        typer.echo(f"Validation failed: {error}", err=True)
        raise typer.Exit(code=2) from error

    typer.echo(f"Validated experiment: {loaded_manifest.config.name}")
    typer.echo(f"Dataset version: {dataset.version}")
    typer.echo(f"Test cases: {len(dataset.cases)}")
    typer.echo(f"Dataset digest: {dataset.digest}")
    typer.echo(f"Manifest digest: {loaded_manifest.digest}")


@app.command()
def run(
    manifest: Annotated[Path, typer.Argument(exists=True, readable=True)],
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Root directory for the run artifact."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Stable run ID; an existing run is never overwritten."),
    ] = None,
) -> None:
    """Execute an experiment and write its JSON and Markdown reports."""
    try:
        loaded_manifest = load_manifest(manifest)
        dataset = load_dataset(loaded_manifest)
        run_result = execute_experiment(
            loaded_manifest,
            dataset,
            artifact_root=artifact_root,
            run_id=run_id,
        )
        _raise_if_local_endpoint_unavailable(run_result)
        evaluations_path = run_result.artifact_dir / "evaluations.jsonl"
        evaluations = evaluate_generations(
            loaded_manifest,
            dataset,
            run_result.generations,
            artifact_path=evaluations_path,
        )
        analysis = analyze_experiment(loaded_manifest, dataset, run_result.generations, evaluations)
        report = build_experiment_report(run_result, evaluations, analysis)
        experiment_path = run_result.artifact_dir / "experiment.json"
        markdown_path = run_result.artifact_dir / "report.md"
        write_experiment_report(experiment_path, report)
        write_markdown_report(markdown_path, render_markdown(report))
    except (
        AggregationInputError,
        ArtifactError,
        DatasetError,
        EvaluationInputError,
        ExecutionError,
        ManifestError,
        ValidationError,
    ) as error:
        typer.echo(f"Run failed: {error}", err=True)
        raise typer.Exit(code=2) from error

    decision = "PASS" if report.gates.passed else "FAIL"
    typer.echo(f"Decision: {decision}")
    typer.echo(f"Experiment: {report.experiment}")
    typer.echo(f"JSON report: {experiment_path}")
    typer.echo(f"Markdown report: {markdown_path}")
    if not report.gates.passed:
        raise typer.Exit(code=1)


def _raise_if_local_endpoint_unavailable(run_result: ExperimentRun) -> None:
    """Turn an entirely unreachable local endpoint into the documented code 2."""
    generations = run_result.generations
    local_configurations = {
        generation.configuration
        for generation in generations
        if generation.provider == "openai_compatible"
    }
    unavailable_types = {"authentication_error", "network_error", "timeout"}
    for configuration in sorted(local_configurations):
        attempts = [item for item in generations if item.configuration == configuration]
        if attempts and all(
            item.status == "provider_error"
            and item.error is not None
            and item.error.type in unavailable_types
            for item in attempts
        ):
            raise ExecutionError(
                f"openai-compatible endpoint unavailable for configuration {configuration!r}; "
                "check the local server and provider_options.base_url"
            )


def main() -> None:
    """Run the EvalForge command-line application."""
    app()
