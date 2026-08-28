"""Command-line interface for EvalForge."""

from pathlib import Path
from typing import Annotated

import typer

from evalforge import __version__
from evalforge.config import ManifestError, load_manifest
from evalforge.dataset import DatasetError, load_dataset

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


def main() -> None:
    """Run the EvalForge command-line application."""
    app()
