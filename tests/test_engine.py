"""Milestone 2 execution, provider isolation, and artifact round trips."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from evalforge.artifacts import (
    ArtifactError,
    read_dataset_snapshot,
    read_generations,
    read_manifest_snapshot,
)
from evalforge.config import load_manifest
from evalforge.engine import ExecutionError, execute_experiment
from evalforge.models import GenerationRecord
from evalforge.providers import DeterministicMockProvider


def write_example(tmp_path: Path, *, provider: str = "mock") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(
            [
                '{"id":"case-1","input":{"text":"Invoice #1\\nTotal: USD 12.50"},'
                '"expected":{"value":"x"}}',
                '{"id":"case-2","input":{"text":"Invoice #2\\nTotal: EUR 8,50"},'
                '"expected":{"value":"y"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "eval.yaml"
    manifest.write_text(
        f"""name: execution-test
dataset:
  path: cases.jsonl
  version: '1.0'
configurations:
  baseline:
    provider: {provider}
    model: baseline
  candidate:
    provider: {provider}
    model: candidate
output_schema:
  type: object
  properties:
    value:
      type: string
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 0.0
""",
        encoding="utf-8",
    )
    return manifest


def test_both_configurations_run_every_case_and_mock_output_is_repeatable(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    first = execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="first")
    second = execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="second")

    assert len(first.generations) == 4
    assert {record.configuration for record in first.generations} == {"baseline", "candidate"}
    assert {record.case_id for record in first.generations} == {"case-1", "case-2"}
    assert all(record.status == "success" for record in first.generations)
    assert all(record.origin == "fresh" for record in first.generations)
    assert [record.normalized_response for record in first.generations] == [
        record.normalized_response for record in second.generations
    ]
    assert all(record.estimated_cost_usd == 0.0 for record in first.generations)


def test_provider_error_is_recorded_without_aborting_remaining_cases(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))

    def provider_factory(model_config):
        return DeterministicMockProvider(model_config.model, fail_case_ids={"case-1"})

    result = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="provider-error",
        provider_factory=provider_factory,
    )

    assert len(result.generations) == 4
    errors = [record for record in result.generations if record.status == "provider_error"]
    assert len(errors) == 2
    assert {record.case_id for record in errors} == {"case-1"}
    assert all(record.error is not None for record in errors)
    assert all(record.error.type == "mock_provider_error" for record in errors if record.error)
    assert sum(record.status == "success" for record in result.generations) == 2


def test_infrastructure_error_opens_circuit_but_keeps_complete_records(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))

    class UnavailableProvider:
        calls = 0

        def generate(self, request):
            self.calls += 1
            error = RuntimeError("local endpoint unavailable")
            error.error_type = "network_error"  # type: ignore[attr-defined]
            raise error

    provider = UnavailableProvider()

    result = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="circuit",
        provider_factory=lambda _: provider,
    )

    assert provider.calls == 2
    assert len(result.generations) == 4
    assert all(record.status == "provider_error" for record in result.generations)
    assert all(record.error is not None for record in result.generations)
    assert (
        sum(record.error.details.get("circuit_open", False) for record in result.generations) == 2
    )


def test_generation_artifacts_round_trip_to_domain_models(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    result = execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="round-trip")
    artifact_dir = result.artifact_dir

    restored_manifest = read_manifest_snapshot(artifact_dir / "manifest.snapshot.yaml")
    restored_dataset = read_dataset_snapshot(
        artifact_dir / "dataset.snapshot.jsonl",
        version="1.0",
        source_path=manifest.path.parent / "cases.jsonl",
    )
    restored_generations = read_generations(artifact_dir / "generations.jsonl")

    assert restored_manifest == manifest.config
    assert restored_dataset.digest == result.dataset.digest
    assert restored_dataset.cases == result.dataset.cases
    assert restored_generations == result.generations


def test_generation_id_includes_provider_identity(tmp_path: Path) -> None:
    first_manifest = load_manifest(write_example(tmp_path / "first", provider="provider-a"))
    second_manifest = load_manifest(write_example(tmp_path / "second", provider="provider-b"))

    def factory(model_config):
        return DeterministicMockProvider(model_config.model)

    first = execute_experiment(
        first_manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="provider-a",
        provider_factory=factory,
    )
    second = execute_experiment(
        second_manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="provider-b",
        provider_factory=factory,
    )

    assert first.generations[0].normalized_request == second.generations[0].normalized_request
    assert first.generations[0].generation_id != second.generations[0].generation_id


def test_generation_record_rejects_inconsistent_terminal_states(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    result = execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="valid")
    valid = result.generations[0]
    payload = valid.model_dump(mode="python")

    invalid_success = {**payload, "status": "success", "error": {"type": "x", "message": "x"}}
    with pytest.raises(ValueError, match="successful generation cannot contain"):
        GenerationRecord.model_validate(invalid_success)

    invalid_error = {**payload, "status": "provider_error", "error": None}
    with pytest.raises(ValueError, match="must contain an error"):
        GenerationRecord.model_validate(invalid_error)

    invalid_error_response = {
        **payload,
        "status": "provider_error",
        "error": {"type": "x", "message": "x"},
    }
    with pytest.raises(ValueError, match="cannot contain a response"):
        GenerationRecord.model_validate(invalid_error_response)

    invalid_time = {
        **payload,
        "started_at": valid.ended_at + timedelta(seconds=1),
    }
    with pytest.raises(ValueError, match="ended_at must be greater"):
        GenerationRecord.model_validate(invalid_time)

    invalid_linkage = {**payload, "experiment": "other"}
    with pytest.raises(ValueError, match="experiment must match normalized_request"):
        GenerationRecord.model_validate(invalid_linkage)


def test_invalid_generation_artifact_is_rejected_by_domain_parser(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    result = execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="invalid")
    path = result.artifact_dir / "generations.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    record["status"] = "provider_error"
    record["error"] = None
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ArtifactError, match="invalid generation artifact"):
        read_generations(path)


def test_existing_run_directory_is_not_overwritten(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="same")

    with pytest.raises(ArtifactError, match="artifact run directory already exists"):
        execute_experiment(manifest, artifact_root=tmp_path / "artifacts", run_id="same")


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "../escape", "nested/run", "nested\\run", "C:\\outside"],
)
def test_run_id_is_one_safe_path_component_and_cannot_escape_artifact_root(
    tmp_path: Path, run_id: str
) -> None:
    manifest = load_manifest(write_example(tmp_path))
    artifact_root = tmp_path / "artifacts"
    with pytest.raises(ExecutionError, match="run_id"):
        execute_experiment(manifest, artifact_root=artifact_root, run_id=run_id)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "nested").exists()
    assert not (tmp_path / "outside").exists()


def test_concurrency_must_be_positive(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    with pytest.raises(ExecutionError, match="concurrency must be at least 1"):
        execute_experiment(manifest, artifact_root=tmp_path / "artifacts", concurrency=0)


def test_concurrent_execution_preserves_deterministic_order(tmp_path: Path) -> None:
    manifest = load_manifest(write_example(tmp_path))
    serial_run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="serial",
        concurrency=1,
    )
    concurrent_run = execute_experiment(
        manifest,
        artifact_root=tmp_path / "artifacts",
        run_id="concurrent",
        concurrency=4,
    )
    serial_cases = [(r.configuration, r.case_id, r.status) for r in serial_run.generations]
    concurrent_cases = [(r.configuration, r.case_id, r.status) for r in concurrent_run.generations]
    assert serial_cases == concurrent_cases
    assert len(concurrent_run.generations) == 4
