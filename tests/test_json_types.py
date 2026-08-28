"""Unit tests for recursive JSON normalization, deep freezing, and canonical digests."""

import datetime

import pytest

from evalforge.json_types import (
    FrozenDict,
    canonical_digest,
    freeze_json,
    thaw_json,
    validate_json_value,
)


def test_frozen_dict_blocks_mutations() -> None:
    frozen = FrozenDict({"a": 1, "b": 2})

    with pytest.raises(TypeError, match="does not support item assignment"):
        frozen["a"] = 10

    with pytest.raises(TypeError, match="does not support item deletion"):
        del frozen["a"]

    with pytest.raises(TypeError, match="is immutable"):
        frozen.pop("a")

    with pytest.raises(TypeError, match="is immutable"):
        frozen.popitem()

    with pytest.raises(TypeError, match="is immutable"):
        frozen.clear()

    with pytest.raises(TypeError, match="is immutable"):
        frozen.update({"a": 3})

    with pytest.raises(TypeError, match="is immutable"):
        frozen.setdefault("c", 4)

    with pytest.raises(TypeError, match="is immutable"):
        frozen |= {"c": 4}

    with pytest.raises(TypeError):
        dict.__setitem__(frozen, "a", 10)

    with pytest.raises(TypeError, match="does not support item assignment"):
        frozen._data["a"] = 10  # type: ignore[index]

    assert frozen == {"a": 1, "b": 2}


def test_freeze_json_nested_structures() -> None:
    raw = {
        "str": "hello",
        "int": 42,
        "float": 3.14,
        "bool": True,
        "none": None,
        "list": [{"nested_key": "val"}, [1, 2]],
        "mapping": {"k": {"inner": [10, 20]}},
    }

    frozen = freeze_json(raw)

    assert isinstance(frozen, FrozenDict)
    assert isinstance(frozen["list"], tuple)
    assert isinstance(frozen["list"][0], FrozenDict)
    assert isinstance(frozen["list"][1], tuple)
    assert isinstance(frozen["mapping"], FrozenDict)
    assert isinstance(frozen["mapping"]["k"], FrozenDict)
    assert isinstance(frozen["mapping"]["k"]["inner"], tuple)

    thawed = thaw_json(frozen)
    assert thawed == raw
    assert isinstance(thawed, dict)
    assert isinstance(thawed["list"], list)
    assert isinstance(thawed["list"][0], dict)


@pytest.mark.parametrize(
    "invalid_val,expected_error",
    [
        (float("nan"), "must be finite"),
        (float("inf"), "must be finite"),
        (float("-inf"), "must be finite"),
        (b"bytes", "cannot be bytes"),
        (datetime.date(2026, 1, 1), "cannot be a date or datetime object"),
        (datetime.datetime(2026, 1, 1, 12, 0, 0), "cannot be a date or datetime object"),
        ({1, 2, 3}, "cannot be a set"),
        ({1: "non-string key"}, "mapping keys must be strings"),
        (object(), "contains unsupported type"),
    ],
)
def test_validate_and_freeze_rejects_invalid_values(
    invalid_val: object, expected_error: str
) -> None:
    with pytest.raises(ValueError, match=expected_error):
        validate_json_value(invalid_val)

    with pytest.raises(ValueError, match=expected_error):
        freeze_json(invalid_val)


def test_canonical_digest_stability() -> None:
    data1 = {"b": [1, 2], "a": {"z": 10, "y": 20}}
    data2 = {"a": {"y": 20, "z": 10}, "b": (1, 2)}

    digest1 = canonical_digest(data1)
    digest2 = canonical_digest(data2)

    assert digest1 == digest2
    assert len(digest1) == 64
