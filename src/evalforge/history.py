"""Durable local run history backed by a small, versioned SQLite database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalforge.aggregation import AggregationInputError
from evalforge.analysis import ExperimentAnalysis, analyze_experiment
from evalforge.artifacts import (
    ArtifactError,
    read_dataset_snapshot,
    read_evaluations,
    read_experiment_report,
    read_generations,
    read_manifest_snapshot,
)
from evalforge.evaluators import EvaluationInputError, evaluate_generations
from evalforge.json_types import canonical_digest, thaw_json
from evalforge.report import ExperimentReport


class HistoryError(ValueError):
    """Raised when history storage or a replay input is invalid."""


@dataclass(frozen=True)
class HistoryRun:
    """A compact indexed run record suitable for CLI and future UI consumers."""

    run_id: str
    experiment: str
    decision: str
    artifact_root: Path
    artifact_dir: Path
    manifest_digest: str
    dataset_version: str
    dataset_digest: str
    indexed_at: str
    artifact_digests: dict[str, str]
    report: ExperimentReport

    @property
    def artifacts(self) -> dict[str, str]:
        return {
            name: str(self.artifact_dir / name)
            for name in (
                "manifest.snapshot.yaml",
                "dataset.snapshot.jsonl",
                "generations.jsonl",
                "evaluations.jsonl",
                "experiment.json",
                "report.md",
            )
        }

    def as_dict(self, *, include_report: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "decision": self.decision,
            "artifact_root": str(self.artifact_root),
            "artifact_dir": str(self.artifact_dir),
            "manifest_digest": self.manifest_digest,
            "dataset_version": self.dataset_version,
            "dataset_digest": self.dataset_digest,
            "indexed_at": self.indexed_at,
            "artifact_digests": self.artifact_digests,
            "artifacts": self.artifacts,
        }
        if include_report:
            value["report"] = thaw_json(self.report.model_dump(mode="python"))
        return value


def default_history_path(artifact_root: Path | None = None) -> Path:
    """Resolve the default DB below the effective artifact root."""
    return (artifact_root or Path("artifacts")).expanduser().resolve() / "evalforge.sqlite3"


def resolve_history_path(
    history_db: Path | None = None, *, artifact_root: Path | None = None
) -> Path:
    """Resolve an explicit DB path or the artifact-root-local default."""
    return history_db.expanduser().resolve() if history_db else default_history_path(artifact_root)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def _report_json(report: ExperimentReport) -> str:
    return (
        json.dumps(
            thaw_json(report.model_dump(mode="python")),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        + "\n"
    )


_ARTIFACT_NAMES = (
    "manifest.snapshot.yaml",
    "dataset.snapshot.jsonl",
    "generations.jsonl",
    "evaluations.jsonl",
    "experiment.json",
    "report.md",
)


def _artifact_digests(artifact_dir: Path) -> dict[str, str]:
    """Require and hash the complete immutable artifact set."""
    digests: dict[str, str] = {}
    for name in _ARTIFACT_NAMES:
        candidate = artifact_dir / name
        if candidate.is_symlink():
            raise HistoryError(f"cannot index run; required artifact is missing or unsafe: {name}")
        path = candidate.resolve()
        if path.parent != artifact_dir or not path.is_file():
            raise HistoryError(f"cannot index run; required artifact is missing or unsafe: {name}")
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise HistoryError(f"could not hash artifact {path}: {error}") from error
        digests[name] = digest.hexdigest()
    return digests


class HistoryRepository:
    """SQLite repository for immutable completed experiment reports."""

    schema_version = 2

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5.0)
            self.connection = connection
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA busy_timeout = 5000")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self._initialize()
        except HistoryError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise HistoryError(f"could not open history database {self.path}: {error}") from error

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> HistoryRepository:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _initialize(self) -> None:
        try:
            version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
            if version > self.schema_version:
                raise HistoryError(
                    f"history database schema version {version} is newer than supported "
                    f"version {self.schema_version}"
                )
            if version == 0:
                with self.connection:
                    self.connection.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS schema_meta (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS runs (
                            id INTEGER PRIMARY KEY,
                            artifact_root TEXT NOT NULL,
                            run_id TEXT NOT NULL,
                            artifact_dir TEXT NOT NULL,
                            experiment TEXT NOT NULL,
                            decision TEXT NOT NULL CHECK (decision IN ('passed', 'failed')),
                            manifest_digest TEXT NOT NULL,
                            dataset_version TEXT NOT NULL,
                            dataset_digest TEXT NOT NULL,
                            indexed_at TEXT NOT NULL,
                            report_digest TEXT NOT NULL,
                            artifact_digests TEXT NOT NULL,
                            report_json TEXT NOT NULL,
                            UNIQUE (artifact_root, run_id)
                        );
                        CREATE INDEX IF NOT EXISTS runs_experiment_idx
                            ON runs (experiment, indexed_at DESC);
                        CREATE INDEX IF NOT EXISTS runs_decision_idx
                            ON runs (decision, indexed_at DESC);
                        INSERT OR REPLACE INTO schema_meta(key, value)
                            VALUES ('schema_version', '2');
                        PRAGMA user_version = 2;
                        """
                    )
            elif version == 1:
                with self.connection:
                    self.connection.execute(
                        "ALTER TABLE runs ADD COLUMN artifact_digests TEXT NOT NULL DEFAULT '{}'"
                    )
                    self.connection.execute(
                        "UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'"
                    )
                    self.connection.execute("PRAGMA user_version = 2")
        except sqlite3.Error as error:
            raise HistoryError(
                f"could not initialize history database {self.path}: {error}"
            ) from error

    def index_report(self, report: ExperimentReport, artifact_dir: Path) -> HistoryRun:
        """Transactionally index a completed report, rejecting incompatible collisions."""
        artifact_dir = artifact_dir.expanduser().resolve()
        artifact_root = artifact_dir.parent
        artifact_digests = _artifact_digests(artifact_dir)
        report_json = _report_json(report)
        report_digest = canonical_digest(report_json)
        indexed_at = datetime.now(UTC).isoformat()
        try:
            with self.connection:
                existing = self.connection.execute(
                    """
                    SELECT * FROM runs WHERE artifact_root = ? AND run_id = ?
                    """,
                    (str(artifact_root), report.run_id),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["artifact_dir"] == str(artifact_dir)
                        and existing["report_digest"] == report_digest
                    ):
                        try:
                            stored_digests = json.loads(existing["artifact_digests"] or "{}")
                        except (TypeError, json.JSONDecodeError) as error:
                            raise HistoryError(
                                "history contains invalid artifact digest metadata"
                            ) from error
                        if stored_digests == {}:
                            self.connection.execute(
                                "UPDATE runs SET artifact_digests = ? WHERE id = ?",
                                (
                                    json.dumps(
                                        artifact_digests,
                                        sort_keys=True,
                                        separators=(",", ":"),
                                    ),
                                    existing["id"],
                                ),
                            )
                            refreshed = self.connection.execute(
                                "SELECT * FROM runs WHERE id = ?", (existing["id"],)
                            ).fetchone()
                            if refreshed is None:
                                raise HistoryError(
                                    "history migration did not refresh the indexed run"
                                )
                            return self._row_to_run(refreshed)
                        if stored_digests != artifact_digests:
                            raise HistoryError("history artifacts have changed since indexing")
                        return self._row_to_run(existing)
                    raise HistoryError(
                        "history run collision: the same artifact root and run ID already "
                        "refer to different report data"
                    )
                self.connection.execute(
                    """
                    INSERT INTO runs(
                        artifact_root, run_id, artifact_dir, experiment, decision,
                        manifest_digest, dataset_version, dataset_digest, indexed_at,
                        report_digest, artifact_digests, report_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(artifact_root),
                        report.run_id,
                        str(artifact_dir),
                        report.experiment,
                        report.gates.decision,
                        report.manifest_digest,
                        report.dataset_version,
                        report.dataset_digest,
                        indexed_at,
                        report_digest,
                        json.dumps(artifact_digests, sort_keys=True, separators=(",", ":")),
                        report_json,
                    ),
                )
                row = self.connection.execute(
                    "SELECT * FROM runs WHERE artifact_root = ? AND run_id = ?",
                    (str(artifact_root), report.run_id),
                ).fetchone()
                if row is None:
                    raise HistoryError("history insert did not return the indexed run")
                return self._row_to_run(row)
        except HistoryError:
            raise
        except sqlite3.Error as error:
            raise HistoryError(f"could not index run in {self.path}: {error}") from error

    def _row_to_run(self, row: sqlite3.Row) -> HistoryRun:
        try:
            report = ExperimentReport.model_validate_json(row["report_json"])
        except ValidationError as error:
            raise HistoryError(f"history contains an invalid stored report: {error}") from error
        try:
            artifact_digests = json.loads(row["artifact_digests"] or "{}")
        except (TypeError, json.JSONDecodeError) as error:
            raise HistoryError("history contains invalid artifact digest metadata") from error
        if not isinstance(artifact_digests, dict) or not all(
            isinstance(name, str) and isinstance(digest, str)
            for name, digest in artifact_digests.items()
        ):
            raise HistoryError("history contains invalid artifact digest metadata")
        return HistoryRun(
            run_id=row["run_id"],
            experiment=row["experiment"],
            decision=row["decision"],
            artifact_root=Path(row["artifact_root"]),
            artifact_dir=Path(row["artifact_dir"]),
            manifest_digest=row["manifest_digest"],
            dataset_version=row["dataset_version"],
            dataset_digest=row["dataset_digest"],
            indexed_at=row["indexed_at"],
            artifact_digests=artifact_digests,
            report=report,
        )

    def list_runs(
        self, *, experiment: str | None = None, decision: str | None = None
    ) -> tuple[HistoryRun, ...]:
        """List indexed runs newest first, with optional exact filters."""
        if decision is not None and decision not in {"passed", "failed"}:
            raise HistoryError("history decision filter must be 'passed' or 'failed'")
        query = "SELECT * FROM runs"
        parameters: list[str] = []
        clauses: list[str] = []
        if experiment is not None:
            clauses.append("experiment = ?")
            parameters.append(experiment)
        if decision is not None:
            clauses.append("decision = ?")
            parameters.append(decision)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY indexed_at DESC, id DESC"
        try:
            rows = self.connection.execute(query, parameters).fetchall()
            return tuple(self._row_to_run(row) for row in rows)
        except sqlite3.Error as error:
            raise HistoryError(f"could not list history from {self.path}: {error}") from error

    def get_run(self, run_id: str) -> HistoryRun:
        """Get one run, rejecting ambiguity across multiple artifact roots."""
        try:
            rows = self.connection.execute(
                "SELECT * FROM runs WHERE run_id = ? ORDER BY indexed_at DESC, id DESC",
                (run_id,),
            ).fetchall()
        except sqlite3.Error as error:
            raise HistoryError(f"could not read history from {self.path}: {error}") from error
        if not rows:
            raise HistoryError(f"run ID {run_id!r} was not found in {self.path}")
        if len(rows) > 1:
            raise HistoryError(
                f"run ID {run_id!r} exists under multiple artifact roots; use a specific history DB"
            )
        return self._row_to_run(rows[0])


def replay_run(run: HistoryRun) -> ExperimentAnalysis:
    """Reevaluate immutable snapshots without constructing or invoking a provider."""
    artifact_dir = run.artifact_dir
    if artifact_dir.is_symlink() or not artifact_dir.is_dir():
        raise HistoryError(
            f"cannot replay run; artifact directory is missing or unsafe: {artifact_dir}"
        )
    resolved_artifact_dir = artifact_dir.resolve()
    if resolved_artifact_dir != artifact_dir:
        raise HistoryError(
            "cannot replay run; artifact directory resolves outside its indexed path"
        )
    required = tuple(resolved_artifact_dir / name for name in _ARTIFACT_NAMES)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise HistoryError(f"cannot replay run; missing artifact(s): {', '.join(missing)}")
    try:
        if any(
            path.resolve().parent != resolved_artifact_dir
            or path.is_symlink()
            or not path.is_file()
            for path in required
        ):
            raise HistoryError("cannot replay run; an artifact resolves outside its run directory")
        for path in required:
            name = path.name
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as error:
                raise HistoryError(f"cannot read artifact {name}: {error}") from error
            if run.artifact_digests.get(name) != digest:
                raise HistoryError(f"artifact integrity check failed for {name}")
        manifest = read_manifest_snapshot(required[0])
        manifest_digest = canonical_digest(manifest.model_dump(mode="json"))
        if not (manifest_digest == run.manifest_digest == run.report.manifest_digest):
            raise HistoryError("manifest snapshot digest does not match the indexed report")
        dataset = read_dataset_snapshot(required[1], version=manifest.dataset.version)
        if not (
            dataset.digest == run.dataset_digest == run.report.dataset_digest
            and dataset.version
            == run.dataset_version
            == run.report.dataset_version
            == manifest.dataset.version
        ):
            raise HistoryError("dataset snapshot metadata does not match the indexed report")
        generations = read_generations(required[2])
        read_evaluations(required[3])
        stored_report = read_experiment_report(required[4])
        if stored_report != run.report:
            raise HistoryError("stored report does not match the report indexed in history")
        evaluations = evaluate_generations(manifest, dataset, generations, artifact_path=None)
        return analyze_experiment(manifest, dataset, generations, evaluations)
    except (ArtifactError, AggregationInputError, EvaluationInputError, ValidationError) as error:
        raise HistoryError(f"cannot replay run {run.run_id!r}: {error}") from error


def load_report_for_history(path: Path) -> ExperimentReport:
    """Read a report through the same strict parser used by artifact consumers."""
    return read_experiment_report(path)
