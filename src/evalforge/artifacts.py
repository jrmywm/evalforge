"""Portable, atomic artifact persistence for experiment snapshots and reports."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from evalforge.config import ExperimentConfig
from evalforge.dataset import DatasetSnapshot, TestCase
from evalforge.json_types import canonical_digest, thaw_json
from evalforge.models import GenerationRecord

if TYPE_CHECKING:
    from evalforge.evaluators.base import EvaluationResult
    from evalforge.report import ExperimentReport


class ArtifactError(ValueError):
    """Raised when an artifact cannot be written or parsed."""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    except OSError as error:
        raise ArtifactError(f"could not write artifact {path}: {error}") from error
    finally:
        if temporary:
            temporary_path = Path(temporary)
            if temporary_path.exists():
                temporary_path.unlink()


def _atomic_write_new(path: Path, content: str) -> None:
    """Atomically create a new artifact and reject an existing destination."""
    if path.exists():
        raise ArtifactError(f"artifact already exists: {path.resolve()}")
    _atomic_write(path, content)


def write_manifest_snapshot(path: Path, config: ExperimentConfig) -> None:
    """Write the validated manifest as a YAML snapshot."""
    data = thaw_json(config.model_dump(mode="json"))
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def read_manifest_snapshot(path: Path) -> ExperimentConfig:
    """Parse a manifest snapshot back into the strict domain model."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return ExperimentConfig.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ArtifactError(f"invalid manifest snapshot {path}: {error}") from error


def write_dataset_snapshot(path: Path, dataset: DatasetSnapshot) -> None:
    """Write one canonical JSON object per test case."""
    lines = [
        json.dumps(
            thaw_json(case.model_dump(mode="json")), ensure_ascii=False, separators=(",", ":")
        )
        for case in dataset.cases
    ]
    _atomic_write(path, "\n".join(lines) + "\n")


def read_dataset_snapshot(
    path: Path, *, version: str = "snapshot", source_path: Path | None = None
) -> DatasetSnapshot:
    """Parse a JSONL dataset snapshot back into a validated dataset model."""
    cases: list[TestCase] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                cases.append(TestCase.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError) as error:
                raise ArtifactError(
                    f"invalid dataset snapshot {path} at line {line_number}: {error}"
                ) from error
    except OSError as error:
        raise ArtifactError(f"could not read dataset snapshot {path}: {error}") from error
    if not cases:
        raise ArtifactError(f"dataset snapshot {path} contains no test cases")
    return DatasetSnapshot(
        path=(source_path or path).resolve(),
        version=version,
        digest=canonical_digest([case.model_dump(mode="json") for case in cases]),
        cases=tuple(cases),
    )


def write_generations(
    path: Path, records: tuple[GenerationRecord, ...] | list[GenerationRecord]
) -> None:
    """Write generation records as JSONL."""
    lines = [
        json.dumps(
            thaw_json(record.model_dump(mode="python")),
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
        for record in records
    ]
    _atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def read_generations(path: Path) -> tuple[GenerationRecord, ...]:
    """Parse generation JSONL back into immutable generation records."""
    records: list[GenerationRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                records.append(GenerationRecord.model_validate_json(line))
            except ValidationError as error:
                raise ArtifactError(
                    f"invalid generation artifact {path} at line {line_number}: {error}"
                ) from error
    except OSError as error:
        raise ArtifactError(f"could not read generation artifact {path}: {error}") from error
    return tuple(records)


def write_evaluations(
    path: Path, records: tuple[EvaluationResult, ...] | list[EvaluationResult]
) -> None:
    """Atomically write immutable evaluation results without overwriting."""
    if path.exists():
        raise ArtifactError(f"evaluation artifact already exists: {path.resolve()}")
    lines = [
        json.dumps(
            thaw_json(record.model_dump(mode="python")),
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
        for record in records
    ]
    _atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))


def read_evaluations(path: Path) -> tuple[EvaluationResult, ...]:
    """Parse evaluation JSONL and re-run strict domain validation."""
    from evalforge.evaluators.base import EvaluationResult

    results: list[EvaluationResult] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                results.append(EvaluationResult.model_validate_json(line))
            except ValidationError as error:
                raise ArtifactError(
                    f"invalid evaluation artifact {path} at line {line_number}: {error}"
                ) from error
    except OSError as error:
        raise ArtifactError(f"could not read evaluation artifact {path}: {error}") from error
    return tuple(results)


def write_experiment_report(path: Path, report: ExperimentReport) -> None:
    """Atomically write the strict report model as JSON without overwriting."""
    _atomic_write_new(
        path,
        json.dumps(
            thaw_json(report.model_dump(mode="python")),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        + "\n",
    )


def read_experiment_report(path: Path) -> ExperimentReport:
    """Read and strictly validate an experiment JSON report."""
    from evalforge.report import ExperimentReport

    try:
        return ExperimentReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ArtifactError(f"invalid experiment report {path}: {error}") from error


def write_markdown_report(path: Path, markdown: str) -> None:
    """Atomically write deterministic Markdown without overwriting."""
    _atomic_write_new(path, markdown)
