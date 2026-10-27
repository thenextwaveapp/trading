"""Parameter sweeps — expand a strategy spec over a cartesian grid.

The registry is the source of truth: an axis names a registry path and a set
of values. Values are validated by running each expanded spec through the
normal parser/capability gates, so a bad value fails that run honestly instead
of being silently dropped. There is no arbitrary combination cap.
"""
import json
from itertools import product

from .params import PARAM_BY_KEY, set_path


class SweepError(ValueError):
    pass


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _dedupe(values):
    out, seen = [], set()
    for value in values:
        key = _canonical(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def prepare_axes(axes) -> list[tuple[str, list]]:
    """Validate axis declarations before any data is loaded."""
    if not isinstance(axes, list) or not axes:
        raise SweepError("add at least one sweep axis")
    prepared, seen = [], set()
    for axis in axes:
        if not isinstance(axis, dict):
            raise SweepError("each axis must be an object with path and values")
        path = axis.get("path")
        if not isinstance(path, str) or not path:
            raise SweepError("each axis needs a parameter path")
        if path in seen:
            raise SweepError(f"duplicate axis: {path}")
        param = PARAM_BY_KEY.get(path)
        if param is None:
            raise SweepError(f"unknown parameter: {path}")
        if not param.sweep:
            raise SweepError(f"{param.label} is not sweepable")
        if not param.backtest:
            raise SweepError(
                f"{param.label} is not supported by the backtest engine")
        values = axis.get("values")
        if not isinstance(values, list) or not values:
            raise SweepError(f"{param.label} needs at least one value")
        prepared.append((path, _dedupe(values)))
        seen.add(path)
    return prepared


def expand_prepared(spec: dict, prepared: list[tuple[str, list]]):
    """Yield (variant_spec, changes) for every combination of prepared axes."""
    for combo in product(*(values for _path, values in prepared)):
        variant = spec
        changes = {}
        for (path, _values), value in zip(prepared, combo):
            variant = set_path(variant, path, value)
            changes[path] = value
        yield variant, changes


def expand_specs(spec: dict, axes):
    """Convenience wrapper used by tests and direct callers."""
    return expand_prepared(spec, prepare_axes(axes))


def _display(value, param=None) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    if (param and param.percent and isinstance(value, (int, float))
            and not isinstance(value, bool)):
        text = f"{value * 100:g}%"
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    else:
        text = str(value)
    return text if len(text) <= 120 else text[:117] + "..."


def label_for(changes: dict) -> str:
    bits = []
    for path, value in changes.items():
        param = PARAM_BY_KEY.get(path)
        bits.append(f"{param.label if param else path}={_display(value, param)}")
    return " · ".join(bits)
