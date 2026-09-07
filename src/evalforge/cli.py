"""Command-line interface for EvalForge."""

import ipaddress
import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from evalforge import __version__
from evalforge.aggregation import AggregationInputError
from evalforge.analysis import analyze_experiment
from evalforge.artifacts import (
    ArtifactError,
    read_experiment_report,
    write_experiment_report,
    write_markdown_report,
)
from evalforge.config import ManifestError, load_manifest
from evalforge.dataset import DatasetError, load_dataset
from evalforge.engine import ExecutionError, ExperimentRun, execute_experiment
from evalforge.evaluators import EvaluationInputError, evaluate_generations
from evalforge.history import (
    HistoryError,
    HistoryRepository,
    replay_run,
    resolve_history_path,
)
from evalforge.json_types import thaw_json
from evalforge.report import build_experiment_report, render_markdown

app = typer.Typer(
    add_completion=False,
    help="Evaluate LLM configurations against a reproducible baseline.",
    no_args_is_help=True,
)
history_app = typer.Typer(help="List, inspect, and replay completed local runs.")
app.add_typer(history_app, name="history")


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
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="SQLite history path (defaults below artifact root)."),
    ] = None,
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency",
            min=1,
            help="Maximum concurrent inference requests per configuration.",
        ),
    ] = 1,
) -> None:
    """Execute an experiment and write its JSON and Markdown reports."""
    try:
        loaded_manifest = load_manifest(manifest)
        dataset = load_dataset(loaded_manifest)
        effective_artifact_root = (artifact_root or Path("artifacts")).expanduser().resolve()
        run_result = execute_experiment(
            loaded_manifest,
            dataset,
            artifact_root=effective_artifact_root,
            run_id=run_id,
            concurrency=concurrency,
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
        history_path = resolve_history_path(
            history_db, artifact_root=run_result.artifact_dir.parent
        )
        with HistoryRepository(history_path) as history:
            history.index_report(report, run_result.artifact_dir)
    except (
        AggregationInputError,
        ArtifactError,
        DatasetError,
        EvaluationInputError,
        ExecutionError,
        HistoryError,
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


@history_app.command("list")
def history_list(
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Artifact root containing the default history DB."),
    ] = None,
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="Explicit SQLite history path."),
    ] = None,
    experiment: Annotated[str | None, typer.Option("--experiment")] = None,
    decision: Annotated[str | None, typer.Option("--decision")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """List indexed completed runs newest first."""
    try:
        path = resolve_history_path(history_db, artifact_root=artifact_root)
        with HistoryRepository(path) as history:
            runs = history.list_runs(experiment=experiment, decision=decision)
    except HistoryError as error:
        typer.echo(f"History failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(json.dumps([run.as_dict() for run in runs], ensure_ascii=True, sort_keys=True))
        return
    typer.echo(f"History: {path}")
    if not runs:
        typer.echo("No runs found.")
        return
    for run in runs:
        typer.echo(f"{run.run_id}\t{run.decision.upper()}\t{run.experiment}\t{run.artifact_dir}")


@history_app.command("import")
def history_import(
    artifact_dir: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, readable=True),
    ],
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Artifact root containing the default history DB."),
    ] = None,
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="Explicit SQLite history path."),
    ] = None,
) -> None:
    """Import a completed artifact directory without rerunning inference."""
    try:
        resolved_artifact_dir = artifact_dir.expanduser().resolve()
        if not resolved_artifact_dir.is_dir():
            raise HistoryError(f"artifact directory does not exist: {resolved_artifact_dir}")
        report = read_experiment_report(resolved_artifact_dir / "experiment.json")
        history_path = resolve_history_path(
            history_db, artifact_root=artifact_root or resolved_artifact_dir.parent
        )
        with HistoryRepository(history_path) as history:
            imported = history.index_report(report, resolved_artifact_dir)
    except (ArtifactError, HistoryError, ValidationError) as error:
        typer.echo(f"Import failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"Imported run: {imported.run_id}")
    typer.echo(f"Experiment: {imported.experiment}")
    typer.echo(f"History: {history_path}")


@history_app.command("show")
def history_show(
    run_id: Annotated[str, typer.Argument()],
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Artifact root containing the default history DB."),
    ] = None,
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="Explicit SQLite history path."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Show one indexed run and its artifact references."""
    try:
        path = resolve_history_path(history_db, artifact_root=artifact_root)
        with HistoryRepository(path) as history:
            run = history.get_run(run_id)
    except HistoryError as error:
        typer.echo(f"History failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(
            json.dumps(
                run.as_dict(include_report=True),
                ensure_ascii=True,
                sort_keys=True,
                default=lambda value: (
                    value.isoformat() if hasattr(value, "isoformat") else str(value)
                ),
            )
        )
        return
    typer.echo(f"Run: {run.run_id}")
    typer.echo(f"Experiment: {run.experiment}")
    typer.echo(f"Decision: {run.decision.upper()}")
    typer.echo(f"Artifact directory: {run.artifact_dir}")
    for name, artifact in run.artifacts.items():
        typer.echo(f"{name}: {artifact}")


@app.command("replay")
def replay(
    run_id: Annotated[str, typer.Argument()],
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Artifact root containing the default history DB."),
    ] = None,
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="Explicit SQLite history path."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Reevaluate stored snapshots offline without invoking a provider."""
    try:
        path = resolve_history_path(history_db, artifact_root=artifact_root)
        with HistoryRepository(path) as history:
            run = history.get_run(run_id)
        analysis = replay_run(run)
    except (
        AggregationInputError,
        ArtifactError,
        EvaluationInputError,
        HistoryError,
        ValidationError,
    ) as error:
        typer.echo(f"Replay failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(
            json.dumps(
                thaw_json(analysis.model_dump(mode="python")),
                ensure_ascii=True,
                sort_keys=True,
                default=str,
            )
        )
        return
    typer.echo(f"Replay decision: {analysis.gates.decision.upper()}")
    typer.echo(
        f"Experiment: {analysis.baseline.configuration} vs {analysis.candidate.configuration}"
    )


@app.command()
def serve(
    history_db: Annotated[
        Path | None,
        typer.Option("--history-db", help="SQLite history path (defaults below artifact root)."),
    ] = None,
    artifact_root: Annotated[
        Path | None,
        typer.Option("--artifact-root", help="Artifact root containing the default history DB."),
    ] = None,
    host: Annotated[str, typer.Option(help="Bind host; loopback is required by default.")] = (
        "127.0.0.1"
    ),
    port: Annotated[int, typer.Option(help="Bind port.")] = 8765,
    allow_remote: Annotated[
        bool,
        typer.Option("--allow-remote", help="Allow binding to a non-loopback host."),
    ] = False,
) -> None:
    """Serve the local history and workspace-run API for a dashboard."""
    if not 1 <= port <= 65535:
        typer.echo("Serve failed: port must be between 1 and 65535", err=True)
        raise typer.Exit(code=2)
    normalized_host = host.strip().lower()
    try:
        is_loopback = (
            normalized_host == "localhost" or ipaddress.ip_address(normalized_host).is_loopback
        )
    except ValueError:
        is_loopback = False
    if not is_loopback and not allow_remote:
        typer.echo(
            "Serve failed: non-loopback hosts require --allow-remote; "
            "no authentication is provided",
            err=True,
        )
        raise typer.Exit(code=2)
    if not is_loopback:
        typer.echo(
            "Warning: serving remotely without authentication; use only on a trusted network.",
            err=True,
        )
    try:
        import uvicorn

        from evalforge.api import create_app

        history_path = resolve_history_path(history_db, artifact_root=artifact_root)
        if not history_path.is_file():
            raise HistoryError(f"history database does not exist: {history_path}")
        with HistoryRepository(history_path):
            pass
        application = create_app(history_db=history_db, artifact_root=artifact_root)
        uvicorn.run(application, host=host, port=port)
    except (HistoryError, OSError) as error:
        typer.echo(f"Serve failed: {error}", err=True)
        raise typer.Exit(code=2) from error


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
