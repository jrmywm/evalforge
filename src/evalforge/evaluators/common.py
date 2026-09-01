"""Shared parsing and comparison helpers for deterministic evaluators."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from evalforge.json_types import thaw_json
from evalforge.models import GenerationRecord

NUMERIC_TOLERANCE = 1e-6
PathTokens = tuple[str, ...]


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonstandard JSON constant {value!r} is not allowed")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r} is not allowed")
        result[key] = value
    return result


def parse_generation_output(generation: GenerationRecord) -> tuple[Any | None, str | None]:
    """Return normalized JSON output, or a user-facing parse failure reason."""
    output = generation.normalized_response
    if output is None:
        output = generation.raw_response
    if output is None:
        return None, "generation did not contain a response"
    output = thaw_json(output)
    if isinstance(output, str):
        try:
            return json.loads(
                output,
                parse_constant=_reject_constant,
                object_pairs_hook=_reject_duplicate_keys,
            ), None
        except (json.JSONDecodeError, ValueError) as error:
            return None, f"output is not valid JSON: {error}"
    return output, None


def json_pointer(path: PathTokens) -> str:
    """Render path tokens as an RFC 6901 JSON Pointer."""
    return (
        ""
        if not path
        else "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in path)
    )


def flatten_expected(value: Any, prefix: PathTokens = ()) -> dict[PathTokens, Any]:
    """Flatten nested expected objects into collision-free token paths."""
    if isinstance(value, Mapping):
        if not value:
            return {prefix: value} if prefix else {}
        flattened: dict[PathTokens, Any] = {}
        for key, child in value.items():
            path = (*prefix, str(key))
            flattened.update(flatten_expected(child, path))
        return flattened
    return {prefix: value}


def flatten_actual(value: Any, prefix: PathTokens = ()) -> set[PathTokens]:
    """Collect leaf paths in actual output for extra-field reporting."""
    if isinstance(value, Mapping):
        if not value:
            return {prefix} if prefix else set()
        paths: set[PathTokens] = set()
        for key, child in value.items():
            path = (*prefix, str(key))
            paths.update(flatten_actual(child, path))
        return paths
    return {prefix}


def get_path(value: Any, path: PathTokens) -> tuple[bool, Any]:
    current = value
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            return False, None
        current = current[component]
    return True, current


def values_equal(expected: Any, actual: Any, tolerance: float = 1e-6) -> bool:
    """Compare JSON values with strict types and a small finite-number tolerance."""
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not (math.isfinite(float(expected)) and math.isfinite(float(actual))):
            return False
        return abs(float(expected) - float(actual)) <= tolerance
    if isinstance(expected, Mapping) or isinstance(actual, Mapping):
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return False
        if set(expected) != set(actual):
            return False
        return all(values_equal(expected[key], actual[key], tolerance) for key in expected)
    if isinstance(expected, (list, tuple)) or isinstance(actual, (list, tuple)):
        if not isinstance(expected, (list, tuple)) or not isinstance(actual, (list, tuple)):
            return False
        return len(expected) == len(actual) and all(
            values_equal(expected_item, actual_item, tolerance)
            for expected_item, actual_item in zip(expected, actual, strict=True)
        )
    if type(expected) is not type(actual):
        return False
    return expected == actual
