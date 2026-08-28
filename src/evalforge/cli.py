"""Command-line interface for EvalForge."""

from typing import Annotated

import typer

from evalforge import __version__

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


def main() -> None:
    """Run the EvalForge command-line application."""
    app()
