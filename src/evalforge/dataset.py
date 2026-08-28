"""JSON Lines dataset contracts and loading functions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from evalforge.config import DatasetReference, LoadedManifest
from evalforge.json_types import (
    FrozenDict,
    canonical_digest,
    freeze_json,
)


class DatasetError(ValueError):
    """Raised when a test-case dataset cannot be loaded or validated."""


def _reject_json_constants(constant: str) -> None:
    raise ValueError(f"nonstandard JSON constant {constant!r} is not allowed")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r} is not allowed")
        result[key] = value
    return result


class TestCase(BaseModel):
    """One input and expected structured output in an evaluation dataset."""

    __test__ = False

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(min_length=1)
    input: FrozenDict = Field(min_length=1)
    expected: FrozenDict = Field(min_length=1)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    description: str | None = None

    @field_validator("id", mode="after")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id cannot be whitespace-only")
        return value

    @field_validator("input", "expected", mode="before")
    @classmethod
    def freeze_and_validate_mapping(cls, value: Any, info: Any) -> FrozenDict:
        if not isinstance(value, Mapping):
            raise ValueError(f"{info.field_name} must be a mapping")
        frozen = freeze_json(value, path=info.field_name)
        if len(frozen) < 1:
            raise ValueError(f"{info.field_name} must contain at least 1 key")
        return frozen

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("tags must be a sequence of strings")
        seen: set[str] = set()
        cleaned_tags: list[str] = []
        for tag in value:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"tags must be non-empty strings, got {tag!r}")
            if tag in seen:
                raise ValueError(f"duplicate tag {tag!r} in test case")
            seen.add(tag)
            cleaned_tags.append(tag)
        return tuple(cleaned_tags)


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
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise DatasetError(f"could not read dataset {path}: {error}") from error

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        try:
            raw_case = json.loads(
                line,
                parse_constant=_reject_json_constants,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise DatasetError(f"invalid JSON in {path} at line {line_number}: {error}") from error

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
