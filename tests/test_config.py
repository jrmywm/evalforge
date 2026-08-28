"""Tests for strict manifest validation, deep immutability, schema checks, and YAML loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evalforge.config import ManifestError, load_manifest


def write_manifest(path: Path, dataset_path: str = "cases.jsonl", extra: str = "") -> None:
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
{extra}""",
        encoding="utf-8",
    )


def test_missing_manifest_file_raises_manifest_error(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ManifestError, match="manifest does not exist"):
        load_manifest(non_existent)


def test_manifest_root_not_mapping_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="must contain a YAML mapping"):
        load_manifest(manifest_path)


def test_unknown_manifest_field_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, extra="unexpected_setting: true\n")

    with pytest.raises(ManifestError, match="Extra inputs are not permitted"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    "name,ds_path,version,match_error",
    [
        ("   ", "cases.jsonl", "1.0", "name cannot be whitespace-only"),
        ("test", "   ", "1.0", "cannot be whitespace-only"),
        ("test", "cases.jsonl", "   ", "cannot be whitespace-only"),
    ],
)
def test_whitespace_only_manifest_fields_are_rejected(
    tmp_path: Path, name: str, ds_path: str, version: str, match_error: str
) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        f"""name: {name!r}
dataset:
  path: {ds_path!r}
  version: {version!r}
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
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=match_error):
        load_manifest(manifest_path)


def test_manifest_digest_is_reproducible_across_formatting_and_comments(tmp_path: Path) -> None:
    manifest_path_1 = tmp_path / "eval1.yaml"
    write_manifest(manifest_path_1)

    manifest_path_2 = tmp_path / "eval2.yaml"
    manifest_path_2.write_text(
        """# Leading comment
name: "test-experiment"

dataset:
  path: "cases.jsonl"
  version: "1.0"

configurations:
  baseline:
    model: baseline
    provider: mock
  candidate:
    model: candidate
    provider: mock

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

    manifest_1 = load_manifest(manifest_path_1)
    manifest_2 = load_manifest(manifest_path_2)

    assert manifest_1.digest == manifest_2.digest


def test_manifest_deep_immutability(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        """name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
    inference_parameters:
      nested:
        temperature: 0.7
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

    manifest = load_manifest(manifest_path)
    initial_digest = manifest.digest

    with pytest.raises(ValidationError, match="Instance is frozen"):
        manifest.config.name = "tampered"  # type: ignore[misc]

    with pytest.raises(TypeError, match="does not support item assignment"):
        manifest.config.output_schema["tampered"] = True

    with pytest.raises(TypeError, match="does not support item assignment"):
        manifest.config.configurations["candidate"].inference_parameters["temperature"] = 2.0

    with pytest.raises(TypeError, match="does not support item assignment"):
        manifest.config.configurations["candidate"].inference_parameters["nested"][
            "temperature"
        ] = 2.0

    # Ensure manifest digest and state remain identical
    assert manifest.digest == initial_digest
    assert "tampered" not in manifest.config.output_schema


@pytest.mark.parametrize(
    "gate_yaml",
    [
        "  schema_validity:\n    minimum: .nan\n",
        "  schema_validity:\n    minimum: .inf\n",
        "  schema_validity:\n    minimum: -.inf\n",
        "  schema_validity:\n    maximum: .nan\n",
        "  schema_validity:\n    maximum: .inf\n",
        "  schema_validity:\n    maximum: -.inf\n",
        "  schema_validity:\n    minimum: 0.0\n    maximum_regression: .nan\n",
        "  schema_validity:\n    minimum: 0.0\n    maximum_regression: .inf\n",
    ],
)
def test_quality_gates_reject_nan_and_infinities(tmp_path: Path, gate_yaml: str) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        f"""name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
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
{gate_yaml}""",
        encoding="utf-8",
    )

    with pytest.raises(
        ManifestError, match="Input should be a finite number|greater than or equal to 0"
    ):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    "inf_params_yaml",
    [
        "      temp: .nan\n",
        "      temp: .inf\n",
        "      temp: -.inf\n",
        "      nested:\n        val: .nan\n",
        "      timestamp: 2026-01-01\n",
        "      raw_date: 2026-01-01 12:00:00\n",
    ],
)
def test_inference_parameters_reject_non_finite_and_non_json_values(
    tmp_path: Path, inf_params_yaml: str
) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        f"""name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
    inference_parameters:
{inf_params_yaml}output_schema:
  type: object
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="must be finite|cannot be a date or datetime"):
        load_manifest(manifest_path)


def test_output_schema_valid_draft_2020_12(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        """name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
output_schema:
  $schema: "https://json-schema.org/draft/2020-12/schema"
  type: object
  required:
    - invoice_id
  properties:
    invoice_id:
      type: string
evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    assert manifest.config.output_schema["type"] == "object"


@pytest.mark.parametrize(
    "invalid_schema_yaml,expected_error",
    [
        ("output_schema: {}\n", "output_schema cannot be empty"),
        ("output_schema:\n  type: invalid_type_name\n", "invalid JSON Schema"),
        ("output_schema:\n  required: 'should be an array'\n", "invalid JSON Schema"),
        ("output_schema:\n  properties: 'should be a mapping'\n", "invalid JSON Schema"),
        (
            "output_schema:\n"
            "  $schema: 'https://json-schema.org/draft/unknown/schema'\n"
            "  type: object\n",
            "unsupported or invalid \\$schema dialect",
        ),
    ],
)
def test_output_schema_semantic_validation_rejects_invalid_schemas(
    tmp_path: Path, invalid_schema_yaml: str, expected_error: str
) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        f"""name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
  candidate:
    provider: mock
    model: candidate
{invalid_schema_yaml}evaluators:
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=expected_error):
        load_manifest(manifest_path)


def test_quality_gates_rejects_unknown_metrics(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    write_manifest(manifest_path, extra="  unsupported_metric:\n    minimum: 0.5\n")

    with pytest.raises(ManifestError, match="unknown quality gate metric: 'unsupported_metric'"):
        load_manifest(manifest_path)


def test_quality_gates_requires_associated_evaluators(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        """name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
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
  field_accuracy:
    minimum: 0.9
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ManifestError, match="quality gate 'field_accuracy' requires evaluator 'field_accuracy'"
    ):
        load_manifest(manifest_path)


def test_evaluators_reject_duplicates(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_text(
        """name: test-experiment
dataset:
  path: cases.jsonl
  version: "1.0"
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
  - type: json_schema
quality_gates:
  schema_validity:
    minimum: 1.0
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="duplicate evaluator types are not allowed"):
        load_manifest(manifest_path)


def test_duplicate_yaml_keys_rejected_at_any_depth(tmp_path: Path) -> None:
    # Duplicate top-level
    top_dup = tmp_path / "top_dup.yaml"
    top_dup.write_text("name: a\nname: b\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="found duplicate key 'name'"):
        load_manifest(top_dup)

    # Duplicate nested key
    nested_dup = tmp_path / "nested_dup.yaml"
    nested_dup.write_text(
        """name: test
dataset:
  path: cases.jsonl
  version: "1.0"
configurations:
  baseline:
    provider: mock
    model: baseline
    model: duplicate_model
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
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="found duplicate key 'model'"):
        load_manifest(nested_dup)


def test_unhashable_yaml_mapping_keys_rejected(tmp_path: Path) -> None:
    unhashable_manifest = tmp_path / "unhashable.yaml"
    unhashable_manifest.write_text(
        """[1, 2]: mapping_value
""",
        encoding="utf-8",
    )
    with pytest.raises(
        ManifestError, match="unsupported mapping key type|unhashable or invalid key"
    ):
        load_manifest(unhashable_manifest)


def test_malformed_utf8_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval.yaml"
    manifest_path.write_bytes(b"name: \xff\xfe\xfd\n")

    with pytest.raises(ManifestError, match="could not read manifest|invalid YAML"):
        load_manifest(manifest_path)
