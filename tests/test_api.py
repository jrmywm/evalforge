"""Read-only local API acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from evalforge.api import LOCAL_DEV_ORIGINS, create_app
from evalforge.cli import app
from evalforge.providers import DeterministicMockProvider

RUNNER = CliRunner()
PASS_MANIFEST = Path("examples/invoice/pass.yaml")
REGRESSION_MANIFEST = Path("examples/invoice/regression.yaml")


def _run(tmp_path: Path, manifest: Path, run_id: str, database: Path) -> None:
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
    expected = 0 if manifest == PASS_MANIFEST else 1
    assert result.exit_code == expected, result.stdout + result.stderr


def test_api_health_list_filter_detail_and_unknown_run(tmp_path: Path) -> None:
    database = tmp_path / "history.sqlite3"
    _run(tmp_path, PASS_MANIFEST, "pass", database)
    _run(tmp_path, REGRESSION_MANIFEST, "regression", database)
    client = TestClient(create_app(history_db=database))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    listed = client.get("/api/runs")
    assert listed.status_code == 200
    assert {item["run_id"] for item in listed.json()} == {"pass", "regression"}
    filtered = client.get("/api/runs", params={"decision": "failed"})
    assert filtered.status_code == 200
    assert [item["run_id"] for item in filtered.json()] == ["regression"]
    invalid_filter = client.get("/api/runs", params={"decision": "unknown"})
    assert invalid_filter.status_code == 422

    detail = client.get("/api/runs/pass")
    assert detail.status_code == 200
    value = detail.json()
    assert value["run_id"] == "pass"
    assert value["report"]["baseline_summary"]["case_pass_count"] == 20
    assert "artifact_digests" in value
    assert client.get("/api/runs/missing").status_code == 404


def test_api_replay_is_offline_and_cors_is_local_only(monkeypatch: object, tmp_path: Path) -> None:
    database = tmp_path / "history.sqlite3"
    _run(tmp_path, PASS_MANIFEST, "pass", database)

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("API replay must not invoke a provider")

    monkeypatch.setattr(DeterministicMockProvider, "generate", fail_if_called)
    client = TestClient(create_app(history_db=database))
    replayed = client.post("/api/runs/pass/replay")
    assert replayed.status_code == 200
    assert replayed.json()["gates"]["decision"] == "passed"

    preflight = client.options(
        "/api/runs",
        headers={
            "Origin": LOCAL_DEV_ORIGINS[0],
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == LOCAL_DEV_ORIGINS[0]
    remote = client.options(
        "/api/runs",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in remote.headers


def test_api_missing_database_is_actionable_without_path_disclosure(tmp_path: Path) -> None:
    client = TestClient(create_app(history_db=tmp_path / "missing.sqlite3"))
    response = client.get("/api/runs")
    assert response.status_code == 500
    assert response.json() == {"detail": "history database unavailable"}
    assert "missing.sqlite3" not in json.dumps(response.json())


def test_serve_rejects_remote_host_and_missing_database(tmp_path: Path) -> None:
    remote = RUNNER.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert remote.exit_code == 2
    assert "--allow-remote" in remote.stderr

    missing = RUNNER.invoke(
        app,
        ["serve", "--history-db", str(tmp_path / "missing.sqlite3")],
    )
    assert missing.exit_code == 2
    assert "does not exist" in missing.stderr
