"""JSON Lines dataset contracts and loading functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evalforge.config import DatasetReference, LoadedManifest, canonical_digest


class DatasetError(ValueError):
    """Raised when a test-case dataset cannot be loaded or validated."""


class TestCase(BaseModel):
    """One input and expected structured output in an evaluation dataset."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    input: dict[str, Any] = Field(min_length=1)
    expected: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    description: str | None = None


class DatasetSnapshot(BaseModel):
    """A validated, immutable snapshot of all cases for one experiment."""

    model_config = ConfigDict(frozen=True)

    path: Path
    version: str
    digest: str
    cases: tuple[TestCase, ...]


def resolve_dataset_path(manifest: LoadedManifest) -> Path:
    """Resolve a dataset reference relative to its manifest, not the caller CWD."""
    reference: DatasetReference = manifest.config.dataset
    return (manifest.path.parent / Path(reference.path)).resolve()


def load_dataset(manifest: LoadedManifest) -> DatasetSnapshot:
    """Load a JSON Lines dataset with unique, valid test-case identifiers."""
    path = resolve_dataset_path(manifest)
    if not path.is_file():
        raise DatasetError(f"dataset does not exist: {path}")

    cases: list[TestCase] = []
    seen_ids: set[str] = set()

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DatasetError(f"could not read dataset {path}: {error}") from error

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        try:
            raw_case = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(
                f"invalid JSON in {path} at line {line_number}: {error.msg}"
            ) from error

        try:
            case = TestCase.model_validate(raw_case)
        except ValidationError as error:
            raise DatasetError(
                f"invalid test case in {path} at line {line_number}: {error}"
            ) from error

        if case.id in seen_ids:
            raise DatasetError(
                f"duplicate test-case ID {case.id!r} in {path} at line {line_number}"
            )

        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise DatasetError(f"dataset {path} contains no test cases")

    return DatasetSnapshot(
        path=path,
        version=manifest.config.dataset.version,
        digest=canonical_digest([case.model_dump(mode="json") for case in cases]),
        cases=tuple(cases),
    )
