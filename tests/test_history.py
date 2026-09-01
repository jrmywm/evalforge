"""Durable SQLite history and offline replay acceptance tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalforge.artifacts import read_experiment_report
from evalforge.cli import app
from evalforge.history import HistoryError, HistoryRepository, _report_json, replay_run
from evalforge.json_types import canonical_digest
from evalforge.providers import DeterministicMockProvider

RUNNER = CliRunner()
PASS_MANIFEST = Path("examples/invoice/pass.yaml")
REGRESSION_MANIFEST = Path("examples/invoice/regression.yaml")


def _run(
    tmp_path: Path, manifest: Path = PASS_MANIFEST, run_id: str = "run", db: Path | None = None
) -> Path:
    database = db or tmp_path / "history.sqlite3"
    result = RUNNER.invoke(
        app,
        [
            "run",
            str(manifest),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            run_id,
            "--history-db",
            str(database),
        ],
    )
    expected_code = 0 if manifest == PASS_MANIFEST else 1
    assert result.exit_code == expected_code, result.stdout + result.stderr
    return tmp_path / "artifacts" / run_id


def test_history_schema_index_is_transactional_and_idempotent(tmp_path: Path) -> None:
    artifact_dir = _run(tmp_path)
    db_path = tmp_path / "history.sqlite3"
    report = read_experiment_report(artifact_dir / "experiment.json")
    with HistoryRepository(db_path) as history:
        indexed = history.index_report(report, artifact_dir)
        repeated = history.index_report(report, artifact_dir)
        assert repeated == indexed
        with pytest.raises(HistoryError, match="collision"):
            history.index_report(
                report.model_copy(update={"evalforge_version": "tampered"}), artifact_dir
            )

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'runs'").fetchone()
    finally:
        connection.close()


def test_history_list_show_and_filters_are_user_facing(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "history.sqlite3"
    _run(tmp_path, run_id="pass", db=db_path)
    _run(tmp_path, REGRESSION_MANIFEST, run_id="regression", db=db_path)

    listed = RUNNER.invoke(app, ["history", "list", "--history-db", str(db_path), "--json"])
    assert listed.exit_code == 0, listed.stdout + listed.stderr
    values = json.loads(listed.stdout)
    assert {value["run_id"] for value in values} == {"pass", "regression"}
    filtered = RUNNER.invoke(
        app,
        [
            "history",
            "list",
            "--history-db",
            str(db_path),
            "--decision",
            "failed",
            "--json",
        ],
    )
    assert filtered.exit_code == 0
    assert [value["run_id"] for value in json.loads(filtered.stdout)] == ["regression"]

    shown = RUNNER.invoke(app, ["history", "show", "pass", "--history-db", str(db_path), "--json"])
    assert shown.exit_code == 0, shown.stdout + shown.stderr
    shown_value = json.loads(shown.stdout)
    assert shown_value["report"]["run_id"] == "pass"
    assert shown_value["artifacts"]["experiment.json"].endswith("pass\\experiment.json")


def test_replay_uses_only_stored_snapshots_and_no_provider(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = _run(tmp_path)
    db_path = tmp_path / "history.sqlite3"

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("replay must not invoke a provider")

    monkeypatch.setattr(DeterministicMockProvider, "generate", fail_if_called)
    replayed = RUNNER.invoke(app, ["replay", "run", "--history-db", str(db_path), "--json"])
    assert replayed.exit_code == 0, replayed.stdout + replayed.stderr
    assert json.loads(replayed.stdout)["gates"]["decision"] == "passed"

    (artifact_dir / "evaluations.jsonl").unlink()
    missing = RUNNER.invoke(app, ["replay", "run", "--history-db", str(db_path)])
    assert missing.exit_code == 2
    assert "missing artifact" in missing.stderr


def test_replay_repository_api_returns_analysis(tmp_path: Path) -> None:
    artifact_dir = _run(tmp_path)
    with HistoryRepository(tmp_path / "history.sqlite3") as history:
        run = history.get_run("run")
    analysis = replay_run(run)
    assert analysis.gates.passed
    assert analysis.candidate.case_pass_count == 20
    assert artifact_dir.is_dir()


def test_default_run_and_history_use_the_same_cwd_artifact_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = (Path(__file__).resolve().parents[1] / PASS_MANIFEST).resolve()
    monkeypatch.chdir(tmp_path)
    result = RUNNER.invoke(app, ["run", str(manifest), "--run-id", "default"])
    assert result.exit_code == 0, result.stdout + result.stderr

    listed = RUNNER.invoke(app, ["history", "list", "--json"])
    assert listed.exit_code == 0, listed.stdout + listed.stderr
    assert [item["run_id"] for item in json.loads(listed.stdout)] == ["default"]

    shown = RUNNER.invoke(app, ["history", "show", "default", "--json"])
    assert shown.exit_code == 0, shown.stdout + shown.stderr
    assert json.loads(shown.stdout)["run_id"] == "default"


def test_replay_rejects_tampered_artifact_digest_without_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_dir = _run(tmp_path)
    db_path = tmp_path / "history.sqlite3"

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("replay must not invoke a provider")

    monkeypatch.setattr(DeterministicMockProvider, "generate", fail_if_called)
    generations_path = artifact_dir / "generations.jsonl"
    generations_path.write_text(
        generations_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    replayed = RUNNER.invoke(app, ["replay", "run", "--history-db", str(db_path)])
    assert replayed.exit_code == 2
    assert "integrity" in replayed.stderr.lower() or "digest" in replayed.stderr.lower()


def test_v1_history_migration_backfills_artifact_digests(tmp_path: Path) -> None:
    artifact_dir = _run(tmp_path)
    report = read_experiment_report(artifact_dir / "experiment.json")
    report_json = _report_json(report)
    db_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY,
            artifact_root TEXT NOT NULL,
            run_id TEXT NOT NULL,
            artifact_dir TEXT NOT NULL,
            experiment TEXT NOT NULL,
            decision TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            dataset_digest TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            report_digest TEXT NOT NULL,
            report_json TEXT NOT NULL,
            UNIQUE (artifact_root, run_id)
        );
        INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');
        PRAGMA user_version = 1;
        """
    )
    connection.execute(
        """
        INSERT INTO runs(
            artifact_root, run_id, artifact_dir, experiment, decision,
            manifest_digest, dataset_version, dataset_digest, indexed_at,
            report_digest, report_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(artifact_dir.parent),
            report.run_id,
            str(artifact_dir),
            report.experiment,
            report.gates.decision,
            report.manifest_digest,
            report.dataset_version,
            report.dataset_digest,
            "2026-09-01T00:00:00+00:00",
            canonical_digest(report_json),
            report_json,
        ),
    )
    connection.commit()
    connection.close()

    with HistoryRepository(db_path) as history:
        upgraded = history.index_report(report, artifact_dir)
        assert set(upgraded.artifact_digests) == {
            "manifest.snapshot.yaml",
            "dataset.snapshot.jsonl",
            "generations.jsonl",
            "evaluations.jsonl",
            "experiment.json",
            "report.md",
        }
        assert (
            history.connection.execute(
                "SELECT artifact_digests FROM runs WHERE run_id = ?", (report.run_id,)
            ).fetchone()[0]
            != "{}"
        )


def test_replay_requires_exact_indexed_manifest_and_dataset_metadata(tmp_path: Path) -> None:
    artifact_dir = _run(tmp_path)
    db_path = tmp_path / "history.sqlite3"
    report = read_experiment_report(artifact_dir / "experiment.json")
    tampered_values = (
        ("manifest_digest", "tampered-manifest", "manifest snapshot digest"),
        ("dataset_digest", "tampered-dataset", "dataset snapshot metadata"),
        ("dataset_version", "tampered-version", "dataset snapshot metadata"),
    )
    for column, value, message in tampered_values:
        connection = sqlite3.connect(db_path)
        connection.execute(f"UPDATE runs SET {column} = ? WHERE run_id = ?", (value, report.run_id))
        connection.commit()
        connection.close()
        with HistoryRepository(db_path) as history:
            run = history.get_run(report.run_id)
        with pytest.raises(HistoryError, match=message):
            replay_run(run)
        connection = sqlite3.connect(db_path)
        connection.execute(
            f"UPDATE runs SET {column} = ? WHERE run_id = ?",
            (getattr(report, column), report.run_id),
        )
        connection.commit()
        connection.close()


def test_history_imports_clean_clone_without_provider(monkeypatch, tmp_path: Path) -> None:
    source_dir = _run(tmp_path / "source")
    clone_dir = tmp_path / "clone" / "run"
    shutil.copytree(source_dir, clone_dir)
    database = tmp_path / "imported.sqlite3"

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("artifact import must not invoke a provider")

    monkeypatch.setattr(DeterministicMockProvider, "generate", fail_if_called)
    imported = RUNNER.invoke(
        app,
        ["history", "import", str(clone_dir), "--history-db", str(database)],
    )
    assert imported.exit_code == 0, imported.stdout + imported.stderr
    assert "Imported run: run" in imported.stdout

    repeated = RUNNER.invoke(
        app,
        ["history", "import", str(clone_dir), "--history-db", str(database)],
    )
    assert repeated.exit_code == 0, repeated.stdout + repeated.stderr
    with HistoryRepository(database) as history:
        run = history.get_run("run")
    assert run.artifact_dir == clone_dir.resolve()


def test_history_import_rejects_incomplete_artifact_directory(tmp_path: Path) -> None:
    source_dir = _run(tmp_path / "source")
    clone_dir = tmp_path / "incomplete"
    shutil.copytree(source_dir, clone_dir)
    (clone_dir / "evaluations.jsonl").unlink()
    database = tmp_path / "imported.sqlite3"

    result = RUNNER.invoke(
        app,
        ["history", "import", str(clone_dir), "--history-db", str(database)],
    )
    assert result.exit_code == 2
    assert "required artifact" in result.stderr or "missing" in result.stderr
