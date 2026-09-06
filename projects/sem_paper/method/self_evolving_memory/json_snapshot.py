from __future__ import annotations

from collections.abc import Mapping
import math

from research_platform.platform.kernel import JsonInput, JsonObject, JsonValue


class FrozenJsonArray(list[JsonValue]):
    """Read-only list-compatible JSON array for strict document schemas."""

    __slots__ = ()

    @staticmethod
    def _blocked(*args, **kwargs):
        del args, kwargs
        raise TypeError("frozen JSON array does not support mutation")

    __setitem__ = _blocked
    __delitem__ = _blocked
    append = _blocked
    clear = _blocked
    extend = _blocked
    insert = _blocked
    pop = _blocked
    remove = _blocked
    reverse = _blocked
    sort = _blocked
    __iadd__ = _blocked
    __imul__ = _blocked

    def __deepcopy__(self, memo):
        copied = [thaw_json(value) for value in self]
        memo[id(self)] = copied
        return copied


class FrozenJsonObject(dict[str, JsonValue]):
    """Read-only dict-compatible JSON object for runtime value contracts."""

    __slots__ = ()

    @staticmethod
    def _blocked(*args, **kwargs):
        del args, kwargs
        raise TypeError("frozen JSON object does not support mutation")

    __setitem__ = _blocked
    __delitem__ = _blocked
    clear = _blocked
    pop = _blocked
    popitem = _blocked
    setdefault = _blocked
    update = _blocked
    __ior__ = _blocked

    def __deepcopy__(self, memo):
        copied = {key: thaw_json(value) for key, value in self.items()}
        memo[id(self)] = copied
        return copied


def freeze_json(value: JsonInput, *, label: str = "SEM JSON value") -> JsonValue:
    """Snapshot a JSON input into recursively immutable, finite values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        rows: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{label} object keys must be strings")
            rows[key] = freeze_json(item, label=f"{label}.{key}")
        return FrozenJsonObject(rows)
    if isinstance(value, list):
        return FrozenJsonArray(
            freeze_json(item, label=f"{label} item") for item in value
        )
    if isinstance(value, tuple):
        return tuple(freeze_json(item, label=f"{label} item") for item in value)
    raise TypeError(f"{label} contains unsupported type {type(value).__name__}")


def freeze_json_mapping(
    value: Mapping[str, JsonInput],
    *,
    label: str = "SEM JSON object",
) -> JsonObject:
    frozen = freeze_json(value, label=label)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{label} must be an object")
    return frozen


def thaw_json(value: JsonValue) -> object:
    """Return detached mutable JSON data for documents and transport."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    return value


def thaw_json_mapping(value: Mapping[str, JsonValue]) -> dict[str, object]:
    thawed = thaw_json(value)
    if not isinstance(thawed, dict):
        raise TypeError("SEM frozen JSON object did not thaw to a dictionary")
    return thawed


__all__ = ["freeze_json", "freeze_json_mapping", "thaw_json", "thaw_json_mapping"]
