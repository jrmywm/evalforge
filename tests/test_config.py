"""Tests for strict manifest validation and JSONL dataset loading."""

from pathlib import Path

import pytest

from evalforge.config import ManifestError, load_manifest
from evalforge.dataset import DatasetError, load_dataset


def write_manifest(path: Path, dataset_path: str, extra: str = "") -> None:
    path.write_text(
        f"""name: test-experiment
dataset:
  path: {dataset_path}
  version: \"1.0\"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
output_schema:
  type: object
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
{extra}""",
        encoding="utf-8",
    )


def test_dataset_path_is_resolved_relative_to_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_dir = tmp_path / "experiment"
    manifest_dir.mkdir()
    dataset_path = manifest_dir / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":{"text":"hello"},"expected":{"value":"world"}}\n',
        encoding="utf-8",
    )
    manifest_path = manifest_dir / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")
    monkeypatch.chdir(tmp_path)

    dataset = load_dataset(load_manifest(manifest_path))

    assert dataset.path == dataset_path.resolve()
    assert dataset.version == "1.0"
    assert len(dataset.cases) == 1


def test_unknown_manifest_field_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl", extra="unexpected_setting: true\n")

    with pytest.raises(ManifestError, match="Extra inputs are not permitted"):
        load_manifest(manifest_path)


def test_duplicate_test_case_ids_are_rejected(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                '{"id":"duplicate","input":{"text":"a"},"expected":{"value":"a"}}',
                '{"id":"duplicate","input":{"text":"b"},"expected":{"value":"b"}}',
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match="duplicate test-case ID 'duplicate'.*line 2"):
        load_dataset(load_manifest(manifest_path))


def test_invalid_json_line_reports_its_location(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":{"text":"a"},"expected":{"value":"a"}}\nnot json\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match="line 2"):
        load_dataset(load_manifest(manifest_path))
