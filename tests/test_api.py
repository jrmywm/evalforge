"""Read-only local API acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_api_can_execute_workspace_manifest_and_index_result(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            history_db=tmp_path / "history.sqlite3",
            artifact_root=tmp_path / "artifacts",
            workspace_root=Path.cwd(),
        )
    )
    response = client.post(
        "/api/runs",
        json={"manifest": "examples/invoice/pass.yaml", "run_id": "api-pass"},
    )
    assert response.status_code == 201
    assert response.json()["decision"] == "passed"
    assert client.get("/api/runs/api-pass").status_code == 200


def test_api_rejects_invalid_and_escaping_manifest_paths(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            history_db=tmp_path / "history.sqlite3",
            artifact_root=tmp_path / "artifacts",
            workspace_root=Path.cwd(),
        )
    )
    missing = client.post("/api/runs", json={"manifest": "examples/invoice/missing.yaml"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "manifest_not_found"
    traversal = client.post("/api/runs", json={"manifest": "../README.md"})
    assert traversal.status_code == 422
    assert traversal.json()["detail"]["code"] == "invalid_manifest_path"
    absolute = client.post(
        "/api/runs", json={"manifest": str(Path.cwd() / "examples/invoice/pass.yaml")}
    )
    assert absolute.status_code == 422
    assert client.post("/api/runs", json={"manifest": "examples/../README.md"}).status_code == 422


def test_api_returns_typed_error_for_run_failure(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            history_db=tmp_path / "history.sqlite3",
            artifact_root=tmp_path / "artifacts",
            workspace_root=Path.cwd(),
        )
    )
    payload = {"manifest": "examples/invoice/pass.yaml", "run_id": "same"}
    assert client.post("/api/runs", json=payload).status_code == 201
    failed = client.post("/api/runs", json=payload)
    assert failed.status_code == 422
    assert failed.json()["detail"]["code"] == "run_failed"


def test_api_returns_typed_error_for_invalid_manifest_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "broken.yaml").write_text("name: [not valid", encoding="utf-8")
    client = TestClient(
        create_app(
            workspace_root=workspace,
            artifact_root=tmp_path / "artifacts",
            history_db=tmp_path / "history.sqlite3",
        )
    )

    response = client.post("/api/runs", json={"manifest": "broken.yaml"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_manifest"


def test_api_rejects_symlink_manifest_escape_when_supported(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "pass.yaml").write_text(
        (Path.cwd() / "examples/invoice/pass.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    link = workspace / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    client = TestClient(
        create_app(
            workspace_root=workspace,
            artifact_root=tmp_path / "artifacts",
            history_db=tmp_path / "history.sqlite3",
        )
    )

    response = client.post("/api/runs", json={"manifest": "linked/pass.yaml"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_manifest_path"


def test_api_defaults_history_beside_default_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = Path.cwd() / "examples/invoice/pass.yaml"
    (workspace / "pass.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (workspace / "dataset.jsonl").write_text(
        (Path.cwd() / "examples/invoice/dataset.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    client = TestClient(create_app(workspace_root=workspace))

    response = client.post("/api/runs", json={"manifest": "pass.yaml", "run_id": "default"})

    assert response.status_code == 201
    value = response.json()
    assert Path(value["artifact_root"]) == (workspace / "artifacts").resolve()
    assert Path(value["artifact_dir"]) == (workspace / "artifacts/default").resolve()
    assert (workspace / "artifacts/evalforge.sqlite3").is_file()
