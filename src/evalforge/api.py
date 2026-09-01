"""Local HTTP API for indexed EvalForge history and workspace runs."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from evalforge import __version__
from evalforge.aggregation import AggregationInputError
from evalforge.analysis import analyze_experiment
from evalforge.artifacts import (
    ArtifactError,
    write_experiment_report,
    write_markdown_report,
)
from evalforge.config import ManifestError, load_manifest
from evalforge.dataset import DatasetError, load_dataset
from evalforge.engine import ExecutionError, execute_experiment
from evalforge.evaluators import EvaluationInputError, evaluate_generations
from evalforge.history import (
    HistoryError,
    HistoryRepository,
    replay_run,
    resolve_history_path,
)
from evalforge.report import build_experiment_report, render_markdown

LOCAL_DEV_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


class RunRequest(BaseModel):
    """The intentionally small browser-to-run contract."""

    manifest: str = Field(min_length=1, max_length=240)
    run_id: str | None = Field(default=None, max_length=120)


def _manifest_path(identifier: str, workspace_root: Path) -> Path:
    """Resolve one relative YAML manifest below the configured workspace."""
    candidate = Path(identifier)
    # PureWindowsPath catches drive-qualified and UNC paths even if deployed on
    # a host whose native Path implementation is POSIX.
    if candidate.is_absolute() or PureWindowsPath(identifier).is_absolute():
        raise ValueError("manifest must be a relative path inside the workspace")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("manifest path cannot contain traversal or empty components")
    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("manifest must be a .yaml or .yml file")
    root = workspace_root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("manifest must resolve inside the workspace") from error
    if not resolved.is_file():
        raise FileNotFoundError("manifest was not found inside the workspace")
    return resolved


def _execute_manifest(
    manifest_path: Path,
    *,
    artifact_root: Path,
    history_path: Path,
    run_id: str | None,
) -> Any:
    """Run the same domain pipeline as the CLI, without invoking a shell."""
    loaded_manifest = load_manifest(manifest_path)
    dataset = load_dataset(loaded_manifest)
    run_result = execute_experiment(
        loaded_manifest, dataset, artifact_root=artifact_root, run_id=run_id
    )
    evaluations = evaluate_generations(
        loaded_manifest,
        dataset,
        run_result.generations,
        artifact_path=run_result.artifact_dir / "evaluations.jsonl",
    )
    analysis = analyze_experiment(loaded_manifest, dataset, run_result.generations, evaluations)
    report = build_experiment_report(run_result, evaluations, analysis)
    write_experiment_report(run_result.artifact_dir / "experiment.json", report)
    write_markdown_report(run_result.artifact_dir / "report.md", render_markdown(report))
    with HistoryRepository(history_path) as history:
        return history.index_report(report, run_result.artifact_dir)


def _history_error(message: str, *, status_code: int = 500) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _run_error(code: str, message: str, *, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _is_unknown_run(error: HistoryError) -> bool:
    return "was not found" in str(error)


def create_app(
    *,
    history_db: Path | None = None,
    artifact_root: Path | None = None,
    workspace_root: Path | None = None,
) -> FastAPI:
    """Build a local API bound to one history database and workspace."""
    root = (workspace_root or Path.cwd()).resolve()
    effective_artifact_root = (artifact_root or root / "artifacts").resolve()
    history_path = resolve_history_path(history_db, artifact_root=effective_artifact_root)
    application = FastAPI(
        title="EvalForge local API",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.history_path = history_path
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_DEV_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(HistoryError)
    async def handle_history_error(_request: Request, _error: HistoryError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "history unavailable"})

    @application.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    def read_runs(*, experiment: str | None = None, decision: str | None = None) -> tuple[Any, ...]:
        if not history_path.is_file():
            raise HistoryError("history database does not exist")
        with HistoryRepository(history_path) as history:
            return history.list_runs(experiment=experiment, decision=decision)

    def read_run(run_id: str) -> Any:
        if not history_path.is_file():
            raise HistoryError("history database does not exist")
        with HistoryRepository(history_path) as history:
            return history.get_run(run_id)

    @application.post("/api/runs", status_code=201)
    def create_run(request: RunRequest) -> dict[str, Any]:
        """Synchronously execute and index one workspace-local manifest."""
        try:
            manifest_path = _manifest_path(request.manifest, root)
        except ValueError as error:
            raise _run_error("invalid_manifest_path", str(error), status_code=422) from error
        except FileNotFoundError as error:
            raise _run_error("manifest_not_found", str(error), status_code=404) from error
        try:
            indexed = _execute_manifest(
                manifest_path,
                artifact_root=effective_artifact_root,
                history_path=history_path,
                run_id=request.run_id,
            )
        except (ManifestError, DatasetError) as error:
            raise _run_error(
                "invalid_manifest", f"invalid manifest: {error}", status_code=422
            ) from error
        except (
            AggregationInputError,
            ArtifactError,
            EvaluationInputError,
            ExecutionError,
            HistoryError,
            ValidationError,
            ValueError,
        ) as error:
            raise _run_error("run_failed", f"run failed: {error}", status_code=422) from error
        return indexed.as_dict(include_report=True)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "evalforge-api", "version": __version__}

    @application.get("/api/runs")
    def list_runs(
        experiment: str | None = None,
        decision: Literal["passed", "failed"] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            runs = read_runs(experiment=experiment, decision=decision)
        except HistoryError as error:
            raise _history_error("history database unavailable") from error
        return [run.as_dict() for run in runs]

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            run = read_run(run_id)
        except HistoryError as error:
            if _is_unknown_run(error):
                raise _history_error("run not found", status_code=404) from error
            raise _history_error("history database unavailable") from error
        return run.as_dict(include_report=True)

    @application.post("/api/runs/{run_id}/replay")
    def replay(run_id: str) -> dict[str, Any]:
        try:
            run = read_run(run_id)
            analysis = replay_run(run)
        except HistoryError as error:
            if _is_unknown_run(error):
                raise _history_error("run not found", status_code=404) from error
            raise _history_error(
                "replay failed: stored artifacts are unavailable", status_code=422
            ) from error
        return jsonable_encoder(analysis.model_dump(mode="python"))

    return application
