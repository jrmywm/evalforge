"""Tests for JSON Lines dataset validation, deep immutability, encoding, and error paths."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evalforge.config import load_manifest
from evalforge.dataset import DatasetError, load_dataset


def write_manifest(path: Path, dataset_path: str = "cases.jsonl") -> None:
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
  properties:
    val:
      type: string
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
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


@pytest.mark.parametrize(
    "record,duplicate_key",
    [
        (
            '{"id":"first","id":"second","input":{"text":"a"},"expected":{"value":"a"}}',
            "id",
        ),
        (
            '{"id":"case-1","input":{"text":"a","text":"b"},"expected":{"value":"a"}}',
            "text",
        ),
        (
            '{"id":"case-1","input":{"nested":{"value":1,"value":2}},"expected":{"value":"a"}}',
            "value",
        ),
    ],
)
def test_duplicate_json_keys_are_rejected(tmp_path: Path, record: str, duplicate_key: str) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(record + "\n", encoding="utf-8")
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match=rf"duplicate JSON key '{duplicate_key}' is not allowed"):
        load_dataset(load_manifest(manifest_path))


def test_empty_dataset_is_rejected(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text("\n\n   \n", encoding="utf-8")
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match="contains no test cases"):
        load_dataset(load_manifest(manifest_path))


def test_missing_dataset_file_raises_dataset_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "missing_cases.jsonl")

    with pytest.raises(DatasetError, match="dataset does not exist"):
        load_dataset(load_manifest(manifest_path))


def test_malformed_utf8_dataset_raises_dataset_error(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_bytes(
        b'{"id":"case-1","input":{"text":"\xff\xfe\xfd"},"expected":{"val":"a"}}\n'
    )
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match="could not read dataset"):
        load_dataset(load_manifest(manifest_path))


def test_utf8_bom_dataset_is_supported(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_bytes(
        b'\xef\xbb\xbf{"id":"case-1","input":{"text":"hello"},"expected":{"val":"world"}}\n'
    )
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    dataset = load_dataset(load_manifest(manifest_path))
    assert len(dataset.cases) == 1
    assert dataset.cases[0].id == "case-1"


def test_dataset_deep_immutability(tmp_path: Path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":{"text":"hello","meta":{"k":"v"}},"expected":{"nested":{"value":"world"}},"tags":["tag1"]}\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    manifest = load_manifest(manifest_path)
    dataset = load_dataset(manifest)
    initial_digest = dataset.digest

    case = dataset.cases[0]

    with pytest.raises(ValidationError, match="Instance is frozen"):
        case.id = "mutated-id"  # type: ignore[misc]

    with pytest.raises(TypeError, match="does not support item assignment"):
        case.input["text"] = "mutated"

    with pytest.raises(TypeError, match="does not support item assignment"):
        case.input["meta"]["k"] = "mutated"

    with pytest.raises(TypeError, match="does not support item assignment"):
        case.expected["nested"]["value"] = "mutated"

    with pytest.raises(AttributeError):
        case.tags.append("mutated")  # type: ignore[attr-defined]

    assert dataset.digest == initial_digest
    assert case.input["text"] == "hello"


@pytest.mark.parametrize(
    "invalid_record,expected_err",
    [
        (
            '{"id":"c1","input":{"score":NaN},"expected":{"val":"a"}}',
            "nonstandard JSON constant 'NaN'",
        ),
        (
            '{"id":"c1","input":{"score":Infinity},"expected":{"val":"a"}}',
            "nonstandard JSON constant 'Infinity'",
        ),
        (
            '{"id":"c1","input":{"score":-Infinity},"expected":{"val":"a"}}',
            "nonstandard JSON constant '-Infinity'",
        ),
        (
            '{"id":"c1","input":{"nested":{"v":NaN}},"expected":{"val":"a"}}',
            "nonstandard JSON constant 'NaN'",
        ),
    ],
)
def test_nan_and_infinities_in_dataset_are_rejected(
    tmp_path: Path, invalid_record: str, expected_err: str
) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(invalid_record + "\n", encoding="utf-8")
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match=expected_err):
        load_dataset(load_manifest(manifest_path))


@pytest.mark.parametrize(
    "bad_case,match_err",
    [
        ('{"id":"  ","input":{"t":"a"},"expected":{"val":"a"}}', "id cannot be whitespace-only"),
        ('{"id":"c1","input":{"t":"a"},"expected":{}}', "expected must contain at least 1 key"),
        ('{"id":"c1","input":{},"expected":{"val":"a"}}', "input must contain at least 1 key"),
        (
            '{"id":"c1","input":{"t":"a"},"expected":{"val":"a"},"tags":["tag1","tag1"]}',
            "duplicate tag 'tag1'",
        ),
        (
            '{"id":"c1","input":{"t":"a"},"expected":{"val":"a"},"tags":["  "]}',
            "tags must be non-empty strings",
        ),
    ],
)
def test_testcase_validation_constraints(tmp_path: Path, bad_case: str, match_err: str) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(bad_case + "\n", encoding="utf-8")
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, "cases.jsonl")

    with pytest.raises(DatasetError, match=match_err):
        load_dataset(load_manifest(manifest_path))
