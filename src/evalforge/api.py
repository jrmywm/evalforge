"""Read-only local HTTP API over indexed EvalForge history."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from evalforge import __version__
from evalforge.history import HistoryError, HistoryRepository, replay_run, resolve_history_path

LOCAL_DEV_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


def _history_error(message: str, *, status_code: int = 500) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _is_unknown_run(error: HistoryError) -> bool:
    return "was not found" in str(error)


def create_app(*, history_db: Path | None = None, artifact_root: Path | None = None) -> FastAPI:
    """Build a read-only API bound to one local history database."""
    history_path = resolve_history_path(history_db, artifact_root=artifact_root)
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
