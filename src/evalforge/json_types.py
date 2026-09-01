"""Canonical JSON-compatible value validation, deep-freezing, and thawing."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from pydantic_core import core_schema


class FrozenDict(Mapping[str, Any]):
    """A read-only mapping that serializes cleanly with Pydantic and JSON."""

    __slots__ = ("_data",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        source = values or {}
        copied: dict[str, Any] = {}
        for key, value in source.items():
            if not isinstance(key, str):
                raise ValueError(f"$ mapping keys must be strings, got {type(key).__name__}")
            copied[key] = value
        object.__setattr__(self, "_data", MappingProxyType(copied))

    @classmethod
    def _from_frozen(cls, values: dict[str, Any]) -> FrozenDict:
        instance = cls.__new__(cls)
        object.__setattr__(instance, "_data", MappingProxyType(values))
        return instance

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._data)!r})"

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object does not support item assignment")

    def __delitem__(self, key: Any) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object does not support item deletion")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def popitem(self) -> Any:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def clear(self) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def setdefault(self, key: Any, default: Any = None) -> Any:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    def __ior__(self, other: Any) -> FrozenDict:
        raise TypeError(f"'{self.__class__.__name__}' object is immutable")

    @classmethod
    def _validate(cls, value: Any) -> FrozenDict:
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(value)
        raise ValueError("value must be a mapping")

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            json_schema_input_schema=core_schema.dict_schema(
                core_schema.str_schema(), core_schema.any_schema()
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                thaw_json,
                return_schema=core_schema.dict_schema(),
            ),
        )


def validate_json_value(value: Any, path: str = "$") -> None:
    """Recursively validate that a value conforms to strict JSON data types with finite numbers."""
    if value is None or isinstance(value, (bool, str, int)):
        if isinstance(value, (datetime.date, datetime.datetime)):
            raise ValueError(f"{path} cannot be a date or datetime object")
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return

    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{path} cannot be bytes")

    if isinstance(value, (datetime.date, datetime.datetime)):
        raise ValueError(f"{path} cannot be a date or datetime object")

    if isinstance(value, set):
        raise ValueError(f"{path} cannot be a set")

    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} mapping keys must be strings, got {type(key).__name__}")
            child_path = f"{path}.{key}" if path != "$" else key
            validate_json_value(item, child_path)
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            validate_json_value(item, f"{path}[{index}]")
        return

    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def freeze_json(value: Any, path: str = "$") -> Any:
    """Recursively validate and convert JSON data into deeply immutable representations."""
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, (datetime.date, datetime.datetime)):
        raise ValueError(f"{path} cannot be a date or datetime object")

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return value

    if isinstance(value, str):
        return value

    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{path} cannot be bytes")

    if isinstance(value, set):
        raise ValueError(f"{path} cannot be a set")

    if isinstance(value, Mapping):
        frozen_items: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} mapping keys must be strings, got {type(key).__name__}")
            child_path = f"{path}.{key}" if path != "$" else key
            frozen_items[key] = freeze_json(item, child_path)
        return FrozenDict._from_frozen(frozen_items)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))

    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def thaw_json(value: Any) -> Any:
    """Recursively convert frozen JSON structures back into standard dicts and lists."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    # Domain models stored as values inside FrozenDicts remain immutable but
    # should still serialize as their JSON-compatible field mappings.
    if hasattr(value, "model_dump"):
        return thaw_json(value.model_dump(mode="python"))

    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]

    return value


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest for JSON-compatible data."""
    thawed = thaw_json(value)
    serialized = json.dumps(
        thawed,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
